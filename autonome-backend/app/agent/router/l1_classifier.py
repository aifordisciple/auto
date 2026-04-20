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


# L1 意图分类系统提示词（v2: 合并 L1+L2 为单次调用）
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
- confidence 反映你对意图判断的确信程度，0.0 表示完全不确定，1.0 表示绝对确定。

槽位提取规则（仅当意图为 skill_forge/explicit_skill/data_probe 时执行）：
- skill_forge: 提取 analysis_type(分析类型如DEG/clustering/trajectory), input_file(输入数据路径), tool(分析工具如Seurat/Scanpy), species(物种如human/mouse)
- explicit_skill: 提取技能执行所需的参数键值对
- data_probe: 提取 file_path(数据文件路径), probe_type(探查类型如structure/quality/statistics), file_format(文件格式如h5ad/fastq/bam)
- 未提及的必需参数加入 missing_slots
- chat/diagnostic/literature 意图时 slots 和 missing_slots 留空"""


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

        ⚠️ 修复：
        1. ChatPromptTemplate 会将花括号视为模板变量，JSON 示例中的花括号
           必须转义（{ → {{, } → }}），否则报 "Nested replacement fields" 错误。
        2. 本地 Ollama Qwen3 模型默认开启 think 模式，/v1 端点不支持 think 参数，
           通过在 prompt 开头注入 /no_think 标签禁用思考链输出。
        """
        # Qwen3 专用：/no_think 标签禁用思考链（Ollama /v1 端点不支持 think 参数）
        no_think_prefix = "/no_think\n" if self.is_local else ""

        # 在提示词中追加 JSON 格式要求（v2: 包含 slots 和 missing_slots）
        # ⚠️ 花括号必须双写转义，否则 LangChain ChatPromptTemplate 报错
        json_instruction = (
            "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
            '{{"intent": "chat|skill_forge|explicit_skill|diagnostic|literature|data_probe", '
            '"confidence": 0.0-1.0, '
            '"entities": {{"key": "value"}}, '
            '"skill_id": null, '
            '"requires_followup": false, '
            '"followup_question": null, '
            '"slots": {{"key": "value"}}, '
            '"missing_slots": []}}'
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", no_think_prefix + INTENT_CLASSIFICATION_PROMPT + json_instruction),
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
