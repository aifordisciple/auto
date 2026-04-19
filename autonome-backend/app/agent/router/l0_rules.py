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
            SystemStateRule(),        # 优先级 1: 系统状态
            ActiveViewRule(),         # 优先级 2: 活跃视图
            ExplicitSkillRule(),      # 优先级 3: 显式技能
            ErrorPatternRule(),       # 优先级 4: 错误关键词
            LiteraturePatternRule(),  # 优先级 5: 文献模式
            ProbePatternRule(),       # 优先级 6: 数据探查
            CodeGenPatternRule(),     # 优先级 7: 代码生成
            ChitchatRule(),           # 优先级 8: 闲聊
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