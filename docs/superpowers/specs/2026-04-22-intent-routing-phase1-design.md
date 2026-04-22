# 意图识别与路由系统第一阶段升级设计规格

> 日期: 2026-04-22
> 范围: 全栈一次性交付（后端意图体系 + 路由引擎 + 参数探查 + Graph 节点 + 前端交互）
> 兼容策略: 完全替换旧 IntentType，不留双体系

---

## 1. 目标

将 Autonome Studio 的意图识别与路由系统从"6 意图单轮路由"升级为"12 原子意图 DAG 调度 + Active Probing 参数探查"架构，实现文档 `docs/modules/意图识别与路由系统.md` 中定义的阶段一至阶段五全部内容。

## 2. 现有架构分析

### 2.1 当前意图体系

文件: `autonome-backend/app/agent/router/schemas.py`

6 个 IntentType: CHAT, SKILL_FORGE, EXPLICIT_SKILL, DIAGNOSTIC, LITERATURE, DATA_PROBE

INTENT_NODE_MAP 将每个意图映射到 LangGraph 节点名。

### 2.2 当前路由引擎

文件: `autonome-backend/app/agent/router/engine.py`

三级漏斗: L0 规则拦截(0ms) → L1 LLM 分类(~250ms) → L2 上下文自动填充

### 2.3 当前 L0 规则

文件: `autonome-backend/app/agent/router/l0_rules.py`

8 条优先级规则: SystemStateRule, ActiveViewRule, ExplicitSkillRule, ErrorPatternRule, LiteraturePatternRule, ProbePatternRule, CodeGenPatternRule, ChitchatRule

### 2.4 当前 L1 分类器

文件: `autonome-backend/app/agent/router/l1_classifier.py`

双模式: Ollama 原生客户端(JSON mode) / 第三方 API(with_structured_output)。输出 IntentExtraction 单一意图。

### 2.5 当前 L2 提取器

文件: `autonome-backend/app/agent/router/l2_extractor.py`

v2 中 L2 的 LLM 调用已消除，仅保留 `_enrich_from_context` 上下文自动填充。

### 2.6 当前 Graph

文件: `autonome-backend/app/agent/graph.py`

单轮路由: intent_router_node → 条件边 → 6 个 Agent 节点 → END

### 2.7 当前 Agent 节点

文件: `autonome-backend/app/agent/nodes/`

6 个节点均为 stub（仅标记 intent_data，实际执行在 chat.py SSE 循环中）。

### 2.8 当前 Chat API

文件: `autonome-backend/app/api/routes/chat.py`

~930 行 SSE 流式函数，包含意图分类、系统提示词选择、LLM 流式调用、data_probe 工具绑定。

### 2.9 当前前端

- ChatStage.tsx 使用 Vercel AI SDK useChat hook
- useChatSync 桥接 useChat 状态到 Zustand store
- 无 ToolInvocation 渲染逻辑
- 无 Active Probing 表单组件

### 2.10 关键问题

1. 两套意图系统(IntentRouterEngine 6 种 vs SkillMatcher 4 种)需统一
2. LangGraph 节点为 stub，实际执行在 chat.py
3. 无 DAG 多任务调度能力
4. 无参数缺失时的前端表单交互
5. L2 探查机制过于简单(仅上下文自动填充)

---

## 3. 目标架构

### 3.1 意图体系: 12 原子意图 (MECE)

```python
class IntentType(str, Enum):
    # 组1: 计算与编排 (Compute & Engineering)
    WORKFLOW_ORCHESTRATE = "INTENT_WORKFLOW_ORCHESTRATE"
    SKILL_FORGE = "INTENT_SKILL_FORGE"
    EXPLICIT_EXEC = "INTENT_EXPLICIT_EXEC"
    VERSION_CONTROL = "INTENT_VERSION_CONTROL"
    # 组2: 视觉与探究 (Perception & Discovery)
    VISUAL_PERCEPTION_AND_TWEAK = "INTENT_VISUAL_PERCEPTION_AND_TWEAK"
    DATA_PROBE = "INTENT_DATA_PROBE"
    LITERATURE_MINING = "INTENT_LITERATURE_MINING"
    # 组3: 运维与协作 (Operations & Collaboration)
    SYSTEM_ASSET_OPS = "INTENT_SYSTEM_ASSET_OPS"
    COLLABORATION = "INTENT_COLLABORATION"
    DIAGNOSTIC_RECOVERY = "INTENT_DIAGNOSTIC_RECOVERY"
    # 组4: 通用兜底 (General Support)
    GENERAL_CHAT = "INTENT_GENERAL_CHAT"
    SYSTEM_MACRO = "INTENT_SYSTEM_MACRO"
```

### 3.2 DAG 数据结构

```python
class TaskNode(BaseModel):
    task_id: str
    intent: IntentType
    raw_instruction: str
    dependencies: List[str] = []      # 依赖的前置 task_id
    resolved_assets: List[str] = []   # 指代消解后的 FileID
    parameters: Dict[str, Any] = {}   # 初步提取的参数

class TaskDAG(BaseModel):
    nodes: List[TaskNode]
    is_conditional: bool = False      # 是否包含 If/Else 探针
```

### 3.3 Active Probing 数据结构

```python
class ProbingRequest(BaseModel):
    is_missing: bool
    missing_params: List[str]
    ui_schema: Dict[str, Any]         # JSON Schema 供前端渲染表单
    message_to_user: str
```

### 3.4 扩展的 AgentState

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], ...]
    context: Dict[str, Any]
    intent_data: Optional[Dict]
    skill_id: Optional[str]
    execution_result: Optional[Dict]
    # --- 新增 DAG 调度状态 ---
    dag: Optional[TaskDAG]
    current_task_idx: int
    active_probing: Optional[ProbingRequest]
    task_results: Dict[str, Any]
```

### 3.5 路由引擎架构

```
L0 规则拦截 (0ms, ~30-40% 命中)
    ↓ 未命中
L1 DAG 解构器 (~250ms, 输出 TaskDAG)
    ↓
L2 参数探查 (Active Probing)
    ↓ 缺参数 → 挂起, 返回 ProbingRequest
    ↓ 参数齐全 → 放行
Worker 节点执行
    ↓ 任务完成, current_task_idx++
    ↓ DAG 还有任务 → 回到 L2 探查下一个任务
    ↓ DAG 全部完成 → END
```

---

## 4. 后端改造详细设计

### 4.1 schemas.py 改造

**文件**: `autonome-backend/app/agent/router/schemas.py`

操作:
1. 替换 IntentType 为 12 个原子意图枚举
2. 更新 INTENT_NODE_MAP 映射到新的节点名
3. 新增 TaskNode, TaskDAG, ProbingRequest 模型
4. 扩展 AgentState 增加 dag, current_task_idx, active_probing, task_results 字段
5. 保留 IntentExtraction 作为 L0 规则的输出格式（L0 仍返回单一意图，由 engine 包装为单节点 DAG）

INTENT_NODE_MAP 新映射:

| IntentType | 节点名 |
|------------|--------|
| WORKFLOW_ORCHESTRATE | orchestrator_node |
| SKILL_FORGE | skill_forge_node |
| EXPLICIT_EXEC | explicit_exec_node |
| VERSION_CONTROL | version_control_node |
| VISUAL_PERCEPTION_AND_TWEAK | ui_state_node |
| DATA_PROBE | data_probe_node |
| LITERATURE_MINING | literature_node |
| SYSTEM_ASSET_OPS | system_asset_node |
| COLLABORATION | collaboration_node |
| DIAGNOSTIC_RECOVERY | diagnostic_node |
| GENERAL_CHAT | chat_node |
| SYSTEM_MACRO | system_macro_node |

### 4.2 l0_rules.py 改造

**文件**: `autonome-backend/app/agent/router/l0_rules.py`

操作:
1. 更新现有规则的意图映射到新 IntentType
2. 新增 3 条规则:

**VersionControlRule** (优先级 4.5, 插入 ErrorPatternRule 之后):
- 关键词: "回滚|版本|对比|rollback|version|diff|历史|撤销"
- 映射: VERSION_CONTROL

**VisualTweakRule** (优先级 6.5, 插入 ProbePatternRule 之后):
- 关键词: "调色|配色|阈值|DPI|分辨率|颜色|palette|theme|tweak|调整.*图"
- 映射: VISUAL_PERCEPTION_AND_TWEAK

**SystemMacroRule** (优先级 0.5, 最高优先级):
- 检测 `/status`, `/clear`, `/help` 等系统指令
- 映射: SYSTEM_MACRO

3. 更新 ActiveViewRule.VIEW_INTENT_MAP 扩展更多视图映射

### 4.3 l1_classifier.py 改造

**文件**: `autonome-backend/app/agent/router/l1_classifier.py`

操作:
1. 重写系统提示词为 `L1_DECOMPOSER_PROMPT_TEMPLATE`
   - 列出 11 种核心原子意图（排除 SYSTEM_MACRO，由 L0 拦截）
   - 注入 Workspace Context 占位符 `{workspace_context}`
   - 包含指代消解指令
   - 包含 TaskDAG JSON 输出示例
2. `classify()` 方法改为 `decompose()`，输出 TaskDAG
3. 使用 `with_structured_output(TaskDAG)` 强制结构化输出
4. Ollama 模式: JSON format 指令更新为 TaskDAG schema
5. 保留 `_fallback_intent_from_text` 兜底逻辑

### 4.4 l2_extractor.py 改造

**文件**: `autonome-backend/app/agent/router/l2_extractor.py`

操作:
1. 新增 `ProbingRequest` 模型（定义在 schemas.py 中，与 TaskNode/TaskDAG 同文件）
2. 新增 `check_task_parameters(task: TaskNode, skill_registry) -> ProbingRequest` 函数
3. 对 EXPLICIT_EXEC 意图:
   - 从 skill_registry 拉取 schema.yaml 的 required 参数
   - 对比 task.parameters，找出 missing
   - 缺失时构造 ui_schema（JSON Schema 格式，含 enum/default/minimum/maximum）
4. 对 SKILL_FORGE 意图: 检查关键参数（species, input_file 等）
5. 参数齐全或不需要参数的意图: 返回 ProbingRequest(is_missing=False)
6. 保留 `_enrich_from_context` 逻辑，在参数探查前先尝试上下文自动填充

### 4.5 engine.py 改造

**文件**: `autonome-backend/app/agent/router/engine.py`

操作:
1. `route()` 方法改为返回 TaskDAG（而非 IntentExtraction）
2. L0 命中时: 将单一 IntentExtraction 包装为单节点 TaskDAG
3. L1 调用改为 `decompose()` 获取 TaskDAG
4. L2 调用改为 `check_task_parameters()` 获取 ProbingRequest
5. 新增 `route_result` 包含 `dag: TaskDAG` + `probing: Optional[ProbingRequest]`

### 4.6 graph.py 改造

**文件**: `autonome-backend/app/agent/graph.py`

操作:
1. 更新 AgentState 为扩展版本
2. 重写 `intent_router_node`:
   - 调用 engine.route() 获取 TaskDAG + ProbingRequest
   - 存储 dag 到 state
   - 如果 probing.is_missing, 设置 active_probing 并返回
3. 重写 `route_by_intent` 为 `determine_next_step`:
   - 最高优先级: active_probing.is_missing → "ask_user_node"
   - DAG 全部完成 → END
   - 按 dag.nodes[current_task_idx].intent 分发到 Worker 节点
4. 新增 `ask_user_node`:
   - 构造 `request_parameters` ToolCall（含 ui_schema）
   - 发送 AIMessage(content="", tool_calls=[...])
5. 新增节点注册: orchestrator_node, ui_state_node, system_asset_node, version_control_node, collaboration_node, system_macro_node
6. Worker 节点执行完毕后推进 current_task_idx，检查 DAG 是否还有任务

### 4.7 Agent 节点改造

**目录**: `autonome-backend/app/agent/nodes/`

操作:
1. 更新现有 6 个节点的意图映射
2. 新增节点:
   - `orchestrator_node.py` — Nextflow 流程编排（阶段一 stub: 标记意图 + 返回"工作流编排功能开发中"提示，不执行实际编排）
   - `ui_state_node.py` — 视觉微调 + SCI 级输出约束 Prompt（阶段一完整实现: 注入视觉微调系统提示词）
   - `system_asset_node.py` — 资源调度 + 计费（阶段一 stub: 标记意图 + 返回提示）
   - `version_control_node.py` — 版本控制（阶段一 stub: 标记意图 + 返回提示）
   - `collaboration_node.py` — 团队协作（阶段一 stub: 标记意图 + 返回提示）
   - `system_macro_node.py` — 系统宏指令处理（阶段一完整实现: 处理 /status, /clear, /help 等指令）
3. 强化 `skill_forge_node.py`:
   - 注入 FORGE_SYSTEM_PROMPT（非破坏性更新 + 强制参数系统 + 生信默认值）
4. 强化 `data_probe_node.py`: 保持现有 probe_tools 绑定逻辑

### 4.8 chat.py 适配

**文件**: `autonome-backend/app/api/routes/chat.py`

操作:
1. 更新意图到系统提示词的映射:
   - SKILL_FORGE / EXPLICIT_EXEC / DIAGNOSTIC_RECOVERY → SYSTEM_PROMPT_CODE
   - DATA_PROBE → SYSTEM_PROMPT_DATA_PROBE_TEMPLATE
   - VISUAL_PERCEPTION_AND_TWEAK → SYSTEM_PROMPT_VISUAL (新增)
   - CHAT / LITERATURE_MINING → SYSTEM_PROMPT_CHAT
   - WORKFLOW_ORCHESTRATE → SYSTEM_PROMPT_ORCHESTRATE (新增)
2. 新增 SYSTEM_PROMPT_VISUAL: 视觉微调模式（SCI 级输出约束）
3. 新增 SYSTEM_PROMPT_ORCHESTRATE: 工作流编排模式
4. 处理 Active Probing: 当 intent_result 包含 ProbingRequest 时，通过 SSE 流发送 Vercel AI SDK 兼容的 ToolCall 事件（事件类型 `data-tool-call`，含 `toolCallId`, `toolName: "request_parameters"`, `args: {message, schema}`），前端 useChat hook 自动解析为 toolInvocations

### 4.9 SkillMatcher 清理

**文件**: `autonome-backend/app/services/skill_matcher.py`

操作:
1. 将 SkillMatcher 的 IntentType 替换为新的 IntentType
2. 更新匹配逻辑中的意图映射
3. SkillMatcherWithFallback 保持关键词匹配功能（用于技能推荐 API），但 IntentType 统一

---

## 5. 前端改造详细设计

### 5.1 ParameterProbingCard 组件

**新文件**: `autonome-studio/src/components/chat/ParameterProbingCard.tsx`

功能:
- 接收 ToolInvocation（含 args.message 和 args.schema）
- 根据 ui_schema 的 properties 动态渲染表单:
  - `enum` 类型 → 下拉选择框
  - `type: "number"` → 数字输入框（含 min/max/step）
  - `type: "string"` → 文本输入框
  - `type: "boolean"` → 开关
- 预填 default 值
- 用户提交后调用 `addToolResult({ toolCallId, result: formData })`
- 样式: 橙色边框卡片，"系统拦截：缺失必要参数" 标题

### 5.2 ChatStage.tsx 适配

**文件**: `autonome-studio/src/components/chat/ChatStage.tsx`

操作:
1. 在消息渲染循环中检测 `toolInvocations`
2. 对 `toolName === "request_parameters"` 的 ToolInvocation:
   - state !== "result" → 渲染 ParameterProbingCard
   - state === "result" → 渲染"参数已补全"确认标记
3. 对其他 toolInvocation 类型保持默认渲染

### 5.3 MemoizedMessageItem.tsx 适配

**文件**: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`

操作:
1. 传递 toolInvocations 和 addToolResult 到消息渲染
2. 支持 ParameterProbingCard 的渲染位置（在消息内容下方）

### 5.4 意图感知 UI 增强

操作:
1. 在 useChatSync 中处理 `intent` 数据事件，将意图类型存入 store
2. ChatInputBox 可根据当前意图显示不同的提示文案（可选，非阻塞）

---

## 6. 数据流

### 6.1 正常流程（参数齐全）

```
用户输入 → L0 规则拦截
         → L1 DAG 解构（输出 TaskDAG）
         → L2 参数探查（ProbingRequest.is_missing=False）
         → Worker 节点执行
         → current_task_idx++
         → DAG 还有任务? → 回到 L2
         → DAG 完成 → END
```

### 6.2 参数缺失流程（Active Probing）

```
用户输入 → L0 规则拦截
         → L1 DAG 解构
         → L2 参数探查（ProbingRequest.is_missing=True）
         → ask_user_node（发送 request_parameters ToolCall）
         → 前端渲染 ParameterProbingCard
         → 用户填写表单提交
         → 参数合并到 task.parameters
         → Worker 节点执行
         → 继续 DAG 调度
```

### 6.3 L0 命中流程

```
用户输入 → L0 规则命中（如 /status）
         → 包装为单节点 TaskDAG
         → SYSTEM_MACRO → system_macro_node
         → 直接执行，不经过 L1
```

---

## 7. 兼容性与非破坏性保障

1. **现有功能路径保持可用**: chat, skill_forge, data_probe, diagnostic, literature 五个核心路径在新意图体系下有明确映射
2. **降级路径**: L1 置信度低于阈值时降级为 GENERAL_CHAT；L0/L1 均未命中时走 GENERAL_CHAT
3. **前端无 ToolInvocation 时行为不变**: ParameterProbingCard 仅在检测到 request_parameters ToolCall 时渲染
4. **数据库模型不变**: 仅 AgentState 扩展，不修改数据库 schema
5. **现有工具不变**: probe_tools, bio_tools, literature_tools, report_tools 保持不变
6. **SkillMatcher 保留**: 用于技能推荐 API 路由，IntentType 统一但匹配逻辑不变

---

## 8. 旧意图到新意图的映射

| 旧 IntentType | 新 IntentType | 说明 |
|---------------|---------------|------|
| CHAT | GENERAL_CHAT | 通用问答 |
| SKILL_FORGE | SKILL_FORGE | 代码锻造（不变） |
| EXPLICIT_SKILL | EXPLICIT_EXEC | 显式技能执行 |
| DIAGNOSTIC | DIAGNOSTIC_RECOVERY | 错误诊断+自愈 |
| LITERATURE | LITERATURE_MINING | 文献解析 |
| DATA_PROBE | DATA_PROBE | 数据探查（不变） |
| (无) | WORKFLOW_ORCHESTRATE | 新增：工作流编排 |
| (无) | VERSION_CONTROL | 新增：版本控制 |
| (无) | VISUAL_PERCEPTION_AND_TWEAK | 新增：视觉感知 |
| (无) | SYSTEM_ASSET_OPS | 新增：系统资产调度 |
| (无) | COLLABORATION | 新增：团队协作 |
| (无) | SYSTEM_MACRO | 新增：系统宏指令 |

---

## 9. 测试策略

1. **L0 规则单测**: 每条规则的正例/负例/边界
2. **L1 解构器单测**: 单意图/多意图/指代消解/JSON 解析失败兜底
3. **L2 探查器单测**: 参数齐全/参数缺失/不同意图类型的探查逻辑
4. **Engine 集成测**: L0 命中/L1 命中/置信度降级/完整 DAG 流程
5. **Graph 集成测**: 单任务路由/多任务 DAG/Active Probing 挂起恢复
6. **前端单测**: ParameterProbingCard 渲染/表单提交/不同 schema 类型
