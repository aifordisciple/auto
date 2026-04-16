# AUTONOME STUDIO 系统架构文档

> **文档版本**: 3.0.0
> **更新日期**: 2026-04-12
> **项目定位**: AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端

---

## 目录

1. [系统概述](#1-系统概述)
2. [后端架构](#2-后端架构)
   - 2.1 [V2 统一 Agent 系统](#21-v2-统一-agent-系统)
   - 2.2 [路由节点详解](#22-路由节点详解)
   - 2.3 [模块化工具系统](#23-模块化工具系统)
   - 2.4 [技能生态系统](#24-技能生态系统)
   - 2.5 [三阶段技能推荐](#25-三阶段技能推荐)
   - 2.6 [系统学习层](#26-系统学习层)
   - 2.7 [Docker 沙箱执行引擎](#27-docker-沙箱执行引擎)
   - 2.8 [基础设施服务](#28-基础设施服务)
   - 2.9 [API 路由层](#29-api-路由层)
   - 2.10 [数据模型层](#210-数据模型层)
3. [前端架构](#3-前端架构)
   - 3.1 [页面与路由](#31-页面与路由)
   - 3.2 [状态管理 (Zustand)](#32-状态管理-zustand)
   - 3.3 [核心组件](#33-核心组件)
   - 3.4 [自定义 Hooks](#34-自定义-hooks)
   - 3.5 [平台适配层 (Adapter)](#35-平台适配层-adapter)
   - 3.6 [共享包 (Packages)](#36-共享包-packages)
   - 3.7 [API 客户端](#37-api-客户端)
4. [数据流与交互](#4-数据流与交互)
5. [部署架构](#5-部署架构)

---

## 1. 系统概述

Autonome Studio 是一个面向生物信息学分析的 AI 原生 IDE，采用 **前后端分离 + Docker 沙箱** 的架构设计：

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Autonome Studio V2 架构图                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────┐     ┌──────────────────┐                      │
│  │   Frontend       │     │   Backend        │                      │
│  │   (Next.js 16)   │────▶│   (FastAPI)     │                      │
│  │   Port: 3001     │     │   Port: 8000    │                      │
│  └──────────────────┘     └────────┬─────────┘                      │
│                                    │                                  │
│                           ┌────────▼─────────┐                       │
│                           │  Unified Agent   │                       │
│                           │  (V2 单节点图)    │                       │
│                           │  - Router 路由    │                       │
│                           │  - 5 意图分发     │                       │
│                           │  - SandboxPlanner│                       │
│                           │  - SuperExec V4  │                       │
│                           └────────┬─────────┘                       │
│                                    │                                  │
│                    ┌───────────────┼───────────────┐                  │
│                    ▼               ▼               ▼                  │
│           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│           │ Docker Sandbox│ │Container Pool│ │  PTY Manager │        │
│           │ (代码执行)    │ │ (暖池管理)   │ │ (Claude Code)│        │
│           └──────────────┘ └──────────────┘ └──────────────┘        │
│                                    │                                  │
│  ┌─────────────────────────────────▼──────────────────────────────┐  │
│  │                    Data Layer                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐    │  │
│  │  │ PostgreSQL  │  │   Redis     │  │   FileSystem        │    │  │
│  │  │ + pgvector  │  │   Cache     │  │   (uploads/)       │    │  │
│  │  │ Port: 5433  │  │   Port: 6379│  │                     │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心设计理念

1. **Agent 不直接执行代码**：Agent 只负责制定计划和输出代码，实际执行由前端拦截策略卡片后交由沙箱运行
2. **SKILL 优先策略**：优先复用已有的标准化技能包，无法匹配时才进入 Live Coding 模式
3. **环境探针先行**：在处理任何数据前，强制调用探针工具了解数据结构，杜绝盲目猜测
4. **三阶段技能推荐**：规则引擎 + 向量检索 + LLM 精排，平衡速度与准确性
5. **系统学习闭环**：从执行反馈中自动提取方法论，持续优化推荐质量
6. **V2 单节点图架构**：统一 Agent 使用单节点 LangGraph，内部分发到专业节点，避免跨节点状态冲突
7. **4 级参数预填**：零 LLM 成本的确定性参数推断策略，提升技能执行效率
8. **容器暖池**：预热 Docker 容器消除 3-5s 启动延迟，提高代码执行响应速度

---

## 2. 后端架构

后端采用 FastAPI + LangGraph 构建，核心模块包括：

### 2.1 V2 统一 Agent 系统

#### 2.1.1 V2 架构总览

V2 采用 **单节点 LangGraph** 架构，`build_unified_agent()` 创建仅含一个 `"unified"` 节点的 StateGraph，由 `unified_agent_node` 内部完成意图分类和分发。相比 V1 多节点图，避免了跨节点状态类型冲突。

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
│  │     ┌────────────────┬──────────────────────────────────┐     │     │
│  │     │ CHAT           │ chat_node()                      │     │     │
│  │     │ EXPLICIT_SKILL │ skill_execute_node()             │     │     │
│  │     │ VAGUE_ANALYSIS │ sandbox_planner_node() → 回退    │     │     │
│  │     │                │ super_executor_node()            │     │     │
│  │     │ TROUBLESHOOT   │ troubleshooting_node()           │     │     │
│  │     │ SYSTEM_ACTION  │ param_update_node() /            │     │     │
│  │     │                │ system_action_node()             │     │     │
│  │     │ (默认)         │ retrieval_node()                 │     │     │
│  │     └────────────────┴──────────────────────────────────┘     │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

**文件路径**: `autonome-backend/app/agent/unified_executor.py`

**核心函数**:

| 函数 | 描述 |
|------|------|
| `build_unified_agent(...)` | V2 唯一 Agent 构建器，创建单节点 LangGraph |
| `unified_agent_node(state)` | 核心分发函数，路由到专业节点 |
| `super_executor_node(state)` | 包装 SuperExecutorV4，处理 VAGUE_ANALYSIS |

**`build_unified_agent` 参数**:

```python
def build_unified_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    physical_file_info: str,
    user_id: int,
    project_id: int,
    selected_skill_id: str = None,
    vision_config: dict = None,
    task_mode: str = None
) -> CompiledGraph
```

#### 2.1.2 V2 意图类型 (IntentType)

V2 从 7 种意图精简为 5 种，通过 `sub_intent` 保留合并类型的语义：

| 意图类型 | 描述 | 处理节点 | sub_intent |
|----------|------|----------|------------|
| `CHAT` | 闲聊/理论问答 | `chat_node()` | `casual` / `theory` |
| `EXPLICIT_SKILL` | 明确提及技能 | `skill_execute_node()` | - |
| `VAGUE_ANALYSIS` | 模糊分析需求 | `sandbox_planner_node()` → 回退 `super_executor_node()` | `pipeline_build` |
| `TROUBLESHOOT` | 错误诊断 | `troubleshooting_node()` | - |
| `SYSTEM_ACTION` | 系统操作 | `param_update_node()` / `system_action_node()` | `ui_update` |

**合并说明**:
- `PIPELINE_BUILD` 合并到 `VAGUE_ANALYSIS`（`sub_intent="pipeline_build"`）
- `UI_UPDATE` 合并到 `SYSTEM_ACTION`（`sub_intent="ui_update"`）

#### 2.1.3 路由器 (Router Node)

**文件路径**: `autonome-backend/app/agent/nodes/router.py`

路由器是 V2 的"快速网关"，使用轻量级 LLM + `with_structured_output(IntentClassification, method="json_mode")` 进行意图分类。

**快速路径（零 LLM 成本）**:

| 触发条件 | 路由结果 | 延迟 |
|----------|----------|------|
| 问候/感谢/告别/帮助 | `CHAT` + `casual` | 0ms |
| `[UI_ACTION:REQUEST_SKILL_PARAMS]` 前缀 | `SYSTEM_ACTION` + `ui_update` | 0ms |
| `[UI_ACTION:EXECUTE_SKILL]` 前缀 | `EXPLICIT_SKILL` | 0ms |
| 短消息 + 知识关键词 | `CHAT` + `theory` | 0ms |

**置信度门控**: 低于 `AUTONOME_ROUTER_CONFIDENCE_THRESHOLD`（默认 0.6）的意图自动降级为 `CHAT`，防止误路由。

#### 2.1.4 V2 Schema 定义

**文件路径**: `autonome-backend/app/agent/schemas.py`

| Schema | 描述 | 关键字段 |
|--------|------|----------|
| `IntentClassification` | 意图分类结果 | intent, confidence, entities, reason, chat_subtype, sub_intent |
| `StrategyCard` | 单步任务/策略卡片 | title, description, task_summary, tool_id, parameters, steps |
| `BlueprintResult` | 复杂任务蓝图 | project_goal, is_complex_task, tasks: list[BlueprintNode] |
| `ParamUpdate` | V2 参数自然语言更新 | param_updates: list[{key, value, operation}], message |
| `InteractivePlotConfig` | 交互式图表配置 | plot_type (10种), title, data_source, parameters |
| `MatchedSkill` | 匹配技能 | skill_id, skill_type, match_score, match_reason |

#### 2.1.5 V1 → V2 迁移说明

| V1 组件 | V2 状态 | 替代方案 |
|---------|---------|----------|
| `build_bio_agent` / `build_bio_agent_v2` | 已删除 | `build_unified_agent()` |
| `build_bio_agent_v2_simple` | 已删除 | `build_unified_agent()` |
| 7 意图类型 | 精简为 5 | `PIPELINE_BUILD` → `VAGUE_ANALYSIS`, `UI_UPDATE` → `SYSTEM_ACTION` |
| 多节点 StateGraph | 单节点图 | `unified_agent_node` 内部分发 |

---

### 2.2 路由节点详解

**文件路径**: `autonome-backend/app/agent/nodes/`

| 节点文件 | 函数 | 意图 | 描述 |
|----------|------|------|------|
| `router.py` | `router_node_logic()` | - | 意图分类网关，快速路径 + LLM 分类 |
| `chat.py` | `chat_node()` | CHAT | 闲聊响应（硬编码快速响应 + LLM 理论问答） |
| `skill_execute.py` | `skill_execute_node()` | EXPLICIT_SKILL | 加载技能定义，推断参数，生成 StrategyCard |
| `sandbox_planner.py` | `sandbox_planner_node()` | VAGUE_ANALYSIS | PTY + Claude Code 沙箱规划器（门控） |
| `live_coding.py` | `live_coding_node()` | 回退 | 无技能匹配时的代码生成回退 |
| `retrieval.py` | `retrieval_node()` | 默认 | 技能检索匹配，输出 `json_action_menu` |
| `troubleshooting.py` | `troubleshooting_node()` | TROUBLESHOOT | 错误诊断和修复建议 |
| `system_action.py` | `system_action_node()` | SYSTEM_ACTION | 系统级操作（目录列表、文件查看等） |
| `param_update.py` | `param_update_node()` | SYSTEM_ACTION+ui_update | 自然语言参数修改，输出 `json_param_update` |
| `blueprint.py` | `blueprint_node()` | - | 多步 DAG 蓝图规划 |
| `knowledge.py` | `knowledge_node()` | - | 知识型 SKILL 处理（代码模式参考） |
| `skill_form_builder.py` | `skill_form_builder_node()` | - | 4 级参数预填，零 LLM 成本 |

#### 2.2.1 沙箱规划器 (SandboxPlanner)

**文件路径**: `autonome-backend/app/agent/nodes/sandbox_planner.py`

V2 关键组件：通过 PTY 启动 Claude Code 进行沙箱规划，集成 MCP 技能搜索。

**特性**:
- 事件回调驱动的 SSE 流式输出
- 最多 2 次静默重试（指数退避）
- 容器暖池集成（`AUTONOME_USE_CONTAINER_POOL=true`）
- 结构化输出提取（`[AUTONOME_RESULT_START]` 标记）
- 回退到 `ResultExtractor` + `json_repair`
- 转换为 `StrategyCard` 兼容格式

**门控**: `AUTONOME_USE_SANDBOX_PLANNER` 环境变量控制启用

**执行策略**: VAGUE_ANALYSIS 意图优先尝试 SandboxPlanner，失败回退到 SuperExecutorV4

#### 2.2.2 4 级参数预填 (SkillFormBuilder)

**文件路径**: `autonome-backend/app/agent/nodes/skill_form_builder.py`

零 LLM 成本的确定性参数推断策略：

```
优先级: 显式提及 > 实体提取 > 工作区推断 > 默认值

Level 1: 显式提及 — 用户消息中直接提到的参数值
Level 2: 实体提取 — 从用户消息中提取的实体（文件名、算法名等）
Level 3: 工作区推断 — 从项目文件结构推断（如检测到 .h5ad 文件推断输入路径）
Level 4: 默认值 — SKILL.md 中定义的参数默认值
```

每个参数携带 `{value, source, confidence}` 元数据，供前端可视化标记参数来源。

#### 2.2.3 参数自然语言更新 (ParamUpdate)

**文件路径**: `autonome-backend/app/agent/nodes/param_update.py`

用户可通过自然语言修改策略卡片参数（如"把分辨率改成 0.4"），使用 `with_structured_output(ParamUpdate)` 解析为结构化更新，输出 `json_param_update` 代码块供前端解析。

---

### 2.3 模块化工具系统

**文件路径**: `autonome-backend/app/agent/tools/`

#### 2.3.1 工具注册表 (ToolRegistry)

**文件路径**: `autonome-backend/app/agent/tools/registry.py`

单例模式，管理所有注册的工具：

```python
class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None
    def get(self, tool_id: str) -> BaseTool | None
    def list_tools() -> List[BaseTool]
    def get_tools_by_category(category: ToolCategory) -> List[BaseTool]
```

#### 2.3.2 工具基类 (BaseTool)

**文件路径**: `autonome-backend/app/agent/tools/base.py`

```python
class BaseTool:
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]

    async def execute(self, params: Dict[str, Any], context: ExecutionContext) -> ToolResult
```

#### 2.3.3 工具类别

| 类别 | 工具 | 功能 |
|------|------|------|
| `CODE_EXECUTION` | `CodeExecutionTool`, `PythonExecutionTool`, `RExecutionTool` | 代码执行 |
| `DATA_PROBE` | `DataProbeTool`, `ScanWorkspaceTool`, `PeekTabularTool`, `InspectH5adTool` | 数据探查 |
| `FILE_OPERATION` | `FileOperationTool` | 文件操作（copy, move, delete, mkdir, list, exists） |

#### 2.3.4 探针工具列表

| 工具名 | 功能 | 使用场景 |
|--------|------|----------|
| `peek_tabular_data` | 预览表格文件（CSV/TSV） | 处理表格数据前，了解表头和维度 |
| `scan_workspace` | 扫描目录结构 | 需要找文件但不确定位置 |
| `inspect_h5ad` | 解析 .h5ad 单细胞数据 | 处理单细胞 AnnData 数据前 |
| `inspect_fastq` | 预览 FASTQ 测序文件 | RNA-Seq、单细胞等测序数据预览 |
| `inspect_bam` | 预览 BAM 比对文件 | 比对结果快速预览 |

---

### 2.4 技能生态系统

#### 2.4.1 技能解析器

**文件路径**: `autonome-backend/app/core/skill_parser.py`

**功能描述**: 解析 SKILL.md 文件，提取元数据、参数 Schema 和专家知识库。

**关键类**:

| 类名 | 描述 | 使用场景 |
|------|------|----------|
| `SkillBundleParser` | 文件系统解析器 | 加载官方预置技能 |
| `DBSkillParser` | 数据库解析器 | 加载用户自定义技能（带权限过滤） |
| `get_combined_skills()` | 统一获取方法 | 返回用户可见的所有技能 |

---

#### 2.4.2 技能执行器

**文件路径**: `autonome-backend/app/services/skill_executor.py`

**功能描述**: 整合样本表预处理和并行执行，支持多种执行器类型。

**执行器类型映射**:

| 执行器类型 | 描述 | 执行方式 |
|------------|------|----------|
| `Python_env` | 单 Python 脚本 | Docker 沙箱 + Python 解释器 |
| `R_env` | 单 R 脚本 | Docker 沙箱 + Rscript |
| `Logical_Blueprint` | Nextflow 工作流 | Nextflow DSL2 编译执行 |
| `Bash_env` | Bash 脚本 | Docker 沙箱 + Shell |

**执行流程**:

```
SkillExecutor(skill_id, params, project_id)
    │
    ├── 1. preprocess()
    │   ├── 处理样本表参数
    │   ├── 注入系统变量 (PROJECT_ID, TASK_OUT_DIR)
    │   └── 验证参数完整性
    │
    ├── 2. 根据执行器类型分发
    │   ├── Logical_Blueprint → _execute_nextflow()
    │   ├── Python_env → _execute_python()
    │   ├── R_env → _execute_r()
    │   └── Bash_env → _execute_bash()
    │
    └── 3. 返回执行结果
```

---

### 2.5 三阶段技能推荐

**文件路径**: `autonome-backend/app/services/skill_matcher.py`

#### 2.5.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     技能推荐系统架构 (混合模式)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  用户查询 ──→ 规则引擎(快速筛选) ──→ 向量检索(语义匹配) ──→ LLM精排     │
│     │              (<50ms)           (~100ms)          (~1-2s)          │
│     │                │                    │                │            │
│     │                ▼                    ▼                ▼            │
│     │           候选技能集 ← ← ← ← ← ← ← ←┘                │            │
│     │                │                                      │            │
│     └───────────────→│← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘            │
│                      ▼                                                   │
│              推荐结果 + 参数建议                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.5.2 匹配模式

| 模式 | 描述 | 响应时间 |
|------|------|----------|
| `FAST` | 仅规则+向量匹配 | <200ms |
| `PRECISE` | 完整三阶段匹配（含LLM精排） | ~1-2s |
| `AUTO` | 系统根据置信度自动决定 | 自适应 |

#### 2.5.3 流程决策逻辑

| 场景 | 规则置信度 | 向量相似度 | 是否触发LLM |
|---------------|-----------|-----------|------------|
| 高置信度 | ≥ 0.85 | - | 否 |
| 中置信度 | 0.5-0.85 | ≥ 0.75 | 否 |
| 低置信度 | < 0.5 | < 0.6 | 是 |
| 候选接近 | - | 多个差距<0.1 | 是 |

#### 2.5.4 核心组件

| 组件 | 文件路径 | 功能 |
|------|----------|------|
| `SkillMatcher` | `skill_matcher.py` | 统一匹配器，整合三阶段 |
| `SkillKeywordsIndexer` | `skill_keywords_indexer.py` | 从 SKILL.md 提取关键词 |
| `SkillEmbeddingService` | `skill_embedding_service.py` | 技能语义向量计算 |
| `SkillVectorSearch` | `skill_vector_search.py` | pgvector 向量检索 |
| `LLMSkillMatcher` | `llm_skill_matcher.py` | LLM 精排、参数推断 |
| `SkillMatcherConfig` | `skill_matcher_config.py` | 同义词映射、关键词权重 |

#### 2.5.5 意图类型

| 类型 | 描述 | 置信度 | 处理方式 |
|------|------|--------|----------|
| `explicit_skill` | 明确提及技能名称 | > 0.9 | 直接调用对应 SKILL |
| `implicit_skill` | 隐式技能需求 | 0.5-0.9 | 推荐并询问确认 |
| `live_coding` | 需要自定义代码 | < 0.5 | 回退到 Live Coding |
| `general_question` | 一般问题 | - | 知识问答 |

---

### 2.6 系统学习层

**文件路径**: `autonome-backend/app/services/system_learning/`

#### 2.6.1 系统学习架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    系统学习层架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐                                                │
│  │ 执行反馈    │ ←── 用户确认执行、结果评价                      │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                 Success Evaluator                           │  │
│  │  - 评估执行结果质量                                        │  │
│  │  - 检测失败模式和成功模式                                  │  │
│  └──────────────────────────┬──────────────────────────────────┘  │
│                             │                                     │
│         ┌───────────────────┼───────────────────┐                │
│         ▼                   ▼                   ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ 方法提取器  │    │ 技能注入器  │    │ 权重优化器  │          │
│  │MethodExtractor│  │SkillInjector│    │WeightOptimizer│          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│         │                   │                   │                 │
│         └───────────────────┴───────────────────┘                │
│                             │                                     │
│                             ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              反馈到 Agent 上下文                            │  │
│  │  - 注入相关系统技能                                         │  │
│  │  - 调整推荐权重                                             │  │
│  │  - 优化执行策略                                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.6.2 核心组件

| 组件 | 文件路径 | 功能 |
|------|----------|------|
| `SuccessEvaluator` | `success_evaluator.py` | 评估执行结果质量 |
| `SkillInjector` | `skill_injector.py` | 隐身注入系统技能到 Agent 上下文（混合检索: pgvector 70% + 关键词 Jaccard 30%） |
| `MethodExtractor` | `method_extractor.py` | 从执行历史中提取方法论（LLM + 脱敏） |
| `PrivacyValidator` | `privacy_validator.py` | 隐私验证（12 条正则规则 + 禁止关键词列表） |
| `SessionPool` | `session_pool.py` | 会话池管理（JSON 文件存储，置信度≥0.8，≥3 轮消息，7 天过期，最大 10K 条） |
| `BatchScheduler` | `batch_scheduler.py` | 批处理调度（Celery Beat: 每小时学习周期，每日向量索引重建，每日过期清理） |

#### 2.6.3 技能注入器 (SkillInjector)

**文件路径**: `autonome-backend/app/services/system_learning/skill_injector.py`

**功能**: 在 Agent 处理用户请求时，自动检索并注入相关的系统级技能。

**配置参数**:
- `TOP_K`: 最多注入技能数量 (默认 3)
- `SIMILARITY_THRESHOLD`: 向量相似度阈值 (默认 0.7)
- `VECTOR_WEIGHT`: 向量检索权重 (默认 0.7)
- `KEYWORD_WEIGHT`: 关键词检索权重 (默认 0.3)

---

### 2.7 Docker 沙箱执行引擎

**文件路径**: `autonome-backend/app/tools/bio_tools.py`

**功能描述**: 通过 Docker API 在隔离容器中执行用户代码，提供安全的代码运行环境。

**核心架构**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Sandbox 架构                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐      Unix Socket      ┌──────────────┐ │
│  │   FastAPI       │ ──────────────────▶   │ Docker Daemon│ │
│  │   Backend       │   /var/run/docker.sock│              │ │
│  └─────────────────┘                        └──────┬───────┘ │
│                                                     │         │
│                                          ┌─────────▼────────┐│
│                                          │  Container       ││
│                                          │  ┌────────────┐  ││
│                                          │  │ Script.py  │  ││
│                                          │  │ or Script.R│  ││
│                                          │  └────────────┘  ││
│                                          │                   ││
│  Mount Points:                           │  Resources:       ││
│  /workspace ←→ uploads/                │  - 4GB Memory    ││
│  /opt/conda ←→ autonome_conda/           │  - Network: none ││
│                                          │  - CapDrop: ALL  ││
│                                          └───────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**关键函数**:

```python
def run_container(
    image: str,
    command: str | list,
    language: str = "python",
    environment: dict = None,
    timeout: int = 3600,
    cli_mode: bool = False
) -> tuple[str, int]:
    """
    执行流程：
    1. 准备环境变量和挂载目录
    2. 支持 cli_mode
    3. 创建容器（无网络、资源限制）
    4. 启动并等待执行完成
    5. 提取日志并清理容器
    """
```

---

### 2.8 基础设施服务

#### 2.8.1 容器暖池 (ContainerPoolService)

**文件路径**: `autonome-backend/app/services/container_pool_service.py`

**功能**: 预热 Docker 容器消除 3-5s 启动延迟。

**池类型**:

| 池类型 | 最小容器数 | 最大容器数 | 空闲超时 |
|--------|-----------|-----------|----------|
| PYTHON | 2 | 5 | 300s |
| R | 1 | 3 | 400s |
| GENERAL | 1 | 3 | 600s |

**特性**:
- `sleep infinity` 保持容器存活，`docker exec` 执行任务
- 线程安全（per-type 锁 + 空闲队列）
- 后台清理线程（60s 间隔）
- 容器释放时健康检查
- 统计指标：创建数、复用数、错误数、等待时间、复用率
- 全局单例: `get_container_pool()` / `init_container_pool()`

**门控**: `AUTONOME_USE_CONTAINER_POOL` 环境变量

#### 2.8.2 PTY 管理器 (PtyManager)

**文件路径**: `autonome-backend/app/services/pty_manager.py`

**功能**: Claude Code PTY 会话管理，支持本地 PTY 和 Docker 容器两种模式。

**特性**:
- OS 级 `pty.openpty()` + `os.fork()` 原生 PTY 管理
- ANSI 输出清洗（`ANSICleaner`）
- 结构化输出提取（`[AUTONOME_RESULT_START]` / `[AUTONOME_RESULT_END]` 标记）
- 细粒度提取错误: `MARKER_NOT_FOUND`, `JSON_INVALID`, `JSON_TRUNCATED`, `EMPTY_OUTPUT`
- 回退到 `json_repair` 修复畸形 JSON

#### 2.8.3 Web 终端管理器 (TerminalManager)

**文件路径**: `autonome-backend/app/services/terminal_manager.py`

**功能**: Web 终端 Docker PTY 管理。

**特性**:
- 创建 PTY 启用的 Docker 容器（Tty=True, OpenStdin=True）
- WebSocket ↔ Docker attach socket 双向数据泵
- 安全: NetworkMode=none, CapDrop=ALL, no-new-privileges, 4GB/2CPU/256PID 限制
- 挂载: 项目目录(rw), conda(ro), skills(ro), biosource(ro), 用户包(rw)
- 会话生命周期: create, attach, resize, destroy
- 全局单例: `terminal_manager`

#### 2.8.4 三级缓存服务 (CacheService)

**文件路径**: `autonome-backend/app/services/cache_service.py`

**功能**: L1 内存 + L2 Redis + L3 数据库三级缓存。

#### 2.8.5 Agent 缓存 (AgentCache)

**文件路径**: `autonome-backend/app/services/agent_cache.py`

**功能**: 编译后 LangGraph Agent 实例的 LRU 缓存（容量=50, TTL=1h），避免每次请求重建。

#### 2.8.6 数据探针服务 (DataProbeService)

**文件路径**: `autonome-backend/app/services/data_probe_service.py`

**功能**: 规划前数据探测，防止 AI 盲猜列名和文件路径。

#### 2.8.7 沙箱重试处理器 (SandboxRetryHandler)

**文件路径**: `autonome-backend/app/services/sandbox_retry_handler.py`

**功能**: 执行失败自动重试（最多 2 次），带错误标记检测。

#### 2.8.8 意图分类器 (IntentClassifier)

**文件路径**: `autonome-backend/app/services/intent_classifier.py`

**功能**: 轻量级规则分类（casual/theory/analytical），<5ms 延迟。

---

### 2.9 API 路由层

**文件路径**: `autonome-backend/app/api/routes/`

| 路由文件 | 端点前缀 | 功能描述 |
|----------|----------|----------|
| `auth.py` | `/api/auth` | 用户认证、登录、注册、Token 刷新 |
| `chat.py` | `/api/chat` | 聊天会话管理、流式对话、消息历史 |
| `chat_session.py` | `/api/chat/sessions` | 会话 CRUD、重命名、自动命名、删除 |
| `chat_bookmark.py` | `/api/chat/bookmarks` | 消息书签 CRUD（含笔记） |
| `chat_experience.py` | `/api/chat/experiences` | 经验资产关联 |
| `chat_search.py` | `/api/chat/search` | PostgreSQL 全文搜索 |
| `chat_summary.py` | `/api/chat/summary` | AI 生成会话摘要（含缓存） |
| `chat_tags.py` | `/api/chat/tags` | 会话标签 CRUD 和标签过滤 |
| `chat_interpret.py` | `/api/chat/interpret` | 分析结果深度解读 |
| `tasks.py` | `/api/tasks` | 异步任务管理 |
| `skills/` | `/api/skills` | 技能模块化路由 |
| `skills_forge.py` | `/api/skills/forge` | 技能锻造 |
| `skill_recommend.py` | `/api/skills/recommend` | 技能推荐 |
| `skill_market.py` | `/api/skills/market` | 技能市场 |
| `skill_share.py` | `/api/skills/share` | 技能分享（含权限管理） |
| `skill_version.py` | `/api/skills/versions` | 技能版本管理和回滚 |
| `skill_monitor.py` | `/api/skills/monitor` | 技能监控指标和告警 |
| `super_executor.py` | `/api/super-executor` | 超级执行器 |
| `projects.py` | `/api/projects` | 项目管理 |
| `admin.py` | `/api/admin` | 管理员功能 |
| `billing.py` | `/api/billing` | 计费系统 |
| `packages.py` | `/api/packages` | 包管理 |
| `genomes.py` | `/api/genomes` | 参考基因组 |
| `databases.py` | `/api/databases` | 分析数据库 |
| `terminal.py` | `/api/terminal` | Web Terminal |
| `claude_executor.py` | `/api/claude` | Claude 执行器 |
| `blueprint.py` | `/api/blueprint` | 蓝图管理 |
| `system.py` | `/api/system` | 系统配置 |
| `system_learning.py` | `/api/system/learning` | 系统学习管理（统计、触发、技能 CRUD） |
| `analytics.py` | `/api/analytics` | 分析数据 |
| `preferences.py` | `/api/preferences` | 用户偏好 |
| `knowledge.py` | `/api/knowledge` | 知识库 |
| `weights.py` | `/api/weights` | 权重配置 |
| `learning.py` | `/api/learning` | 学习配置 |
| `sample_sheets.py` | `/api/sample-sheets` | 样本表管理 |
| `plot.py` | `/api/plot` | 绘图服务 |
| `error_diagnostic.py` | `/api/error-diagnostic` | 错误诊断和一键修复 |
| `dashboard.py` | `/api/dashboard` | 研究仪表板（计费分析、活跃工作流、待办事项） |
| `experiences.py` | `/api/experiences` | 经验资产 |
| `templates.py` | `/api/templates` | 模板管理 |
| `ai_assistant.py` | `/api/ai-assistant` | AI 助手 |
| `ai_interpret.py` | `/api/ai-interpret` | AI 解读 |
| `public.py` | `/api/public` | 公开端点 |
| `users.py` | `/api/users` | 用户管理 |

**技能模块化路由** (`skills/` 目录):

| 文件 | 功能 |
|------|------|
| `admin.py` | 技能审核管理 |
| `catalog.py` | 技能目录 |
| `favorites.py` | 技能收藏 |
| `forge.py` | 技能锻造 |
| `my.py` | 我的技能 |
| `reviews.py` | 技能评价 |
| `stats.py` | 技能统计 |
| `testing.py` | 技能测试 |
| `transform.py` | 技能转换 |
| `versions.py` | 版本管理 |
| `draft.py` | 草稿管理 |
| `crud.py` | 基础 CRUD |

**认证机制**:
- JWT Token (HS256)
- 7 天有效期
- 自动刷新机制

---

### 2.10 数据模型层

**文件路径**: `autonome-backend/app/models/`

#### 2.10.1 模块化结构

```
models/
├── __init__.py      # 统一入口，向后兼容
├── domain.py        # 向后兼容入口
├── enums.py         # 所有枚举定义
├── uuid.py          # UUID 生成函数
├── user.py          # 用户和计费账户模型
├── project.py       # 项目、数据文件模型
├── chat.py          # 会话、消息、书签、标签模型
├── task.py          # 任务记录模型
├── config.py        # 系统配置模型
├── skill/           # 技能相关模型目录
│   ├── __init__.py
│   ├── asset.py     # SkillAsset 模型（含 pgvector embedding）
│   ├── version.py   # 版本模型
│   ├── review.py    # 评价模型
│   ├── favorite.py  # 收藏模型
│   ├── history.py   # 执行历史
│   ├── recommendation.py  # 推荐日志
│   ├── share.py     # 分享模型（含权限）
│   └── draft.py     # 草稿模型
├── experience.py    # 经验资产模型
├── sharing.py       # 用户组和分享模型
├── package.py       # 用户包管理模型
├── genome.py        # 参考基因组模型
├── database.py      # 分析数据库模型
├── billing.py       # 计费模型
├── claude_executor.py  # Claude 执行器模型
├── system_skill.py  # 系统技能模型（含 pgvector、方法类型、注入追踪）
├── skill_template.py # 技能模板模型
├── skill_bundle.py  # 技能包模型
├── forge_session.py # 锻造会话模型
├── feedback_weight.py  # 反馈权重模型
├── learning_metrics.py # 学习指标模型
├── user_preference.py  # 用户偏好模型
└── domain_knowledge.py # 领域知识模型
```

#### 2.10.2 核心数据模型

| 模型 | 描述 | 关键字段 |
|------|------|----------|
| `User` | 用户 | id, username, email, role |
| `BillingAccount` | 计费账户 | user_id, balance, tier |
| `Project` | 项目 | id, name, description, owner_id |
| `DataFile` | 数据文件 | project_id, path, type, size |
| `ChatSession` | 聊天会话 | id, title, project_id, user_id |
| `ChatMessage` | 聊天消息 | id, session_id, role, content |
| `SkillAsset` | 技能资产 | skill_id, name, executor_type, status, embedding |
| `SkillVersion` | 技能版本 | skill_id, version, change_log |
| `SkillReview` | 技能审核 | skill_id, reviewer_id, rating |
| `TaskRecord` | 异步任务 | id, task_type, status, result |
| `SystemSkill` | 系统技能 | skill_id, method_type, embedding, injection_count, success_rate |
| `ExperienceAsset` | 经验资产 | id, user_id, content, type |

#### 2.10.3 技能状态流转

```
DRAFT → PENDING_REVIEW → PUBLISHED
         ↓
       REJECTED → (修改后) → PENDING_REVIEW
```

---

## 3. 前端架构

前端采用 Next.js 16 (App Router) + TypeScript + Zustand 构建。

### 3.1 页面与路由

**文件路径**: `autonome-studio/src/app/`

| 页面路径 | 文件 | 功能描述 |
|----------|------|----------|
| `/` | `page.tsx` | 主 IDE 页面（懒加载 ChatStage，骨架屏回退） |
| `/login` | `login/page.tsx` | 登录/注册页面 |
| `/admin` | `admin/page.tsx` | 管理员面板（统计、用户、集群、技能、嵌入标签） |
| `/admin/skills` | `admin/skills/page.tsx` | 技能审核管理 |
| `/skill-forge` | `skill-forge/page.tsx` | 重定向到 `/?open=skill-center&tab=forge` |
| `/skill-market` | `skill-market/page.tsx` | 独立技能市场页 |
| `/dashboard` | `dashboard/page.tsx` | 研究仪表板 |
| `/share/[token]` | `share/[token]/page.tsx` | 分享页面 |

**页面本地组件**:

| 页面 | 组件目录 | 关键组件 |
|------|----------|----------|
| `/dashboard` | `dashboard/components/` | BillingAnalyticsPanel, ActiveWorkflowsPanel, ActionItemsPanel, RecentAssetsPanel, MiniDAGView, ETABadge |
| `/skill-forge` | `skill-forge/components/` | SkillDraftEditor, ForgeChatStage, ForgeToolbar, ParameterSchemaEditor/, TestPanel/ |
| `/skill-market` | `skill-market/components/` | SkillCard, SkillDetailDrawer, CategoryNav |

### 3.2 状态管理 (Zustand)

**文件路径**: `autonome-studio/src/store/`

| Store 文件 | 功能 | 关键状态 |
|------------|------|----------|
| `useAuthStore.ts` | 认证状态 | user, token, credits_balance, persist 中间件 |
| `useChatStore.ts` | 聊天状态 | messages, streamingContent, bookmarks, inlineAction (4 阶段工作流) |
| `useWorkspaceStore.ts` | 工作区状态 | currentProject, files, selectedFiles, ToolParameter/ToolSchema 类型 |
| `useTaskStore.ts` | 任务状态 | tasks, activeTask, logs, retry 支持 (progress_status, attempt, max_retries) |
| `useUIStore.ts` | UI 状态 | activeOverlay (单一状态), Immer 集成, OverlayType 联合类型 |
| `useForgeStore.ts` | 技能锻造状态 | draft, session, ExecutorType, ToolMode (chat/code_import/skill_import) |
| `useShortcutStore.ts` | 快捷键状态 | shortcuts, commandPaletteOpen, persist 中间件 |

**useUIStore OverlayType 联合类型**:

```typescript
type OverlayType = 'taskCenter' | 'settings' | 'projectCenter' | 'controlPanel'
  | 'dataCenter' | 'skillCenter' | 'skillForge' | 'packageManager'
  | 'superExecutor' | 'terminal' | 'userCenter' | 'claudeTerminal' | 'chatSearch';
```

**流式消息优化 (ChatStore)**:

```typescript
interface ChatState {
  streamingMessageId: string | null;
  streamingContent: string;
  setStreamingMessageId: (id: string | null) => void;
  appendStreamingContent: (chunk: string) => void;
  commitStreamingContent: () => void;
  clearStreamingContent: () => void;
}
```

### 3.3 核心组件

**文件路径**: `autonome-studio/src/components/`

#### 3.3.1 聊天组件 (`chat/`)

| 组件 | 功能描述 |
|------|----------|
| `ChatStage.tsx` | 聊天主舞台，渲染消息列表 |
| `ChatInputBox.tsx` | 聊天输入框 |
| `StrategyCard/` | 策略卡片子目录（index.tsx, LogModal.tsx, parseUtils.ts, types.ts） |
| `StreamingMarkdown.tsx` | 流式 Markdown 渲染 |
| `MemoizedMessageItem.tsx` | 消息列表项（优化） |
| `VirtualizedMessageList.tsx` | 虚拟化消息列表 |
| `IntentCard.tsx` | 意图识别卡片 |
| `BlueprintCard.tsx` | 蓝图卡片 (PI Agent) |
| `ExecutionPlanCard.tsx` | 执行计划卡片 |
| `BattleReportCard.tsx` | 战报卡片 |
| `BookmarkPanel.tsx` | 书签面板 |
| `DAGCanvas.tsx` | DAG 可视化画布 |
| `QuickExecute.tsx` | 快速执行组件 |
| `InteractivePlotCard/` | 交互式图表卡片（index.tsx, PlotCanvas.tsx, utils.ts, types.ts） |
| `ChatSearchModal.tsx` | 聊天搜索弹窗 |
| `RecommendationCard.tsx` | 技能推荐卡片（V2: 渲染 json_action_menu） |
| `InlineActionMenu/` | 4 阶段内联操作工作流（index.tsx, types.ts, CSS Module） |
| `components/` | 共享子组件（MessageActionButtons, ExecutionResultCard, TransformToSkillPrompt, TablePreview, AttachmentPicker, SysLogCard） |

#### 3.3.2 布局组件 (`layout/`)

| 组件 | 功能描述 |
|------|----------|
| `Sidebar.tsx` | 侧边栏导航 |
| `SessionSidebar.tsx` | 会话列表侧边栏 |
| `TopHeader.tsx` | 顶部标题栏 |

#### 3.3.3 覆盖层组件 (`overlays/`)

| 组件/目录 | 功能描述 |
|-----------|----------|
| `SkillCenter.tsx` | 技能中心（统一入口，5 Tab） |
| `SkillCenter/SkillExecutePanel.tsx` | 执行面板 |
| `SkillCenter/SkillExecutePanel/` | 执行面板子目录（MobilePanels.tsx, categories.ts, types.ts） |
| `SkillCenter/MySkillsPanel.tsx` | 我的技能面板 |
| `SkillCenter/SkillMarketPanel.tsx` | 市场面板 |
| `SkillCenter/ForgePanel.tsx` | 工厂面板 |
| `SkillCenter/SettingsPanel.tsx` | 设置面板 |
| `SkillCenter/PendingDraftsList.tsx` | 待提交草稿 |
| `SkillCenter/SkillDetailDrawer.tsx` | 技能详情抽屉 |
| `SkillCenter/SkillRecommendArea.tsx` | 技能推荐区域 |
| `SkillCenter/ParameterGroupPanel.tsx` | 参数分组面板 |
| `SkillCenter/parameterGrouper.ts` | 参数分组工具函数 |
| `SkillCenter/ExecutionProgress.tsx` | 执行进度组件 |
| `SkillCenter/SampleSheetGenerator/` | 样本表生成器（index.tsx, SkillSheetInput, SampleTableEditor, ComparisonGroupEditor, DirectoryScanner, utils） |
| `TaskCenter.tsx` | 任务中心 |
| `DataCenter.tsx` | 数据中心 |
| `DataCenter/` | 数据中心子目录（DatabasePanel, GenomePanel, CustomFieldsEditor, GenomeDetailDrawer, DatabaseDetailDrawer, ImportGenomeModal, GenomeFormModal, DatabaseFormModal, TreeNode, utils, types） |
| `ProjectCenter.tsx` | 项目中心 |
| `SettingsCenter.tsx` | 设置中心 |
| `UserCenter/` | 用户中心子目录（index.tsx, ProfilePanel, SecurityPanel, AIPanel, ShortcutsPanel, WalletPanel） |
| `ControlPanel.tsx` | 控制面板 |
| `SuperExecutorPanel.tsx` | 超级执行器面板 |
| `WebTerminal.tsx` | Web Terminal |
| `ClaudeTerminal.tsx` | Claude Terminal |
| `ForgeOverlay.tsx` | 锻造覆盖层 |
| `PackageManager.tsx` | 包管理器 |
| `TopUpModal.tsx` | 充值弹窗 |
| `CreateFolderModal.tsx` | 创建文件夹弹窗 |
| `MoveFileModal.tsx` | 移动文件弹窗 |
| `RenameModal.tsx` | 重命名弹窗 |
| `UploadManager.tsx` | 上传管理器 |

#### 3.3.4 技能中心架构

```
SkillCenter.tsx (统一入口，5 Tab)
    │
    ├── SkillExecutePanel.tsx    # 执行 Tab
    │   └── SkillExecutePanel/   # 子组件（移动端面板、分类、类型）
    ├── MySkillsPanel.tsx        # 我的 Tab
    ├── SkillMarketPanel.tsx     # 市场 Tab
    ├── ForgePanel.tsx           # 工厂 Tab
    └── SettingsPanel.tsx        # 设置 Tab
```

#### 3.3.5 其他组件

| 组件/目录 | 功能描述 |
|-----------|----------|
| `CommandPalette/` | VS Code 风格命令面板（Cmd+K 唤起） |
| `mobile/` | 移动端组件（MobileNav, MobileSidebarSheet） |
| `onboarding/` | 新手引导（OnboardingGuide） |
| `common/` | 通用组件（FilePicker） |
| `GlobalOverlay.tsx` | 全局覆盖层容器 |
| `ThemeProvider.tsx` | 主题提供者 |
| `ShortcutManager.tsx` | 快捷键管理器 |
| `ToastProvider.tsx` | Toast 通知提供者 |
| `MarkdownBlock.tsx` | Markdown 渲染块 |
| `HybridPathInput.tsx` | 混合路径输入组件 |
| `FilePicker.tsx` | 文件选择器 |

### 3.4 自定义 Hooks

**文件路径**: `autonome-studio/src/hooks/`

| Hook | 功能 |
|------|------|
| `useChatStream.ts` | SSE 流式处理，消息收发，SuperExecutor V2 事件 |
| `useImmediateStream.ts` | 即时渲染流（替代打字机效果），rAF 节流 |
| `useSmartScroll.ts` | 智能自动滚动（用户滚动检测，暂停/恢复） |
| `useIsMobile.ts` | 视口断点检测（<768px） |
| `usePerformance.ts` | 防抖、节流 hooks |
| `useFilePreview.ts` | 文件预览状态（图片、PDF、表格、代码、文本） |
| `useMessageActions.ts` | 重试 AI 回复、编辑重发、深度解读 |
| `usePasteUpload.ts` | Ctrl+V 粘贴图片/文件 |
| `useChatEventListeners.ts` | 全局事件监听器管理（自动清理） |
| `useKeyboardShortcut.ts` | 键盘快捷键绑定 |
| `useSkillParams.ts` | 获取技能参数定义 |
| `useChat.ts` | 索引文件，重导出所有 chat hooks |

### 3.5 平台适配层 (Adapter)

**文件路径**: `autonome-studio/src/adapter/`

支持 Web 和 Tauri 桌面双平台：

| 文件 | 功能 |
|------|------|
| `platform.ts` | 平台检测（isTauri, isWeb, isSSR, getPlatform） |
| `api.adapter.ts` | 统一 API 适配器（Web + Tauri），ApiError 类 |
| `sse.adapter.ts` | 统一 SSE 适配器（Web + Tauri），chat/task 流类型 |
| `websocket.adapter.ts` | 统一 WebSocket 适配器（Web + Tauri），重连逻辑 |
| `fs.adapter.ts` | 统一文件系统适配器（Web API + Tauri IPC），文件选择对话框 |
| `updater.adapter.tsx` | 桌面端自动更新（Tauri），检查/下载/安装 |

### 3.6 共享包 (Packages)

**文件路径**: `packages/`

| 包名 | 功能 | 关键导出 |
|------|------|----------|
| `@autonome/shared-types` | 共享类型定义 | ApiResponse, User, Project, Skill, ChatMessage, Task, FolderNode, PlatformType |
| `@autonome/shared-utils` | 共享工具函数 | cn(), formatDate(), formatFileSize(), delay(), generateId(), debounce(), throttle(), safeJsonParse() |
| `@autonome/shared-store` | 共享 Store 类型 | 重导出 shared-types（Store 仍从 studio 直接导入） |
| `@autonome/shared-components` | 共享组件 | 重导出 adapter 层（组件仍从 studio 直接导入） |

### 3.7 API 客户端

**文件路径**: `autonome-studio/src/lib/`

| 文件 | 功能 |
|------|------|
| `api.ts` | 后端 API 客户端（动态 BASE_URL, JWT 自动注入, 401 重定向） |
| `utils.ts` | 通用工具函数 |
| `analytics.ts` | 用户行为分析（事件类型、会话追踪、批量上报） |
| `apiCache.ts` | 内存 API 缓存（TTL, stale-while-revalidate, 请求去重） |
| `contentFilter.ts` | LLM 输出过滤（thinking 标签、参数标签，兼容 DeepSeek/Claude 等） |
| `KeyboardShortcuts.ts` | 全局快捷键系统（OS 检测） |

**API 客户端核心**:

```typescript
// 动态获取后端 URL
export const BASE_URL = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';

// 通用请求方法
export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  // 自动添加 JWT Token
  // 处理 FormData vs JSON
  // 统一错误处理
  // 401 自动跳转登录
}
```

---

## 4. 数据流与交互

### 4.1 V2 统一 Agent 执行流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    V2 统一 Agent 执行流程                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  用户输入                                                          │
│      │                                                             │
│      ▼                                                             │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  unified_agent_node                                         │   │
│  │                                                              │   │
│  │  1. router_node_logic() → IntentClassification              │   │
│  │     - 快速路径: casual_chat / UI_ACTION (零 LLM)            │   │
│  │     - LLM 分类: 5 种意图类型                                  │   │
│  │     - 置信度门控: <0.6 降级为 CHAT                            │   │
│  │                                                              │   │
│  │  2. 按 intent_type 分发到专业节点                             │   │
│  └────────────────────────────────────────────────────────────┘   │
│          │                                                         │
│          ▼                                                         │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │  专业节点输出                                               │    │
│  │                                                              │   │
│  │  - CHAT → 文本回复                                          │   │
│  │  - EXPLICIT_SKILL → json_strategy (StrategyCard)           │   │
│  │  - VAGUE_ANALYSIS → json_strategy / battle_report          │   │
│  │  - TROUBLESHOOT → 诊断建议                                  │   │
│  │  - SYSTEM_ACTION → json_param_update / 系统操作结果         │   │
│  │  - 默认 → json_action_menu (RecommendationCard)            │   │
│  └───────────────────────────────────────────────────────────┘    │
│          │                                                         │
│          ▼                                                         │
│  ┌────────────────────┐                                            │
│  │ Frontend           │                                            │
│  │ - StrategyCard     │ ← json_strategy                            │
│  │ - RecommendationCard│ ← json_action_menu                        │
│  │ - BlueprintCard    │ ← json_blueprint                           │
│  │ - ParamUpdate      │ ← json_param_update                       │
│  │ 等待用户确认       │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼ 用户点击"确认执行"                                       │
│  ┌────────────────────┐                                            │
│  │ Docker Sandbox     │                                            │
│  │ (bio_tools.py)     │                                            │
│  │ 或 Container Pool  │                                            │
│  └────────────────────┘                                            │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 超级执行器流程 (Super Executor V4)

```
START → PHASE_1_EXPLORE → PHASE_2_INSTALL_DEPS → PHASE_3_EXECUTE → END
             ↓                    ↓                    ↓
       [探测代码生成]        [conda安装]          [分析执行+重试]
       [沙箱执行]           [启用网络]            [生成战报]
```

**SSE 事件类型**:
- `phase_change`: 阶段切换
- `exploration_progress`: 探查进度
- `install_progress`: 安装进度
- `execution_output`: 执行输出
- `debug_retry`: 调试重试
- `battle_report`: 战报生成

### 4.3 技能锻造流程

```
原始素材 (代码/文本)
    │
    ▼
┌─────────────────────────────────┐
│ forgeSessionApi.chatStream()    │
│ (流式对话锻造)                   │
└───────────────┬─────────────────┘
                │ SSE Stream
                ▼
┌─────────────────────────────────┐
│ Crafter Agent (crafter.py)      │
│                                 │
│ 1. 分析素材                     │
│ 2. 提取参数 Schema              │
│ 3. 重构代码 (参数化)            │
│ 4. 生成专家知识                 │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ 前端实时更新 Draft              │
│ - name, description             │
│ - parameters_schema             │
│ - script_code                   │
│ - expert_knowledge              │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ testDraftSkillStream()          │
│ 1. 自动生成测试数据             │
│ 2. 执行代码验证                 │
│ 3. 自动修复问题                 │
│ 4. 返回测试结果                 │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ commitSkill() / submitSkill()   │
│ 保存到数据库 / 提交审核         │
└─────────────────────────────────┘
```

### 4.4 三阶段技能推荐流程

```
用户查询
    │
    ├── 阶段1: 规则引擎 (<50ms)
    │   ├── 关键词匹配
    │   ├── 同义词扩展
    │   └── 置信度计算
    │
    ├── 阶段2: 向量检索 (~100ms)
    │   ├── embedding 计算
    │   └── pgvector 相似度搜索
    │
    └── 阶段3: LLM 精排 (~1-2s)
        ├── 候选技能排序
        └── 参数推断

推荐结果
    │
    ├── skill_id
    ├── skill_name
    ├── confidence
    └── suggested_parameters
```

---

## 5. 部署架构

### 5.1 Docker Compose 服务编排

**文件路径**: `docker-compose.yml`

| 服务名 | 容器名 | 端口 | 功能 |
|--------|--------|------|------|
| `backend-api` | `autonome-api` | 8000 | FastAPI 后端 |
| `frontend` | `autonome-web` | 3001 | Next.js 前端 |
| `postgres` | `autonome-postgres` | 5433 | PostgreSQL + pgvector |
| `redis` | `autonome-redis` | 6379 | Redis 缓存 |
| `backend-worker` | `autonome-worker` | - | Celery 异步任务 |

### 5.2 目录挂载

```yaml
volumes:
  # 数据持久化
  - postgres_data:/var/lib/postgresql/data
  - redis_data:/data

  # 用户上传文件
  - ./uploads:/workspace

  # Conda 环境 (持久化)
  - ./autonome_conda:/opt/conda

  # Docker Socket (沙箱执行)
  - /var/run/docker.sock:/var/run/docker.sock
```

### 5.3 启动命令

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker logs autonome-api | tail -30
docker logs autonome-web | tail -30

# 重启服务
docker-compose down && docker-compose up -d

# 进入容器调试
docker-compose exec backend-api bash
docker-compose exec postgres psql -U autonome autonome_db
```

---

## 附录：关键文件索引

### 后端核心文件

| 功能 | 文件路径 |
|------|----------|
| V2 统一 Agent 构建器 | `autonome-backend/app/agent/unified_executor.py` |
| V2 Schema 定义 | `autonome-backend/app/agent/schemas.py` |
| V2 路由节点 | `autonome-backend/app/agent/nodes/` |
| V2 路由器 | `autonome-backend/app/agent/nodes/router.py` |
| 沙箱规划器 | `autonome-backend/app/agent/nodes/sandbox_planner.py` |
| 4 级参数预填 | `autonome-backend/app/agent/nodes/skill_form_builder.py` |
| 参数自然语言更新 | `autonome-backend/app/agent/nodes/param_update.py` |
| 超级执行器 V4 | `autonome-backend/app/agent/super_executor_v4.py` |
| PI Agent | `autonome-backend/app/agent/pi_agent.py` |
| 首席 PI Agent | `autonome-backend/app/agent/chief_pi_agent.py` |
| 技能锻造 Agent | `autonome-backend/app/agent/crafter.py` |
| 执行计划 | `autonome-backend/app/agent/execution_plan.py` |
| 上下文构建器 | `autonome-backend/app/agent/context_builder.py` |
| 工具注册表 | `autonome-backend/app/agent/tools/registry.py` |
| 工具基类 | `autonome-backend/app/agent/tools/base.py` |
| Docker 沙箱 | `autonome-backend/app/tools/bio_tools.py` |
| 探针工具 | `autonome-backend/app/tools/probe_tools.py` |
| 技能解析器 | `autonome-backend/app/core/skill_parser.py` |
| 技能执行器 | `autonome-backend/app/services/skill_executor.py` |
| 技能统一匹配器 | `autonome-backend/app/services/skill_matcher.py` |
| 技能关键词索引 | `autonome-backend/app/services/skill_keywords_indexer.py` |
| 技能向量检索 | `autonome-backend/app/services/skill_vector_search.py` |
| LLM 技能匹配器 | `autonome-backend/app/services/llm_skill_matcher.py` |
| 容器暖池 | `autonome-backend/app/services/container_pool_service.py` |
| PTY 管理器 | `autonome-backend/app/services/pty_manager.py` |
| Web 终端管理器 | `autonome-backend/app/services/terminal_manager.py` |
| 三级缓存 | `autonome-backend/app/services/cache_service.py` |
| Agent 缓存 | `autonome-backend/app/services/agent_cache.py` |
| 数据探针服务 | `autonome-backend/app/services/data_probe_service.py` |
| 沙箱重试处理器 | `autonome-backend/app/services/sandbox_retry_handler.py` |
| 意图分类器 | `autonome-backend/app/services/intent_classifier.py` |
| 技能注入器 | `autonome-backend/app/services/system_learning/skill_injector.py` |
| 成功评估器 | `autonome-backend/app/services/success_evaluator.py` |
| MCP 技能搜索 | `autonome-backend/app/mcp/autonome_skills_mcp.py` |
| MCP 语义搜索 | `autonome-backend/app/mcp/semantic_search.py` |
| 数据模型 | `autonome-backend/app/models/domain.py` |

### 前端核心文件

| 功能 | 文件路径 |
|------|----------|
| 主页面 | `autonome-studio/src/app/page.tsx` |
| 聊天 Store | `autonome-studio/src/store/useChatStore.ts` |
| 技能中心 | `autonome-studio/src/components/overlays/SkillCenter.tsx` |
| 策略卡片 | `autonome-studio/src/components/chat/StrategyCard/` |
| 推荐卡片 | `autonome-studio/src/components/chat/RecommendationCard.tsx` |
| 超级执行器面板 | `autonome-studio/src/components/overlays/SuperExecutorPanel.tsx` |
| 命令面板 | `autonome-studio/src/components/CommandPalette/` |
| 新手引导 | `autonome-studio/src/components/onboarding/OnboardingGuide.tsx` |
| API 客户端 | `autonome-studio/src/lib/api.ts` |
| 内容过滤器 | `autonome-studio/src/lib/contentFilter.ts` |
| 快捷键系统 | `autonome-studio/src/lib/KeyboardShortcuts.ts` |
| 平台适配层 | `autonome-studio/src/adapter/` |
| SSE Hook | `autonome-studio/src/hooks/useChatStream.ts` |

---

*文档版本: 3.0.0*
*更新日期: 2026-04-12*
*维护者: Autonome Team*
