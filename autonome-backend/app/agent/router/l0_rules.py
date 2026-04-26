"""
L0 规则拦截层 - 零成本极速意图分发。

通过检测系统级特征和关键词模式，以 0 token 成本完成意图拦截。
未命中任何规则的查询返回 None，放行至 L1 LLM 分类层。

规则按优先级顺序执行，首个命中即返回。

V2.2 升级要点（基于 130 用例测试结果，通过率 56.2% → 80%+）：
- 重构 ErrorPatternRule (优先级 4→5.5): 区分真实报错 vs 假设性/描述性错误提及
- 新增 SystemAssetOpsRule (优先级 4.8): 系统资产运维意图识别
- 新增 WorkflowOrchestrateRule (优先级 6.2): 工作流编排意图识别
- 新增 CollaborationRule (优先级 5.2): 团队协作意图识别
- 扩展 SystemMacroRule: 通用 /command + 短确认语
- 扩展 LiteraturePatternRule: 文献指代模式 + 期刊/数据库标识
- 新增 L0 置信度门控: 低置信度命中放行至 L1
- DescriptionIntentRule 增加文献上下文排除

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

    检测系统命令（/status、/clear、/help、/version、/reset、/stop 等）
    和短确认语（继续、确定、好、可以），直接路由至 SYSTEM_MACRO 意图。

    V2.2 升级：扩展匹配范围
    - 所有以 / 开头的命令（不仅限已知命令列表）
    - 短确认语（≤4 字符）：继续/确定/好的/可以/是的/确认/OK/yes/no
    - /stop 等控制命令

    排除：代码中的 /function() 引用（如 "/clear_memory() 函数"）
    """

    # 已知系统命令（高置信度 1.0）
    KNOWN_MACRO_PATTERN = re.compile(
        r'^\s*/(status|clear|help|version|reset|stop|start|pause|resume|cancel|quit|exit)\b'
    )

    # 任意 /command 模式（中置信度 0.90）
    # 匹配 / 开头的短命令（≤30字符），排除代码中的 /function() 引用
    GENERIC_MACRO_PATTERN = re.compile(
        r'^\s*/([a-zA-Z][\w-]*)\s*(\S+)?\s*$'
    )

    # 短确认语（≤4 字符）
    SHORT_CONFIRM_PATTERN = re.compile(
        r'^(继续|确定|好的|可以|是的|好|是|确认|OK|ok|yes|no|nope)$',
        re.IGNORECASE
    )

    # 排除：代码中的 /function() 引用
    CODE_REFERENCE_PATTERN = re.compile(r'(/\w+\(|/\w+\{)')

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        stripped = query.strip()

        # 排除：代码中引用 /command（如 "/clear_memory() 函数"）
        if self.CODE_REFERENCE_PATTERN.search(stripped) and len(stripped) > 30:
            return None

        # 已知命令
        if self.KNOWN_MACRO_PATTERN.match(stripped):
            command = stripped.split()[0][1:]  # 提取命令名（去掉 /）
            log.debug(f"[L0] SystemMacroRule 命中: 已知命令 /{command}")
            return IntentExtraction(
                intent=IntentType.SYSTEM_MACRO,
                confidence=1.0,
                entities={"macro_command": command},
                requires_followup=False
            )

        # 任意 /command 模式（未知命令，如 /run-fastqc）
        macro_match = self.GENERIC_MACRO_PATTERN.match(stripped)
        if macro_match and len(stripped) <= 30:
            command = macro_match.group(1)
            log.debug(f"[L0] SystemMacroRule 命中: 通用命令 /{command}")
            return IntentExtraction(
                intent=IntentType.SYSTEM_MACRO,
                confidence=0.90,
                entities={"macro_command": command},
                requires_followup=False
            )

        # 短确认语
        if len(stripped) <= 4 and self.SHORT_CONFIRM_PATTERN.match(stripped):
            log.debug(f"[L0] SystemMacroRule 命中: 短确认语 '{stripped}'")
            return IntentExtraction(
                intent=IntentType.SYSTEM_MACRO,
                confidence=0.90,
                entities={"macro_command": "confirm"},
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


class VersionControlRule(Rule):
    """
    优先级 4.5: 版本控制意图识别规则。

    检测回滚、版本对比、历史、撤销等关键词，
    路由到 VERSION_CONTROL 意图。

    V2.2 升级：细化"对比"关键词匹配，避免非版本对比场景误判。
    "对比文献A和B" → LITERATURE_MINING（不是版本控制）
    "对比两次运行结果" → VERSION_CONTROL
    """

    # 版本控制关键词正则
    # "对比" 需要与版本上下文词组合才匹配，避免"对比文献/数据/方法"误判
    VERSION_PATTERN = re.compile(
        r'(回滚|版本对比|对比版本|对比.*运行|对比.*结果|rollback|version|'
        r'diff\s+版本|历史版本|撤销|版本|对比.*环境)',
        re.IGNORECASE
    )

    # 排除模式：对比文献/文章/数据 → 不是版本控制
    # 注意："对比.*环境" 不排除，因为"对比两次运行的环境差异"属于版本控制意图
    VERSION_EXCLUSION_PATTERN = re.compile(
        r'(对比.*文献|对比.*文章|对比.*论文|对比.*数据|对比.*方法|对比.*样本|'
        r'对比.*配置|对比.*工作区)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        # 排除：对比文献/文章/数据等非版本对比场景
        if self.VERSION_EXCLUSION_PATTERN.search(query):
            return None

        if self.VERSION_PATTERN.search(query):
            log.debug("[L0] VersionControlRule 命中")
            return IntentExtraction(
                intent=IntentType.VERSION_CONTROL,
                confidence=0.85,
                entities={},
                requires_followup=False
            )
        return None


class SystemAssetOpsRule(Rule):
    """
    优先级 4.8: 系统资产运维意图识别规则。

    检测文件管理、节点/实例切换、积分/配额、环境打包、数据挂载等
    系统级运维操作关键词，路由到 SYSTEM_ASSET_OPS 意图。

    V2.2 新增规则：解决 R5 SYSTEM_ASSET_OPS 通过率仅 20% 的问题。
    之前无 L0 规则覆盖此意图，完全依赖 L1 分类（L1 无法区分运维操作 vs 执行分析）。

    关键词分组：
    - 文件管理：移动/删除/归档/转存/清理/冷存储
    - 计算资源：节点.*切换/切换.*节点/实例.*切换/高配/低配
    - 配额计费：积分/配额/消耗/余额/计费
    - 环境管理：打包.*镜像/自定义镜像/环境.*打包/环境.*克隆
    - 数据挂载：挂载/卸载/数据库.*挂载
    - 任务控制：停掉.*任务/终止.*任务/取消.*任务
    """

    SYSTEM_ASSET_PATTERN = re.compile(
        r'(移动|删除|归档|转存|清理.*文件|冷存储|'
        r'节点.*切换|切换.*节点|切.*大.*节点|切.*高配|切到.*节点|切.*内存|'
        r'实例.*切换|切换.*实例|高配|低配|升级.*实例|'
        r'积分|配额|消耗.*积分|余额|计费|'
        r'打包.*镜像|自定义镜像|环境.*打包|环境.*克隆|环境.*导出|'
        r'挂载|卸载|数据库.*挂载|挂载.*数据库|'
        r'停掉.*任务|停.*任务|终止.*任务|取消.*任务)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.SYSTEM_ASSET_PATTERN.search(query):
            log.debug("[L0] SystemAssetOpsRule 命中")
            return IntentExtraction(
                intent=IntentType.SYSTEM_ASSET_OPS,
                confidence=0.88,
                entities={},
                requires_followup=False
            )
        return None


class LiteraturePatternRule(Rule):
    """
    优先级 5: 文献模式拦截。

    检测 DOI 链接、PDF 上传、论文/文献关键词。
    V2.2 升级：扩展文献上下文关键词，支持文献指代模式和期刊/数据库标识。

    匹配模式（任一命中即拦截）：
    1. DOI 链接 / DOI 关键词
    2. 论文/文献/paper/article/复现 关键词
    3. "这篇/这篇文章/这篇文献" 等文献指代模式，
       强烈暗示用户正在操作一篇文档/论文
    4. 期刊来源标识（Nature/Cell/Science/Lancet/NEJM/BioRxiv 等）
       或数据库标识（GSE\d+/PMID/PMC\d+）
    """

    DOI_PATTERN = re.compile(r'doi\.org|doi:', re.IGNORECASE)

    # 直接关键词
    LITERATURE_KEYWORDS = re.compile(
        r'(论文|文献|paper|article|复现|reproduce)',
        re.IGNORECASE
    )

    # 文献指代模式：用户在引用一篇文档进行操作
    REFERENCE_ACTION_PATTERN = re.compile(
        r'(这篇|这篇文章|这篇文献|这篇论文|'
        r'这文献|那篇|那篇文章|那篇文献|'
        r'左侧.*文章|左边.*文章|工作区.*文献|'
        r'文献\s*[AB]|文章\s*[AB])',
        re.IGNORECASE
    )

    # 期刊/数据库标识（从 Nature/Cell 等期刊或 GEO/PMC 等数据库提取信息）
    # 注意：Cell/Nature/Science 在生信语境中很常见（"Cell Ranger"、"单细胞"、"Nature 配色"），
    # 必须与明确的文献上下文词组合才能匹配，避免过度匹配
    JOURNAL_ACTION_PATTERN = re.compile(
        r'((?:Nature|Cell|Science|Lancet|NEJM|JAMA)\s+(?:Methods|Biotech|Biology|Medicine|Genetics|Communications)|'
        r'BioRxiv|medRxiv|PNAS|Genome\s+Biol|'
        r'GSE\d+|PMC\d+|PMID)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        # 排除：当查询同时包含视觉微调关键词时，不拦截为 LITERATURE_MINING
        # 例如："把这篇文章的配色换成 Nature 风格" → 视觉微调优先
        VISUAL_OVERRIDE_PATTERN = re.compile(
            r'(配色|颜色|调色板|阈值|DPI|分辨率|palette|theme|样式|改成|换成|修改.*图|调整.*图)',
            re.IGNORECASE
        )
        if VISUAL_OVERRIDE_PATTERN.search(query):
            log.debug("[L0] LiteraturePatternRule 未命中: 查询包含视觉微调关键词，放行至 VisualTweakRule")
            return None

        # 模式1: DOI
        if self.DOI_PATTERN.search(query):
            log.debug("[L0] LiteraturePatternRule 命中: DOI")
            return IntentExtraction(
                intent=IntentType.LITERATURE_MINING,
                confidence=0.90,
                entities={},
                requires_followup=False
            )

        # 模式2: 直接关键词
        if self.LITERATURE_KEYWORDS.search(query):
            log.debug("[L0] LiteraturePatternRule 命中: 直接关键词")
            return IntentExtraction(
                intent=IntentType.LITERATURE_MINING,
                confidence=0.90,
                entities={},
                requires_followup=False
            )

        # 模式3: 文献指代模式（"这篇"/"文献A"等）
        if self.REFERENCE_ACTION_PATTERN.search(query):
            log.debug("[L0] LiteraturePatternRule 命中: 文献指代模式")
            return IntentExtraction(
                intent=IntentType.LITERATURE_MINING,
                confidence=0.85,
                entities={},
                requires_followup=False
            )

        # 模式4: 期刊/数据库标识
        if self.JOURNAL_ACTION_PATTERN.search(query):
            log.debug("[L0] LiteraturePatternRule 命中: 期刊/数据库标识")
            return IntentExtraction(
                intent=IntentType.LITERATURE_MINING,
                confidence=0.85,
                entities={},
                requires_followup=False
            )

        return None


class CollaborationRule(Rule):
    """
    优先级 5.2: 团队协作意图识别规则。

    检测共享/权限/团队/协同等关键词，路由到 COLLABORATION 意图。

    V2.2 新增规则：解决 R8 COLLABORATION 通过率仅 40% 的问题。

    关键区分（与 SYSTEM_ASSET_OPS 的边界）：
    - "分享给李教授" → COLLABORATION（涉及人员和权限）
    - "移动文件到文件夹" → SYSTEM_ASSET_OPS（纯文件管理，不涉及人员）
    - "克隆工作区给实习生" → COLLABORATION（涉及人员协作）
    """

    COLLABORATION_PATTERN = re.compile(
        r'(分享|共享|权限|只读|编辑权限|协同|'
        r'团队|科室|分享链接|对外分享|'
        r'加入.*项目|邀请|移除.*成员|'
        r'发布.*技能库|技能库.*发布|发布到.*团队|发布到.*科室|'
        r'克隆.*工作区|克隆.*环境|克隆给|'
        r'导出.*审计|审计日志|操作记录|对话记录|'
        r'公开.*编辑|开放.*编辑|设为公开)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.COLLABORATION_PATTERN.search(query):
            log.debug("[L0] CollaborationRule 命中")
            return IntentExtraction(
                intent=IntentType.COLLABORATION,
                confidence=0.88,
                entities={},
                requires_followup=False
            )
        return None


class ErrorPatternRule(Rule):
    """
    优先级 5.5（从 4 降级）: 错误关键词模式拦截。

    检测中英文错误关键词，路由到诊断恢复意图。
    V2.2 升级：区分真实报错诊断 vs 假设性/描述性错误提及。

    核心逻辑：
    - 真实报错：用户正在经历错误，需要诊断恢复（"报错了"、"崩溃了"、"ValueError"）
    - 假设性提及：用户只是提到错误概念，不需要诊断（"如果遇到报错"、"报错怎么办"）
    - 标识符内嵌：错误词出现在文件名/变量名中（"名字带 failed 的文件"）

    优先级从 4 降为 5.5 的原因：
    - 让 VersionControlRule(4.5) 优先触发，避免"报错+对比"被误判为 DIAGNOSTIC_RECOVERY
    - 让 SystemAssetOpsRule(4.8) 优先触发，避免"停掉任务"被误判为 DIAGNOSTIC_RECOVERY
    - 让 LiteraturePatternRule(5) 优先触发，避免文献中的错误词被误判
    """

    # 强错误模式：用户正在经历的真实错误（句尾/句中出现，表示事件已发生）
    STRONG_ERROR_PATTERN = re.compile(
        r'(报错[了！]|出错[了！]|失败了|崩溃[了！]|crash(ed|ing)?|'
        r'failed|traceback|exception|OOMKilled|'
        r'Error\s+[in：]|ValueError|TypeError|KeyError|FileNotFoundError|'
        r'No space left|报错说|报错：|报错信息|'
        r'挂了|卡死了|跑挂了|死循环)',
        re.IGNORECASE
    )

    # 假设性/描述性模式排除：这些是讨论错误概念，不是真实报错
    HYPOTHETICAL_PATTERN = re.compile(
        r'(如果.*遇到|如果.*报错|遇到.*怎么办|遇到.*解决思路|'
        r'如果.*失败|万一.*出错|如何处理.*error|'
        r'报错的话|报错怎么办|经常遇到|总是遇到)',
        re.IGNORECASE
    )

    # 标识符/名称模式排除：错误词出现在文件名、变量名等标识符中
    IDENTIFIER_PATTERN = re.compile(
        r'(名字带\s*[`\'"]?\s*(error|failed|报错|出错)|'
        r'叫\s*[`\'"]?\s*\S*(error|failed)|'
        r'包含\s*(error|failed))',
        re.IGNORECASE
    )

    # V2.3: 数据探查类查询排除（避免"检测文件编码"、"文件乱码"等被误判为 DIAGNOSTIC_RECOVERY）
    DATA_INSPECTION_EXCLUSION = re.compile(
        r'(检测.*编码|检测.*分隔符|检测.*格式|检测.*文件编码|'
        r'编码.*检测|分隔符.*检测|探测.*编码|探测.*分隔符|'
        r'检查.*NA|检查.*缺失|预览.*数据|查看.*结构|'
        r'文件.*打不开|乱码|文件.*格式.*检测)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        # 排除：数据探查类查询（文件编码/格式检测等，放行给 ProbePatternRule）
        if self.DATA_INSPECTION_EXCLUSION.search(query):
            log.debug("[L0] ErrorPatternRule 未命中: 数据探查类查询，放行至 ProbePatternRule")
            return None

        # 排除：假设性错误讨论（"如果遇到报错怎么办"）
        if self.HYPOTHETICAL_PATTERN.search(query):
            log.debug("[L0] ErrorPatternRule 未命中: 假设性错误讨论")
            return None

        # 排除：错误词出现在标识符/文件名中
        if self.IDENTIFIER_PATTERN.search(query):
            log.debug("[L0] ErrorPatternRule 未命中: 错误词出现在标识符中")
            return None

        # 匹配：真实的错误事件
        if self.STRONG_ERROR_PATTERN.search(query):
            log.debug("[L0] ErrorPatternRule 命中: 真实报错诊断")
            return IntentExtraction(
                intent=IntentType.DIAGNOSTIC_RECOVERY,
                confidence=0.90,
                entities={"error_type": "keyword_detected"},
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
    # V2.3 扩展：覆盖编码检测、NA检测、集合运算、summary stats、VCF解析等场景
    PROBE_KEYWORDS = re.compile(
        r'(查看|预览|看看|结构|统计|inspect|preview|peek|查看数据|数据结构|'
        r'检测编码|分隔符|编码格式|文件编码|分隔符检测|分隔符.*检测|'
        r'检测.*编码|检测.*分隔符|检测.*格式|检测.*文件格式|'
        r'NA.*比例|NA.*检测|缺失率|缺失值|缺失检测|缺失.*统计|统计.*缺失|统计.*NA|'
        r'重叠|overlap|intersect|交集|并集|集合.*操作|'
        r'BAM.*头|BAM.*header|VCF样本|VCF.*sample|检测样本|'
        r'最小值|最大值|极值|min.*max|range.*值|分布.*范围|'
        r'数据.*维度|行列.*数|多少.*行.*列|多少.*列|矩阵.*形状|shape.*矩阵|矩阵.*维度|'
        r'读取.*列名|取得.*列名|列名.*列表|有哪些.*列)',
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
        r'scan\s*dir|show\s*files|what\s*files|'
        r'扫描文件夹|扫描.*目录|文件.*配对|配对.*文件|配对末端|双端.*文件|'
        r'R1.*R2|R2.*R1|匹配.*文件名|文件名.*匹配|'
        r'FASTQ.*配对|fastq.*pair|查找.*配对|查找.*R1|查找.*R2)',
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


class WorkflowOrchestrateRule(Rule):
    """
    优先级 6.2: 工作流编排意图识别规则。

    检测 Nextflow/DSL2/nf-core/Snakemake/pipeline/编排等关键词，
    路由到 WORKFLOW_ORCHESTRATE 意图。

    V2.2 新增规则：解决 R11 WORKFLOW_ORCHESTRATE 通过率仅 30% 的问题。
    L1 无法区分"写 Nextflow 工作流"和"写普通脚本"，需要 L0 提供确定性拦截。

    关键区分：
    - "写一个 Nextflow 脚本" → WORKFLOW_ORCHESTRATE（Nextflow 是工作流引擎）
    - "写一个 R 脚本" → SKILL_FORGE（R 脚本是技能代码）
    - "编排一个流程" → WORKFLOW_ORCHESTRATE
    - "跑 FastQC" → EXPLICIT_EXEC（单技能执行）
    """

    WORKFLOW_PATTERN = re.compile(
        r'(Nextflow|nextflow|DSL2|nf-core|nf_core|'
        r'编排.*流程|编排.*工作流|流程编排|'
        r'写.*工作流|写.*pipeline|写.*流程|'
        r'连起来跑|串联.*步骤|串成.*流水线|'
        r'Snakemake|snakemake|Cromwell|cromwell|WDL|'
        r'自动化.*流程|自动化.*pipeline)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        if self.WORKFLOW_PATTERN.search(query):
            log.debug("[L0] WorkflowOrchestrateRule 命中")
            return IntentExtraction(
                intent=IntentType.WORKFLOW_ORCHESTRATE,
                confidence=0.88,
                entities={},
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


class DescriptionIntentRule(Rule):
    """
    优先级 6.8: 纯描述/大纲/解释意图拦截。

    检测用户只是"索要大纲、列步骤、解释概念、介绍流程"等纯文本输出请求，
    路由到 GENERAL_CHAT，防止被误判为 WORKFLOW_ORCHESTRATE 或 SKILL_FORGE。

    V2.2 升级：增加文献上下文排除。
    当查询包含文献指代词（"这篇/文章/文献/论文/Nature/Cell"）时不拦截，
    让 LiteraturePatternRule(5) 优先处理。

    ⚠️ 关键区分（与 CodeGenPatternRule / L1 WORKFLOW_ORCHESTRATE 的边界）：
    - "给我列一个GATK WES分析的10步大纲" → 纯描述请求，属于 GENERAL_CHAT
    - "介绍一下RNA-seq分析流程" → 知识解释，属于 GENERAL_CHAT
    - "跑GATK WES分析" / "执行这个pipeline" → 需要真正执行，属于 SKILL_FORGE / WORKFLOW_ORCHESTRATE
    - "帮我写一个Nextflow脚本" → 代码生成，属于 SKILL_FORGE

    仅匹配明确包含"描述/大纲/介绍/解释/列出/列举/说明/概述/总结/梳理"
    等纯输出意图词的模式，不匹配"跑/运行/执行/做"等执行意图词。
    """

    # 纯描述意图关键词正则
    # 匹配模式：描述词 + (可选的"流程/步骤/方案/思路"等结构词)
    DESCRIPTION_PATTERN = re.compile(
        r'(给我列|列一个|列一下|列出|列举|介绍一下|介绍|解释一下|解释|说明一下|说明|概述|总结一下|总结|梳理一下|梳理|'
        r'大纲|提纲|步骤大纲|流程大纲|方案大纲|'
        r'describe|outline|explain|summarize|list\s+the\s+steps|give\s+me\s+an\s+overview)',
        re.IGNORECASE
    )

    # 排除模式：如果同时包含明确的执行意图词，则不拦截（让 L1 判断）
    # 例如："列一个大纲然后帮我跑一下" → 包含执行意图，不拦截
    EXECUTION_EXCLUSION_PATTERN = re.compile(
        r'(跑|运行|执行|做.*分析|run|execute|帮我跑|帮我做|帮我执行)',
        re.IGNORECASE
    )

    # 文献上下文排除：查询包含文献指代词时不拦截，让 LiteraturePatternRule 处理
    # 防御性措施：即使 LiteraturePatternRule(5) 未命中（理论上不应发生），
    # DescriptionIntentRule(6.8) 也不会将文献查询误判为 GENERAL_CHAT
    LITERATURE_CONTEXT_PATTERN = re.compile(
        r'(这篇|文章|文献|论文|paper|article|期刊|Nature|Cell|Science|Lancet|GSE\d|PMID|PMC\d)',
        re.IGNORECASE
    )

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        # 先排除：如果包含执行意图词，不拦截，交给 L1 判断
        if self.EXECUTION_EXCLUSION_PATTERN.search(query):
            return None

        # 排除：如果包含文献上下文指示词，不拦截，让 LiteraturePatternRule 处理
        if self.LITERATURE_CONTEXT_PATTERN.search(query):
            return None

        if self.DESCRIPTION_PATTERN.search(query):
            log.debug("[L0] DescriptionIntentRule 命中: 纯描述/大纲/解释请求")
            return IntentExtraction(
                intent=IntentType.GENERAL_CHAT,
                confidence=0.85,
                entities={"description_type": "outline_or_explanation"},
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


# L0 置信度阈值：低于此值的 L0 命中放行至 L1 判断
# CodeGenPatternRule(0.80) 等低置信度规则命中后不强制拦截，
# 而是记录匹配但放行至 L1 做更好决策
L0_CONFIDENCE_THRESHOLD = 0.85


class L0RuleEngine:
    """
    L0 规则拦截引擎。

    按优先级依次评估规则列表，首个命中即返回。
    未命中返回 None，放行至 L1 LLM 分类层。

    V2.2 升级：新增置信度门控。
    低置信度命中（< L0_CONFIDENCE_THRESHOLD）记录但放行至 L1，
    避免低置信度规则强制拦截导致误分类。
    """

    def __init__(self):
        # 按优先级排序（数值越小优先级越高），首个命中即返回
        self.rules: List[Rule] = [
            SystemMacroRule(),              # 0.5: 系统宏指令（V2.2: 扩展 /command + 短确认语）
            SystemStateRule(),              # 1: 系统状态
            ActiveViewRule(),               # 2: 活跃视图
            ExplicitSkillRule(),            # 3: 显式技能
            VersionControlRule(),           # 4.5: 版本控制
            SystemAssetOpsRule(),           # 4.8: 系统资产运维（V2.2 新增）
            LiteraturePatternRule(),        # 5: 文献模式（V2.2: 扩展文献指代+期刊标识）
            CollaborationRule(),            # 5.2: 团队协作（V2.2 新增）
            ErrorPatternRule(),             # 5.5: 错误关键词（V2.2: 从4降级，增加假设/标识符排除）
            ProbePatternRule(),             # 6: 数据探查
            WorkflowOrchestrateRule(),      # 6.2: 工作流编排（V2.2 新增）
            VisualTweakRule(),              # 6.5: 视觉微调
            DescriptionIntentRule(),        # 6.8: 纯描述/大纲/解释（V2.2: 增加文献上下文排除）
            CodeGenPatternRule(),           # 7: 代码生成
            ChitchatRule(),                 # 8: 闲聊
        ]

    def evaluate(self, query: str, context: Dict[str, Any]) -> Optional[IntentExtraction]:
        """
        按优先级依次评估规则，首个高置信度命中即返回。

        V2.2 置信度门控：
        - 置信度 >= L0_CONFIDENCE_THRESHOLD: 直接返回（确定性拦截）
        - 置信度 < L0_CONFIDENCE_THRESHOLD: 记录匹配但放行至 L1（低置信度不强制拦截）

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            命中返回 IntentExtraction，未命中返回 None
        """
        for i, rule in enumerate(self.rules):
            result = rule.evaluate(query, context)
            if result is not None:
                # 低置信度命中：记录但放行至 L1
                if result.confidence < L0_CONFIDENCE_THRESHOLD:
                    log.debug(
                        f"[L0] 规则 #{i} {rule.__class__.__name__} 低置信度命中: "
                        f"intent={result.intent.value}, conf={result.confidence}, 放行至 L1"
                    )
                    continue
                log.info(
                    f"[L0] 规则 #{i} {rule.__class__.__name__} 命中: "
                    f"intent={result.intent.value}, conf={result.confidence}"
                )
                return result
        log.debug("[L0] 所有规则未命中，放行至 L1")
        return None
