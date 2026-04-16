# AUTONOME Agent 系统文档

> **文档版本**: 2.0.0
> **更新日期**: 2026-04-12
> **架构版本**: V2 (Unified Agent)

---

## 目录

1. [V2 统一 Agent 架构](#1-v2-统一-agent-架构)
2. [路由节点详解](#2-路由节点详解)
3. [V2 Schema 定义](#3-v2-schema-定义)
4. [辅助 Agent](#4-辅助-agent)
5. [工具系统](#5-工具系统)
6. [提示词系统](#6-提示词系统)
7. [V1 → V2 迁移](#7-v1--v2-迁移)

---

## 1. V2 统一 Agent 架构

### 1.1 架构概览

V2 采用 **单节点 LangGraph** 架构。`build_unified_agent()` 创建仅含一个 `"unified"` 节点的 StateGraph，由 `unified_agent_node` 内部完成意图分类和分发。

**核心文件**: `autonome-backend/app/agent/unified_executor.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                    V2 统一 Agent 架构                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  用户消息                                                             │
│      │                                                                │
│      ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │              unified_agent_node (单节点)                     │     │
│  │                                                               │     │
│  │  1. router_node_logic() → IntentClassification               │     │
│  │     - 快速路径: casual_chat / UI_ACTION (零 LLM)             │     │
│  │     - LLM 分类: 5 种意图类型                                  │     │
│  │     - 置信度门控: <0.6 降级为 CHAT                            │     │
│  │                                                               │     │
│  │  2. 按 intent_type 分发:                                     │     │
│  │     CHAT           → chat_node()                             │     │
│  │     EXPLICIT_SKILL → skill_execute_node()                   │     │
│  │     VAGUE_ANALYSIS → sandbox_planner_node()                  │     │
│  │                      ↓ (失败回退)                             │     │
│  │                      super_executor_node()                   │     │
│  │     TROUBLESHOOT   → troubleshooting_node()                 │     │
│  │     SYSTEM_ACTION  → param_update_node() /                  │     │
│  │                      system_action_node()                    │     │
│  │     (默认)         → retrieval_node()                        │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  LangGraph: START → "unified" → END                                   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心函数

| 函数 | 描述 | 位置 |
|------|------|------|
| `build_unified_agent(...)` | V2 唯一 Agent 构建器 | `unified_executor.py:265` |
| `unified_agent_node(state)` | 核心分发函数 | `unified_executor.py:162` |
| `super_executor_node(state)` | SuperExecutorV4 包装 | `unified_executor.py:70` |
| `should_use_super_executor(intent)` | 判断是否使用超级执行器 | `unified_executor.py:328` |

### 1.3 构建参数

```python
build_unified_agent(
    api_key: str,           # LLM API Key
    base_url: str,          # LLM API Base URL
    model_name: str,        # 模型名称
    physical_file_info: str, # 项目文件树信息
    user_id: int,           # 用户 ID
    project_id: int,        # 项目 ID
    selected_skill_id: str = None,  # 预选技能 ID
    vision_config: dict = None,     # 视觉模型配置
    task_mode: str = None           # 任务模式
) -> CompiledGraph
```

### 1.4 状态定义

```python
class UnifiedExecutorState(TypedDict):
    messages: list              # 对话消息列表
    intent: str                 # 意图类型
    next: str                   # 下一步路由
    physical_file_info: str     # 文件树信息
    skill_id: str               # 技能 ID
    skill_params: dict          # 技能参数
    project_id: int             # 项目 ID
    user_id: int                # 用户 ID
```

### 1.5 意图类型 (IntentType)

V2 从 7 种精简为 5 种，通过 `sub_intent` 保留合并类型语义：

| 意图类型 | 描述 | 处理节点 | sub_intent |
|----------|------|----------|------------|
| `CHAT` | 闲聊/理论问答 | `chat_node()` | `casual` / `theory` |
| `EXPLICIT_SKILL` | 明确提及技能 | `skill_execute_node()` | - |
| `VAGUE_ANALYSIS` | 模糊分析需求 | `sandbox_planner_node()` → 回退 `super_executor_node()` | `pipeline_build` |
| `TROUBLESHOOT` | 错误诊断 | `troubleshooting_node()` | - |
| `SYSTEM_ACTION` | 系统操作 | `param_update_node()` / `system_action_node()` | `ui_update` |

**合并说明**:
- `PIPELINE_BUILD` → 合并到 `VAGUE_ANALYSIS`（`sub_intent="pipeline_build"`）
- `UI_UPDATE` → 合并到 `SYSTEM_ACTION`（`sub_intent="ui_update"`）

---

## 2. 路由节点详解

**文件路径**: `autonome-backend/app/agent/nodes/`

### 2.1 路由器 (Router)

**文件**: `router.py`

V2 的"快速网关"，使用轻量级 LLM + `with_structured_output(IntentClassification, method="json_mode")`。

**快速路径（零 LLM 成本）**:

| 触发条件 | 路由结果 | 延迟 |
|----------|----------|------|
| 问候/感谢/告别/帮助 | `CHAT` + `casual` | 0ms |
| `[UI_ACTION:REQUEST_SKILL_PARAMS]` | `SYSTEM_ACTION` + `ui_update` | 0ms |
| `[UI_ACTION:EXECUTE_SKILL]` | `EXPLICIT_SKILL` | 0ms |
| 短消息 + 知识关键词 | `CHAT` + `theory` | 0ms |

**置信度门控**: 低于 `AUTONOME_ROUTER_CONFIDENCE_THRESHOLD`（默认 0.6）自动降级为 `CHAT`。

### 2.2 闲聊节点 (Chat)

**文件**: `chat.py`

- `chat_node()`: 同步返回硬编码响应（问候/感谢/告别/帮助）
- `build_chat_agent()`: 异步 LangGraph 变体，支持 LLM 流式理论问答

### 2.3 技能执行节点 (SkillExecute)

**文件**: `skill_execute.py`

流程: 加载技能定义 → 推断参数 → 生成 StrategyCard → 输出 `json_strategy`

### 2.4 沙箱规划器节点 (SandboxPlanner)

**文件**: `sandbox_planner.py`

V2 关键组件：PTY + Claude Code 沙箱规划，集成 MCP 技能搜索。

**特性**:
- 事件回调驱动的 SSE 流式输出
- 最多 2 次静默重试（指数退避）
- 容器暖池集成（`AUTONOME_USE_CONTAINER_POOL=true`）
- 结构化输出提取（`[AUTONOME_RESULT_START]` 标记）
- 回退到 `ResultExtractor` + `json_repair`
- 转换为 `StrategyCard` 兼容格式

**门控**: `AUTONOME_USE_SANDBOX_PLANNER` 环境变量

**执行策略**: VAGUE_ANALYSIS 优先尝试 SandboxPlanner，失败回退 SuperExecutorV4

### 2.5 4 级参数预填节点 (SkillFormBuilder)

**文件**: `skill_form_builder.py`

零 LLM 成本的确定性参数推断：

```
优先级: 显式提及 > 实体提取 > 工作区推断 > 默认值

Level 1: 显式提及 — 用户消息中直接提到的参数值
Level 2: 实体提取 — 从用户消息中提取的实体（文件名、算法名等）
Level 3: 工作区推断 — 从项目文件结构推断
Level 4: 默认值 — SKILL.md 中定义的参数默认值
```

每个参数携带 `{value, source, confidence}` 元数据，供前端可视化标记。

### 2.6 参数自然语言更新节点 (ParamUpdate)

**文件**: `param_update.py`

用户通过自然语言修改策略卡片参数（如"把分辨率改成 0.4"），使用 `with_structured_output(ParamUpdate)` 解析，输出 `json_param_update` 代码块。

### 2.7 技能检索节点 (Retrieval)

**文件**: `retrieval.py`

加载技能目录 → LLM 挑选 top 3 匹配 → 输出 `json_action_menu` 格式

### 2.8 错误诊断节点 (Troubleshooting)

**文件**: `troubleshooting.py`

发送用户消息 + 提取的错误信息到诊断 LLM。

### 2.9 系统操作节点 (SystemAction)

**文件**: `system_action.py`

系统级操作：目录列表、文件查看、临时文件清理等。

### 2.10 蓝图规划节点 (Blueprint)

**文件**: `blueprint.py`

多步 DAG 蓝图规划，输出 `json_blueprint` 格式。

### 2.11 知识技能节点 (Knowledge)

**文件**: `knowledge.py`

知识型 SKILL 处理：引用代码模式，生成代码和 `json_strategy`。

### 2.12 Live Coding 回退节点 (LiveCoding)

**文件**: `live_coding.py`

无技能匹配时的代码生成回退。强制编码标准：argparse、中文注释、错误处理、TASK_OUT_DIR、TSV 输出、发表级图形。支持交互式可视化模式。

---

## 3. V2 Schema 定义

**文件**: `autonome-backend/app/agent/schemas.py`

### 3.1 IntentClassification

```python
class IntentClassification(BaseModel):
    intent: IntentType           # 5 种意图类型
    confidence: float            # 0-1 置信度
    entities: dict[str, Any]     # 提取的实体
    reason: str                  # 分类原因 (max 200 chars)
    chat_subtype: Optional[Literal["casual", "theory"]]  # V2: 闲聊子类型
    sub_intent: Optional[Literal["pipeline_build", "ui_update"]]  # V2: 子意图
```

### 3.2 StrategyCard

```python
class StrategyCard(BaseModel):
    title: str
    description: str
    task_summary: str
    tool_id: str
    parameters: dict[str, Any]
    steps: list[dict[str, Any]]
    estimated_time: Optional[str]
    task_mode: Optional[str]
    visualization_config: Optional[dict]
```

### 3.3 ParamUpdate

```python
class ParamUpdate(BaseModel):
    param_updates: list[dict]  # [{key, value, operation}]
    message: str               # 更新描述
```

### 3.4 BlueprintResult

```python
class BlueprintResult(BaseModel):
    project_goal: str
    is_complex_task: bool
    tasks: list[BlueprintNode]
```

### 3.5 其他 Schema

| Schema | 描述 |
|--------|------|
| `RouteQuery` | 快速路由结果 (casual_chat, bio_analysis, complex_blueprint, skill_execute) |
| `MatchedSkill` | 匹配技能 (skill_id, skill_type, match_score, match_reason) |
| `IntentResult` | 内部意图结果 (casual_chat, knowledge_skill, executable_skill, live_coding) |
| `BlueprintNode` | DAG 任务节点 (task_id, name, tool, depends_on, expected_input/output, instruction) |
| `InteractivePlotConfig` | 交互式图表配置 (plot_type 10种, title, data_source, parameters) |
| `ChatResponse` | 聊天响应 (content, is_streaming) |

---

## 4. 辅助 Agent

### 4.1 超级执行器 V4 (SuperExecutorV4)

**文件**: `autonome-backend/app/agent/super_executor_v4.py`

三阶段执行流程，处理复杂分析任务：

```
START → PHASE_1_EXPLORE → PHASE_2_INSTALL_DEPS → PHASE_3_EXECUTE → END
```

| 阶段 | 状态 | 功能 |
|------|------|------|
| Phase 1 | `phase_1_exploring` | 生成并执行探查代码，获取文件详细结构 |
| Phase 2 | `phase_2_installing` | 解析依赖，使用 conda 安装缺失的包 |
| Phase 3 | `phase_3_executing` | 基于探查结果生成并执行最终脚本 |
| 战报 | `battle_report` | 生成执行结果摘要和分析报告 |

### 4.2 PI Agent (Planning & Intelligence)

**文件**: `autonome-backend/app/agent/pi_agent.py`, `chief_pi_agent.py`

当任务复杂度超过阈值时触发深度规划：
- 分解任务为子任务
- 确定执行依赖关系
- 生成执行蓝图 (BlueprintCard)

### 4.3 技能锻造 Agent (Crafter)

**文件**: `autonome-backend/app/agent/crafter.py`

将非结构化素材逆向提炼为标准技能包。

**锻造四大铁律**:
1. **参数自动化抽取**: 必须使用 argparse (Python) 或 optparse (R)
2. **强制详细注释**: 详尽的中文块级注释和行级注释
3. **强制 TSV 输出**: 表格数据必须输出为 Tab 分割格式
4. **发表级图形**: 300 DPI、PDF 矢量、色盲友好配色

### 4.4 执行计划与编排器

**文件**: `execution_plan.py`, `orchestrator.py`

- `ExecutionPlan`: 步骤列表 + 依赖关系 + 状态管理
- `StepOrchestrator`: 拓扑排序执行、并行无依赖步骤、实时 SSE 推送、智能重试

### 4.5 上下文构建器

**文件**: `autonome-backend/app/agent/context_builder.py`

构建技能目录和上下文信息，供 Agent 提示词使用。

### 4.6 响应解析器

**文件**: `autonome-backend/app/agent/response_parser.py`

解析 LLM 输出，提取代码块、策略卡片、蓝图等结构化内容。

---

## 5. 工具系统

**文件路径**: `autonome-backend/app/agent/tools/`

### 5.1 工具注册表 (ToolRegistry)

**文件**: `registry.py`

单例模式，管理所有注册的工具：

```python
class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None
    def get(self, tool_id: str) -> BaseTool | None
    def list_tools() -> List[BaseTool]
    def get_tools_by_category(category: ToolCategory) -> List[BaseTool]

# 全局辅助函数
get_tool_registry() -> ToolRegistry
get_tool(tool_id: str) -> BaseTool | None
list_all_tools() -> List[BaseTool]
get_tools_for_prompt() -> List[BaseTool]
```

### 5.2 工具基类 (BaseTool)

**文件**: `base.py`

```python
class BaseTool(ABC):
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]

    async def execute(self, params: Dict[str, Any], context: ExecutionContext) -> ToolResult
```

### 5.3 工具类别

| 类别 | 工具 | 功能 |
|------|------|------|
| `CODE_EXECUTION` | `CodeExecutionTool`, `PythonExecutionTool`, `RExecutionTool` | 代码执行 |
| `DATA_PROBE` | `DataProbeTool`, `ScanWorkspaceTool`, `PeekTabularTool`, `InspectH5adTool` | 数据探查 |
| `FILE_OPERATION` | `FileOperationTool` | 文件操作（copy, move, delete, mkdir, list, exists） |

---

## 6. 提示词系统

**文件路径**: `autonome-backend/app/agent/prompts/`

### 6.1 系统提示词

**文件**: `system_prompt.py`

| 函数 | 功能 |
|------|------|
| `SYSTEM_PROMPT` | 核心系统提示词常量 |
| `build_context_prompt()` | 构建上下文提示词（项目信息、文件树等） |
| `build_full_prompt()` | 组装完整提示词（系统 + 上下文 + 用户） |

### 6.2 技能提示词

**文件**: `skill_prompt.py`

| 函数 | 功能 |
|------|------|
| `format_skill_for_prompt()` | 将技能元数据格式化为提示词片段 |
| `build_skill_catalog()` | 构建技能目录提示词 |

---

## 7. V1 → V2 迁移

### 7.1 已删除组件

| V1 组件 | V2 替代 | 说明 |
|---------|---------|------|
| `build_bio_agent()` | `build_unified_agent()` | V1 主 Agent 构建器 |
| `build_bio_agent_v2()` | `build_unified_agent()` | V1 第二版构建器 |
| `build_bio_agent_v2_simple()` | `build_unified_agent()` | V1 简化版构建器 |

### 7.2 意图类型变更

| V1 意图 | V2 状态 | 替代方案 |
|---------|---------|----------|
| `CHAT` | 保留 | `chat_subtype` 区分 casual/theory |
| `EXPLICIT_SKILL` | 保留 | 不变 |
| `VAGUE_ANALYSIS` | 保留 | 新增 SandboxPlanner 门控路径 |
| `TROUBLESHOOT` | 保留 | 不变 |
| `SYSTEM_ACTION` | 保留 | 合并 UI_UPDATE 为 sub_intent |
| `PIPELINE_BUILD` | 合并 | → `VAGUE_ANALYSIS` + `sub_intent="pipeline_build"` |
| `UI_UPDATE` | 合并 | → `SYSTEM_ACTION` + `sub_intent="ui_update"` |

### 7.3 架构变更

| 维度 | V1 | V2 |
|------|----|----|
| 图结构 | 多节点 StateGraph | 单节点 StateGraph |
| 路由 | 条件边 | `unified_agent_node` 内部分发 |
| 状态 | 跨节点状态类型冲突 | 单一 `UnifiedExecutorState` |
| 参数推断 | LLM 推断 | 4 级确定性预填（零 LLM 成本） |
| 模糊分析 | 仅 SuperExecutorV4 | SandboxPlanner → 回退 SuperExecutorV4 |
| 参数修改 | 重新执行 | 自然语言 ParamUpdate |

---

*文档版本: 2.0.0*
*更新日期: 2026-04-12*
*维护者: Autonome Team*
