"""
方法提取器 - 从成功会话中提取抽象化方法

核心功能:
1. LLM 提取方法论
2. 自动脱敏处理
3. 隐私二次验证
4. 生成结构化候选

这是系统学习层的核心组件，负责从用户对话中识别和提取
可复用的方法论，同时确保不包含任何用户敏感数据。

使用方式:
    from app.services.system_learning.method_extractor import get_method_extractor

    extractor = get_method_extractor(llm_client)
    candidates = extractor.extract_from_session(messages, session_id)
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import json
import os

from app.core.logger import log
from app.services.system_learning.privacy_validator import get_privacy_validator


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class MethodCandidate:
    """
    方法候选数据结构

    从会话中提取的可复用方法论，经隐私验证后可存入技能库。

    属性:
        method_type: 方法类型 (analysis_strategy | error_fix | execution_opt)
        name: 方法名称（抽象化）
        description: 方法描述（脱敏）
        instructions: 可执行指令模板（Markdown格式）
        triggers: 触发关键词列表
        tags: 标签列表
        examples: 示例列表
        confidence: 提取置信度
        source_session: 来源会话ID

    示例:
        >>> candidate = MethodCandidate(
        ...     method_type="analysis_strategy",
        ...     name="差异表达分析策略",
        ...     description="RNA-seq差异分析的标准流程",
        ...     instructions="# 目标\\n执行DESeq2差异分析...",
        ...     triggers=["DESeq2", "差异分析", "count矩阵"],
        ...     tags=["transcriptomics", "rnaseq"],
        ...     confidence=0.85
        ... )
    """
    method_type: str  # analysis_strategy | error_fix | execution_opt
    name: str
    description: str
    instructions: str  # Markdown 格式
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    confidence: float = 0.6
    source_session: Optional[str] = None


# ============================================================================
# LLM 提取提示词
# ============================================================================

EXTRACTION_SYSTEM_PROMPT = """你是 AUTONOME 系统的方法提取专家。

任务：从对话中提取可复用的方法论。

【隐私规则 - 必须遵守】
- 禁止提取用户数据内容（基因序列、样本名、具体数值、项目名称）
- 禁止提取项目路径或文件名
- 禁止提取组织/团队/个人信息
- 仅提取：分析策略、参数推荐模式、错误处理逻辑

【提取要求】
1. method_type: analysis_strategy（分析方法） | error_fix（错误修复） | execution_opt（执行优化）
2. name: 抽象化名称（如"差异表达分析策略"而非"小鼠肝脏RNA-seq分析"）
3. triggers: 触发关键词（如"DESeq2"、"差异分析"、"count矩阵"）
4. instructions: 可执行指令模板（Markdown格式，包含 # 目标、# 约束、# 步骤）
5. examples: 抽象输入输出模式（用 {{value}} 替代具体值）

【输出格式】严格 JSON：
{
  "skills": [{
    "method_type": "analysis_strategy",
    "name": "技能名称",
    "description": "简要描述",
    "prompt": "# 目标\\n...\\n# 约束\\n...\\n# 步骤\\n...",
    "triggers": ["关键词1", "关键词2"],
    "tags": ["标签1", "标签2"],
    "confidence": 0.8
  }]
}

如果对话不包含可复用的方法论，返回 {"skills": []}"""

EXTRACTION_USER_PROMPT = """请从以下对话中提取方法论：

【会话内容】
{conversation}

【用户主要问题】
{primary_questions}

请提取可复用的方法论，返回 JSON 格式。"""


# ============================================================================
# 方法提取器
# ============================================================================

class MethodExtractor:
    """
    方法提取器

    核心职责:
    1. 格式化会话内容供 LLM 分析
    2. 调用 LLM 提取方法论候选
    3. 解析和验证提取结果
    4. 通过隐私验证器确保内容安全

    使用示例:
        >>> from langchain_openai import ChatOpenAI
        >>> llm = ChatOpenAI(model="gpt-4")
        >>> extractor = MethodExtractor(llm)
        >>> candidates = extractor.extract_from_session(messages, "session_001")
    """

    # 配置常量
    MAX_CONTENT_LENGTH = 2000  # 单条消息最大长度
    MAX_QUESTIONS = 5  # 最多提取的问题数

    def __init__(self, llm_client=None):
        """
        初始化提取器

        Args:
            llm_client: LLM 客户端（LangChain ChatOpenAI 或类似）
        """
        self.llm_client = llm_client
        self.privacy_validator = get_privacy_validator()

    def extract_from_session(
        self,
        session_messages: List[Dict[str, str]],
        session_id: Optional[str] = None
    ) -> List[MethodCandidate]:
        """
        从会话中提取方法候选

        提取流程:
        1. 格式化对话内容
        2. 提取用户问题
        3. 调用 LLM 进行提取
        4. 解析提取结果
        5. 隐私验证

        Args:
            session_messages: 消息列表 [{"role": "user|assistant", "content": "..."}]
            session_id: 会话ID（用于追踪）

        Returns:
            List[MethodCandidate]: 提取的方法候选列表
        """
        if not session_messages:
            log.debug("会话消息为空，跳过提取")
            return []

        log.info(f"开始从会话 {session_id} 提取方法论，共 {len(session_messages)} 条消息")

        # -------------------------------------------------------------------------
        # 1. 准备对话内容
        # -------------------------------------------------------------------------
        conversation = self._format_conversation(session_messages)
        primary_questions = self._extract_user_questions(session_messages)

        # -------------------------------------------------------------------------
        # 2. 调用 LLM 提取
        # -------------------------------------------------------------------------
        try:
            extraction_result = self._call_llm(conversation, primary_questions)
        except Exception as e:
            log.error(f"LLM 提取失败: {e}")
            return []

        # -------------------------------------------------------------------------
        # 3. 解析结果
        # -------------------------------------------------------------------------
        candidates = self._parse_extraction(extraction_result, session_id)

        if not candidates:
            log.info(f"会话 {session_id} 未提取到有效方法论")
            return []

        # -------------------------------------------------------------------------
        # 4. 隐私验证
        # -------------------------------------------------------------------------
        valid_candidates = []
        for candidate in candidates:
            is_valid, errors = self.privacy_validator.validate_candidate({
                "name": candidate.name,
                "description": candidate.description,
                "instructions": candidate.instructions,
                "triggers": candidate.triggers,
                "tags": candidate.tags
            })

            if is_valid:
                valid_candidates.append(candidate)
                log.info(f"方法候选验证通过: {candidate.name}")
            else:
                log.warning(f"方法候选隐私验证失败: {errors}")

        log.info(f"会话 {session_id} 提取完成: {len(valid_candidates)} 个有效候选")
        return valid_candidates

    def _format_conversation(self, messages: List[Dict]) -> str:
        """
        格式化对话内容

        将消息列表转换为适合 LLM 分析的文本格式。
        截断过长内容以控制 token 消耗。

        Args:
            messages: 消息列表

        Returns:
            str: 格式化的对话文本
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # 截断过长内容
            if len(content) > self.MAX_CONTENT_LENGTH:
                content = content[:self.MAX_CONTENT_LENGTH] + "...(truncated)"

            # 角色标签
            role_label = "[用户]" if role == "user" else "[助手]"
            lines.append(f"{role_label}: {content}")

        return "\n\n".join(lines)

    def _extract_user_questions(self, messages: List[Dict]) -> str:
        """
        提取用户问题

        收集用户消息作为主要问题列表。
        用于帮助 LLM 理解会话意图。

        Args:
            messages: 消息列表

        Returns:
            str: 用户问题文本
        """
        questions = []
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."
                questions.append(content)

        return "\n".join(questions[:self.MAX_QUESTIONS])

    def _call_llm(self, conversation: str, primary_questions: str) -> Dict:
        """
        调用 LLM 进行提取

        Args:
            conversation: 格式化的对话内容
            primary_questions: 用户问题列表

        Returns:
            Dict: 提取结果字典
        """
        if self.llm_client is None:
            log.warning("LLM 客户端未配置，跳过提取")
            return {"skills": []}

        user_prompt = EXTRACTION_USER_PROMPT.format(
            conversation=conversation,
            primary_questions=primary_questions
        )

        try:
            response = self.llm_client.invoke([
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ])

            content = response.content if hasattr(response, 'content') else str(response)

            # 解析 JSON
            content = content.strip()

            # 清理可能的 markdown 代码块
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]

            if content.endswith("```"):
                content = content[:-3]

            content = content.strip()
            result = json.loads(content)

            log.debug(f"LLM 返回 {len(result.get('skills', []))} 个候选")
            return result

        except json.JSONDecodeError as e:
            log.error(f"JSON 解析失败: {e}")
            return {"skills": []}
        except Exception as e:
            log.error(f"LLM 调用失败: {e}")
            return {"skills": []}

    def _parse_extraction(
        self,
        result: Dict,
        session_id: Optional[str] = None
    ) -> List[MethodCandidate]:
        """
        解析提取结果

        将 LLM 返回的 JSON 解析为 MethodCandidate 对象列表。

        Args:
            result: LLM 返回的结果字典
            session_id: 会话ID

        Returns:
            List[MethodCandidate]: 方法候选列表
        """
        candidates = []

        skills = result.get("skills", [])
        for skill in skills:
            if not isinstance(skill, dict):
                continue

            # 验证必要字段
            name = skill.get("name", "").strip()
            # 支持 prompt 或 instructions 字段
            instructions = skill.get("prompt", skill.get("instructions", "")).strip()

            if not name or not instructions:
                log.debug(f"跳过无效候选: name={name[:20] if name else 'empty'}")
                continue

            candidate = MethodCandidate(
                method_type=skill.get("method_type", "analysis_strategy"),
                name=name,
                description=skill.get("description", name),
                instructions=instructions,
                triggers=skill.get("triggers", []),
                tags=skill.get("tags", []),
                examples=skill.get("examples", []),
                confidence=float(skill.get("confidence", 0.6)),
                source_session=session_id
            )
            candidates.append(candidate)

        return candidates


# ============================================================================
# 全局单例管理
# ============================================================================

_extractor: Optional[MethodExtractor] = None


def get_method_extractor(llm_client=None) -> MethodExtractor:
    """
    获取方法提取器单例

    Args:
        llm_client: LLM 客户端（可选，首次调用时传入）

    Returns:
        MethodExtractor: 方法提取器实例

    使用示例:
        >>> from langchain_openai import ChatOpenAI
        >>> llm = ChatOpenAI(model="gpt-4")
        >>> extractor = get_method_extractor(llm)
    """
    global _extractor
    if _extractor is None:
        _extractor = MethodExtractor(llm_client)
        log.info("方法提取器单例已初始化")
    return _extractor


def reset_method_extractor() -> None:
    """
    重置方法提取器单例

    用于测试或需要重新初始化的场景。
    """
    global _extractor
    _extractor = None
    log.debug("方法提取器单例已重置")