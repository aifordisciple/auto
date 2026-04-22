"""
意图路由引擎 - L0/L1/L2 三层意图识别与路由。

L0 规则拦截 → L1 DAG 解构 → L2 参数探查，三层流水线依次执行。
L0 命中则跳过 L1/L2；L1 解构后 L2 仅检查 DAG 首节点参数。

V2.1 升级要点（Phase 2）：
- IntentRouterEngine 创建 SkillParameterRegistry 实例
- L2 check_task_parameters 接收 skill_registry 参数
- 支持从 SKILL.md 动态拉取 required 参数 schema
"""
from typing import Any, Dict, Optional

from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.l2_extractor import check_task_parameters
from app.agent.router.schemas import IntentExtraction, TaskDAG, TaskNode, RouteResult
from app.services.skill_parameter_registry import SkillParameterRegistry
from app.core.logger import log


class IntentRouterEngine:
    """
    意图路由引擎。

    程序说明：
    三层流水线架构：L0 规则拦截（0 token 成本）→ L1 DAG 解构（LLM）→ L2 参数探查（确定性校验）。
    L0 命中则跳过 L1/L2，直接返回单节点 DAG。
    L1 解构后，L2 仅检查 DAG 首个节点的参数完整性，缺失时生成 ProbingRequest。
    V2.1 新增 SkillParameterRegistry，为 L2 提供动态 SKILL.md 参数 schema 查询能力。
    """

    def __init__(self, session, user_id: str):
        """
        初始化路由引擎。

        程序说明：
        创建三层流水线所需的组件实例。
        L0RuleEngine 无状态，L1Classifier 需要数据库会话解析 LLM 配置，
        SkillParameterRegistry 需要数据库会话查询技能参数定义。

        Args:
            session: 数据库会话
            user_id: 当前用户 ID
        """
        self.l0_engine = L0RuleEngine()
        self.classifier = L1Classifier(session, user_id)
        self._skill_registry = SkillParameterRegistry(session, user_id)

        log.info(
            f"[Router] 初始化引擎: user_id={user_id}, "
            f"skill_registry=enabled"
        )

    async def route(self, query: str, context: Dict[str, Any]) -> RouteResult:
        """
        执行三层意图路由。

        程序说明：
        L0 命中 → 构建单节点 DAG，跳过 L1/L2。
        L0 未命中 → L1 DAG 解构 → L2 参数探查（仅首节点）。
        L2 探查结果为 is_missing 时，RouteResult.probing 有值，
        前端需渲染 Active Probing 表单收集缺失参数。

        Args:
            query: 用户自然语言输入
            context: 前端注入的工作区上下文

        Returns:
            RouteResult: 路由结果（DAG + 可选的 ProbingRequest）
        """
        # L0: 规则拦截（0 token 成本）
        l0_result = self.l0_engine.evaluate(query, context)
        if l0_result:
            log.info(f"[Router] L0 命中: intent={l0_result.intent.value}, confidence={l0_result.confidence}")
            dag = TaskDAG(nodes=[
                TaskNode(
                    task_id="task_1",
                    intent=l0_result.intent,
                    raw_instruction=query,
                    parameters=l0_result.entities,
                )
            ])
            # L0 命中时，将 skill_id 传入 DAG 节点
            if l0_result.skill_id:
                dag.nodes[0].parameters["skill_id"] = l0_result.skill_id
            return RouteResult(dag=dag, probing=None)

        # L1: DAG 解构
        log.info(f"[Router] L0 未命中，调用 L1 解构: query='{query[:50]}...'")
        dag = await self.classifier.decompose(query, context)

        # L2: 参数探查（仅检查第一个任务节点）
        if dag.nodes:
            probing = await check_task_parameters(
                task=dag.nodes[0],
                context=context,
                skill_registry=self._skill_registry
            )
            if probing.is_missing:
                log.info(f"[Router] L2 探查命中: missing_params={probing.missing_params}")
                return RouteResult(dag=dag, probing=probing)
            else:
                log.debug("[Router] L2 探查通过，参数完整")

        return RouteResult(dag=dag, probing=None)