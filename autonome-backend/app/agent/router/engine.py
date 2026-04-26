"""
意图路由引擎 - L0/L1/L2 三层意图识别与路由。

L0 规则拦截 → L1 DAG 解构 → L2 参数探查，三层流水线依次执行。
L0 命中则跳过 L1/L2；L1 解构后 L2 仅检查 DAG 首节点参数。

V2.1 升级要点（Phase 2）：
- IntentRouterEngine 创建 SkillParameterRegistry 实例
- L2 check_task_parameters 接收 skill_registry 参数
- 支持从 SKILL.md 动态拉取 required 参数 schema

V2.0 升级要点（L1 结构化上下文增强）：
- 新增 get_skill_summary 方法：向量搜索优先获取 Top-K 相关技能，全量回退兜底
- route() 方法在调用 L1 解构前注入技能摘要，提升 INTENT_EXPLICIT_EXEC 识别准确率
"""
from typing import Any, Dict, Optional
import os
from pathlib import Path

from app.agent.router.l0_rules import L0RuleEngine
from app.agent.router.l1_classifier import L1Classifier
from app.agent.router.l2_extractor import check_task_parameters
from app.agent.router.schemas import IntentExtraction, TaskDAG, TaskNode, RouteResult, IntentType, ProbingRequest
from app.services.skill_parameter_registry import SkillParameterRegistry
from app.core.config import settings
from app.core.logger import log


def _validate_resolved_assets(dag: TaskDAG, context: Dict[str, Any]) -> TaskDAG:
    """
    Phase 6: 验证 L1 指代消解结果中的 resolved_assets 是否有效。

    程序说明：
    L1 LLM 可能幻觉出不存在的 asset ID。此函数将 resolved_assets 与
    workspace context 中实际存在的文件进行交叉校验，移除无效 ID。
    如果所有 ID 都被移除，降级使用 active_file。

    Args:
        dag: L1 解构产生的 TaskDAG
        context: 前端注入的工作区上下文

    Returns:
        校验后的 TaskDAG（可能修改了 resolved_assets）
    """
    # 收集所有有效的文件标识符（ID 和名称均可匹配）
    valid_ids: set = set()
    context_files = context.get("context_files") or []
    for f in context_files:
        if isinstance(f, dict):
            fid = f.get("id", "")
            fname = f.get("name", "")
            if fid:
                valid_ids.add(fid)
            if fname:
                valid_ids.add(fname)
        elif isinstance(f, str):
            valid_ids.add(f)

    # 同时加入 active_file
    active_file = context.get("active_file")
    if active_file:
        valid_ids.add(active_file)

    for node in dag.nodes:
        if not node.resolved_assets:
            continue
        filtered = [a for a in node.resolved_assets if a in valid_ids]
        if len(filtered) != len(node.resolved_assets):
            removed = set(node.resolved_assets) - set(filtered)
            log.warning(
                f"[Router] 指代消解校验: node={node.task_id}, "
                f"移除无效 assets={removed}, 保留={filtered}"
            )
        if not filtered and active_file:
            # 所有 ID 都无效，降级使用 active_file
            filtered = [active_file]
            log.info(f"[Router] 指代消解校验: node={node.task_id} 全部失效，降级为 active_file={active_file}")
        node.resolved_assets = filtered

    return dag


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

    async def get_skill_summary(self, query: str) -> str:
        """
        获取与用户查询最相关的技能摘要文本，用于注入 L1 提示词。

        程序说明：
        两级策略：优先通过语义搜索引擎（向量检索）获取 Top-K 相关技能，
        获取更精准的技能匹配结果；若语义搜索不可用则回退到全量技能列表，
        取前 50 个技能并截断至 2000 字符，避免提示词过长。
        任何异常均返回"无可用技能"，确保路由流程不中断。

        Args:
            query: 用户自然语言输入

        Returns:
            技能摘要文本，格式为 "skill_id: name - description" 逐行排列
        """
        try:
            # 策略1：向量语义搜索优先（Top-K=12，精准匹配）
            from app.mcp.semantic_search import get_semantic_engine, is_semantic_available
            if is_semantic_available():
                engine = get_semantic_engine()
                if engine._initialized:
                    results = engine.search(query, top_k=12)
                    if results:
                        # 从语义索引中获取技能名称和描述
                        lines = []
                        for skill_id, score in results:
                            entry = engine._index.get(skill_id)
                            if entry:
                                lines.append(f"{skill_id}: {entry.name} - {entry.description}")
                        if lines:
                            summary = "\n".join(lines)
                            log.info(
                                f"[Router] 技能摘要（向量搜索）: {len(lines)} 个技能, "
                                f"长度={len(summary)}"
                            )
                            return summary

            # 策略2：全量回退（最多 50 个技能，截断 2000 字符）
            from app.core.skill_parser import get_skill_parser
            parser = get_skill_parser()
            all_skills = parser.get_all_skills()
            lines = []
            for skill in all_skills[:50]:
                metadata = skill.get("metadata", {})
                skill_id = metadata.get("skill_id", "unknown")
                name = metadata.get("name", "")
                description = metadata.get("description", "")
                lines.append(f"{skill_id}: {name} - {description}")
            if lines:
                summary = "\n".join(lines)[:2000]
                log.info(
                    f"[Router] 技能摘要（全量回退）: {len(lines)} 个技能, "
                    f"长度={len(summary)}"
                )
                return summary

            return "无可用技能"

        except Exception as e:
            log.warning(f"[Router] 获取技能摘要失败: {e}")
            return "无可用技能"

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

            # Phase 6: L0 DATA_PROBE 命中时验证 active_file 是否存在
            if l0_result.intent == IntentType.DATA_PROBE:
                active_file = context.get("active_file")
                if active_file:
                    project_id = context.get("project_id")
                    if project_id:
                        project_dir = str(Path(settings.UPLOAD_DIR) / f"project_{project_id}")
                        abs_path = active_file if os.path.isabs(active_file) else os.path.join(project_dir, active_file.lstrip("/"))
                        if not os.path.exists(abs_path):
                            log.info(f"[Router] L0 DATA_PROBE: active_file 不存在 ({active_file})，触发探查")
                            probing = ProbingRequest(
                                is_missing=True,
                                missing_params=["input_file"],
                                ui_schema={
                                    "type": "object",
                                    "properties": {
                                        "input_file": {
                                            "type": "string",
                                            "title": "目标文件",
                                            "description": "请选择或输入要探查的文件路径"
                                        }
                                    },
                                    "required": ["input_file"]
                                },
                                message_to_user=f"之前使用的文件 {active_file} 似乎已不可用，请重新选择要探查的文件：",
                            )
                            return RouteResult(dag=dag, probing=probing)

            return RouteResult(dag=dag, probing=None)

        # L1: DAG 解构
        log.info(f"[Router] L0 未命中，调用 L1 解构: query='{query[:80]}...'")
        # V2.0: 注入技能摘要，增强 L1 对 INTENT_EXPLICIT_EXEC 的识别能力
        skill_summary = await self.get_skill_summary(query)
        dag = await self.classifier.decompose(query, context, skill_summary=skill_summary)

        # V2.2: 记录 L1 解构结果摘要，便于排查误分类
        if dag.nodes:
            node_intents = [n.intent.value for n in dag.nodes]
            log.info(f"[Router] L1 解构完成: nodes={len(dag.nodes)}, intents={node_intents}")

        # Phase 6: 验证指代消解结果中的 resolved_assets 是否有效
        dag = _validate_resolved_assets(dag, context)

        # L2: 参数探查（Phase 7升级：检查所有任务节点，首个缺失即返回）
        if dag.nodes:
            for node in dag.nodes:
                probing = await check_task_parameters(
                    task=node,
                    context=context,
                    skill_registry=self._skill_registry
                )
                if probing.is_missing:
                    log.info(
                        f"[Router] L2 探查命中: node={node.task_id}, "
                        f"intent={node.intent.value}, missing_params={probing.missing_params}"
                    )
                    return RouteResult(dag=dag, probing=probing)
            log.debug("[Router] L2 探查通过，所有节点参数完整")

        return RouteResult(dag=dag, probing=None)