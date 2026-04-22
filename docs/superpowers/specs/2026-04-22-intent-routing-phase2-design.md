# Intent Routing Phase 2: L2 Skill Registry + L1 Context Enhancement + Frontend E2E

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the intent routing pipeline with dynamic skill parameter schemas from SKILL.md, structured workspace context with coreference resolution, and end-to-end frontend Active Probing verification.

**Architecture:** Three independent enhancement modules implemented as vertical slices. L2 replaces hardcoded parameter checks with dynamic SKILL.md schema lookup via skill_parser. L1 replaces raw str(context) injection with typed WorkspaceContext sections and adds coreference resolution prompt rules. Frontend fixes useChat maxSteps, submit loading state, history reconstruction, and syncFromUseChat preservation.

**Tech Stack:** Python/FastAPI (backend), LangGraph (state machine), React/Next.js (frontend), Vercel AI SDK v5 (chat streaming), skill_parser.py (SKILL.md parameter extraction)

---

## Scope

Phase 2 focuses exclusively on deepening the Phase 1 skeleton. Stub node upgrades are deferred to Phase 3.

**In scope:**
- L2 Active Probing: skill_registry integration with SKILL.md parameters_schema
- L1 Decomposer: structured WorkspaceContext + coreference resolution rules
- Frontend: Active Probing e2e verification and fixes

**Out of scope:**
- 6 stub node upgrades (orchestrator, system_asset, version_control, collaboration, data_probe, literature)
- L0 rule engine changes
- LangGraph graph structure changes
- IntentType enum or TaskDAG model changes (WorkspaceContext is the only schemas.py addition)

---

## 1. L2 Active Probing Enhancement

### 1.1 Current State

- `_check_explicit_exec_params()` hardcodes `required_keys = ["species", "input_file"]`
- `_check_skill_forge_params()` always returns `is_missing=False`
- `PROBING_INTENTS = {EXPLICIT_EXEC, SKILL_FORGE}`
- `skill_registry` parameter threaded through but never used
- Commented-out TODO for `skill_registry.get_skill_schema()`

### 1.2 SkillParameterRegistry Service

**New file:** `autonome-backend/app/services/skill_parameter_registry.py`

A lightweight service wrapping skill_parser to provide parameter schema lookup for L2:

```python
class SkillParameterRegistry:
    """技能参数注册表：从 SKILL.md / DB 动态拉取参数定义"""

    def __init__(self, session, user_id: str):
        self.session = session
        self.user_id = user_id

    async def get_parameters_schema(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        获取技能的完整参数 schema。

        调用 skill_parser.get_combined_skill_by_id() 获取 parameters_schema，
        包含 properties (各参数定义) 和 required (必填参数名列表)。

        Returns:
            参数 schema dict，格式: {"type": "object", "properties": {...}, "required": [...]}
            如果技能不存在或无参数定义，返回 None
        """

    async def get_required_params(self, skill_id: str) -> List[str]:
        """
        获取技能的必填参数名列表。

        Returns:
            必填参数名列表，如 ["sample_sheet", "output_dir"]
            如果技能不存在，返回空列表
        """

    async def build_ui_schema(
        self,
        skill_id: str,
        missing_params: List[str]
    ) -> Dict[str, Any]:
        """
        从技能 schema 构建前端 JSON Schema 表单定义。

        仅包含缺失参数的属性定义，用于 ParameterProbingCard 渲染。

        处理自定义 format 字段:
        - format: "filepath" → 添加 hint "请输入文件路径"
        - format: "directorypath" → 添加 hint "请输入目录路径"
        - format: "sample-table" → 添加 hint "请输入样本表路径"

        Returns:
            JSON Schema object，格式: {"type": "object", "properties": {...}, "required": [...]}
        """
```

### 1.3 Updated _check_explicit_exec_params

Replace hardcoded check with dynamic schema lookup:

```python
async def _check_explicit_exec_params(
    task: TaskNode,
    context: Dict[str, Any],
    skill_registry: Optional[SkillParameterRegistry] = None
) -> ProbingRequest:
    # Phase 1: 如果有 skill_id 且 skill_registry 可用，动态拉取参数 schema
    skill_id = task.parameters.get("skill_id")
    if skill_id and skill_registry:
        schema = await skill_registry.get_parameters_schema(skill_id)
        if schema and schema.get("required"):
            # 检查 task.parameters 中是否包含所有 required 参数
            missing = [p for p in schema["required"] if not task.parameters.get(p)]
            if missing:
                ui_schema = await skill_registry.build_ui_schema(skill_id, missing)
                return ProbingRequest(
                    is_missing=True,
                    missing_params=missing,
                    ui_schema=ui_schema,
                    message_to_user=f"执行技能 {skill_id} 需要补充以下参数："
                )
            # 所有必填参数已齐备，放行
            return ProbingRequest(is_missing=False, missing_params=[], ui_schema={}, message_to_user="")

    # Phase 2 (fallback): 无 skill_id 或 skill_registry 不可用时，使用通用必填参数检查
    required_keys = ["species", "input_file"]
    merged_params = {**task.parameters, **_enrich_from_context(context)}
    missing = [key for key in required_keys if key not in merged_params or not merged_params[key]]
    if missing:
        ui_schema = _build_fallback_ui_schema(missing)
        return ProbingRequest(
            is_missing=True,
            missing_params=missing,
            ui_schema=ui_schema,
            message_to_user="执行分析需要补充以下核心参数，请确认："
        )
    return ProbingRequest(is_missing=False, missing_params=[], ui_schema={}, message_to_user="")
```

### 1.4 Extended PROBING_INTENTS

```python
PROBING_INTENTS = {
    IntentType.EXPLICIT_EXEC,      # 技能执行：检查 skill schema required 参数
    IntentType.SKILL_FORGE,        # 代码锻造：宽松检查（允许示例数据替代）
    IntentType.DATA_PROBE,         # 数据探查：检查 input_file / active_file
    IntentType.LITERATURE_MINING,  # 文献挖掘：检查 pdf_file / doi
}
```

New check functions:

```python
async def _check_data_probe_params(task, context) -> ProbingRequest:
    """数据探查需要文件目标"""
    has_file = task.parameters.get("input_file") or context.get("active_file")
    if not has_file:
        return ProbingRequest(
            is_missing=True,
            missing_params=["input_file"],
            ui_schema={
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "title": "数据文件路径",
                        "format": "filepath"
                    }
                },
                "required": ["input_file"]
            },
            message_to_user="数据探查需要指定目标文件，请选择或输入文件路径："
        )
    return ProbingRequest(is_missing=False, missing_params=[], ui_schema={}, message_to_user="")

async def _check_literature_params(task, context) -> ProbingRequest:
    """文献挖掘需要文档目标"""
    has_doc = (task.parameters.get("pdf_file") or task.parameters.get("doi")
               or context.get("active_file"))
    if not has_doc:
        return ProbingRequest(
            is_missing=True,
            missing_params=["pdf_file"],
            ui_schema={
                "type": "object",
                "properties": {
                    "pdf_file": {
                        "type": "string",
                        "title": "文献文件 (PDF)",
                        "format": "filepath"
                    },
                    "doi": {
                        "type": "string",
                        "title": "DOI 链接 (可选)"
                    }
                },
                "required": ["pdf_file"]
            },
            message_to_user="文献挖掘需要指定目标文献，请上传或输入文件路径："
        )
    return ProbingRequest(is_missing=False, missing_params=[], ui_schema={}, message_to_user="")
```

### 1.5 Updated check_task_parameters

```python
async def check_task_parameters(
    task: TaskNode,
    context: Dict[str, Any],
    skill_registry: Optional[SkillParameterRegistry] = None
) -> ProbingRequest:
    if task.intent == IntentType.EXPLICIT_EXEC:
        return await _check_explicit_exec_params(task, context, skill_registry)
    elif task.intent == IntentType.SKILL_FORGE:
        return await _check_skill_forge_params(task, context)
    elif task.intent == IntentType.DATA_PROBE:
        return await _check_data_probe_params(task, context)
    elif task.intent == IntentType.LITERATURE_MINING:
        return await _check_literature_params(task, context)
    # 其他意图无需参数探查
    return ProbingRequest(is_missing=False, missing_params=[], ui_schema={}, message_to_user="")
```

### 1.6 Updated IntentRouterEngine

In `engine.py`, create `SkillParameterRegistry` in `__init__` and pass to `check_task_parameters`:

```python
class IntentRouterEngine:
    def __init__(self, session, user_id: str):
        self.l0_engine = L0RuleEngine()
        self.classifier = L1Classifier(session, user_id)
        self._skill_registry = SkillParameterRegistry(session, user_id)
        log.info(f"[Router] 初始化引擎: user_id={user_id}, skill_registry=enabled")

    async def route(self, query: str, context: Dict[str, Any]) -> RouteResult:
        # L0: 规则拦截
        l0_result = self.l0_engine.evaluate(query, context)
        if l0_result:
            dag = TaskDAG(nodes=[TaskNode(
                task_id="task_1",
                intent=l0_result.intent,
                raw_instruction=query,
                entities=l0_result.entities,
                skill_id=l0_result.skill_id,
            )])
            return RouteResult(dag=dag, probing=None)

        # L1: DAG 解构
        dag = await self.classifier.decompose(query, context)

        # L2: 参数探查（仅检查第一个任务节点）
        if dag.nodes:
            probing = await check_task_parameters(
                task=dag.nodes[0],
                context=context,
                skill_registry=self._skill_registry
            )
            return RouteResult(dag=dag, probing=probing if probing.is_missing else None)

        return RouteResult(dag=dag, probing=None)
```

---

## 2. L1 Decomposer Enhancement

### 2.1 Current State

- `workspace_context` injected as `str(context)` — unstructured
- No coreference resolution rules in prompt
- LLM has no guidance for resolving "this file", "that result"

### 2.2 WorkspaceContext Typed Model

**Add to:** `autonome-backend/app/agent/router/schemas.py`

```python
class WorkspaceContext(BaseModel):
    """结构化工作区上下文，供 L1 解构器消费"""
    active_file: Optional[str] = Field(None, description="当前打开的文件路径或 ID")
    active_file_type: Optional[str] = Field(None, description="文件类型 (h5ad, csv, fastq, bam, etc.)")
    recent_files: List[Dict[str, str]] = Field(default_factory=list, description="最近使用的文件 [{id, name, type}]")
    active_skills: List[Dict[str, str]] = Field(default_factory=list, description="工作区中可用的技能 [{id, name, category}]")
    last_execution_status: Optional[str] = Field(None, description="上次执行状态 (success/failed)")
    last_execution_result: Optional[str] = Field(None, description="上次执行结果摘要")
    workspace_summary: Optional[str] = Field(None, description="工作区自然语言摘要")
```

### 2.3 Context Builder

**New file:** `autonome-backend/app/agent/router/context_builder.py`

```python
def build_workspace_context(context: Dict[str, Any]) -> WorkspaceContext:
    """从原始前端上下文字典构建结构化 WorkspaceContext"""

    # 提取活跃文件
    active_file = context.get("active_file")
    active_file_type = _infer_file_type(active_file) if active_file else None

    # 提取最近文件列表
    context_files = context.get("context_files", [])
    recent_files = [
        {"id": f.get("id", ""), "name": f.get("name", ""), "type": _infer_file_type(f.get("name", ""))}
        for f in context_files
    ] if isinstance(context_files, list) else []

    # 提取可用技能
    available_skills = context.get("available_skills", [])
    active_skills = [
        {"id": s.get("id", ""), "name": s.get("name", ""), "category": s.get("category", "")}
        for s in available_skills
    ] if isinstance(available_skills, list) else []

    # 提取上次执行结果
    last_execution_status = context.get("last_execution_status")
    last_execution_result = context.get("last_execution_result")

    # 生成工作区摘要
    workspace_summary = _generate_summary(active_file, recent_files, active_skills, last_execution_status)

    return WorkspaceContext(
        active_file=active_file,
        active_file_type=active_file_type,
        recent_files=recent_files[:10],  # 限制最多 10 个
        active_skills=active_skills[:10],
        last_execution_status=last_execution_status,
        last_execution_result=str(last_execution_result)[:200] if last_execution_result else None,
        workspace_summary=workspace_summary
    )

def format_workspace_context_for_prompt(ws: WorkspaceContext) -> str:
    """将 WorkspaceContext 格式化为 L1 提示词中的结构化文本"""

    sections = []

    # 活跃文件
    if ws.active_file:
        file_info = f"- 文件: {ws.active_file}"
        if ws.active_file_type:
            file_info += f" (类型: {ws.active_file_type})"
        sections.append(f"### 当前活跃文件\n{file_info}")

    # 最近文件列表
    if ws.recent_files:
        files_str = "\n".join(f"  - {f['name']} (ID: {f['id']}, 类型: {f['type']})" for f in ws.recent_files)
        sections.append(f"### 最近文件列表\n{files_str}")

    # 可用技能
    if ws.active_skills:
        skills_str = "\n".join(f"  - {s['name']} (ID: {s['id']}, 分类: {s['category']})" for s in ws.active_skills)
        sections.append(f"### 可用技能\n{skills_str}")

    # 上次执行结果
    if ws.last_execution_status:
        result_str = f"- 状态: {ws.last_execution_status}"
        if ws.last_execution_result:
            result_str += f"\n- 摘要: {ws.last_execution_result}"
        sections.append(f"### 上次执行结果\n{result_str}")

    # 工作区摘要
    if ws.workspace_summary:
        sections.append(f"### 工作区摘要\n{ws.workspace_summary}")

    if not sections:
        return "无可用上下文"

    return "\n\n".join(sections)

def _infer_file_type(filename: str) -> str:
    """从文件名推断类型"""
    if not filename:
        return "unknown"
    ext_map = {
        ".h5ad": "AnnData", ".csv": "CSV", ".tsv": "TSV", ".txt": "TXT",
        ".fastq": "FASTQ", ".fq": "FASTQ", ".bam": "BAM", ".sam": "SAM",
        ".bed": "BED", ".gff": "GFF", ".gtf": "GTF", ".fa": "FASTA",
        ".fasta": "FASTA", ".pdf": "PDF", ".rds": "RDS", ".mtx": "MTX",
    }
    for ext, ftype in ext_map.items():
        if filename.lower().endswith(ext):
            return ftype
    return "unknown"

def _generate_summary(active_file, recent_files, active_skills, last_status) -> str:
    """生成工作区自然语言摘要"""
    parts = []
    if active_file:
        parts.append(f"用户正在查看 {active_file}")
    if recent_files:
        parts.append(f"工作区有 {len(recent_files)} 个文件")
    if active_skills:
        parts.append(f"有 {len(active_skills)} 个可用技能")
    if last_status == "failed":
        parts.append("上次执行失败，可能需要诊断")
    return "；".join(parts) if parts else ""
```

### 2.4 Updated L1 Prompt Template

Add coreference resolution rules to `L1_DECOMPOSER_PROMPT_TEMPLATE`:

```
## 指代消解规则 (Coreference Resolution)

当用户输入包含指代词时，必须将其映射到工作区上下文中的具体实体，并填入 resolved_assets：

| 指代词模式 | 映射目标 | resolved_assets 填写 |
|-----------|---------|---------------------|
| "这个文件"、"这个数据"、"它" | 当前活跃文件 | [active_file ID] |
| "上面的结果"、"上次的结果" | 上次执行结果 | [result ID] |
| "那个技能"、"XX技能" | 可用技能中匹配项 | [skill_id] |
| "左侧文件"、"文件列表中的XX" | 最近文件中匹配项 | [file_id] |

**关键约束**：
1. 如果指代词可以消解，必须在 resolved_assets 中填入具体的 ID
2. 如果指代词无法消解（上下文中无匹配实体），保留 raw_instruction 中的原始指代词，不要猜测或编造 ID
3. 多个指代词指向同一实体时，resolved_assets 中只保留一个 ID
```

### 2.5 Updated L1Classifier.decompose()

Replace `workspace_context = str(context) if context else "无可用上下文"` with:

```python
from app.agent.router.context_builder import build_workspace_context, format_workspace_context_for_prompt

# In decompose():
ws_ctx = build_workspace_context(context or {})
workspace_context = format_workspace_context_for_prompt(ws_ctx)
```

Apply the same change in `_decompose_with_json_mode()`.

---

## 3. Frontend Active Probing E2E Verification and Fixes

### 3.1 Fix useChat Configuration

**File:** `autonome-studio/src/components/chat/ChatStage.tsx`

Add `maxSteps: 5` to the `useChat` configuration. After `addToolResult` is called, the SDK needs to continue the conversation loop to process the tool result and resume the LangGraph state machine.

```tsx
const { messages, addToolResult, ... } = useChat({
  api: '/api/chat',
  maxSteps: 5,
  body: { session_id: currentSessionId },
  onFinish: (message) => { /* existing finish handler */ },
  onError: (error) => { /* existing error handler */ },
})
```

### 3.2 Add Submit Loading State

**File:** `autonome-studio/src/components/chat/ParameterProbingCard.tsx`

- Add `isSubmitting` boolean state
- Set to `true` when form is submitted
- Disable submit button and show spinner when `isSubmitting`
- The parent component (MemoizedMessageItem) can also check the tool invocation state to infer loading

```tsx
const [isSubmitting, setIsSubmitting] = useState(false)

const handleSubmit = (e: React.FormEvent) => {
  e.preventDefault()
  setIsSubmitting(true)
  onSubmit(values)
  // Note: isSubmitting will be reset when the tool invocation state changes
  // to "output-available" or "output-error" in the parent component
}
```

### 3.3 Fix History Message Reconstruction

**File:** `autonome-studio/src/components/chat/ChatStage.tsx`

When loading historical messages from the backend API, tool invocation parts are not reconstructed. The `setAiMessages` call only creates text parts from content.

- After loading historical messages, check if any backend message has `tool_calls` metadata
- If present, reconstruct tool invocation parts for rendering
- This ensures the "参数已补全" indicator appears for historical sessions

### 3.4 Fix syncFromUseChat Preservation

**File:** `autonome-studio/src/store/useChatStore.ts`

In the `syncFromUseChat` merge logic, preserve `toolInvocationParts`:

```typescript
// When merging messages, preserve toolInvocationParts from either source
const merged = {
  ...existing,
  ...incoming,
  toolInvocationParts: incoming.toolInvocationParts ?? existing.toolInvocationParts,
  thinkingContent: incoming.thinkingContent ?? existing.thinkingContent,
  attachments: incoming.attachments ?? existing.attachments,
}
```

### 3.5 E2E Test Flow

Manual verification of the complete Active Probing flow:

1. **Trigger**: User sends "运行 FastQC 对 sample.fastq 进行质量控制"
2. **L0/L1 Routing**: Routes to `EXPLICIT_EXEC` intent
3. **L2 Detection**: Detects missing parameters (dynamic from SKILL.md or fallback species/input_file)
4. **Backend SSE**: Sends `request_parameters` tool call event with JSON Schema
5. **Frontend Render**: `ParameterProbingCard` renders form with species dropdown and file input
6. **User Fills**: User selects species and enters file path
7. **Submit**: User clicks "确认并继续执行", `addToolResult` sends data back
8. **Loading State**: Submit button shows loading indicator
9. **Backend Resume**: Backend processes tool result, resumes LangGraph
10. **Completion**: Frontend shows "参数已补全" green checkmark
11. **Execution**: Backend continues to execute the skill

---

## File Structure

### New Files
- `autonome-backend/app/services/skill_parameter_registry.py` — SkillParameterRegistry service
- `autonome-backend/app/agent/router/context_builder.py` — WorkspaceContext builder + formatter

### Modified Files
- `autonome-backend/app/agent/router/l2_extractor.py` — Dynamic schema lookup, extended PROBING_INTENTS
- `autonome-backend/app/agent/router/engine.py` — Create SkillParameterRegistry in __init__
- `autonome-backend/app/agent/router/schemas.py` — Add WorkspaceContext model
- `autonome-backend/app/agent/router/l1_classifier.py` — Structured context + coreference rules
- `autonome-studio/src/components/chat/ChatStage.tsx` — maxSteps + history reconstruction
- `autonome-studio/src/components/chat/ParameterProbingCard.tsx` — Submit loading state
- `autonome-studio/src/store/useChatStore.ts` — syncFromUseChat preservation

### Unchanged Files
- `autonome-backend/app/agent/router/l0_rules.py`
- `autonome-backend/app/agent/graph.py`
- All 6 stub nodes in `autonome-backend/app/agent/nodes/`
- `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` (no changes needed)
- `autonome-studio/src/components/chat/VirtualizedMessageList.tsx` (no changes needed)
