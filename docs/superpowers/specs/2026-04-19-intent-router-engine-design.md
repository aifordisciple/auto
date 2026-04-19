# Intent Router Engine 2.0 Design

> Date: 2026-04-19
> Status: Approved
> Scope: Full replacement of existing SkillMatcher + LangGraph orchestration

## 1. Overview

Replace the current keyword-only intent recognition (`SkillMatcher`) with a multi-stage funnel architecture: **L0 (Rule Interception) + L1 (LLM Structured Classification) + L2 (Slot Extraction)**. Integrate with a LangGraph `StateGraph` to route messages to specialized Agent nodes.

### Problem Statement

- Current `SkillMatcher` is purely keyword-based with no LLM semantic understanding
- Intent results are only used for prompt selection (2 prompts), matched skills are discarded
- No LangGraph orchestration graph exists; no multi-Agent routing
- Literature Agent is orphaned (never called from chat flow)
- Blueprint execution is broken

### Design Goals

1. **Low latency**: L0 rule interception at 0ms for ~30-40% of requests
2. **High accuracy**: L1 LLM classification for semantic understanding
3. **Slot filling**: L2 extracts entities/parameters for downstream Agents
4. **User-configurable models**: Reuse existing `get_llm_config()` 3-tier config chain
5. **Proactive follow-up**: Intercept missing parameters before waking expensive Agents

## 2. Intent Classification Schema

**File:** `app/agent/router/schemas.py`

### IntentType Enum (6 categories)

| Intent | Description | L0 Catchable? | L2 Needed? |
|--------|-------------|---------------|------------|
| `chat` | General Q&A, concept explanation | Yes (chitchat) | No |
| `skill_forge` | Generate/execute analysis code | Partially (codegen patterns) | Yes |
| `explicit_skill` | User directly specifies a skill ID | Yes (skill name/ID in query) | Yes |
| `diagnostic` | Error diagnosis, environment issues | Yes (error patterns, failed status) | No |
| `literature` | Literature/DOI/paper reproduction | Yes (DOI, PDF upload) | No |
| `data_probe` | Data preview/inspection | Partially (probe keywords + file type) | Yes |

### IntentExtraction Model

```python
class IntentExtraction(BaseModel):
    intent: IntentType
    confidence: float          # 0.0-1.0
    entities: Dict[str, str]   # Extracted bio entities
    skill_id: Optional[str]    # Only for explicit_skill
    requires_followup: bool
    followup_question: Optional[str]
    # routing_target is computed by engine, not by LLM
    # Mapping: chat→chat_node, skill_forge→skill_forge_node, etc.
```

**Note:** `routing_target` is a computed field derived from `intent` by the engine, not output by the LLM. The mapping is:
- `chat` → `chat_node`
- `skill_forge` → `skill_forge_node`
- `explicit_skill` → `explicit_skill_node`
- `diagnostic` → `diagnostic_node`
- `literature` → `literature_node`
- `data_probe` → `data_probe_node`

### SlotExtraction Model (L2 Output)

```python
class SlotExtraction(BaseModel):
    """L2 槽位提取结果，与 IntentExtraction.entities 合并"""
    slots: Dict[str, str]      # Extracted slot key-value pairs
    missing_slots: List[str]   # Required but unfilled slot names
    context_enrichments: Dict[str, str]  # Auto-filled from workspace context
```

### AgentState (LangGraph)

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], "Message history"]
    context: Dict[str, Any]           # Workspace context from frontend
    intent_data: Optional[Dict]       # IntentExtraction result
    skill_id: Optional[str]           # Matched skill ID
    execution_result: Optional[Dict]  # Execution result
```

## 3. L0 Rule Interception Layer

**File:** `app/agent/router/l0_rules.py`

### Architecture

Rules are registered as an ordered list of `Rule` instances, evaluated by priority. First match wins; unmatched queries fall through to L1.

```python
class Rule(ABC):
    @abstractmethod
    def evaluate(self, query: str, context: Dict) -> Optional[IntentExtraction]: ...
```

### Rule Priority Order

| Priority | Rule | Trigger | Intent |
|----------|------|---------|--------|
| 1 | `SystemStateRule` | `last_execution_status=failed` in context | `diagnostic` |
| 2 | `ActiveViewRule` | `active_view=literature_upload` in context | `literature` |
| 3 | `ExplicitSkillRule` | Skill name/ID in query or `skill_id` in context | `explicit_skill` |
| 4 | `ErrorPatternRule` | Regex: error/exception/报错/失败 | `diagnostic` |
| 5 | `LiteraturePatternRule` | DOI, PDF, 论文/文献 keywords | `literature` |
| 6 | `ProbePatternRule` | 查看/预览/结构 + file type context | `data_probe` |
| 7 | `CodeGenPatternRule` | 写代码/跑流程/分析 keywords | `skill_forge` |
| 8 | `ChitchatRule` | Greetings, thanks, short non-technical input | `chat` |

### Key Design Decisions

- **Not migrating** old `skill_matcher_config.py` (620 lines of synonyms/weights). L1 LLM provides semantic understanding natively.
- L0 rules are **intent-centric** (coarse-grained, fast), not skill-centric (fine-grained, slow).
- Each rule is an independent class for testability and extensibility.
- Expected L0 hit rate: ~30-40% of requests.

## 4. L1 LLM Classification Layer

**File:** `app/agent/router/l1_classifier.py`

### Model Configuration

**No hardcoded models.** Reuses the existing 3-tier config chain via `get_llm_config(session, user_id)`:

1. **User override** (User model: `llm_api_key`, `llm_base_url`, `llm_model_name`)
2. **System config** (SystemConfig DB row: `openai_api_key`, `openai_base_url`, `default_model`)
3. **Environment variables** (.env fallback)

### Dual-Mode Classification

```python
class L1Classifier:
    def __init__(self, session: AsyncSession, user_id: str):
        self.llm_config = get_llm_config(session, user_id)
        self.is_local = _is_local_model(self.llm_config.base_url)

    async def classify(self, query: str, context: Dict) -> IntentExtraction:
        if self.is_local:
            # Ollama: JSON mode + manual parsing (no function calling support)
            return await self._classify_with_json_mode(query, context)
        else:
            # Third-party API: with_structured_output (function calling)
            return await self._classify_with_structured_output(query, context)
```

### Confidence Threshold

- Default: 0.7
- Below threshold: degrade to `chat` intent (safe fallback)
- On LLM failure: return `chat` with confidence 0.0

### System Prompt

Focused on 6-intent classification with context-aware analysis. Instructs the model to:
- Consider workspace context (active file, UI state)
- Extract bio entities (gene names, tools, thresholds)
- Detect missing parameters for `skill_forge`/`explicit_skill`
- Set `requires_followup=True` when critical parameters are missing

## 5. L2 Slot Extraction Layer

**File:** `app/agent/router/l2_extractor.py`

### Independent from L1

L2 is a separate class invoked after L1 classification. It uses intent-specific prompts for targeted entity extraction.

### Intent-Specific Extraction

| Intent | Extraction Focus | Example Entities |
|--------|-----------------|------------------|
| `skill_forge` | Analysis type, input data, parameters | `analysis_type: "DEG"`, `input_file: "matrix.h5ad"` |
| `explicit_skill` | Skill parameters from SKILL.md schema | Skill-specific params |
| `data_probe` | File path, inspection type | `file_path: "/workspace/data.h5ad"`, `probe_type: "structure"` |
| `chat` | None (skip) | - |
| `diagnostic` | None (skip) | - |
| `literature` | None (skip) | - |

### Context Enrichment

L2 also enriches entities from workspace context:
- If `context.active_file` exists and intent needs input data, auto-inject as `input_file`
- If `context.selected_cells` exists, inject as `cell_count`

### Latency Impact

- L0 hit: 0ms
- L1 only (chat/diagnostic/literature): ~200ms
- L1 + L2 (skill_forge/explicit_skill/data_probe): ~400ms
- Only 30-40% of requests need L2

## 6. Orchestration Engine

**File:** `app/agent/router/engine.py`

```python
# Intent → Node mapping (computed, not from LLM)
INTENT_NODE_MAP = {
    IntentType.CHAT: "chat_node",
    IntentType.SKILL_FORGE: "skill_forge_node",
    IntentType.EXPLICIT_SKILL: "explicit_skill_node",
    IntentType.DIAGNOSTIC: "diagnostic_node",
    IntentType.LITERATURE: "literature_node",
    IntentType.DATA_PROBE: "data_probe_node",
}

class IntentRouterEngine:
    def __init__(self, session: AsyncSession, user_id: str):
        self.l0 = L0RuleEngine()
        self.l1 = L1Classifier(session, user_id)
        self.l2 = L2SlotExtractor()
        self.confidence_threshold = 0.7

    async def route(self, query: str, context: Dict) -> IntentExtraction:
        # Step 1: L0 fast interception
        result = self.l0.evaluate(query, context)
        if result:
            result.routing_target = INTENT_NODE_MAP[result.intent]
            return result

        # Step 2: L1 LLM classification
        result = await self.l1.classify(query, context)

        # Step 3: L2 slot extraction (only for intents that need it)
        if result.intent in (IntentType.SKILL_FORGE, IntentType.EXPLICIT_SKILL, IntentType.DATA_PROBE):
            slot_result = await self.l2.extract(query, context, result.intent, self.l1.primary_llm)
            result.entities = {**result.entities, **slot_result.slots, **slot_result.context_enrichments}

        # Step 4: Confidence degradation
        if result.confidence < self.confidence_threshold:
            result.intent = IntentType.CHAT

        # Step 5: Compute routing target
        result.routing_target = INTENT_NODE_MAP[result.intent]

        return result
```

## 7. LangGraph Orchestration

**File:** `app/agent/graph.py`

### Graph Structure

```
[Entry] → intent_router_node → conditional_edge → chat_node → END
                                           ├→ skill_forge_node → END
                                           ├→ explicit_skill_node → END
                                           ├→ diagnostic_node → END
                                           ├→ literature_node → END
                                           └→ data_probe_node → END
```

### Entry Node: intent_router_node

`session` and `user_id` are injected via LangGraph's `configurable` mechanism:

```python
async def intent_router_node(state: AgentState, config: RunnableConfig):
    query = state["messages"][-1].content
    context = state.get("context", {})

    # Injected via graph.invoke(state, config={"configurable": {"session": ..., "user_id": ...}})
    session = config["configurable"]["session"]
    user_id = config["configurable"]["user_id"]

    engine = IntentRouterEngine(session, user_id)
    intent_result = await engine.route(query, context)

    # Follow-up interception: don't wake expensive Agents
    if intent_result.requires_followup and intent_result.followup_question:
        return {
            "messages": [AIMessage(content=intent_result.followup_question)],
            "intent_data": intent_result.model_dump()
        }

    return {"intent_data": intent_result.model_dump()}
```

### Conditional Edge: route_by_intent

```python
def route_by_intent(state: AgentState) -> str:
    intent_data = state.get("intent_data", {})
    if intent_data.get("requires_followup"):
        return END
    return intent_data.get("routing_target", "chat_node")
```

### Integration with chat.py

Current `chat_stream()` directly calls `ChatOpenAI.astream()`. After refactoring:

1. `chat_stream()` creates `IntentRouterEngine(session, user_id)`
2. Builds LangGraph graph, injects `AgentState`
3. Graph executes; `intent_router_node` classifies and routes
4. `chat_node` uses existing `ChatOpenAI.astream()` logic
5. `skill_forge_node` invokes `SkillExecutor`
6. `explicit_skill_node` invokes matched skill directly
7. `diagnostic_node` uses error analysis prompt
8. `literature_node` wraps existing `literature_agent.py`
9. `data_probe_node` invokes `probe_tools.py`

## 8. Agent Node Responsibilities

| Node | Responsibility | Core Dependency | Output |
|------|---------------|-----------------|--------|
| `chat_node` | General conversation, concept explanation | `ChatOpenAI.astream()` | SSE streaming text |
| `skill_forge_node` | Generate/execute analysis code | `SkillExecutor` + Docker sandbox | Code + execution result |
| `explicit_skill_node` | Execute specified skill | `SkillExecutor` + SKILL.md | Skill execution result |
| `diagnostic_node` | Error diagnosis and fix | Error analysis prompt + sandbox | Fix suggestion/code |
| `literature_node` | Literature parsing/reproduction | `literature_agent.py` | Literature summary/method |
| `data_probe_node` | Data preview/inspection | `probe_tools.py` | Data structure/stats |

## 9. Migration Plan

### Phase 1: Intent Engine Core (This Implementation)

- Create `app/agent/router/` directory with L0/L1/L2/engine/schemas
- Create `app/agent/graph.py` LangGraph orchestration
- Create `app/agent/nodes/` with Agent node skeletons
- Modify `chat.py` to integrate new intent engine

### Phase 2: Agent Node Implementation (Follow-up)

- Implement full logic for each Agent node
- Integrate `SkillExecutor`, `probe_tools`, `literature_agent`

### Phase 3: Legacy Cleanup (Follow-up)

- Deprecate old `SkillMatcher`, delete dead code
- Remove `skill_matcher_config.py`, `skill_keywords_indexer.py`
- Remove `skill_matcher_with_fallback.py` (already dead code)

### Files to Deprecate

| File | Reason |
|------|--------|
| `app/services/skill_matcher.py` | Replaced by `IntentRouterEngine` |
| `app/services/skill_matcher_config.py` | Replaced by `L0RuleEngine` |
| `app/services/skill_keywords_indexer.py` | Replaced by L1 LLM semantic understanding |
| `app/services/skill_matcher_with_fallback.py` | Already dead code |

### Files to Preserve

| File | Reason |
|------|--------|
| `app/services/skill_executor.py` | Called by `skill_forge_node` and `explicit_skill_node` |
| `app/tools/probe_tools.py` | Called by `data_probe_node` |
| `app/agent/literature_agent.py` | Wrapped by `literature_node` |
| `app/utils/llm_config.py` | Reused by `L1Classifier` |

## 10. File Structure

```
app/agent/
  router/
    __init__.py
    schemas.py          # IntentType, IntentExtraction, AgentState
    engine.py           # IntentRouterEngine orchestrator
    l0_rules.py         # L0 rule interception layer
    l1_classifier.py    # L1 LLM classification layer
    l2_extractor.py     # L2 slot extraction layer
  graph.py              # LangGraph StateGraph orchestration
  nodes/
    __init__.py
    chat_node.py        # General conversation node
    skill_forge_node.py # Code generation/execution node
    explicit_skill_node.py # Skill execution node
    diagnostic_node.py  # Error diagnosis node
    literature_node.py  # Literature parsing node
    data_probe_node.py  # Data inspection node
  literature_agent.py   # Preserved, wrapped by literature_node
```

## 11. Key Design Decisions

1. **L0 re-designed from scratch** - Not migrating 620 lines of keyword config; L1 LLM provides semantic understanding natively
2. **L2 independent from L1** - Different intents need different extraction strategies; chat/diagnostic/literature skip L2 entirely
3. **Model from user config** - No hardcoded model names; reuses `get_llm_config()` 3-tier chain (User → SystemConfig → .env)
4. **Dual-mode L1** - Local models (Ollama) use JSON mode; third-party APIs use structured output (function calling)
5. **6 intents** - Including `explicit_skill` to preserve the "user directly specifies skill" semantic from old `IntentType.EXPLICIT_SKILL`
6. **Follow-up interception** - Missing parameters caught at router level, saving expensive Agent invocations
7. **Phased migration** - Phase 1 builds core, Phase 2 fills nodes, Phase 3 cleans legacy
