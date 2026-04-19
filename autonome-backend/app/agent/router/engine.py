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
