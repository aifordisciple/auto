"""
L1 LLM 分类层 - 大模型结构化意图分类。

使用用户配置的 LLM（通过 get_llm_config 三级 fallback 解析），
以结构化输出方式完成意图分类和初步实体提取。

双模式：
- 本地模型（Ollama）: 采用原生异步客户端 (AsyncClient)，支持 think 模式控制和强制 JSON 输出。
- 第三方 API: with_structured_output (function calling)
"""
from typing import Any, Dict
import json
import ollama
from json_repair import repair_json

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
3. 'data_probe': 用户请求查看、预览、统计当前的数据集特征（如 h5ad 结构、fastq 质量），或者探索工作区的文件结构（如"有哪些文件"、"目录结构"、"文件列表"）。
4. 'skill_forge': 用户要求在 IDE 中真正执行/运行生信分析或 Pipeline，需要系统调度代码执行环境。关键标志：用户明确要求"跑/运行/执行/做"分析，且期望得到实际运行结果。
5. 'explicit_skill': 用户直接指定了某个技能的名称或 ID 来执行。
6. 'chat': 通用的闲聊、基础概念解释、代码示例展示。⚠️ 重要：仅请求代码/脚本/示例但不要求执行的情况（如"写一个PCA脚本"、"给我一个Seurat流程"、"怎么用Scanpy做聚类"）属于 chat，不是 skill_forge。

分析规则：
- 结合用户提供的 Context（当前选中的文件、UI 状态）进行综合判断。
- 提取明确提及的生信实体（基因名、算法包、阈值参数）。
- ⚠️ 追问条件收紧：仅当用户明确要求"执行/运行"分析（skill_forge），且同时缺失输入数据文件路径时，才将 requires_followup 设为 true。仅请求代码示例或理论解释时，即使未提及输入文件，也不追问。
- 保持客观和科学严谨，禁止主观臆测。
- confidence 反映你对意图判断的确信程度，0.0 表示完全不确定，1.0 表示绝对确定。

槽位提取规则（仅当意图为 skill_forge/explicit_skill/data_probe 时执行）：
- skill_forge: 提取 analysis_type(分析类型如DEG/clustering/trajectory), input_file(输入数据路径), tool(分析工具如Seurat/Scanpy), species(物种如human/mouse)
- explicit_skill: 提取技能执行所需的参数键值对
- data_probe: 提取 file_path(数据文件路径), probe_type(探查类型如structure/quality/statistics/workspace_scan), file_format(文件格式如h5ad/fastq/bam)。当用户询问工作区文件结构时，probe_type 为 workspace_scan
- 未提及的必需参数加入 missing_slots
- chat/diagnostic/literature 意图时 slots 和 missing_slots 留空"""


class L1Classifier:
    """
    L1 LLM 结构化意图分类器。

    从用户中心配置解析 LLM，支持本地原生模型和第三方 API 双模式。
    """

    def __init__(self, session, user_id: str):
        """
        初始化分类器。

        程序说明：
        根据用户配置初始化分类器参数，构建针对第三方 API 的 ChatOpenAI 实例。
        本地模式的客户端将在具体调用时动态生成。

        Args:
            session: 数据库会话（用于 get_llm_config 解析用户配置）
            user_id: 当前用户 ID
        """
        self.llm_config = get_llm_config(session, user_id)
        self.is_local = _is_local_model(self.llm_config.base_url)
        self.confidence_threshold = 0.7

        # 构建第三方 API 使用的 LLM 实例
        api_key = self.llm_config.api_key or "not-needed"
        self.primary_llm = ChatOpenAI(
            api_key=api_key,
            base_url=self.llm_config.base_url,
            model=self.llm_config.model_name,
            temperature=0.0
        )

        # 构建提示词模板 (仅供第三方 API 模式使用)
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", INTENT_CLASSIFICATION_PROMPT),
            ("human", "Context (Workspace State): {context}\n\nUser Query: {query}")
        ])

        log.info(
            f"[L1] 初始化分类器: model={self.llm_config.model_name}, "
            f"base_url={self.llm_config.base_url}, is_local={self.is_local}, "
            f"source={self.llm_config.source}"
        )

    async def classify(
        self,
        query: str,
        context: Dict[str, Any],
        enable_think: bool = False,
        temperature: float = 0.0
    ) -> IntentExtraction:
        """
        执行意图分类。

        程序说明：
        作为分类任务的主入口，根据配置的 LLM 环境自动路由到对应的处理引擎。
        包含参数系统，支持向下透传推理模式开关及采样温度设定。

        Args:
            query (str): 用户自然语言输入。
            context (Dict[str, Any]): 工作区上下文。
            enable_think (bool): 是否开启大模型的推理思考模式。默认值为 False。
            temperature (float): 采样温度，控制输出稳定性。默认值为 0.0。

        Returns:
            IntentExtraction: 结构化意图提取结果
        """
        log.info(f"[L1] 正在调用 LLM 分类: query='{query[:50]}...'")

        try:
            if self.is_local:
                result = await self._classify_with_json_mode(
                    query=query,
                    context=context,
                    enable_think=enable_think,
                    temperature=temperature
                )
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
        """
        第三方 API 模式：使用 with_structured_output (function calling)。
        """
        llm_with_schema = self.primary_llm.with_structured_output(IntentExtraction)
        chain = self.prompt_template | llm_with_schema
        result = await chain.ainvoke({
            "context": str(context),
            "query": query
        })
        return result

    async def _classify_with_json_mode(
        self,
        query: str,
        context: Dict[str, Any],
        enable_think: bool = False,
        temperature: float = 0.0
    ) -> IntentExtraction:
        """
        本地模型模式：原生 Ollama API + JSON mode + 手动解析。

        程序说明：
        由于 Langchain 的 ChatOpenAI 依赖于兼容 /v1 端点，无法原生支持 think 参数控制，
        此方法改用 ollama.AsyncClient 直接发起请求，确保异步性能。
        通过参数系统传入的 enable_think，在 API 层面直接关闭深度推理模型 (如 Qwen3) 的思考过程。
        利用原生 format='json' 约束，确保输出结构稳定性。

        Args:
            query (str): 用户查询。
            context (Dict[str, Any]): 上下文。
            enable_think (bool): 控制思考模式的参数。
            temperature (float): 采样温度参数。
        """
        # 提取 Ollama 服务的基础 URL，移除可能存在的 /v1 兼容后缀
        host = self.llm_config.base_url
        if host and host.endswith('/v1'):
            host = host[:-3]
        if not host:
            host = "http://localhost:11434"

        # 构建原生异步客户端
        client = ollama.AsyncClient(host=host)

        # 在提示词中追加严格的 JSON 格式要求
        # 注意：使用原生客户端时，不再需要处理 LangChain ChatPromptTemplate 的双括号转义问题
        json_instruction = (
            "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
            '{"intent": "chat|skill_forge|explicit_skill|diagnostic|literature|data_probe", '
            '"confidence": 0.0-1.0, '
            '"entities": {"key": "value"}, '
            '"skill_id": null, '
            '"requires_followup": false, '
            '"followup_question": null, '
            '"slots": {"key": "value"}, '
            '"missing_slots": []}'
        )

        system_msg = INTENT_CLASSIFICATION_PROMPT + json_instruction
        user_msg = f"Context (Workspace State): {str(context)}\n\nUser Query: {query}"

        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg}
        ]

        raw_content = ""
        try:
            # 发送 API 请求：利用原生参数控制思考模式与 JSON 格式
            response: Dict[str, Any] = await client.chat(
                model=self.llm_config.model_name,
                messages=messages,
                think=enable_think,
                format='json',
                options={
                    'temperature': temperature
                }
            )

            raw_content = response['message']['content'].strip()

            # 手动解析 JSON 响应为 IntentExtraction
            repaired = repair_json(raw_content)
            parsed = json.loads(repaired)
            return IntentExtraction(**parsed)

        except Exception as parse_err:
            log.warning(f"[L1] 本地 API 调用或 JSON 解析失败: {parse_err}, 原始响应: {raw_content[:200]}")
            return self._fallback_intent_from_text(raw_content)

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