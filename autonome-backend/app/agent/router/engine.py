"""
意图路由编排引擎 - 三级漏斗式管道 (V2.0)。

L0 规则拦截 (0ms) → L1 DAG 解构 (~250ms) → L2 参数探查

v2.0 升级要点：
- route() 返回 RouteResult(dag=TaskDAG, probing=Optional[ProbingRequest])
- L0 命中时：包装为单节点 TaskDAG，不需要参数探查
- L1 解构失败时：降级为 GENERAL_CHAT 单节点 DAG
- L2 仅检查 DAG 中第一个任务的参数完整性

执行流程：
1. L0 规则拦截（0ms，~30-40% 命中率）→ 单节点 TaskDAG
2. L1 DAG 解构（~250ms）→ 多节点任务图谱
3. L2 参数探查（仅检查第一个任务）→ ProbingRequest 或放行
"""
from typing import Any, Dict, Optional

from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.l2_extractor import check_task_parameters
from app.agent.router.schemas import IntentType, TaskDAG, TaskNode, RouteResult, ProbingRequest
from app.core.logger import log


class IntentRouterEngine:
    """
    意图路由编排引擎 (V2.0)。

    三级漏斗架构：L0 规则拦截 → L1 DAG 解构 → L2 参数探查。
    返回 RouteResult，包含任务图谱 (TaskDAG) 和可选的参数探查请求 (ProbingRequest)。
    """

    def __init__(self, session, user_id: str, skill_registry=None):
        """
        初始化路由引擎。

        Args:
            session: 数据库会话
            user_id: 当前用户 ID
            skill_registry: 技能注册表（用于 L2 参数探查拉取技能定义）
        """
        self.l0_engine = L0RuleEngine()
        # L1Classifier 保留类名以兼容已有导入，实际功能已升级为 DAG 解构器
        self.classifier = L1Classifier(session, user_id)
        self._skill_registry = skill_registry

    async def route(self, query: str, context: Dict[str, Any] = None) -> RouteResult:
        """
        三级漏斗路由主入口 (V2.0)。

        L0 规则拦截 (0ms) → L1 DAG 解构 (~250ms) → L2 参数探查

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            RouteResult: 包含 TaskDAG 和可选 ProbingRequest 的路由结果
        """
        context = context or {}

        # ── L0: 规则拦截 ──────────────────────────────────────
        l0_result = self.l0_engine.evaluate(query, context)
        if l0_result:
            log.info(f"[L0 命中] 意图={l0_result.intent} 置信度={l0_result.confidence}")
            # L0 命中时：包装为单节点 TaskDAG
            dag = TaskDAG(
                nodes=[TaskNode(
                    task_id="task_1",
                    intent=l0_result.intent,
                    raw_instruction=query,
                    parameters=l0_result.slots or {}
                )]
            )
            # L0 命中的意图通常不需要参数探查（如 SYSTEM_MACRO, GENERAL_CHAT）
            return RouteResult(dag=dag, probing=None)

        # ── L1: DAG 解构 ──────────────────────────────────────
        try:
            dag = await self.classifier.decompose(query, context)
            log.info(f"[L1 解构] 节点数={len(dag.nodes)} 条件分支={dag.is_conditional}")
        except Exception as e:
            log.warning(f"[L1 解构失败] 降级为 GENERAL_CHAT: {e}")
            dag = TaskDAG(
                nodes=[TaskNode(
                    task_id="task_1",
                    intent=IntentType.GENERAL_CHAT,
                    raw_instruction=query
                )]
            )

        # ── L2: 参数探查（仅检查第一个任务） ──────────────────
        if dag.nodes:
            first_task = dag.nodes[0]
            probing = await check_task_parameters(
                task=first_task,
                context=context,
                skill_registry=getattr(self, '_skill_registry', None)
            )
            if probing.is_missing:
                log.info(f"[L2 探查] 参数缺失: {probing.missing_params}")
                return RouteResult(dag=dag, probing=probing)

        return RouteResult(dag=dag, probing=None)
