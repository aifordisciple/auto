"""
意图路由编排引擎 - 组合 L0/L1 的漏斗式管道。

v2: L1+L2 合并为单次 LLM 结构化输出调用。
- L1 prompt 包含条件性槽位提取指令
- IntentExtraction schema 扩展了 slots/missing_slots 字段
- 消除 L2 串行调用，TTFB 降低 ~200ms

执行流程：
1. L0 规则拦截（0ms，~30-40% 命中率）
2. L1 LLM 结构化分类 + 条件性槽位提取（~250ms，合并原 L1+L2）
3. 上下文自动填充（从 workspace context 注入已知参数）
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

    v2: L1+L2 合并为单次调用，L2SlotExtractor 仅保留上下文自动填充逻辑。
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
        # L2 仅保留上下文自动填充逻辑，不再做独立 LLM 调用
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

        # Step 2: L1 合并分类 + 槽位提取（单次 LLM 调用）
        # v2: L1 prompt 已包含条件性槽位提取指令，IntentExtraction schema 包含 slots/missing_slots
        result = await self.l1.classify(query, context)
        log.info(
            f"[Engine] L1 结果: intent={result.intent.value}, "
            f"confidence={result.confidence}, "
            f"slots={result.slots_ids if hasattr(result, 'slot_ids') else result.slots}"
        )

        # Step 3: 上下文自动填充（从 workspace context 注入已知参数，替代原 L2 的 _enrich_from_context）
        if result.intent in L2SlotExtractor.EXTRACTION_INTENTS:
            context_enrichments = self.l2._enrich_from_context(result.intent, context)
            # 合并：LLM 提取的 slots 优先，上下文填充补充缺失项
            for key, value in context_enrichments.items():
                if key not in result.slots:
                    result.slots[key] = value
            # 同时合并到 entities，保持下游兼容
            result.entities = {
                **result.entities,
                **result.slots,
                **context_enrichments,
            }
            log.info(f"[Engine] 上下文填充: enrichments={context_enrichments}")

        # Step 4: 置信度降级保护
        if result.confidence < self.confidence_threshold:
            log.warning(f"[Engine] 置信度过低 ({result.confidence})，降级为 chat")
            result.intent = IntentType.CHAT

        # Step 5: 计算 routing_target
        result.routing_target = INTENT_NODE_MAP[result.intent]

        log.info(f"[Engine] 最终路由: intent={result.intent.value}, target={result.routing_target}")
        return result
