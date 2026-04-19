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
