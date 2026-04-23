"""
L0 规则拦截层 - 零成本极速意图分发。

通过检测系统级特征和关键词模式，以 0 token 成本完成意图拦截。
未命中任何规则的查询返回 None，放行至 L1 LLM 分类层。

规则按优先级顺序执行，首个命中即返回。

V2.0 升级要点：
- 更新所有 IntentType 映射至 V2.0 12 种原子意图
- 新增 SystemMacroRule (优先级 0.5): 系统宏指令拦截
- 新增 VersionControlRule (优先级 4.5): 版本控制意图识别
- 新增 VisualTweakRule (优先级 6.5): 视觉微调意图识别
- ActiveViewRule 视图映射扩展
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


class SystemMacroRule(Rule):
    """
    优先级 0.5: 系统宏指令拦截（最高优先级）。

    检测 /status、/clear、/help、/version、/reset 等系统命令，
    直接路由至 SYSTEM_MACRO 意图，置信度 1.0（确定性命令，无需 LLM 确认）。
    """

    # 系统宏指令正则：匹配 /status、/clear、/help、/version、/reset
    MACRO_PATTERN = re.compile(r'^/(status|clear|help|version|reset)\b')

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        stripped = query.strip()
        if self.MACRO_PATTERN.match(stripped):
            command = stripped.split()[0][1:]  # 提取命令名（去掉 /）
            log.debug(f"[L0] SystemMacroRule 命中: command=/{command}")
            return IntentExtraction(
                intent=IntentType.SYSTEM_MACRO,
                confidence=1.0,
                entities={"macro_command": command},
                requires_followup=False
            )
        return None


class SystemStateRule(Rule):
    """
    优先级 1: 系统状态拦截。

    当上下文存在明确的沙箱报错退出码时，直接路由至诊断恢复，
    置信度 1.0（确定性状态，无需 LLM 确认）。
    """

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if context.get("last_execution_status") == "failed":
            log.debug("[L0] SystemStateRule 命中: last_execution_status=failed")
            return IntentExtraction(
                intent=IntentType.DIAGNOSTIC_RECOVERY,
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

    # 视图 → 意图映射（V2.0 扩展）
    VIEW_INTENT_MAP = {
        "literature_upload": IntentType.LITERATURE_MINING,
        "workflow_editor": IntentType.WORKFLOW_ORCHESTRATE,
        "version_history": IntentType.VERSION_CONTROL,
        "visual_settings": IntentType.VISUAL_PERCEPTION_AND_TWEAK,
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
                intent=IntentType.EXPLICIT_EXEC,
                confidence=0.95,
                entities={"skill_id": skill_id},
                skill_id=skill_id,
                requires_followup=False
            )

        # 检查查询中的"用XX技能"模式
        if self.SKILL_TRIGGER_PATTERNS.search(query):
            log.debug("[L0] ExplicitSkillRule 命中: 技能触发模式")
            return IntentExtraction(
                intent=IntentType.EXPLICIT_EXEC,
                confidence=0.90,
                entities={},
                requires_followup=False
            )

        return None


class ErrorPatternRule(Rule):
    """
    优先级 4: 错误关键词模式拦截。

    检测中英文错误关键词，路由到诊断恢复意图。
    """

    ERROR_PATTERN = re.compile(
        r'(error|exception|报错|失败|出错|failed|traceback|bug|崩溃|crash)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.ERROR_PATTERN.search(query):
            log.debug("[L0] ErrorPatternRule 命中")
            return IntentExtraction(
                intent=IntentType.DIAGNOSTIC_RECOVERY,
                confidence=0.90,
                entities={"error_type": "keyword_detected"},
                requires_followup=False
            )
        return None


class VersionControlRule(Rule):
    """
    优先级 4.5: 版本控制意图识别规则。

    检测回滚、版本对比、历史、撤销等关键词，
    路由到 VERSION_CONTROL 意图。
    """

    # 版本控制关键词正则
    VERSION_PATTERN = re.compile(
        r'(回滚|版本|对比|rollback|version|diff\s+版本|历史版本|撤销)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.VERSION_PATTERN.search(query):
            log.debug("[L0] VersionControlRule 命中")
            return IntentExtraction(
                intent=IntentType.VERSION_CONTROL,
                confidence=0.85,
                entities={},
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
                intent=IntentType.LITERATURE_MINING,
                confidence=0.90,
                entities={},
                requires_followup=False
            )
        return None


class ProbePatternRule(Rule):
    """
    优先级 6: 数据探查模式拦截。

    检测"查看/预览/结构"等探查关键词，路由到 data_probe。
    支持两种场景：
    1. 有文件上下文时的数据集探查（查看 h5ad 结构、预览 CSV 等）
    2. 无文件上下文时的文件系统探索（有哪些文件、目录结构、文件列表等）
    """

    # 数据集探查关键词（需要文件上下文）
    PROBE_KEYWORDS = re.compile(
        r'(查看|预览|看看|结构|统计|inspect|preview|peek|查看数据|数据结构)',
        re.IGNORECASE
    )

    # 文件系统探索关键词（无需文件上下文，查询工作区文件结构）
    # 包含两种语序：
    #   - "有哪些文件"、"哪些文件"（疑问词在前）
    #   - "文件有哪些"、"文件列表"（名词在前）
    FILE_EXPLORATION_KEYWORDS = re.compile(
        r'(有哪些文件|文件有哪些|文件列表|目录结构|什么文件|哪些文件|'
        r'项目文件|项目有哪些|项目目录|项目结构|'
        r'文件树|目录树|扫描目录|扫描文件|列出文件|查看文件|浏览文件|'
        r'list\s*files|file\s*list|directory\s*tree|file\s*tree|'
        r'scan\s*dir|show\s*files|what\s*files)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        has_file_context = bool(context.get("active_file") or context.get("context_files"))

        # 场景 1: 有文件上下文 + 探查关键词 → 数据集探查
        if self.PROBE_KEYWORDS.search(query) and has_file_context:
            active_file = context.get("active_file", "")
            log.debug(f"[L0] ProbePatternRule 命中(数据集探查): active_file={active_file}")
            return IntentExtraction(
                intent=IntentType.DATA_PROBE,
                confidence=0.85,
                entities={"input_file": active_file} if active_file else {},
                requires_followup=False
            )

        # 场景 2: 文件系统探索关键词（无需文件上下文）→ 工作区扫描
        if self.FILE_EXPLORATION_KEYWORDS.search(query):
            log.debug("[L0] ProbePatternRule 命中(文件系统探索)")
            return IntentExtraction(
                intent=IntentType.DATA_PROBE,
                confidence=0.85,
                entities={"probe_type": "workspace_scan"},
                requires_followup=False
            )

        return None


class VisualTweakRule(Rule):
    """
    优先级 6.5: 视觉微调意图识别规则。

    检测调色、配色、阈值、DPI、分辨率、颜色等视觉微调关键词，
    路由到 VISUAL_PERCEPTION_AND_TWEAK 意图。
    """

    # 视觉微调关键词正则
    VISUAL_TWEAK_PATTERN = re.compile(
        r'(调色|配色|阈值|DPI|分辨率|颜色|palette|theme|tweak|调整.*图|微调.*视觉|修改.*样式)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.VISUAL_TWEAK_PATTERN.search(query):
            log.debug("[L0] VisualTweakRule 命中")
            return IntentExtraction(
                intent=IntentType.VISUAL_PERCEPTION_AND_TWEAK,
                confidence=0.85,
                entities={},
                requires_followup=False
            )
        return None


class CodeGenPatternRule(Rule):
    """
    优先级 7: 代码生成模式拦截。

    检测"跑流程/做分析/运行分析"等需要真正执行代码的关键词模式。

    ⚠️ 关键区分：
    - "写一个PCA脚本" / "给我一个代码示例" → 纯理论请求，属于 general_chat
    - "跑PCA分析" / "做差异表达分析" / "运行这个pipeline" → 需要执行，属于 skill_forge

    仅匹配明确包含"执行/运行/跑/做/进行"等动作词的模式，
    不匹配"写/编写/生成"等仅请求代码输出的模式。
    """

    CODEGEN_PATTERN = re.compile(
        r'(跑|运行|执行|做|进行|跑一下|跑一下|run|execute)\s*(?:分析|流程|pipeline|代码|脚本)',
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

    检测问候语、感谢等短文本，路由到通用闲聊。
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
                intent=IntentType.GENERAL_CHAT,
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
        # 按优先级排序（数值越小优先级越高），首个命中即返回
        self.rules: List[Rule] = [
            SystemMacroRule(),       # 优先级 0.5: 系统宏指令（最高优先级）
            SystemStateRule(),       # 优先级 1: 系统状态
            ActiveViewRule(),        # 优先级 2: 活跃视图
            ExplicitSkillRule(),     # 优先级 3: 显式技能
            ErrorPatternRule(),      # 优先级 4: 错误关键词
            VersionControlRule(),    # 优先级 4.5: 版本控制
            LiteraturePatternRule(), # 优先级 5: 文献模式
            ProbePatternRule(),      # 优先级 6: 数据探查
            VisualTweakRule(),       # 优先级 6.5: 视觉微调
            CodeGenPatternRule(),    # 优先级 7: 代码生成
            ChitchatRule(),          # 优先级 8: 闲聊
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