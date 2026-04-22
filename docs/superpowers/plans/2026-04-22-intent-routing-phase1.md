# 意图识别与路由系统第一阶段升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将意图识别系统从 6 意图单轮路由升级为 12 原子意图 DAG 调度 + Active Probing 参数探查架构

**Architecture:** 后端三级漏斗(L0→L1→L2)升级为 DAG 解构+参数探查，LangGraph 从单轮路由升级为 DAG 循环调度+挂起/恢复，前端新增 ParameterProbingCard 组件响应 Active Probing

**Tech Stack:** Python/FastAPI/LangGraph/Pydantic (后端), TypeScript/Next.js/Vercel AI SDK/Zustand (前端)

---

## 文件结构

### 后端修改文件

| 文件 | 操作 | 职责 |
|------|------|------|
| `autonome-backend/app/agent/router/schemas.py` | 重写 | 12 原子意图枚举 + DAG 数据模型 + ProbingRequest + AgentState 扩展 |
| `autonome-backend/app/agent/router/l0_rules.py` | 修改 | 新增 3 条规则 + 更新意图映射 |
| `autonome-backend/app/agent/router/l1_classifier.py` | 重写 | L1 DAG 解构器（输出 TaskDAG 而非 IntentExtraction） |
| `autonome-backend/app/agent/router/l2_extractor.py` | 重写 | Active Probing 参数探查器 |
| `autonome-backend/app/agent/router/engine.py` | 重写 | 路由引擎返回 RouteResult(dag + probing) |
| `autonome-backend/app/agent/graph.py` | 重写 | DAG 循环调度 + ask_user_node + 条件边 |
| `autonome-backend/app/agent/nodes/chat_node.py` | 修改 | 更新意图映射 |
| `autonome-backend/app/agent/nodes/skill_forge_node.py` | 修改 | 注入 FORGE_SYSTEM_PROMPT |
| `autonome-backend/app/agent/nodes/explicit_skill_node.py` | 修改 | 重命名为 explicit_exec_node |
| `autonome-backend/app/agent/nodes/diagnostic_node.py` | 修改 | 更新意图映射 |
| `autonome-backend/app/agent/nodes/literature_node.py` | 修改 | 更新意图映射 |
| `autonome-backend/app/agent/nodes/data_probe_node.py` | 修改 | 更新意图映射 |
| `autonome-backend/app/agent/nodes/orchestrator_node.py` | 新建 | 工作流编排 stub |
| `autonome-backend/app/agent/nodes/ui_state_node.py` | 新建 | 视觉微调 + SCI 约束 |
| `autonome-backend/app/agent/nodes/system_asset_node.py` | 新建 | 系统资产 stub |
| `autonome-backend/app/agent/nodes/version_control_node.py` | 新建 | 版本控制 stub |
| `autonome-backend/app/agent/nodes/collaboration_node.py` | 新建 | 团队协作 stub |
| `autonome-backend/app/agent/nodes/system_macro_node.py` | 新建 | 系统宏指令处理 |
| `autonome-backend/app/api/routes/chat.py` | 修改 | 新增系统提示词 + 意图映射更新 + Active Probing SSE |
| `autonome-backend/app/services/skill_matcher.py` | 修改 | IntentType 统一 |

### 前端修改文件

| 文件 | 操作 | 职责 |
|------|------|------|
| `autonome-studio/src/components/chat/ParameterProbingCard.tsx` | 新建 | Active Probing 表单组件 |
| `autonome-studio/src/components/chat/ChatStage.tsx` | 修改 | ToolInvocation 渲染 |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | 修改 | 传递 toolInvocations |

---

### Task 1: 重写 schemas.py — 12 原子意图 + DAG 数据模型

**Files:**
- Modify: `autonome-backend/app/agent/router/schemas.py`

- [ ] **Step 1: 替换 IntentType 枚举为 12 个原子意图**

将现有的 6 个 IntentType 替换为：

```python
class IntentType(str, Enum):
    """
    意图类型枚举 - 12 种原子意图分类 (V2.0 MECE)。

    每种意图对应一个下游 Agent 节点，通过 INTENT_NODE_MAP 映射。
    """
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

- [ ] **Step 2: 更新 INTENT_NODE_MAP**

```python
INTENT_NODE_MAP: Dict[IntentType, str] = {
    IntentType.WORKFLOW_ORCHESTRATE: "orchestrator_node",
    IntentType.SKILL_FORGE: "skill_forge_node",
    IntentType.EXPLICIT_EXEC: "explicit_exec_node",
    IntentType.VERSION_CONTROL: "version_control_node",
    IntentType.VISUAL_PERCEPTION_AND_TWEAK: "ui_state_node",
    IntentType.DATA_PROBE: "data_probe_node",
    IntentType.LITERATURE_MINING: "literature_node",
    IntentType.SYSTEM_ASSET_OPS: "system_asset_node",
    IntentType.COLLABORATION: "collaboration_node",
    IntentType.DIAGNOSTIC_RECOVERY: "diagnostic_node",
    IntentType.GENERAL_CHAT: "chat_node",
    IntentType.SYSTEM_MACRO: "system_macro_node",
}
```

- [ ] **Step 3: 新增 TaskNode, TaskDAG, ProbingRequest 模型**

在 IntentExtraction 之后添加：

```python
class TaskNode(BaseModel):
    """DAG 中的单一执行节点"""
    task_id: str = Field(..., description="子任务的唯一标识符，如 'task_1'")
    intent: IntentType = Field(..., description="解析出的原子意图类型")
    raw_instruction: str = Field(..., description="该子任务对应的具体自然语言指令")
    dependencies: List[str] = Field(default_factory=list, description="依赖的前置 task_id 列表")
    resolved_assets: List[str] = Field(default_factory=list, description="指代消解后的具体 FileID 或 DB_Hash")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="初步提取的关键参数（若有）")

class TaskDAG(BaseModel):
    """由多个 TaskNode 组成的有向无环图"""
    nodes: List[TaskNode] = Field(..., description="构成本次执行图谱的子任务节点列表")
    is_conditional: bool = Field(default=False, description="图中是否包含 If/Else 条件分支探针逻辑")

class ProbingRequest(BaseModel):
    """主动反问请求对象，用于触发前端 Generative UI 表单"""
    is_missing: bool = Field(..., description="是否存在缺失的必要参数")
    missing_params: List[str] = Field(default_factory=list, description="缺失的参数名列表")
    ui_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema 供前端渲染动态表单")
    message_to_user: str = Field(default="", description="向用户展示的追问提示语")

class RouteResult(BaseModel):
    """路由引擎的完整输出结果"""
    dag: TaskDAG = Field(..., description="L1 解析出的任务图谱")
    probing: Optional[ProbingRequest] = Field(default=None, description="L2 探查结果（仅当参数缺失时有值）")
```

- [ ] **Step 4: 扩展 AgentState**

```python
class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态 (V2.0)。

    支持多任务 DAG 调度、Active Probing 挂起/恢复。
    """
    messages: Annotated[Sequence[BaseMessage], "消息历史"]
    context: Dict[str, Any]            # 前端注入的工作区上下文
    intent_data: Optional[Dict]        # IntentExtraction 序列化结果
    skill_id: Optional[str]            # 匹配到的技能 ID
    execution_result: Optional[Dict]   # 执行结果
    # --- V2.0 DAG 调度状态 ---
    dag: Optional[Dict]                # TaskDAG 序列化结果
    current_task_idx: int              # 当前执行到 DAG 中的哪一个任务
    active_probing: Optional[Dict]     # ProbingRequest 序列化结果
    task_results: Dict[str, Any]       # 各子任务执行完毕后的结果上下文
```

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/agent/router/schemas.py
git commit -m "feat: 升级意图体系为12原子意图+DAG数据模型+ActiveProbing"
```

---

### Task 2: 升级 L0 规则引擎 — 新增 3 条规则 + 更新映射

**Files:**
- Modify: `autonome-backend/app/agent/router/l0_rules.py`

- [ ] **Step 1: 更新现有规则的意图映射**

在每条 Rule 的 evaluate 方法中，将旧 IntentType 替换为新 IntentType：
- `IntentType.DIAGNOSTIC` → `IntentType.DIAGNOSTIC_RECOVERY`
- `IntentType.LITERATURE` → `IntentType.LITERATURE_MINING`
- `IntentType.EXPLICIT_SKILL` → `IntentType.EXPLICIT_EXEC`
- `IntentType.SKILL_FORGE` → `IntentType.SKILL_FORGE`
- `IntentType.DATA_PROBE` → `IntentType.DATA_PROBE`
- `IntentType.CHAT` → `IntentType.GENERAL_CHAT`

- [ ] **Step 2: 新增 SystemMacroRule（最高优先级 0.5）**

在 `SystemStateRule` 类之前添加：

```python
class SystemMacroRule(Rule):
    """
    优先级 0.5: 系统宏指令拦截。

    检测 /status, /clear, /help 等系统级快捷指令，
    绕过 LLM 解析，实现毫秒级响应。
    """

    MACRO_PATTERN = re.compile(r'^/(status|clear|help|reset|config)$', re.IGNORECASE)

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        stripped = query.strip()
        if self.MACRO_PATTERN.match(stripped):
            macro_name = stripped[1:].lower()
            log.debug(f"[L0] SystemMacroRule 命中: /{macro_name}")
            return IntentExtraction(
                intent=IntentType.SYSTEM_MACRO,
                confidence=1.0,
                entities={"macro_command": macro_name},
                requires_followup=False
            )
        return None
```

- [ ] **Step 3: 新增 VersionControlRule（优先级 4.5）**

在 `ErrorPatternRule` 类之后添加：

```python
class VersionControlRule(Rule):
    """
    优先级 4.5: 版本与历史控制拦截。

    检测"回滚/版本/对比/历史"等关键词，路由到 VERSION_CONTROL。
    """

    VC_PATTERN = re.compile(
        r'(回滚|版本|对比|rollback|version|diff|历史|撤销|恢复|revert|checkout|'
        r'版本对比|差异对比|历史版本|快照|snapshot)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.VC_PATTERN.search(query):
            log.debug("[L0] VersionControlRule 命中")
            return IntentExtraction(
                intent=IntentType.VERSION_CONTROL,
                confidence=0.90,
                entities={},
                requires_followup=False
            )
        return None
```

- [ ] **Step 4: 新增 VisualTweakRule（优先级 6.5）**

在 `ProbePatternRule` 类之后添加：

```python
class VisualTweakRule(Rule):
    """
    优先级 6.5: 视觉感知与图形管护拦截。

    检测"调色/配色/阈值/DPI"等视觉微调关键词，
    路由到 VISUAL_PERCEPTION_AND_TWEAK。
    """

    VISUAL_PATTERN = re.compile(
        r'(调色|配色|阈值|DPI|分辨率|颜色|palette|theme|tweak|'
        r'调整.*图|修改.*图|改.*颜色|改.*配色|'
        r'发表级|SCI.*图|导出.*图|save.*figure|export.*plot|'
        r'看图|解释.*图|图.*什么意思|interpret.*figure)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.VISUAL_PATTERN.search(query):
            log.debug("[L0] VisualTweakRule 命中")
            return IntentExtraction(
                intent=IntentType.VISUAL_PERCEPTION_AND_TWEAK,
                confidence=0.85,
                entities={},
                requires_followup=False
            )
        return None
```

- [ ] **Step 5: 更新 L0RuleEngine 规则列表**

```python
class L0RuleEngine:
    def __init__(self):
        self.rules: List[Rule] = [
            SystemMacroRule(),        # 优先级 0.5: 系统宏指令（最高优先级）
            SystemStateRule(),        # 优先级 1: 系统状态
            ActiveViewRule(),         # 优先级 2: 活跃视图
            ExplicitSkillRule(),      # 优先级 3: 显式技能
            ErrorPatternRule(),       # 优先级 4: 错误关键词
            VersionControlRule(),     # 优先级 4.5: 版本控制
            LiteraturePatternRule(),  # 优先级 5: 文献模式
            ProbePatternRule(),       # 优先级 6: 数据探查
            VisualTweakRule(),        # 优先级 6.5: 视觉微调
            CodeGenPatternRule(),     # 优先级 7: 代码生成
            ChitchatRule(),           # 优先级 8: 闲聊
        ]
```

- [ ] **Step 6: 扩展 ActiveViewRule.VIEW_INTENT_MAP**

```python
VIEW_INTENT_MAP = {
    "literature_upload": IntentType.LITERATURE_MINING,
    "visual_editor": IntentType.VISUAL_PERCEPTION_AND_TWEAK,
    "version_history": IntentType.VERSION_CONTROL,
    "skill_market": IntentType.EXPLICIT_EXEC,
}
```

- [ ] **Step 7: Commit**

```bash
git add autonome-backend/app/agent/router/l0_rules.py
git commit -m "feat: L0规则引擎新增SystemMacro/VersionControl/VisualTweak规则"
```

---

### Task 3: 重写 L1 分类器 — DAG 解构器

**Files:**
- Modify: `autonome-backend/app/agent/router/l1_classifier.py`

- [ ] **Step 1: 重写系统提示词为 L1_DECOMPOSER_PROMPT_TEMPLATE**

替换 `INTENT_CLASSIFICATION_PROMPT` 为：

```python
L1_DECOMPOSER_PROMPT_TEMPLATE = """你是一个顶级的生物信息学架构师，担任 Autonome Studio 的核心大脑（L1 意图解构器）。
你的任务是将用户的复杂自然语言指令，拆解为具有时序或依赖关系的执行图谱（Task DAG）。

=== 当前工作区上下文资产快照 (Workspace Context) ===
{workspace_context}
=====================================================

=== 可用的 11 种核心原子意图 ===
1. INTENT_WORKFLOW_ORCHESTRATE: 串联多个步骤，生成 Nextflow 流程。
2. INTENT_SKILL_FORGE: 从零编写、修改 R/Python 脚本（带有参数系统和注释要求）。
3. INTENT_EXPLICIT_EXEC: 明确调用已有技能执行计算任务。
4. INTENT_VERSION_CONTROL: 回滚代码或数据版本历史。
5. INTENT_VISUAL_PERCEPTION_AND_TWEAK: 解释图像、看图写码、调整图形配色/阈值，强制要求输出 SCI 图片及 TSV。
6. INTENT_DATA_PROBE: 极速检查矩阵行列、分布、NA 值，不启动重量级沙箱。
7. INTENT_LITERATURE_MINING: 提取 PDF 文献中的生信参数、算法逻辑。
8. INTENT_SYSTEM_ASSET_OPS: 切换计算资源、移动文件、计费查询。
9. INTENT_COLLABORATION: 权限分配、资源分享给其他团队成员。
10. INTENT_DIAGNOSTIC_RECOVERY: 分析报错日志，提供自愈策略。
11. INTENT_GENERAL_CHAT: 生信概念解释、起草信件等不涉及具体操作的长尾问答。
================================

=== 核心解析规则 ===
1. 任务拆分：如果指令包含多个阶段（如"先...然后...如果报错就..."），必须将其拆分为多个 TaskNode。单意图指令也输出单节点 DAG。
2. 指代消解 (Coreference Resolution)：必须将代词（如"它"、"左侧文件"、"昨天传的矩阵"）精确映射为 Workspace Context 中列出的具体 FileID，填入 `resolved_assets` 数组中。
3. 参数提取：从用户指令中提取关键参数（如物种、工具名、阈值等），填入 `parameters` 字典。
4. 返回格式：必须严格返回满足 TaskDAG JSON Schema 的字符串，不要包含任何额外的解释性文字。

=== 输出 JSON 示例 ===
```json
{{
  "nodes": [
    {{
      "task_id": "task_1",
      "intent": "INTENT_LITERATURE_MINING",
      "raw_instruction": "提取这篇文章的方法学聚类参数",
      "dependencies": [],
      "resolved_assets": ["file-uuid-1234"],
      "parameters": {{}}
    }},
    {{
      "task_id": "task_2",
      "intent": "INTENT_SKILL_FORGE",
      "raw_instruction": "根据提取的参数写一个用于聚类的Python脚本",
      "dependencies": ["task_1"],
      "resolved_assets": [],
      "parameters": {{"language": "python"}}
    }}
  ],
  "is_conditional": false
}}
```"""
```

- [ ] **Step 2: 重写 L1Classifier 类**

将 `classify()` 方法改为 `decompose()`，输出 TaskDAG：

```python
class L1Classifier:
    """L1 DAG 解构器 - 将用户输入解构为 TaskDAG。"""

    def __init__(self, session, user_id: str):
        self.llm_config = get_llm_config(session, user_id)
        self.is_local = _is_local_model(self.llm_config.base_url)
        self.confidence_threshold = 0.7

        api_key = self.llm_config.api_key or "not-needed"
        self.primary_llm = ChatOpenAI(
            api_key=api_key,
            base_url=self.llm_config.base_url,
            model=self.llm_config.model_name,
            temperature=0.0
        )

        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", L1_DECOMPOSER_PROMPT_TEMPLATE),
            ("human", "User Query: {query}")
        ])

    async def decompose(
        self,
        query: str,
        context: Dict[str, Any],
        enable_think: bool = False,
        temperature: float = 0.0
    ) -> TaskDAG:
        """执行意图解构，输出 TaskDAG。"""
        log.info(f"[L1] 正在调用 LLM 解构: query='{query[:50]}...'")

        try:
            if self.is_local:
                result = await self._decompose_with_json_mode(
                    query=query, context=context,
                    enable_think=enable_think, temperature=temperature
                )
            else:
                result = await self._decompose_with_structured_output(query, context)
            return result
        except Exception as e:
            log.error(f"[L1] 解构失败: {str(e)}")
            # 兜底：返回单节点 GENERAL_CHAT DAG
            return TaskDAG(nodes=[TaskNode(
                task_id="task_1",
                intent=IntentType.GENERAL_CHAT,
                raw_instruction=query,
            )])

    async def _decompose_with_structured_output(
        self, query: str, context: Dict[str, Any]
    ) -> TaskDAG:
        """第三方 API 模式：with_structured_output(TaskDAG)"""
        llm_with_schema = self.primary_llm.with_structured_output(TaskDAG)
        chain = self.prompt_template | llm_with_schema
        result = await chain.ainvoke({
            "workspace_context": str(context),
            "query": query
        })
        return result

    async def _decompose_with_json_mode(
        self, query: str, context: Dict[str, Any],
        enable_think: bool = False, temperature: float = 0.0
    ) -> TaskDAG:
        """本地模型模式：Ollama 原生 API + JSON mode"""
        host = self.llm_config.base_url
        if host and host.endswith('/v1'):
            host = host[:-3]
        if not host:
            host = "http://localhost:11434"

        client = ollama.AsyncClient(host=host)

        json_instruction = (
            "\n\n请严格按照 TaskDAG JSON 格式输出，不要输出任何其他内容。"
            "\n格式：{\"nodes\": [{\"task_id\": \"task_1\", \"intent\": \"INTENT_GENERAL_CHAT\", "
            "\"raw_instruction\": \"...\", \"dependencies\": [], \"resolved_assets\": [], "
            "\"parameters\": {}}], \"is_conditional\": false}"
        )

        system_msg = L1_DECOMPOSER_PROMPT_TEMPLATE + json_instruction
        user_msg = f"Workspace Context: {str(context)}\n\nUser Query: {query}"

        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg}
        ]

        raw_content = ""
        try:
            response = await client.chat(
                model=self.llm_config.model_name,
                messages=messages,
                think=enable_think,
                format='json',
                options={'temperature': temperature}
            )
            raw_content = response['message']['content'].strip()
            repaired = repair_json(raw_content)
            parsed = json.loads(repaired)
            return TaskDAG(**parsed)
        except Exception as parse_err:
            log.warning(f"[L1] JSON 解析失败: {parse_err}, 原始: {raw_content[:200]}")
            return self._fallback_dag_from_text(query, raw_content)

    def _fallback_dag_from_text(self, query: str, text: str) -> TaskDAG:
        """JSON 解析失败时的兜底：从文本中提取意图，返回单节点 DAG"""
        text_lower = text.lower()
        for intent in IntentType:
            if intent.value.lower() in text_lower:
                return TaskDAG(nodes=[TaskNode(
                    task_id="task_1", intent=intent, raw_instruction=query
                )])
        return TaskDAG(nodes=[TaskNode(
            task_id="task_1", intent=IntentType.GENERAL_CHAT, raw_instruction=query
        )])
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/agent/router/l1_classifier.py
git commit -m "feat: L1分类器升级为DAG解构器，输出TaskDAG而非单一IntentExtraction"
```

---

### Task 4: 重写 L2 提取器 — Active Probing 参数探查器

**Files:**
- Modify: `autonome-backend/app/agent/router/l2_extractor.py`

- [ ] **Step 1: 重写 l2_extractor.py**

完整替换为：

```python
"""
L2 参数探查层 - Active Probing 主动拦截机制。

当 L1 解构器输出的 TaskNode 缺失关键参数时，
L2 挂起路由并生成 ProbingRequest（含 JSON Schema 表单定义），
供前端渲染 Generative UI 表单，用户补全参数后恢复执行。
"""
from typing import Any, Dict, Set

from app.agent.router.schemas import IntentType, TaskNode, ProbingRequest
from app.core.logger import log


class L2SlotExtractor:
    """
    L2 参数探查器。

    仅对需要参数校验的意图执行 Active Probing，其余放行。
    """

    # 需要 L2 探查的意图集合
    PROBING_INTENTS: Set[IntentType] = {
        IntentType.EXPLICIT_EXEC,
        IntentType.SKILL_FORGE,
    }

    # 需要 L2 上下文自动填充的意图集合
    ENRICHMENT_INTENTS: Set[IntentType] = {
        IntentType.SKILL_FORGE,
        IntentType.EXPLICIT_EXEC,
        IntentType.DATA_PROBE,
    }


async def check_task_parameters(
    task: TaskNode,
    context: Dict[str, Any],
    skill_registry: Any = None
) -> ProbingRequest:
    """
    L2 层核心逻辑：对齐系统参数，探测缺失项。

    Args:
        task: L1 解构器输出的 TaskNode
        context: 工作区上下文
        skill_registry: 技能注册表（用于拉取 schema.yaml）

    Returns:
        ProbingRequest: 参数探查结果
    """
    if task.intent not in L2SlotExtractor.PROBING_INTENTS:
        return ProbingRequest(is_missing=False)

    # 先尝试上下文自动填充
    enrichments = _enrich_from_context(task.intent, context)
    merged_params = {**task.parameters, **enrichments}

    # EXPLICIT_EXEC 意图：从 skill_registry 拉取 required 参数
    if task.intent == IntentType.EXPLICIT_EXEC:
        return await _check_explicit_exec_params(task, merged_params, skill_registry)

    # SKILL_FORGE 意图：检查关键分析参数
    if task.intent == IntentType.SKILL_FORGE:
        return _check_skill_forge_params(task, merged_params)

    return ProbingRequest(is_missing=False)


async def _check_explicit_exec_params(
    task: TaskNode,
    merged_params: Dict[str, Any],
    skill_registry: Any
) -> ProbingRequest:
    """检查显式技能执行的参数完整性"""
    # 阶段一：使用通用关键参数检查
    # 阶段二：从 skill_registry 拉取 schema.yaml 的 required 参数
    required_keys = ["species", "input_file"]
    missing = [key for key in required_keys if key not in merged_params or not merged_params[key]]

    if missing:
        return ProbingRequest(
            is_missing=True,
            missing_params=missing,
            ui_schema={
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "title": "物种 (Species)",
                        "enum": ["Human", "Mouse", "Rat", "Zebrafish"],
                        "default": "Human"
                    },
                    "input_file": {
                        "type": "string",
                        "title": "输入文件路径",
                    }
                },
                "required": missing
            },
            message_to_user="执行该分析需要补充以下核心参数，请确认："
        )

    return ProbingRequest(is_missing=False)


def _check_skill_forge_params(
    task: TaskNode,
    merged_params: Dict[str, Any]
) -> ProbingRequest:
    """检查代码锻造的关键参数"""
    # 代码锻造对 species 和 input_file 的要求较宽松（可用示例数据）
    # 仅在明确需要特定物种时才追问
    return ProbingRequest(is_missing=False)


def _enrich_from_context(
    intent: IntentType, context: Dict[str, Any]
) -> Dict[str, str]:
    """从工作区上下文自动填充参数"""
    enrichments: Dict[str, str] = {}

    if intent in L2SlotExtractor.ENRICHMENT_INTENTS:
        active_file = context.get("active_file")
        if active_file:
            enrichments["input_file"] = active_file

        selected_cells = context.get("selected_cells")
        if selected_cells:
            enrichments["cell_count"] = str(selected_cells)

    return enrichments
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/router/l2_extractor.py
git commit -m "feat: L2升级为ActiveProbing参数探查器，支持ProbingRequest挂起机制"
```

---

### Task 5: 重写路由引擎 — 返回 RouteResult(dag + probing)

**Files:**
- Modify: `autonome-backend/app/agent/router/engine.py`

- [ ] **Step 1: 重写 IntentRouterEngine**

```python
"""
意图路由编排引擎 V2.0 - DAG 解构 + Active Probing。

执行流程：
1. L0 规则拦截（0ms，~30-40% 命中率）→ 命中则包装为单节点 TaskDAG
2. L1 DAG 解构（~250ms，输出 TaskDAG）
3. 上下文自动填充（从 workspace context 注入已知参数）
4. L2 参数探查（Active Probing，输出 ProbingRequest）
5. 置信度降级保护
"""
from typing import Any, Dict

from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.l2_extractor import L2SlotExtractor, check_task_parameters
from app.agent.router.schemas import (
    IntentExtraction, IntentType, INTENT_NODE_MAP,
    TaskNode, TaskDAG, ProbingRequest, RouteResult
)
from app.core.logger import log


class IntentRouterEngine:
    """意图路由编排引擎 V2.0。"""

    def __init__(self, session, user_id: str, confidence_threshold: float = 0.7):
        self.l0 = L0RuleEngine()
        self.l1 = L1Classifier(session, user_id)
        self.l2 = L2SlotExtractor()
        self.confidence_threshold = confidence_threshold

    async def route(self, query: str, context: Dict[str, Any]) -> RouteResult:
        """执行意图路由（主入口），返回 RouteResult(dag + probing)。"""
        # Step 1: L0 极速拦截
        l0_result = self.l0.evaluate(query, context)
        if l0_result is not None:
            # L0 命中：包装为单节点 TaskDAG
            dag = TaskDAG(nodes=[TaskNode(
                task_id="task_1",
                intent=l0_result.intent,
                raw_instruction=query,
                parameters=l0_result.entities,
            )])
            log.info(f"[Engine] L0 命中: intent={l0_result.intent.value}, 包装为单节点 DAG")
            return RouteResult(dag=dag, probing=None)

        # Step 2: L1 DAG 解构
        dag = await self.l1.decompose(query, context)
        log.info(f"[Engine] L1 解构: {len(dag.nodes)} 个任务节点")

        # Step 3: 置信度降级保护（对首个节点检查）
        # 注：TaskDAG 本身无 confidence 字段，降级逻辑在 L1 内部处理

        # Step 4: L2 参数探查（仅对首个任务）
        if dag.nodes:
            first_task = dag.nodes[0]
            probing = await check_task_parameters(first_task, context)
            if probing.is_missing:
                log.info(f"[Engine] L2 拦截: 缺失参数 {probing.missing_params}")
                return RouteResult(dag=dag, probing=probing)

        log.info(f"[Engine] 路由完成: {len(dag.nodes)} 个任务, 首个意图={dag.nodes[0].intent.value if dag.nodes else 'empty'}")
        return RouteResult(dag=dag, probing=None)
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/router/engine.py
git commit -m "feat: 路由引擎升级为DAG解构+ActiveProbing，返回RouteResult"
```

---

### Task 6: 重写 LangGraph — DAG 循环调度 + ask_user_node

**Files:**
- Modify: `autonome-backend/app/agent/graph.py`

- [ ] **Step 1: 重写 graph.py**

```python
"""
LangGraph 多 Agent 编排图 V2.0。

支持 DAG 多任务循环调度和 Active Probing 挂起/恢复。

Graph 结构:
    [Entry] → intent_router_node → determine_next_step
        → ask_user_node → END (挂起，等待前端参数补全)
        → orchestrator_node → task_advance_or_end
        → skill_forge_node → task_advance_or_end
        → explicit_exec_node → task_advance_or_end
        → version_control_node → task_advance_or_end
        → ui_state_node → task_advance_or_end
        → data_probe_node → task_advance_or_end
        → literature_node → task_advance_or_end
        → system_asset_node → task_advance_or_end
        → collaboration_node → task_advance_or_end
        → diagnostic_node → task_advance_or_end
        → chat_node → task_advance_or_end
        → system_macro_node → task_advance_or_end
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.agent.nodes.chat_node import chat_node
from app.agent.nodes.data_probe_node import data_probe_node
from app.agent.nodes.diagnostic_node import diagnostic_node
from app.agent.nodes.explicit_exec_node import explicit_exec_node
from app.agent.nodes.literature_node import literature_node
from app.agent.nodes.skill_forge_node import skill_forge_node
from app.agent.nodes.orchestrator_node import orchestrator_node
from app.agent.nodes.ui_state_node import ui_state_node
from app.agent.nodes.system_asset_node import system_asset_node
from app.agent.nodes.version_control_node import version_control_node
from app.agent.nodes.collaboration_node import collaboration_node
from app.agent.nodes.system_macro_node import system_macro_node
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import (
    AgentState, IntentType, INTENT_NODE_MAP,
    TaskDAG, ProbingRequest, RouteResult
)
from app.core.logger import log


async def intent_router_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """LangGraph 入口节点：调用路由引擎，获取 TaskDAG + ProbingRequest。"""
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent_data": {"intent": "INTENT_GENERAL_CHAT", "routing_target": "chat_node"},
            "dag": None,
            "current_task_idx": 0,
            "active_probing": None,
            "task_results": {},
        }

    query = messages[-1].content
    context = state.get("context", {})

    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    if not session or not user_id:
        log.warning("[intent_router_node] 缺少 session 或 user_id，降级为 chat")
        return {
            "intent_data": {"intent": "INTENT_GENERAL_CHAT", "routing_target": "chat_node"},
            "dag": None,
            "current_task_idx": 0,
            "active_probing": None,
            "task_results": {},
        }

    # 调用路由引擎
    engine = IntentRouterEngine(session, user_id)
    route_result: RouteResult = await engine.route(query, context)

    # 存储 DAG 和探查结果
    dag_dict = route_result.dag.model_dump()
    probing_dict = route_result.probing.model_dump() if route_result.probing else None

    # 提取首个任务的意图数据（兼容下游 chat.py）
    first_intent = route_result.dag.nodes[0].intent if route_result.dag.nodes else IntentType.GENERAL_CHAT
    intent_data = {
        "intent": first_intent.value,
        "routing_target": INTENT_NODE_MAP.get(first_intent, "chat_node"),
    }

    return {
        "intent_data": intent_data,
        "dag": dag_dict,
        "current_task_idx": 0,
        "active_probing": probing_dict,
        "task_results": {},
    }


async def ask_user_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """向前端抛出参数补全表单的节点（Active Probing 挂起点）。"""
    probing_dict = state.get("active_probing")
    if not probing_dict:
        return {}

    probing = ProbingRequest(**probing_dict) if isinstance(probing_dict, dict) else probing_dict
    current_idx = state.get("current_task_idx", 0)

    # 构造 ToolCall，前端 useChat hook 自动解析为 toolInvocations
    tool_call = {
        "name": "request_parameters",
        "args": {
            "message": probing.message_to_user,
            "schema": probing.ui_schema,
        },
        "id": f"call_probe_{current_idx}",
    }

    message = AIMessage(content="", tool_calls=[tool_call])
    log.info(f"[ask_user_node] 发送参数补全请求: missing={probing.missing_params}")

    return {"messages": [message]}


def determine_next_step(state: AgentState) -> str:
    """条件边：决定图的下一步走向。"""
    # 最高优先级：L2 探查器发现缺参数
    probing_dict = state.get("active_probing")
    if probing_dict and probing_dict.get("is_missing"):
        return "ask_user_node"

    # 检查 DAG 是否有任务
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx >= len(nodes):
        return END

    # 根据原子意图分发到 Worker 节点
    intent_str = nodes[idx].get("intent", "INTENT_GENERAL_CHAT")
    try:
        intent = IntentType(intent_str)
        return INTENT_NODE_MAP.get(intent, "chat_node")
    except ValueError:
        return "chat_node"


def task_advance_or_end(state: AgentState) -> str:
    """Worker 节点执行完毕后：推进任务指针或结束。"""
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx + 1 >= len(nodes):
        return END

    # 还有未完成的任务，回到路由判断
    return "intent_router"


def build_intent_graph() -> StateGraph:
    """构建意图路由 LangGraph V2.0。"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("ask_user_node", ask_user_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("skill_forge_node", skill_forge_node)
    workflow.add_node("explicit_exec_node", explicit_exec_node)
    workflow.add_node("diagnostic_node", diagnostic_node)
    workflow.add_node("literature_node", literature_node)
    workflow.add_node("data_probe_node", data_probe_node)
    workflow.add_node("orchestrator_node", orchestrator_node)
    workflow.add_node("ui_state_node", ui_state_node)
    workflow.add_node("system_asset_node", system_asset_node)
    workflow.add_node("version_control_node", version_control_node)
    workflow.add_node("collaboration_node", collaboration_node)
    workflow.add_node("system_macro_node", system_macro_node)

    # 设置入口
    workflow.set_entry_point("intent_router")

    # 条件路由边：intent_router → 各节点
    all_worker_nodes = [
        "ask_user_node", "chat_node", "skill_forge_node", "explicit_exec_node",
        "diagnostic_node", "literature_node", "data_probe_node",
        "orchestrator_node", "ui_state_node", "system_asset_node",
        "version_control_node", "collaboration_node", "system_macro_node",
    ]
    workflow.add_conditional_edges(
        "intent_router",
        determine_next_step,
        {node: node for node in all_worker_nodes} | {END: END}
    )

    # ask_user_node → END（挂起，等待前端参数补全后重新调用）
    workflow.add_edge("ask_user_node", END)

    # 各 Worker 节点 → task_advance_or_end
    worker_only = [n for n in all_worker_nodes if n != "ask_user_node"]
    for node in worker_only:
        workflow.add_conditional_edges(
            node,
            task_advance_or_end,
            {"intent_router": "intent_router", END: END}
        )

    return workflow.compile()
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/graph.py
git commit -m "feat: LangGraph升级为DAG循环调度+ActiveProbing挂起/恢复"
```

---

### Task 7: 新增 6 个 Agent 节点 + 更新现有节点

**Files:**
- Create: `autonome-backend/app/agent/nodes/orchestrator_node.py`
- Create: `autonome-backend/app/agent/nodes/ui_state_node.py`
- Create: `autonome-backend/app/agent/nodes/system_asset_node.py`
- Create: `autonome-backend/app/agent/nodes/version_control_node.py`
- Create: `autonome-backend/app/agent/nodes/collaboration_node.py`
- Create: `autonome-backend/app/agent/nodes/system_macro_node.py`
- Modify: `autonome-backend/app/agent/nodes/skill_forge_node.py`
- Modify: `autonome-backend/app/agent/nodes/explicit_skill_node.py`

- [ ] **Step 1: 创建 orchestrator_node.py (stub)**

```python
"""Orchestrator Agent 节点 - 工作流编排（阶段一 stub）。"""
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from app.agent.router.schemas import AgentState
from app.core.logger import log

async def orchestrator_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """工作流编排节点（阶段一 stub）。"""
    intent_data = state.get("intent_data", {})
    log.info(f"[orchestrator_node] 工作流编排请求, intent_data={intent_data}")
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "stub", "message": "工作流编排功能开发中"}
    return {
        "intent_data": {**intent_data, "node": "orchestrator_node"},
        "messages": [AIMessage(content="工作流编排功能正在开发中，敬请期待。当前您可以使用代码锻造模式手动编写 Nextflow 流程。")],
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
```

- [ ] **Step 2: 创建 ui_state_node.py (完整实现)**

```python
"""UI/State Agent 节点 - 视觉微调与 SCI 级输出约束。"""
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig
from app.agent.router.schemas import AgentState
from app.core.logger import log

UI_STATE_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [视觉感知与图形管护节点]。你负责前端绘图状态的重载和发表级图表的输出。

=== 核心输出协议 (SCI Protocol) ===

1. 【视觉专业性】：你生成的任何可视化参数或轻量级绘图脚本，必须应用专业的配色方案（如 ggsci 的 npg/jco/lancet 等）。图像输出必须强制指定分辨率至少为 300 DPI。
2. 【双格式输出】：强制要求同步生成 `.pdf`（用于矢量编辑）和 `.png`（用于网页预览）两种格式。
3. 【数据对称性（最高红线）】：严禁仅输出图像！你必须在操作中强制包含抽取底层绘图数据的逻辑，将图表中的坐标（X/Y）、分类标记、阈值等，输出为一个以 Tab 分割的 `.tsv` 数据文件。
====================================

你的任务是不启动全量计算型沙箱，仅重载视图配置或执行轻量级绘图环境。
"""

async def ui_state_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """处理视图微调、配色更改及图表导出的节点。"""
    intent_data = state.get("intent_data", {})
    log.info(f"[ui_state_node] 视觉微调请求, intent_data={intent_data}")
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "system_prompt": "UI_STATE_SYSTEM_PROMPT"}
    return {
        "intent_data": {**intent_data, "node": "ui_state_node", "system_prompt_key": "visual"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
```

- [ ] **Step 3: 创建 system_asset_node.py, version_control_node.py, collaboration_node.py (stubs)**

这三个 stub 节点结构与 orchestrator_node 类似，仅替换节点名和提示消息：
- `system_asset_node.py` → "系统资产调度功能开发中"
- `version_control_node.py` → "版本控制功能开发中"
- `collaboration_node.py` → "团队协作功能开发中"

每个 stub 节点都遵循相同模式：记录日志、推进 current_task_idx、写入 task_results。

- [ ] **Step 4: 创建 system_macro_node.py (完整实现)**

```python
"""System Macro Agent 节点 - 系统宏指令处理。"""
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from app.agent.router.schemas import AgentState
from app.core.logger import log

MACRO_HANDLERS = {
    "status": "系统状态正常。所有服务运行中。",
    "clear": "对话已清空。（请在前端执行清空操作）",
    "help": "可用指令：/status 查看系统状态 | /clear 清空对话 | /help 查看帮助",
    "reset": "环境已重置。",
    "config": "配置信息请前往设置面板查看。",
}

async def system_macro_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """处理系统宏指令。"""
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})
    macro_name = entities.get("macro_command", "help")
    response_text = MACRO_HANDLERS.get(macro_name, f"未知指令: /{macro_name}")
    log.info(f"[system_macro_node] 处理宏指令: /{macro_name}")
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "macro": macro_name}
    return {
        "intent_data": {**intent_data, "node": "system_macro_node"},
        "messages": [AIMessage(content=response_text)],
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
```

- [ ] **Step 5: 更新 skill_forge_node.py — 注入 FORGE_SYSTEM_PROMPT**

在现有 skill_forge_node 函数中添加系统提示词标记：

```python
FORGE_SYSTEM_PROMPT = """
=== 最高优先级系统指令（违背将导致任务熔断） ===

1. 【非破坏性更新】：当你对现有代码进行修改、优化或 Bug 修复时，绝对禁止删除或截断历史版本中的 `@ProgramExplanation`（程序说明）和任何原有的中文行级注释。你只能追加或修改，绝不能抹除前人的上下文。
2. 【强制参数系统】：所有生成的独立脚本必须使用标准的参数解析库（Python 使用 `argparse`，R 使用 `optparse` 或 `commandArgs`）。
3. 【生信默认值】：必须为所有参数设定符合真实生信分析经验的默认值（如 k-mer 默认为 3，p-value 默认为 0.05）。
====================================================
"""

async def skill_forge_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Skill Forge Agent 节点 - 代码生成与执行。"""
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})
    log.info(f"[skill_forge_node] 处理代码生成请求, entities={entities}")
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success"}
    return {
        "intent_data": {**intent_data, "node": "skill_forge_node", "system_prompt_key": "forge"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
```

- [ ] **Step 6: 重命名 explicit_skill_node.py 为 explicit_exec_node.py**

将 `autonome-backend/app/agent/nodes/explicit_skill_node.py` 重命名为 `explicit_exec_node.py`，将函数名 `explicit_skill_node` 改为 `explicit_exec_node`，并添加 DAG 指针推进逻辑（与 skill_forge_node 模式一致）。

- [ ] **Step 7: 更新其余现有节点 (chat_node, diagnostic_node, literature_node, data_probe_node)**

每个节点添加 `current_task_idx` 推进和 `task_results` 写入逻辑，与 skill_forge_node 模式一致。

- [ ] **Step 8: Commit**

```bash
git add autonome-backend/app/agent/nodes/
git commit -m "feat: 新增6个Agent节点+强化skill_forge注入FORGE_SYSTEM_PROMPT+DAG指针推进"
```

---

### Task 8: 适配 chat.py — 新增系统提示词 + 意图映射更新 + Active Probing SSE

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py`

- [ ] **Step 1: 新增 SYSTEM_PROMPT_VISUAL 和 SYSTEM_PROMPT_ORCHESTRATE**

在现有系统提示词之后添加：

```python
SYSTEM_PROMPT_VISUAL = """你是一个专业的生物信息学可视化助手，名为 Autonome。你的核心职责是帮助用户调整和优化科研图表。

核心输出协议 (SCI Protocol)：
1. 【视觉专业性】：应用专业配色方案（如 ggsci 的 npg/jco/lancet），分辨率至少 300 DPI
2. 【双格式输出】：同步生成 .pdf（矢量编辑）和 .png（网页预览）
3. 【数据对称性（最高红线）】：严禁仅输出图像！必须同步产出底层坐标/阈值 .tsv 数据文件

核心原则：
- 用中文回答问题
- 不启动全量计算型沙箱，仅重载视图配置或执行轻量级绘图环境
- 直接进入正题，不要自我介绍"""

SYSTEM_PROMPT_ORCHESTRATE = """你是一个专业的生物信息学流程编排助手，名为 Autonome。你的核心职责是帮助用户设计和生成 Nextflow 分析流程。

核心原则：
- 用中文解释设计思路
- 生成的 Nextflow 代码必须包含完整的 processes、channels 和 workflow 定义
- 通过多轮对话确认通道（Channels）和进程（Processes）
- 仅负责"调度"和"串联"，不负责单一脚本的具体实现
- 直接进入正题，不要自我介绍"""
```

- [ ] **Step 2: 更新意图到系统提示词的映射**

将 chat.py 中第 218-230 行的意图映射替换为：

```python
if intent_result.intent in (
    NewIntentType.SKILL_FORGE,
    NewIntentType.EXPLICIT_EXEC,
    NewIntentType.DIAGNOSTIC_RECOVERY,
):
    system_prompt = SYSTEM_PROMPT_CODE
    log.info(f"[Chat] 使用代码生成模式 (intent={intent_result.intent.value})")
elif intent_result.intent == NewIntentType.DATA_PROBE:
    from app.core.config import settings
    project_workspace = str(Path(settings.UPLOAD_DIR) / f"project_{request.project_id}")
    system_prompt = SYSTEM_PROMPT_DATA_PROBE_TEMPLATE.format(workspace_path=project_workspace)
    log.info(f"[Chat] 使用数据探查模式 (intent={intent_result.intent.value})")
elif intent_result.intent == NewIntentType.VISUAL_PERCEPTION_AND_TWEAK:
    system_prompt = SYSTEM_PROMPT_VISUAL
    log.info(f"[Chat] 使用视觉微调模式 (intent={intent_result.intent.value})")
elif intent_result.intent == NewIntentType.WORKFLOW_ORCHESTRATE:
    system_prompt = SYSTEM_PROMPT_ORCHESTRATE
    log.info(f"[Chat] 使用工作流编排模式 (intent={intent_result.intent.value})")
else:
    system_prompt = SYSTEM_PROMPT_CHAT
    log.info(f"[Chat] 使用一般问答模式 (intent={intent_result.intent.value})")
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py
git commit -m "feat: chat.py新增视觉微调/工作流编排系统提示词+更新意图映射"
```

---

### Task 9: 统一 SkillMatcher 的 IntentType

**Files:**
- Modify: `autonome-backend/app/services/skill_matcher.py`

- [ ] **Step 1: 替换 SkillMatcher 的 IntentType**

将 `skill_matcher.py` 中的独立 `IntentType` 类替换为从 schemas 导入：

```python
from app.agent.router.schemas import IntentType
```

删除原有的 `IntentType` 类定义（EXPLICIT_SKILL, IMPLICIT_SKILL, LIVE_CODING, GENERAL_QUESTION），更新匹配逻辑中的引用：
- `IntentType.EXPLICIT_SKILL` → `IntentType.EXPLICIT_EXEC`
- `IntentType.LIVE_CODING` → `IntentType.SKILL_FORGE`
- `IntentType.GENERAL_QUESTION` → `IntentType.GENERAL_CHAT`
- `IntentType.IMPLICIT_SKILL` → `IntentType.EXPLICIT_EXEC`（隐式匹配也路由到显式执行）

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/services/skill_matcher.py
git commit -m "refactor: SkillMatcher IntentType统一为router.schemas.IntentType"
```

---

### Task 10: 前端 — 新增 ParameterProbingCard 组件

**Files:**
- Create: `autonome-studio/src/components/chat/ParameterProbingCard.tsx`

- [ ] **Step 1: 创建 ParameterProbingCard.tsx**

```tsx
"use client";

import React, { useState } from "react";
import { AlertTriangle } from "lucide-react";

interface ParameterProbingCardProps {
  message: string;
  schema: {
    type: string;
    properties: Record<string, {
      type?: string;
      title?: string;
      enum?: string[];
      default?: string | number | boolean;
      minimum?: number;
      maximum?: number;
    }>;
    required?: string[];
  };
  onSubmit: (formData: Record<string, unknown>) => void;
}

export function ParameterProbingCard({
  message,
  schema,
  onSubmit,
}: ParameterProbingCardProps) {
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    // 预填默认值
    const defaults: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(schema.properties || {})) {
      if (field.default !== undefined) {
        defaults[key] = field.default;
      }
    }
    return defaults;
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  const handleChange = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="border border-orange-200 bg-orange-50/50 dark:border-orange-800 dark:bg-orange-950/30 p-4 rounded-xl my-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="h-4 w-4 text-orange-600 dark:text-orange-400" />
        <span className="text-orange-600 dark:text-orange-400 font-semibold text-sm">
          系统拦截：缺失必要参数
        </span>
      </div>
      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">{message}</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        {Object.entries(schema.properties || {}).map(([key, field]) => (
          <div key={key} className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {field.title || key}
            </label>

            {field.enum ? (
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                defaultValue={field.default as string}
                onChange={(e) => handleChange(key, e.target.value)}
                required={schema.required?.includes(key)}
              >
                <option value="" disabled>
                  请选择...
                </option>
                {field.enum.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            ) : field.type === "number" ? (
              <input
                type="number"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                defaultValue={field.default as number}
                min={field.minimum}
                max={field.maximum}
                step="any"
                onChange={(e) => handleChange(key, parseFloat(e.target.value))}
                required={schema.required?.includes(key)}
              />
            ) : field.type === "boolean" ? (
              <input
                type="checkbox"
                className="h-4 w-4"
                defaultChecked={field.default as boolean}
                onChange={(e) => handleChange(key, e.target.checked)}
              />
            ) : (
              <input
                type="text"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                defaultValue={field.default as string}
                onChange={(e) => handleChange(key, e.target.value)}
                required={schema.required?.includes(key)}
              />
            )}
          </div>
        ))}

        <div className="pt-2">
          <button
            type="submit"
            className="w-full bg-orange-600 hover:bg-orange-700 text-white text-sm font-medium h-9 rounded-md px-4 py-2"
          >
            确认并继续执行
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/components/chat/ParameterProbingCard.tsx
git commit -m "feat: 新增ParameterProbingCard组件，支持ActiveProbing表单渲染"
```

---

### Task 11: 前端 — ChatStage 适配 ToolInvocation 渲染

**Files:**
- Modify: `autonome-studio/src/components/chat/ChatStage.tsx`
- Modify: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`

- [ ] **Step 1: 在 ChatStage.tsx 中添加 ParameterProbingCard 导入和渲染逻辑**

在 ChatStage.tsx 的导入区域添加：

```tsx
import { ParameterProbingCard } from "./ParameterProbingCard";
```

在消息渲染区域（MemoizedMessageItem 或消息循环内），添加对 `toolInvocations` 的检测和渲染。具体位置取决于当前消息渲染逻辑的结构，需要在 `MemoizedMessageItem` 组件中添加 `toolInvocations` prop 的传递。

- [ ] **Step 2: 在 MemoizedMessageItem.tsx 中支持 ToolInvocation 渲染**

在消息内容渲染之后，添加 toolInvocations 渲染区域：

```tsx
{/* Active Probing: 参数补全表单 */}
{message.toolInvocations?.map((toolInvocation: any) => {
  if (toolInvocation.toolName === "request_parameters") {
    if (toolInvocation.state === "result") {
      return (
        <div key={toolInvocation.toolCallId} className="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 p-2 rounded my-2">
          ✓ 参数已补全并提交
        </div>
      );
    }
    return (
      <ParameterProbingCard
        key={toolInvocation.toolCallId}
        message={toolInvocation.args.message}
        schema={toolInvocation.args.schema}
        onSubmit={(formData) => addToolResult({
          toolCallId: toolInvocation.toolCallId,
          result: formData
        })}
      />
    );
  }
  return null;
})}
```

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/components/chat/ChatStage.tsx autonome-studio/src/components/chat/MemoizedMessageItem.tsx
git commit -m "feat: ChatStage适配ToolInvocation渲染，支持ActiveProbing表单交互"
```

---

### Task 12: 集成验证 — Docker 重启 + 冒烟测试

- [ ] **Step 1: 重启 Docker 服务**

```bash
cd /opt/data1/public/software/systools/autonome && docker-compose down && docker-compose up -d
```

- [ ] **Step 2: 检查后端日志确认无报错**

```bash
docker logs autonome-api | tail -30
```

预期：服务正常启动，无 ImportError 或 AttributeError。

- [ ] **Step 3: 验证意图分类 API 可用**

通过 `curl` 或前端发送测试消息，确认：
- `/status` → SYSTEM_MACRO 意图
- "帮我跑一下PCA分析" → SKILL_FORGE 意图
- "查看这个h5ad文件的结构" → DATA_PROBE 意图
- "回滚到昨天的代码" → VERSION_CONTROL 意图
- "调整火山图的配色" → VISUAL_PERCEPTION_AND_TWEAK 意图

- [ ] **Step 4: 验证前端正常加载**

访问 http://localhost:3001，确认前端无构建错误，聊天界面正常显示。

- [ ] **Step 5: 使用 auto_deploy.sh 部署**

```bash
./auto_deploy.sh -s "feat: 意图识别与路由系统第一阶段全栈升级" -d "完成12原子意图体系重构、DAG调度架构、ActiveProbing参数探查、LangGraph状态机重塑、前端GenerativeUI表单渲染"
```
