# Intent Router Engine 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the keyword-only SkillMatcher with a multi-stage L0+L1+L2 intent router and LangGraph orchestration graph for multi-Agent routing.

**Architecture:** L0 (rule interception, 0ms) → L1 (LLM structured classification via user-configured model) → L2 (intent-specific slot extraction). Results drive a LangGraph StateGraph with conditional edges to 6 Agent nodes.

**Tech Stack:** Python 3.11, LangGraph 1.1.x, LangChain 1.2.x, Pydantic v2, Loguru, FastAPI SSE

---

## File Structure

### New Files (Create)

| File | Responsibility |
|------|---------------|
| `app/agent/router/__init__.py` | Package init, re-exports |
| `app/agent/router/schemas.py` | IntentType enum, IntentExtraction, SlotExtraction, AgentState |
| `app/agent/router/l0_rules.py` | L0 rule engine: Rule ABC + 8 concrete rules |
| `app/agent/router/l1_classifier.py` | L1 LLM classifier: dual-mode (local JSON / API structured output) |
| `app/agent/router/l2_extractor.py` | L2 slot extractor: intent-specific prompts + context enrichment |
| `app/agent/router/engine.py` | IntentRouterEngine orchestrator: L0→L1→L2 pipeline |
| `app/agent/graph.py` | LangGraph StateGraph: intent_router_node + conditional edges |
| `app/agent/nodes/__init__.py` | Package init |
| `app/agent/nodes/chat_node.py` | Chat node: existing ChatOpenAI.astream() logic |
| `app/agent/nodes/skill_forge_node.py` | Skill forge node: code generation + SkillExecutor |
| `app/agent/nodes/explicit_skill_node.py` | Explicit skill node: direct SkillExecutor invocation |
| `app/agent/nodes/diagnostic_node.py` | Diagnostic node: error analysis prompt |
| `app/agent/nodes/literature_node.py` | Literature node: wraps literature_agent.py |
| `app/agent/nodes/data_probe_node.py` | Data probe node: invokes probe_tools |
| `tests/test_intent_router/` | Test directory |
| `tests/test_intent_router/test_schemas.py` | Schema validation tests |
| `tests/test_intent_router/test_l0_rules.py` | L0 rule engine tests |
| `tests/test_intent_router/test_l1_classifier.py` | L1 classifier tests |
| `tests/test_intent_router/test_l2_extractor.py` | L2 extractor tests |
| `tests/test_intent_router/test_engine.py` | Engine orchestrator tests |
| `tests/test_intent_router/test_graph.py` | LangGraph graph tests |

### Modified Files

| File | Change |
|------|--------|
| `autonome-backend/requirements.txt` | Add `langgraph>=0.2.0` explicit dependency |
| `autonome-backend/app/api/routes/chat.py` | Replace SkillMatcher with IntentRouterEngine, integrate LangGraph graph |

---

## Task 1: Add langgraph to requirements.txt

**Files:**
- Modify: `autonome-backend/requirements.txt`

- [ ] **Step 1: Add langgraph explicit dependency**

Add `langgraph>=0.2.0` and `langgraph-prebuilt>=0.1.0` to requirements.txt after the langchain entries:

```
langgraph>=0.2.0
langgraph-prebuilt>=0.1.0
```

- [ ] **Step 2: Rebuild Docker image to pick up new deps**

Run: `docker-compose build --no-cache backend-api && docker-compose up -d backend-api`

- [ ] **Step 3: Verify langgraph version in container**

Run: `docker-compose exec backend-api pip show langgraph`
Expected: Version >= 0.2.0

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/requirements.txt
git commit -m "feat: add langgraph explicit dependency for Intent Router Engine 2.0"
```

---

## Task 2: Create Intent Router Schemas

**Files:**
- Create: `autonome-backend/app/agent/router/__init__.py`
- Create: `autonome-backend/app/agent/router/schemas.py`
- Create: `tests/test_intent_router/__init__.py`
- Create: `tests/test_intent_router/test_schemas.py`

- [ ] **Step 1: Write failing tests for schemas**

```python
# tests/test_intent_router/test_schemas.py
import pytest
from app.agent.router.schemas import (
    IntentType, IntentExtraction, SlotExtraction, AgentState,
    INTENT_NODE_MAP
)


class TestIntentType:
    """意图类型枚举测试"""

    def test_has_six_intents(self):
        assert len(IntentType) == 6

    def test_intent_values(self):
        assert IntentType.CHAT == "chat"
        assert IntentType.SKILL_FORGE == "skill_forge"
        assert IntentType.EXPLICIT_SKILL == "explicit_skill"
        assert IntentType.DIAGNOSTIC == "diagnostic"
        assert IntentType.LITERATURE == "literature"
        assert IntentType.DATA_PROBE == "data_probe"


class TestIntentExtraction:
    """意图提取结果模型测试"""

    def test_valid_minimal(self):
        result = IntentExtraction(
            intent=IntentType.CHAT,
            confidence=0.9,
            entities={},
            requires_followup=False
        )
        assert result.intent == IntentType.CHAT
        assert result.confidence == 0.9
        assert result.skill_id is None
        assert result.followup_question is None

    def test_with_entities(self):
        result = IntentExtraction(
            intent=IntentType.SKILL_FORGE,
            confidence=0.85,
            entities={"gene": "TP53", "tool": "Seurat"},
            requires_followup=True,
            followup_question="请提供输入文件路径"
        )
        assert result.entities["gene"] == "TP53"
        assert result.requires_followup is True

    def test_confidence_bounds(self):
        # confidence 必须在 0.0-1.0 之间
        with pytest.raises(Exception):
            IntentExtraction(
                intent=IntentType.CHAT,
                confidence=1.5,
                entities={},
                requires_followup=False
            )
        with pytest.raises(Exception):
            IntentExtraction(
                intent=IntentType.CHAT,
                confidence=-0.1,
                entities={},
                requires_followup=False
            )

    def test_explicit_skill_has_skill_id(self):
        result = IntentExtraction(
            intent=IntentType.EXPLICIT_SKILL,
            confidence=0.95,
            entities={},
            requires_followup=False,
            skill_id="scrna_qc"
        )
        assert result.skill_id == "scrna_qc"


class TestSlotExtraction:
    """槽位提取结果模型测试"""

    def test_valid_slot_extraction(self):
        result = SlotExtraction(
            slots={"analysis_type": "DEG"},
            missing_slots=["input_file"],
            context_enrichments={"input_file": "/workspace/matrix.h5ad"}
        )
        assert "analysis_type" in result.slots
        assert "input_file" in result.missing_slots

    def test_empty_defaults(self):
        result = SlotExtraction()
        assert result.slots == {}
        assert result.missing_slots == []
        assert result.context_enrichments == {}


class TestIntentNodeMap:
    """意图到节点的映射测试"""

    def test_all_intents_mapped(self):
        """每个 IntentType 都有对应的节点映射"""
        for intent in IntentType:
            assert intent in INTENT_NODE_MAP, f"{intent} 未映射到任何节点"

    def test_node_names_valid(self):
        """映射的节点名称都以 _node 结尾"""
        for intent, node in INTENT_NODE_MAP.items():
            assert node.endswith("_node"), f"{intent} 映射到 {node}，不以 _node 结尾"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_schemas.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'app.agent.router'`

- [ ] **Step 3: Create router package and schemas**

```python
# app/agent/router/__init__.py
"""意图识别引擎 2.0 - L0+L1+L2 漏斗式架构"""
from app.agent.router.schemas import IntentType, IntentExtraction, SlotExtraction, AgentState, INTENT_NODE_MAP

__all__ = [
    "IntentType", "IntentExtraction", "SlotExtraction", "AgentState", "INTENT_NODE_MAP"
]
```

```python
# app/agent/router/schemas.py
"""
意图识别引擎 2.0 数据结构定义。

包含意图类型枚举、提取结果模型、槽位提取模型和 LangGraph 状态定义。
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Annotated

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class IntentType(str, Enum):
    """
    意图类型枚举 - 6 种核心意图分类。

    每种意图对应一个下游 Agent 节点，通过 INTENT_NODE_MAP 映射。
    """
    CHAT = "chat"                      # 通用闲聊、概念解释
    SKILL_FORGE = "skill_forge"        # 生成/执行分析代码
    EXPLICIT_SKILL = "explicit_skill"  # 用户直接指定技能 ID
    DIAGNOSTIC = "diagnostic"          # 报错/环境问题诊断
    LITERATURE = "literature"          # 文献/DOI/论文复现
    DATA_PROBE = "data_probe"          # 数据预览/探查


# 意图 → LangGraph 节点映射（引擎计算，不由 LLM 输出）
INTENT_NODE_MAP: Dict[IntentType, str] = {
    IntentType.CHAT: "chat_node",
    IntentType.SKILL_FORGE: "skill_forge_node",
    IntentType.EXPLICIT_SKILL: "explicit_skill_node",
    IntentType.DIAGNOSTIC: "diagnostic_node",
    IntentType.LITERATURE: "literature_node",
    IntentType.DATA_PROBE: "data_probe_node",
}


class IntentExtraction(BaseModel):
    """
    意图提取结果 - L1 LLM 结构化输出的目标格式。

    下游 LangGraph 节点根据此结果进行确定性路由。
    """
    intent: IntentType = Field(
        description="识别出的核心意图分类"
    )
    confidence: float = Field(
        description="意图识别的置信度 (0.0 到 1.0 之间)",
        ge=0.0,
        le=1.0
    )
    entities: Dict[str, str] = Field(
        default_factory=dict,
        description="从用户输入中提取的生信实体或关键参数"
    )
    skill_id: Optional[str] = Field(
        default=None,
        description="仅 explicit_skill 意图时有值，表示用户指定的技能 ID"
    )
    requires_followup: bool = Field(
        default=False,
        description="是否需要向用户追问缺失的必要参数"
    )
    followup_question: Optional[str] = Field(
        default=None,
        description="如果 requires_followup 为 true，提供追问话术"
    )
    routing_target: Optional[str] = Field(
        default=None,
        description="目标 Agent 节点名，由引擎根据 intent 计算"
    )


class SlotExtraction(BaseModel):
    """
    L2 槽位提取结果。

    slots: LLM 提取的参数键值对
    missing_slots: 必需但未填充的参数名列表
    context_enrichments: 从工作区上下文自动填充的参数
    """
    slots: Dict[str, str] = Field(
        default_factory=dict,
        description="LLM 提取的槽位键值对"
    )
    missing_slots: List[str] = Field(
        default_factory=list,
        description="必需但未填充的参数名"
    )
    context_enrichments: Dict[str, str] = Field(
        default_factory=dict,
        description="从工作区上下文自动填充的参数"
    )


class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态。

    在意图路由节点和各 Agent 节点之间传递。
    """
    messages: Annotated[Sequence[BaseMessage], "消息历史"]
    context: Dict[str, Any]            # 前端注入的工作区上下文
    intent_data: Optional[Dict]        # IntentExtraction 序列化结果
    skill_id: Optional[str]            # 匹配到的技能 ID
    execution_result: Optional[Dict]   # 执行结果
```

- [ ] **Step 4: Create test __init__.py**

```python
# tests/test_intent_router/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_schemas.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/router/ autonome-backend/tests/test_intent_router/
git commit -m "feat: add Intent Router Engine 2.0 schemas (IntentType, IntentExtraction, SlotExtraction, AgentState)"
```

---

## Task 3: Create L0 Rule Interception Layer

**Files:**
- Create: `autonome-backend/app/agent/router/l0_rules.py`
- Create: `tests/test_intent_router/test_l0_rules.py`

- [ ] **Step 1: Write failing tests for L0 rules**

```python
# tests/test_intent_router/test_l0_rules.py
import pytest
from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.schemas import IntentType, IntentExtraction


class TestL0RuleEngine:
    """L0 规则拦截层测试"""

    def setup_method(self):
        self.engine = L0RuleEngine()

    # --- SystemStateRule (Priority 1) ---
    def test_failed_execution_status_routes_diagnostic(self):
        """上下文中 last_execution_status=failed 直接路由到 diagnostic"""
        result = self.engine.evaluate("帮我看看", {"last_execution_status": "failed"})
        assert result is not None
        assert result.intent == IntentType.DIAGNOSTIC
        assert result.confidence == 1.0

    # --- ActiveViewRule (Priority 2) ---
    def test_literature_upload_view_routes_literature(self):
        """上下文中 active_view=literature_upload 路由到 literature"""
        result = self.engine.evaluate("上传文件", {"active_view": "literature_upload"})
        assert result is not None
        assert result.intent == IntentType.LITERATURE

    # --- ExplicitSkillRule (Priority 3) ---
    def test_skill_id_in_context_routes_explicit_skill(self):
        """上下文中包含 skill_id 路由到 explicit_skill"""
        result = self.engine.evaluate("执行分析", {"skill_id": "scrna_qc"})
        assert result is not None
        assert result.intent == IntentType.EXPLICIT_SKILL
        assert result.skill_id == "scrna_qc"

    def test_skill_keyword_in_query(self):
        """查询中包含"用XX技能"路由到 explicit_skill"""
        result = self.engine.evaluate("用单细胞质控技能", {})
        assert result is not None
        assert result.intent == IntentType.EXPLICIT_SKILL

    # --- ErrorPatternRule (Priority 4) ---
    def test_error_keyword_routes_diagnostic(self):
        """查询中包含 error/报错 关键词路由到 diagnostic"""
        result = self.engine.evaluate("运行报错了", {})
        assert result is not None
        assert result.intent == IntentType.DIAGNOSTIC

    def test_exception_keyword_routes_diagnostic(self):
        result = self.engine.evaluate("出现了 exception", {})
        assert result is not None
        assert result.intent == IntentType.DIAGNOSTIC

    # --- LiteraturePatternRule (Priority 5) ---
    def test_doi_routes_literature(self):
        """查询中包含 DOI 路由到 literature"""
        result = self.engine.evaluate("帮我看看 https://doi.org/10.1038/s41592-024-02202-x", {})
        assert result is not None
        assert result.intent == IntentType.LITERATURE

    def test_literature_keyword_routes_literature(self):
        """查询中包含"论文/文献"路由到 literature"""
        result = self.engine.evaluate("复现这篇论文的方法", {})
        assert result is not None
        assert result.intent == IntentType.LITERATURE

    # --- ProbePatternRule (Priority 6) ---
    def test_probe_keyword_with_file_routes_data_probe(self):
        """查询中包含"查看/预览"且有文件上下文路由到 data_probe"""
        result = self.engine.evaluate("查看数据结构", {"active_file": "matrix.h5ad"})
        assert result is not None
        assert result.intent == IntentType.DATA_PROBE

    # --- CodeGenPatternRule (Priority 7) ---
    def test_codegen_keyword_routes_skill_forge(self):
        """查询中包含"写代码/跑流程"路由到 skill_forge"""
        result = self.engine.evaluate("帮我写一个差异分析脚本", {})
        assert result is not None
        assert result.intent == IntentType.SKILL_FORGE

    def test_analysis_keyword_routes_skill_forge(self):
        """查询中包含"做分析/跑分析"路由到 skill_forge"""
        result = self.engine.evaluate("跑一下聚类分析", {})
        assert result is not None
        assert result.intent == IntentType.SKILL_FORGE

    # --- ChitchatRule (Priority 8) ---
    def test_greeting_routes_chat(self):
        """问候语路由到 chat"""
        result = self.engine.evaluate("你好", {})
        assert result is not None
        assert result.intent == IntentType.CHAT

    def test_thanks_routes_chat(self):
        """感谢路由到 chat"""
        result = self.engine.evaluate("谢谢", {})
        assert result is not None
        assert result.intent == IntentType.CHAT

    # --- Fallthrough ---
    def test_ambiguous_query_returns_none(self):
        """模糊查询不命中任何规则，返回 None 放行至 L1"""
        result = self.engine.evaluate("TP53 在乳腺癌中的突变频率", {})
        assert result is None

    def test_short_technical_query_returns_none(self):
        """短技术查询不命中规则，返回 None"""
        result = self.engine.evaluate("Seurat", {})
        assert result is None

    # --- Priority ordering ---
    def test_system_state_overrides_error_keyword(self):
        """系统状态规则优先于关键词规则"""
        # last_execution_status=failed 应该优先命中 SystemStateRule
        result = self.engine.evaluate("报错了", {"last_execution_status": "failed"})
        assert result is not None
        assert result.intent == IntentType.DIAGNOSTIC
        assert result.confidence == 1.0  # SystemStateRule 给 1.0

    def test_explicit_skill_overrides_codegen(self):
        """显式技能规则优先于代码生成规则"""
        result = self.engine.evaluate("用质控技能处理数据", {})
        assert result is not None
        assert result.intent == IntentType.EXPLICIT_SKILL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l0_rules.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'app.agent.router.l0_rules'`

- [ ] **Step 3: Implement L0 rule engine**

```python
# app/agent/router/l0_rules.py
"""
L0 规则拦截层 - 零成本极速意图分发。

通过检测系统级特征和关键词模式，以 0 token 成本完成意图拦截。
未命中任何规则的查询返回 None，放行至 L1 LLM 分类层。

规则按优先级顺序执行，首个命中即返回。
"""
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.agent.router.schemas import IntentExtraction, IntentType
from app.core.logger import log


class Rule(ABC):
    """规则基类 - 每条规则独立实现评估逻辑"""

    @abstractmethod
    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        """
        评估查询是否命中此规则。

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            命中返回 IntentExtraction，未命中返回 None
        """
        ...


class SystemStateRule(Rule):
    """
    优先级 1: 系统状态拦截。

    当上下文存在明确的沙箱报错退出码时，直接路由至诊断，
    置信度 1.0（确定性状态，无需 LLM 确认）。
    """

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if context.get("last_execution_status") == "failed":
            log.debug("[L0] SystemStateRule 命中: last_execution_status=failed")
            return IntentExtraction(
                intent=IntentType.DIAGNOSTIC,
                confidence=1.0,
                entities={"error_source": "execution_failure"},
                requires_followup=False
            )
        return None


class ActiveViewRule(Rule):
    """
    优先级 2: 活跃视图拦截。

    当前端 UI 状态表明用户正在执行特定操作时（如文献上传），
    直接路由到对应意图。
    """

    # 视图 → 意图映射
    VIEW_INTENT_MAP = {
        "literature_upload": IntentType.LITERATURE,
    }

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        active_view = context.get("active_view")
        if active_view and active_view in self.VIEW_INTENT_MAP:
            intent = self.VIEW_INTENT_MAP[active_view]
            log.debug(f"[L0] ActiveViewRule 命中: active_view={active_view}")
            return IntentExtraction(
                intent=intent,
                confidence=0.95,
                entities={},
                requires_followup=False
            )
        return None


class ExplicitSkillRule(Rule):
    """
    优先级 3: 显式技能调用拦截。

    检测上下文中的 skill_id 或查询中的"用XX技能"模式。
    """

    # 匹配"用XX技能"模式的中英文关键词
    SKILL_TRIGGER_PATTERNS = re.compile(
        r'(?:用|使用|调用|执行|运行|run|use|invoke)\s*\S+\s*(?:技能|skill)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        # 检查上下文中的 skill_id
        skill_id = context.get("skill_id")
        if skill_id:
            log.debug(f"[L0] ExplicitSkillRule 命中: skill_id={skill_id}")
            return IntentExtraction(
                intent=IntentType.EXPLICIT_SKILL,
                confidence=0.95,
                entities={"skill_id": skill_id},
                skill_id=skill_id,
                requires_followup=False
            )

        # 检查查询中的"用XX技能"模式
        if self.SKILL_TRIGGER_PATTERNS.search(query):
            log.debug("[L0] ExplicitSkillRule 命中: 技能触发模式")
            return IntentExtraction(
                intent=IntentType.EXPLICIT_SKILL,
                confidence=0.90,
                entities={},
                requires_followup=False
            )

        return None


class ErrorPatternRule(Rule):
    """
    优先级 4: 错误关键词模式拦截。

    检测中英文错误关键词，路由到诊断意图。
    """

    ERROR_PATTERN = re.compile(
        r'(error|exception|报错|失败|出错|failed|traceback|bug|崩溃|crash)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.ERROR_PATTERN.search(query):
            log.debug("[L0] ErrorPatternRule 命中")
            return IntentExtraction(
                intent=IntentType.DIAGNOSTIC,
                confidence=0.90,
                entities={"error_type": "keyword_detected"},
                requires_followup=False
            )
        return None


class LiteraturePatternRule(Rule):
    """
    优先级 5: 文献模式拦截。

    检测 DOI 链接、PDF 上传、论文/文献关键词。
    """

    DOI_PATTERN = re.compile(r'doi\.org|doi:', re.IGNORECASE)
    LITERATURE_KEYWORDS = re.compile(r'(论文|文献|paper|article|复现|reproduce)', re.IGNORECASE)

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.DOI_PATTERN.search(query) or self.LITERATURE_KEYWORDS.search(query):
            log.debug("[L0] LiteraturePatternRule 命中")
            return IntentExtraction(
                intent=IntentType.LITERATURE,
                confidence=0.90,
                entities={},
                requires_followup=False
            )
        return None


class ProbePatternRule(Rule):
    """
    优先级 6: 数据探查模式拦截。

    检测"查看/预览/结构"等探查关键词，且上下文中存在活跃文件时路由到 data_probe。
    仅在有文件上下文时触发，避免将纯概念问题误判为数据探查。
    """

    PROBE_KEYWORDS = re.compile(
        r'(查看|预览|看看|结构|统计|inspect|preview|peek|scan|查看数据|数据结构)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        has_file_context = bool(context.get("active_file") or context.get("context_files"))
        if self.PROBE_KEYWORDS.search(query) and has_file_context:
            active_file = context.get("active_file", "")
            log.debug(f"[L0] ProbePatternRule 命中: active_file={active_file}")
            return IntentExtraction(
                intent=IntentType.DATA_PROBE,
                confidence=0.85,
                entities={"input_file": active_file} if active_file else {},
                requires_followup=False
            )
        return None


class CodeGenPatternRule(Rule):
    """
    优先级 7: 代码生成模式拦截。

    检测"写代码/跑流程/做分析"等代码生成关键词。
    """

    CODEGEN_PATTERN = re.compile(
        r'(写|编写|生成|跑|运行|执行|做|进行)\s*(?:代码|脚本|流程|分析|pipeline|code|script)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.CODEGEN_PATTERN.search(query):
            log.debug("[L0] CodeGenPatternRule 命中")
            return IntentExtraction(
                intent=IntentType.SKILL_FORGE,
                confidence=0.80,
                entities={},
                requires_followup=False
            )
        return None


class ChitchatRule(Rule):
    """
    优先级 8: 闲聊拦截。

    检测问候语、感谢等短文本，路由到 chat。
    仅匹配短文本（<=10 字符）或明确的社交用语。
    """

    CHITCHAT_PATTERN = re.compile(
        r'^(你好|hello|hi|hey|谢谢|感谢|thanks|thank you|好的|ok|okay|嗯|是|否|对|不)$',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        stripped = query.strip()
        # 短文本（<=10 字符）且匹配社交用语模式
        if len(stripped) <= 10 and self.CHITCHAT_PATTERN.match(stripped):
            log.debug("[L0] ChitchatRule 命中")
            return IntentExtraction(
                intent=IntentType.CHAT,
                confidence=0.90,
                entities={},
                requires_followup=False
            )
        return None


class L0RuleEngine:
    """
    L0 规则拦截引擎。

    按优先级依次评估规则列表，首个命中即返回。
    未命中返回 None，放行至 L1 LLM 分类层。
    """

    def __init__(self):
        self.rules: List[Rule] = [
            SystemStateRule(),    # 优先级 1: 系统状态
            ActiveViewRule(),     # 优先级 2: 活跃视图
            ExplicitSkillRule(),  # 优先级 3: 显式技能
            ErrorPatternRule(),   # 优先级 4: 错误关键词
            LiteraturePatternRule(),  # 优先级 5: 文献模式
            ProbePatternRule(),   # 优先级 6: 数据探查
            CodeGenPatternRule(), # 优先级 7: 代码生成
            ChitchatRule(),       # 优先级 8: 闲聊
        ]

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        """
        按优先级依次评估规则，首个命中即返回。

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            命中返回 IntentExtraction，未命中返回 None
        """
        for rule in self.rules:
            result = rule.evaluate(query, context)
            if result is not None:
                return result
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l0_rules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/agent/router/l0_rules.py autonome-backend/tests/test_intent_router/test_l0_rules.py
git commit -m "feat: add L0 rule interception layer (8 rules, priority-ordered)"
```

---

## Task 4: Create L1 LLM Classification Layer

**Files:**
- Create: `autonome-backend/app/agent/router/l1_classifier.py`
- Create: `tests/test_intent_router/test_l1_classifier.py`

- [ ] **Step 1: Write failing tests for L1 classifier**

```python
# tests/test_intent_router/test_l1_classifier.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.schemas import IntentType, IntentExtraction


class TestL1Classifier:
    """L1 LLM 分类层测试"""

    def test_init_with_local_model(self):
        """本地模型（Ollama）初始化时 is_local=True"""
        with patch("app.agent.router.l1_classifier.get_llm_config") as mock_config:
            mock_config.return_value = MagicMock(
                api_key="",
                base_url="http://host.docker.internal:11434/v1",
                model_name="qwen2.5:7b",
                source="system"
            )
            classifier = L1Classifier(session=MagicMock(), user_id="test")
            assert classifier.is_local is True

    def test_init_with_remote_model(self):
        """远程 API 初始化时 is_local=False"""
        with patch("app.agent.router.l1_classifier.get_llm_config") as mock_config:
            mock_config.return_value = MagicMock(
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
                model_name="gpt-4o",
                source="user"
            )
            classifier = L1Classifier(session=MagicMock(), user_id="test")
            assert classifier.is_local is False

    @pytest.mark.asyncio
    async def test_classify_returns_intent_extraction(self):
        """classify 方法返回 IntentExtraction 实例"""
        with patch("app.agent.router.l1_classifier.get_llm_config") as mock_config:
            mock_config.return_value = MagicMock(
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
                model_name="gpt-4o",
                source="user"
            )
            classifier = L1Classifier(session=MagicMock(), user_id="test")

            # Mock LLM 调用
            mock_result = IntentExtraction(
                intent=IntentType.SKILL_FORGE,
                confidence=0.85,
                entities={"tool": "Seurat"},
                requires_followup=False
            )
            classifier._invoke_structured = AsyncMock(return_value=mock_result)

            result = await classifier.classify("帮我做单细胞分析", {})
            assert isinstance(result, IntentExtraction)
            assert result.intent == IntentType.SKILL_FORGE

    @pytest.mark.asyncio
    async def test_classify_fallback_on_failure(self):
        """LLM 调用失败时降级为 chat"""
        with patch("app.agent.router.l1_classifier.get_llm_config") as mock_config:
            mock_config.return_value = MagicMock(
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
                model_name="gpt-4o",
                source="user"
            )
            classifier = L1Classifier(session=MagicMock(), user_id="test")
            classifier._invoke_structured = AsyncMock(side_effect=Exception("API error"))

            result = await classifier.classify("任何查询", {})
            assert result.intent == IntentType.CHAT
            assert result.confidence == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l1_classifier.py -v`
Expected: FAIL - `ModuleNotFoundError`

- [ ] **Step 3: Implement L1 classifier**

```python
# app/agent/router/l1_classifier.py
"""
L1 LLM 分类层 - 大模型结构化意图分类。

使用用户配置的 LLM（通过 get_llm_config 三级 fallback 解析），
以结构化输出方式完成意图分类和初步实体提取。

双模式：
- 本地模型（Ollama）: JSON mode + 手动解析
- 第三方 API: with_structured_output (function calling)
"""
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.agent.router.schemas import IntentExtraction, IntentType
from app.core.logger import log
from app.utils.llm_config import get_llm_config, _is_local_model


# L1 意图分类系统提示词
INTENT_CLASSIFICATION_PROMPT = """你是一个生物信息学 IDE (Autonome Studio) 的中央路由网关。
你的任务是根据用户的输入和当前工作区上下文，精准分类用户的意图，并提取关键的生物学或工程参数。

可选的意图分类：
1. 'diagnostic': 用户遇到代码报错，或者请求修复 bug、环境配置问题。
2. 'literature': 用户提供文献/DOI，或请求复现某篇论文的方法论和图表。
3. 'data_probe': 用户请求查看、预览、统计当前的数据集特征（如 h5ad 结构、fastq 质量）。
4. 'skill_forge': 用户要求生成、编写、修改或执行生信分析代码/Pipeline，或者生成特定的分析图表。
5. 'explicit_skill': 用户直接指定了某个技能的名称或 ID 来执行。
6. 'chat': 通用的闲聊、基础概念解释，不涉及直接的代码生成或系统操作。

分析规则：
- 结合用户提供的 Context（当前选中的文件、UI 状态）进行综合判断。
- 提取明确提及的生信实体（基因名、算法包、阈值参数）。
- 如果用户要求执行分析（skill_forge），但明显缺失关键输入数据或必要参数，将 requires_followup 设为 true，并提供 followup_question。
- 保持客观和科学严谨，禁止主观臆测。
- confidence 反映你对意图判断的确信程度，0.0 表示完全不确定，1.0 表示绝对确定。"""


class L1Classifier:
    """
    L1 LLM 结构化意图分类器。

    从用户中心配置解析 LLM，支持本地模型和第三方 API 双模式。
    """

    def __init__(self, session, user_id: str):
        """
        初始化分类器。

        Args:
            session: 数据库会话（用于 get_llm_config 解析用户配置）
            user_id: 当前用户 ID
        """
        self.llm_config = get_llm_config(session, user_id)
        self.is_local = _is_local_model(self.llm_config.base_url)
        self.confidence_threshold = 0.7

        # 构建 LLM 实例
        api_key = self.llm_config.api_key or "not-needed"
        self.primary_llm = ChatOpenAI(
            api_key=api_key,
            base_url=self.llm_config.base_url,
            model=self.llm_config.model_name,
            temperature=0.0
        )

        # 构建提示词模板
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", INTENT_CLASSIFICATION_PROMPT),
            ("human", "Context (Workspace State): {context}\n\nUser Query: {query}")
        ])

        log.info(
            f"[L1] 初始化分类器: model={self.llm_config.model_name}, "
            f"base_url={self.llm_config.base_url}, is_local={self.is_local}, "
            f"source={self.llm_config.source}"
        )

    async def classify(self, query: str, context: Dict[str, Any]) -> IntentExtraction:
        """
        执行意图分类。

        Args:
            query: 用户自然语言输入
            context: 工作区上下文

        Returns:
            IntentExtraction: 结构化意图提取结果
        """
        log.info(f"[L1] 正在调用 LLM 分类: query='{query[:50]}...'")

        try:
            if self.is_local:
                result = await self._classify_with_json_mode(query, context)
            else:
                result = await self._classify_with_structured_output(query, context)

            # 置信度降级保护
            if result.confidence < self.confidence_threshold:
                log.warning(f"[L1] 置信度过低 ({result.confidence})，降级为 chat")
                result.intent = IntentType.CHAT

            return result

        except Exception as e:
            log.error(f"[L1] 分类失败: {str(e)}")
            return IntentExtraction(
                intent=IntentType.CHAT,
                confidence=0.0,
                entities={},
                requires_followup=False
            )

    async def _classify_with_structured_output(
        self, query: str, context: Dict[str, Any]
    ) -> IntentExtraction:
        """第三方 API 模式：使用 with_structured_output (function calling)"""
        llm_with_schema = self.primary_llm.with_structured_output(IntentExtraction)
        chain = self.prompt_template | llm_with_schema
        result = await chain.ainvoke({
            "context": str(context),
            "query": query
        })
        return result

    async def _classify_with_json_mode(
        self, query: str, context: Dict[str, Any]
    ) -> IntentExtraction:
        """
        本地模型模式：JSON mode + 手动解析。

        Ollama 等本地模型不一定支持 function calling，
        使用 JSON mode 强制输出 JSON，然后手动解析为 IntentExtraction。
        """
        # 在提示词中追加 JSON 格式要求
        json_instruction = (
            "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
            '{"intent": "chat|skill_forge|explicit_skill|diagnostic|literature|data_probe", '
            '"confidence": 0.0-1.0, '
            '"entities": {"key": "value"}, '
            '"skill_id": null, '
            '"requires_followup": false, '
            '"followup_question": null}'
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_CLASSIFICATION_PROMPT + json_instruction),
            ("human", "Context (Workspace State): {context}\n\nUser Query: {query}")
        ])

        chain = prompt | self.primary_llm
        raw_response = await chain.ainvoke({
            "context": str(context),
            "query": query
        })

        # 手动解析 JSON 响应为 IntentExtraction
        try:
            import json
            from json_repair import repair_json

            repaired = repair_json(raw_response.content)
            parsed = json.loads(repaired)
            return IntentExtraction(**parsed)
        except Exception as parse_err:
            log.warning(f"[L1] JSON 解析失败: {parse_err}, 原始响应: {raw_response.content[:200]}")
            # 尝试从响应中提取意图关键词作为兜底
            return self._fallback_intent_from_text(raw_response.content)

    def _fallback_intent_from_text(self, text: str) -> IntentExtraction:
        """从 LLM 原始文本响应中提取意图（JSON 解析失败时的兜底）"""
        text_lower = text.lower()
        for intent in IntentType:
            if intent.value in text_lower:
                return IntentExtraction(
                    intent=intent,
                    confidence=0.5,
                    entities={},
                    requires_followup=False
                )
        return IntentExtraction(
            intent=IntentType.CHAT,
            confidence=0.3,
            entities={},
            requires_followup=False
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l1_classifier.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/agent/router/l1_classifier.py autonome-backend/tests/test_intent_router/test_l1_classifier.py
git commit -m "feat: add L1 LLM classification layer (dual-mode: local JSON / API structured output)"
```

---

## Task 5: Create L2 Slot Extraction Layer

**Files:**
- Create: `autonome-backend/app/agent/router/l2_extractor.py`
- Create: `tests/test_intent_router/test_l2_extractor.py`

- [ ] **Step 1: Write failing tests for L2 extractor**

```python
# tests/test_intent_router/test_l2_extractor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agent.router.l2_extractor import L2SlotExtractor
from app.agent.router.schemas import IntentType, SlotExtraction


class TestL2SlotExtractor:
    """L2 槽位提取层测试"""

    def setup_method(self):
        self.extractor = L2SlotExtractor()

    def test_skip_for_chat_intent(self):
        """chat 意图不需要 L2 提取"""
        assert IntentType.CHAT not in L2SlotExtractor.EXTRACTION_INTENTS

    def test_skip_for_diagnostic_intent(self):
        """diagnostic 意图不需要 L2 提取"""
        assert IntentType.DIAGNOSTIC not in L2SlotExtractor.EXTRACTION_INTENTS

    def test_skip_for_literature_intent(self):
        """literature 意图不需要 L2 提取"""
        assert IntentType.LITERATURE not in L2SlotExtractor.EXTRACTION_INTENTS

    def test_needed_for_skill_forge(self):
        """skill_forge 需要 L2 提取"""
        assert IntentType.SKILL_FORGE in L2SlotExtractor.EXTRACTION_INTENTS

    def test_needed_for_explicit_skill(self):
        """explicit_skill 需要 L2 提取"""
        assert IntentType.EXPLICIT_SKILL in L2SlotExtractor.EXTRACTION_INTENTS

    def test_needed_for_data_probe(self):
        """data_probe 需要 L2 提取"""
        assert IntentType.DATA_PROBE in L2SlotExtractor.EXTRACTION_INTENTS

    def test_context_enrichment_with_active_file(self):
        """上下文中存在 active_file 时自动注入为 input_file"""
        enrichments = self.extractor._enrich_from_context(
            IntentType.SKILL_FORGE,
            {"active_file": "matrix.h5ad", "selected_cells": 2000}
        )
        assert enrichments.get("input_file") == "matrix.h5ad"
        assert enrichments.get("cell_count") == "2000"

    def test_context_enrichment_without_active_file(self):
        """无 active_file 时不注入"""
        enrichments = self.extractor._enrich_from_context(
            IntentType.CHAT,
            {}
        )
        assert "input_file" not in enrichments

    @pytest.mark.asyncio
    async def test_extract_returns_slot_extraction(self):
        """extract 方法返回 SlotExtraction 实例"""
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        # Mock chain invoke
        mock_result = SlotExtraction(
            slots={"analysis_type": "DEG"},
            missing_slots=["input_file"],
            context_enrichments={}
        )
        self.extractor._invoke_extraction = AsyncMock(return_value=mock_result)

        result = await self.extractor.extract(
            "做差异分析", {"active_file": "data.h5ad"},
            IntentType.SKILL_FORGE, mock_llm
        )
        assert isinstance(result, SlotExtraction)
        assert "analysis_type" in result.slots
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l2_extractor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement L2 extractor**

```python
# app/agent/router/l2_extractor.py
"""
L2 槽位提取层 - 意图针对性的参数提取。

在 L1 分类完成后独立调用，针对不同意图使用不同的提取策略：
- skill_forge: 提取分析类型、输入数据、参数
- explicit_skill: 提取技能参数（从 SKILL.md schema）
- data_probe: 提取文件路径、探查类型

chat/diagnostic/literature 跳过 L2，节省延迟。
"""
from typing import Any, Dict, Set

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.agent.router.schemas import IntentType, SlotExtraction
from app.core.logger import log


# 各意图的槽位提取提示词
SKILL_FORGE_EXTRACTION_PROMPT = """你是一个生信分析参数提取器。从用户查询和工作区上下文中提取以下参数：

- analysis_type: 分析类型（如 DEG, clustering, trajectory, annotation 等）
- input_file: 输入数据文件路径
- tool: 使用的分析工具/包（如 Seurat, Scanpy, Monocle3 等）
- species: 物种（如 human, mouse）
- any other relevant parameters

如果某个必需参数在查询中未明确提及，将其加入 missing_slots。

请以 JSON 格式输出：{{"slots": {{"key": "value"}}, "missing_slots": ["param1"], "context_enrichments": {{}}}}"""

DATA_PROBE_EXTRACTION_PROMPT = """你是一个数据探查参数提取器。从用户查询和工作区上下文中提取以下参数：

- file_path: 要探查的数据文件路径
- probe_type: 探查类型（如 structure, quality, statistics, preview 等）
- file_format: 文件格式（如 h5ad, fastq, bam, csv 等）

请以 JSON 格式输出：{{"slots": {{"key": "value"}}, "missing_slots": ["param1"], "context_enrichments": {{}}}}"""

EXPLICIT_SKILL_EXTRACTION_PROMPT = """你是一个技能参数提取器。从用户查询中提取技能执行所需的参数。

根据技能的参数定义，从用户输入中提取对应的值。未提及的必需参数加入 missing_slots。

请以 JSON 格式输出：{{"slots": {{"key": "value"}}, "missing_slots": ["param1"], "context_enrichments": {{}}}}"""


class L2SlotExtractor:
    """
    L2 槽位提取器。

    仅对需要深度参数提取的意图执行，其余跳过。
    """

    # 需要 L2 提取的意图集合
    EXTRACTION_INTENTS: Set[IntentType] = {
        IntentType.SKILL_FORGE,
        IntentType.EXPLICIT_SKILL,
        IntentType.DATA_PROBE,
    }

    # 意图 → 提取提示词映射
    EXTRACTION_PROMPTS = {
        IntentType.SKILL_FORGE: SKILL_FORGE_EXTRACTION_PROMPT,
        IntentType.EXPLICIT_SKILL: EXPLICIT_SKILL_EXTRACTION_PROMPT,
        IntentType.DATA_PROBE: DATA_PROBE_EXTRACTION_PROMPT,
    }

    async def extract(
        self,
        query: str,
        context: Dict[str, Any],
        intent: IntentType,
        llm: ChatOpenAI
    ) -> SlotExtraction:
        """
        执行槽位提取。

        Args:
            query: 用户查询
            context: 工作区上下文
            intent: L1 分类结果
            llm: LLM 实例（复用 L1 的 LLM）

        Returns:
            SlotExtraction: 槽位提取结果
        """
        if intent not in self.EXTRACTION_INTENTS:
            return SlotExtraction()

        log.info(f"[L2] 正在提取 {intent.value} 意图的槽位...")

        try:
            # 1. 从工作区上下文自动填充
            context_enrichments = self._enrich_from_context(intent, context)

            # 2. LLM 提取槽位
            prompt_text = self.EXTRACTION_PROMPTS[intent]
            prompt = ChatPromptTemplate.from_messages([
                ("system", prompt_text),
                ("human", "Context: {context}\n\nUser Query: {query}")
            ])

            chain = prompt | llm
            raw_response = await chain.ainvoke({
                "context": str(context),
                "query": query
            })

            # 3. 解析 LLM 响应为 SlotExtraction
            slots_result = self._parse_extraction_response(raw_response.content)

            # 4. 合并上下文自动填充
            slots_result.context_enrichments = context_enrichments

            return slots_result

        except Exception as e:
            log.error(f"[L2] 槽位提取失败: {str(e)}")
            # 返回仅包含上下文填充的结果
            return SlotExtraction(
                slots={},
                missing_slots=[],
                context_enrichments=self._enrich_from_context(intent, context)
            )

    def _enrich_from_context(
        self, intent: IntentType, context: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        从工作区上下文自动填充参数。

        当上下文中存在 active_file 时，自动注入为 input_file。
        当存在 selected_cells 时，注入为 cell_count。
        """
        enrichments: Dict[str, str] = {}

        # 需要输入数据的意图才自动注入文件
        if intent in (IntentType.SKILL_FORGE, IntentType.EXPLICIT_SKILL, IntentType.DATA_PROBE):
            active_file = context.get("active_file")
            if active_file:
                enrichments["input_file"] = active_file

            selected_cells = context.get("selected_cells")
            if selected_cells:
                enrichments["cell_count"] = str(selected_cells)

        return enrichments

    def _parse_extraction_response(self, raw_content: str) -> SlotExtraction:
        """解析 LLM 原始响应为 SlotExtraction"""
        try:
            import json
            from json_repair import repair_json

            repaired = repair_json(raw_content)
            parsed = json.loads(repaired)
            return SlotExtraction(**parsed)
        except Exception as e:
            log.warning(f"[L2] 响应解析失败: {e}")
            return SlotExtraction()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_l2_extractor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/agent/router/l2_extractor.py autonome-backend/tests/test_intent_router/test_l2_extractor.py
git commit -m "feat: add L2 slot extraction layer (intent-specific prompts + context enrichment)"
```

---

## Task 6: Create Intent Router Engine (Orchestrator)

**Files:**
- Create: `autonome-backend/app/agent/router/engine.py`
- Create: `tests/test_intent_router/test_engine.py`

- [ ] **Step 1: Write failing tests for engine**

```python
# tests/test_intent_router/test_engine.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.router.engine import IntentRouterEngine, INTENT_NODE_MAP
from app.agent.router.schemas import IntentType, IntentExtraction, SlotExtraction


class TestIntentRouterEngine:
    """意图路由编排引擎测试"""

    @pytest.mark.asyncio
    async def test_l0_hit_skips_l1_and_l2(self):
        """L0 命中时跳过 L1 和 L2"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        # L0 应该命中 ErrorPatternRule
        result = await engine.route("运行报错了", {})
        assert result.intent == IntentType.DIAGNOSTIC
        assert result.routing_target == "diagnostic_node"

    @pytest.mark.asyncio
    async def test_l0_hit_sets_routing_target(self):
        """L0 命中时自动计算 routing_target"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        result = await engine.route("你好", {})
        assert result.intent == IntentType.CHAT
        assert result.routing_target == "chat_node"

    @pytest.mark.asyncio
    async def test_l1_called_when_l0_miss(self):
        """L0 未命中时调用 L1"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        # Mock L1 返回结果
        l1_result = IntentExtraction(
            intent=IntentType.SKILL_FORGE,
            confidence=0.85,
            entities={"tool": "Seurat"},
            requires_followup=False
        )
        engine.l1.classify = AsyncMock(return_value=l1_result)
        # Mock L2 返回空结果
        engine.l2.extract = AsyncMock(return_value=SlotExtraction())

        result = await engine.route("Seurat 标准流程", {})
        assert result.intent == IntentType.SKILL_FORGE
        assert result.routing_target == "skill_forge_node"
        engine.l1.classify.assert_called_once()

    @pytest.mark.asyncio
    async def test_l2_called_for_skill_forge(self):
        """skill_forge 意图触发 L2 槽位提取"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        l1_result = IntentExtraction(
            intent=IntentType.SKILL_FORGE,
            confidence=0.85,
            entities={},
            requires_followup=False
        )
        engine.l1.classify = AsyncMock(return_value=l1_result)
        engine.l2.extract = AsyncMock(return_value=SlotExtraction(
            slots={"analysis_type": "QC"},
            context_enrichments={"input_file": "data.h5ad"}
        ))

        result = await engine.route("做质控", {"active_file": "data.h5ad"})
        engine.l2.extract.assert_called_once()
        assert "analysis_type" in result.entities
        assert "input_file" in result.entities

    @pytest.mark.asyncio
    async def test_l2_skipped_for_chat(self):
        """chat 意图跳过 L2"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        l1_result = IntentExtraction(
            intent=IntentType.CHAT,
            confidence=0.9,
            entities={},
            requires_followup=False
        )
        engine.l1.classify = AsyncMock(return_value=l1_result)

        result = await engine.route("什么是单细胞测序", {})
        engine.l2.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_degrades_to_chat(self):
        """低置信度降级为 chat"""
        engine = IntentRouterEngine(session=MagicMock(), user_id="test")

        l1_result = IntentExtraction(
            intent=IntentType.SKILL_FORGE,
            confidence=0.3,  # 低于阈值 0.7
            entities={},
            requires_followup=False
        )
        engine.l1.classify = AsyncMock(return_value=l1_result)

        result = await engine.route("模糊的查询", {})
        assert result.intent == IntentType.CHAT
        assert result.routing_target == "chat_node"

    @pytest.mark.asyncio
    async def test_intent_node_map_complete(self):
        """所有意图都有节点映射"""
        for intent in IntentType:
            assert intent in INTENT_NODE_MAP
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement engine**

```python
# app/agent/router/engine.py
"""
意图路由编排引擎 - 组合 L0/L1/L2 的漏斗式管道。

执行流程：
1. L0 规则拦截（0ms，~30-40% 命中率）
2. L1 LLM 结构化分类（~200ms）
3. L2 槽位提取（~200ms，仅 skill_forge/explicit_skill/data_probe）
4. 置信度降级保护
5. 计算 routing_target
"""
from typing import Any, Dict

from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.l2_extractor import L2SlotExtractor
from app.agent.router.schemas import IntentExtraction, IntentType, INTENT_NODE_MAP
from app.core.logger import log


class IntentRouterEngine:
    """
    意图路由编排引擎。

    组合 L0 规则拦截、L1 LLM 分类、L2 槽位提取三层，
    输出结构化的 IntentExtraction 结果供 LangGraph 条件路由使用。
    """

    def __init__(self, session, user_id: str, confidence_threshold: float = 0.7):
        """
        初始化路由引擎。

        Args:
            session: 数据库会话
            user_id: 当前用户 ID
            confidence_threshold: 置信度阈值，低于此值降级为 chat
        """
        self.l0 = L0RuleEngine()
        self.l1 = L1Classifier(session, user_id)
        self.l2 = L2SlotExtractor()
        self.confidence_threshold = confidence_threshold

    async def route(self, query: str, context: Dict[str, Any]) -> IntentExtraction:
        """
        执行意图路由（主入口）。

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            IntentExtraction: 结构化意图提取结果，包含 routing_target
        """
        # Step 1: L0 极速拦截
        result = self.l0.evaluate(query, context)
        if result is not None:
            result.routing_target = INTENT_NODE_MAP[result.intent]
            log.info(f"[Engine] L0 命中: intent={result.intent.value}, target={result.routing_target}")
            return result

        # Step 2: L1 LLM 分类
        result = await self.l1.classify(query, context)
        log.info(f"[Engine] L1 结果: intent={result.intent.value}, confidence={result.confidence}")

        # Step 3: L2 槽位提取（仅对需要深度提取的意图）
        if result.intent in L2SlotExtractor.EXTRACTION_INTENTS:
            slot_result = await self.l2.extract(
                query, context, result.intent, self.l1.primary_llm
            )
            # 合并 L2 提取的槽位和上下文填充到 entities
            result.entities = {
                **result.entities,
                **slot_result.slots,
                **slot_result.context_enrichments
            }
            log.info(f"[Engine] L2 结果: slots={slot_result.slots}, enrichments={slot_result.context_enrichments}")

        # Step 4: 置信度降级保护
        if result.confidence < self.confidence_threshold:
            log.warning(f"[Engine] 置信度过低 ({result.confidence})，降级为 chat")
            result.intent = IntentType.CHAT

        # Step 5: 计算 routing_target
        result.routing_target = INTENT_NODE_MAP[result.intent]

        log.info(f"[Engine] 最终路由: intent={result.intent.value}, target={result.routing_target}")
        return result
```

- [ ] **Step 4: Update __init__.py to export engine**

```python
# app/agent/router/__init__.py
"""意图识别引擎 2.0 - L0+L1+L2 漏斗式架构"""
from app.agent.router.schemas import IntentType, IntentExtraction, SlotExtraction, AgentState, INTENT_NODE_MAP
from app.agent.router.engine import IntentRouterEngine

__all__ = [
    "IntentType", "IntentExtraction", "SlotExtraction", "AgentState",
    "INTENT_NODE_MAP", "IntentRouterEngine"
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_engine.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/router/engine.py autonome-backend/app/agent/router/__init__.py autonome-backend/tests/test_intent_router/test_engine.py
git commit -m "feat: add IntentRouterEngine orchestrator (L0→L1→L2 pipeline with confidence degradation)"
```

---

## Task 7: Create LangGraph Orchestration + Agent Nodes

**Files:**
- Create: `autonome-backend/app/agent/graph.py`
- Create: `autonome-backend/app/agent/nodes/__init__.py`
- Create: `autonome-backend/app/agent/nodes/chat_node.py`
- Create: `autonome-backend/app/agent/nodes/skill_forge_node.py`
- Create: `autonome-backend/app/agent/nodes/explicit_skill_node.py`
- Create: `autonome-backend/app/agent/nodes/diagnostic_node.py`
- Create: `autonome-backend/app/agent/nodes/literature_node.py`
- Create: `autonome-backend/app/agent/nodes/data_probe_node.py`
- Create: `tests/test_intent_router/test_graph.py`

- [ ] **Step 1: Create agent nodes package**

```python
# app/agent/nodes/__init__.py
"""LangGraph Agent 节点集合"""
```

- [ ] **Step 2: Create chat_node**

```python
# app/agent/nodes/chat_node.py
"""
Chat Agent 节点 - 通用对话和概念解释。

使用 ChatOpenAI.astream() 进行流式输出，
复用现有 chat.py 中的 SYSTEM_PROMPT_CHAT 逻辑。
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.agent.router.schemas import AgentState
from app.core.logger import log


# 通用对话系统提示词
CHAT_SYSTEM_PROMPT = """你是 Autonome Studio 的 AI 助手，一个专业的生物信息学顾问。

你的职责：
- 回答生物信息学相关的概念性问题
- 解释分析方法和算法原理
- 提供实验设计建议
- 推荐合适的分析工具和流程

注意：
- 对于需要执行代码或分析数据的请求，建议用户使用具体的分析功能
- 保持回答的专业性和准确性
- 使用中文回答"""


async def chat_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chat Agent 节点。

    处理通用对话请求，使用 LLM 流式生成回复。
    """
    messages = state.get("messages", [])
    intent_data = state.get("intent_data", {})

    log.info(f"[chat_node] 处理对话请求, entities={intent_data.get('entities', {})}")

    # 此节点返回状态更新，实际 LLM 流式调用在 chat.py 的 SSE 循环中完成
    # 这里只标记意图已路由到 chat_node
    return {
        "intent_data": {**intent_data, "node": "chat_node"}
    }
```

- [ ] **Step 3: Create skill_forge_node**

```python
# app/agent/nodes/skill_forge_node.py
"""
Skill Forge Agent 节点 - 代码生成与执行。

当用户需要生成或执行生信分析代码时路由到此节点。
使用 SkillExecutor 在 Docker 沙箱中执行代码。
"""
from typing import Any, Dict

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def skill_forge_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Skill Forge Agent 节点。

    处理代码生成/执行请求。
    实际的 SkillExecutor 调用和 LLM 代码生成在 chat.py 的 SSE 循环中完成。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[skill_forge_node] 处理代码生成请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "skill_forge_node"}
    }
```

- [ ] **Step 4: Create explicit_skill_node**

```python
# app/agent/nodes/explicit_skill_node.py
"""
Explicit Skill Agent 节点 - 执行用户指定的技能。

当用户直接指定技能 ID 或名称时路由到此节点。
使用 SkillExecutor 执行对应的 SKILL.md 定义的分析流程。
"""
from typing import Any, Dict

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def explicit_skill_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Explicit Skill Agent 节点。

    处理显式技能执行请求。
    """
    intent_data = state.get("intent_data", {})
    skill_id = intent_data.get("skill_id") or state.get("skill_id")

    log.info(f"[explicit_skill_node] 执行技能: skill_id={skill_id}")

    return {
        "intent_data": {**intent_data, "node": "explicit_skill_node"},
        "skill_id": skill_id
    }
```

- [ ] **Step 5: Create diagnostic_node**

```python
# app/agent/nodes/diagnostic_node.py
"""
Diagnostic Agent 节点 - 错误诊断与修复。

当用户遇到代码报错或环境问题时路由到此节点。
分析错误日志并提供修复建议。
"""
from typing import Any, Dict

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def diagnostic_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Diagnostic Agent 节点。

    处理错误诊断请求。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[diagnostic_node] 处理诊断请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "diagnostic_node"}
    }
```

- [ ] **Step 6: Create literature_node**

```python
# app/agent/nodes/literature_node.py
"""
Literature Agent 节点 - 文献解析与论文复现。

当用户涉及文献/DOI/论文复现时路由到此节点。
包装现有的 literature_agent.py。
"""
from typing import Any, Dict

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def literature_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Literature Agent 节点。

    处理文献解析请求，包装现有 literature_agent。
    """
    intent_data = state.get("intent_data", {})

    log.info("[literature_node] 处理文献请求")

    return {
        "intent_data": {**intent_data, "node": "literature_node"}
    }
```

- [ ] **Step 7: Create data_probe_node**

```python
# app/agent/nodes/data_probe_node.py
"""
Data Probe Agent 节点 - 数据预览与探查。

当用户需要查看数据结构、预览数据内容时路由到此节点。
调用 probe_tools.py 中的工具。
"""
from typing import Any, Dict

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def data_probe_node(state: AgentState, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Data Probe Agent 节点。

    处理数据探查请求，调用 probe_tools。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[data_probe_node] 处理数据探查请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "data_probe_node"}
    }
```

- [ ] **Step 8: Create LangGraph orchestration graph**

```python
# app/agent/graph.py
"""
LangGraph 多 Agent 编排图。

意图路由节点 (intent_router_node) 作为入口，
根据 IntentRouterEngine 的结果通过条件边分发到 6 个 Agent 节点。

Graph 结构:
    [Entry] → intent_router_node → conditional_edge → chat_node → END
                                               ├→ skill_forge_node → END
                                               ├→ explicit_skill_node → END
                                               ├→ diagnostic_node → END
                                               ├→ literature_node → END
                                               └→ data_probe_node → END
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.agent.nodes.chat_node import chat_node
from app.agent.nodes.data_probe_node import data_probe_node
from app.agent.nodes.diagnostic_node import diagnostic_node
from app.agent.nodes.explicit_skill_node import explicit_skill_node
from app.agent.nodes.literature_node import literature_node
from app.agent.nodes.skill_forge_node import skill_forge_node
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import AgentState
from app.core.logger import log


async def intent_router_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    LangGraph 入口节点：调用意图引擎，将提取的实体注入 State。

    session 和 user_id 通过 configurable 注入：
    graph.invoke(state, config={"configurable": {"session": ..., "user_id": ...}})
    """
    messages = state.get("messages", [])
    if not messages:
        return {"intent_data": {"intent": "chat", "routing_target": "chat_node"}}

    query = messages[-1].content
    context = state.get("context", {})

    # 从 configurable 注入 session 和 user_id
    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    if not session or not user_id:
        log.warning("[intent_router_node] 缺少 session 或 user_id，降级为 chat")
        return {"intent_data": {"intent": "chat", "routing_target": "chat_node"}}

    # 调用意图识别引擎
    engine = IntentRouterEngine(session, user_id)
    intent_result = await engine.route(query, context)

    # 追问拦截：不唤醒昂贵的 Agent，直接返回追问消息
    if intent_result.requires_followup and intent_result.followup_question:
        log.info(f"[intent_router_node] 追问拦截: {intent_result.followup_question}")
        return {
            "messages": [AIMessage(content=intent_result.followup_question)],
            "intent_data": intent_result.model_dump()
        }

    return {"intent_data": intent_result.model_dump()}


def route_by_intent(state: AgentState) -> str:
    """
    条件边：根据 intent_data 中的 routing_target 分发到对应 Agent 节点。

    如果 requires_followup 为 True，直接返回 END（追问已在入口节点处理）。
    """
    intent_data = state.get("intent_data", {})
    if intent_data.get("requires_followup"):
        return END
    return intent_data.get("routing_target", "chat_node")


def build_intent_graph() -> StateGraph:
    """
    构建意图路由 LangGraph。

    Returns:
        编译后的 StateGraph，可直接调用 .invoke() 或 .astream()
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("skill_forge_node", skill_forge_node)
    workflow.add_node("explicit_skill_node", explicit_skill_node)
    workflow.add_node("diagnostic_node", diagnostic_node)
    workflow.add_node("literature_node", literature_node)
    workflow.add_node("data_probe_node", data_probe_node)

    # 设置入口
    workflow.set_entry_point("intent_router")

    # 条件路由边：intent_router → 各 Agent 节点
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "chat_node": "chat_node",
            "skill_forge_node": "skill_forge_node",
            "explicit_skill_node": "explicit_skill_node",
            "diagnostic_node": "diagnostic_node",
            "literature_node": "literature_node",
            "data_probe_node": "data_probe_node",
            END: END,
        }
    )

    # 各 Agent 节点 → END
    workflow.add_edge("chat_node", END)
    workflow.add_edge("skill_forge_node", END)
    workflow.add_edge("explicit_skill_node", END)
    workflow.add_edge("diagnostic_node", END)
    workflow.add_edge("literature_node", END)
    workflow.add_edge("data_probe_node", END)

    return workflow.compile()
```

- [ ] **Step 9: Write graph tests**

```python
# tests/test_intent_router/test_graph.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.graph import route_by_intent, build_intent_graph
from app.agent.router.schemas import IntentType


class TestRouteByIntent:
    """条件路由函数测试"""

    def test_routes_to_chat_node(self):
        state = {"intent_data": {"routing_target": "chat_node", "requires_followup": False}}
        assert route_by_intent(state) == "chat_node"

    def test_routes_to_skill_forge_node(self):
        state = {"intent_data": {"routing_target": "skill_forge_node", "requires_followup": False}}
        assert route_by_intent(state) == "skill_forge_node"

    def test_routes_to_diagnostic_node(self):
        state = {"intent_data": {"routing_target": "diagnostic_node", "requires_followup": False}}
        assert route_by_intent(state) == "diagnostic_node"

    def test_followup_returns_end(self):
        state = {"intent_data": {"routing_target": "skill_forge_node", "requires_followup": True}}
        from langgraph.graph import END
        assert route_by_intent(state) == END

    def test_missing_intent_defaults_to_chat(self):
        state = {"intent_data": {}}
        assert route_by_intent(state) == "chat_node"

    def test_no_intent_data_defaults_to_chat(self):
        state = {}
        assert route_by_intent(state) == "chat_node"


class TestBuildIntentGraph:
    """LangGraph 图构建测试"""

    def test_graph_compiles(self):
        """图能成功编译"""
        graph = build_intent_graph()
        assert graph is not None
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/test_graph.py -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add autonome-backend/app/agent/graph.py autonome-backend/app/agent/nodes/ autonome-backend/tests/test_intent_router/test_graph.py
git commit -m "feat: add LangGraph orchestration graph with 6 Agent nodes and conditional routing"
```

---

## Task 8: Integrate Intent Router into Chat Route

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py`

- [ ] **Step 1: Read current chat.py to understand the exact modification points**

Run: `head -200 autonome-backend/app/api/routes/chat.py`

Key modification points in `chat_stream()`:
1. Replace `SkillMatcher` import and usage (lines ~156-164) with `IntentRouterEngine`
2. Use `intent_data` from the engine result to select system prompt and route
3. Pass `intent_data` to the SSE stream for frontend consumption

- [ ] **Step 2: Modify chat.py - replace SkillMatcher with IntentRouterEngine**

In the `chat_stream()` function, replace the intent classification block:

**Old code (to replace):**
```python
from app.services.skill_matcher import SkillMatcher, IntentType
matcher = SkillMatcher()
match_result = await matcher.match(request.message, context={"project_id": request.project_id})
intent_type = match_result.get("intent_type", IntentType.GENERAL_QUESTION)
```

**New code:**
```python
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import IntentType as NewIntentType

# 使用意图识别引擎 2.0 进行分类
router_engine = IntentRouterEngine(session=session, user_id=current_user.id)
intent_result = await router_engine.route(
    query=request.message,
    context={
        "project_id": request.project_id,
        "skill_id": request.skill_id,
        "active_file": request.context_files[0] if request.context_files else None,
        "context_files": request.context_files,
    }
)
intent_type = intent_result.intent.value
intent_data = intent_result.model_dump()
```

- [ ] **Step 3: Update system prompt selection logic**

**Old code (to replace):**
```python
if intent_type in (IntentType.LIVE_CODING, IntentType.IMPLICIT_SKILL, IntentType.EXPLICIT_SKILL):
    system_prompt = SYSTEM_PROMPT_CODE
else:
    system_prompt = SYSTEM_PROMPT_CHAT
```

**New code:**
```python
# 根据新意图类型选择系统提示词
if intent_result.intent in (NewIntentType.SKILL_FORGE, NewIntentType.EXPLICIT_SKILL, NewIntentType.DIAGNOSTIC):
    system_prompt = SYSTEM_PROMPT_CODE
else:
    system_prompt = SYSTEM_PROMPT_CHAT
```

- [ ] **Step 4: Add intent_data to SSE events**

In the SSE event loop, after the `session_info` event, add an `intent` event:

```python
# 发送意图识别结果给前端
yield {
    "event": "intent",
    "data": json.dumps(intent_data, ensure_ascii=False)
}
```

- [ ] **Step 5: Handle followup interception in SSE**

Before the LLM streaming loop, check if the intent result requires followup:

```python
# 如果意图引擎要求追问，直接返回追问消息而不调用 LLM
if intent_result.requires_followup and intent_result.followup_question:
    # ... save and yield the followup as an AI message, then return
```

- [ ] **Step 6: Rebuild and test**

Run: `docker-compose down && docker-compose up -d`
Run: `docker logs autonome-api | tail -30`

- [ ] **Step 7: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py
git commit -m "feat: integrate Intent Router Engine 2.0 into chat route (replace SkillMatcher)"
```

---

## Task 9: Run Full Test Suite + Docker Validation

- [ ] **Step 1: Run all intent router tests**

Run: `cd autonome-backend && python -m pytest tests/test_intent_router/ -v`
Expected: All PASS

- [ ] **Step 2: Run existing test suite to check for regressions**

Run: `cd autonome-backend && python -m pytest tests/ -v --tb=short`
Expected: No new failures

- [ ] **Step 3: Rebuild Docker and verify API starts**

Run: `docker-compose down && docker-compose up -d`
Run: `sleep 5 && docker logs autonome-api | tail -30`
Expected: API starts without import errors

- [ ] **Step 4: Test chat endpoint with curl**

Run a simple chat request to verify the intent router is working:

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test", "message": "你好"}'
```

Expected: SSE stream with `intent` event showing `{"intent": "chat", ...}`

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve integration issues from Intent Router Engine 2.0"
```

---

## Task 10: Deploy

- [ ] **Step 1: Run auto_deploy**

```bash
./auto_deploy.sh -s "feat: Intent Router Engine 2.0 - L0+L1+L2 漏斗式意图识别 + LangGraph 多Agent编排" -d "替换 SkillMatcher 为 IntentRouterEngine，实现 L0 规则拦截(8条规则) + L1 LLM结构化分类(复用用户配置模型) + L2 槽位提取(意图针对性)。新增 LangGraph StateGraph 编排图，6个Agent节点(chat/skill_forge/explicit_skill/diagnostic/literature/data_probe)，条件路由分发。修改 chat.py 接入新引擎，SSE 新增 intent 事件。"
```
