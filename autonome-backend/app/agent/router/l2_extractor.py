"""
L2 参数探查层 - Active Probing 主动拦截机制。

当 L1 解构器输出的 TaskNode 缺失关键参数时，
L2 挂起路由并生成 ProbingRequest（含 JSON Schema 表单定义），
供前端渲染 Generative UI 表单，用户补全参数后恢复执行。

V2.0 升级要点：
- LLM 调用已消除，仅保留上下文自动填充 + 参数完整性校验
- 新增 ProbingRequest 生成逻辑，支持前端 Generative UI 表单
- 仅对 EXPLICIT_EXEC 和 SKILL_FORGE 意图执行参数探查

历史说明：
- V1.0 中 L2 使用 LLM 提取槽位（SKILL_FORGE / EXPLICIT_SKILL / DATA_PROBE 三个意图）
- V2.0 将 LLM 提取合并到 L1，L2 退化为纯确定性校验 + ProbingRequest 生成
- 意图从 EXPLICIT_SKILL 更名为 EXPLICIT_EXEC，DATA_PROBE 不再需要 L2 探查
"""
from typing import Any, Dict, Set

from app.agent.router.schemas import IntentType, TaskNode, ProbingRequest
from app.core.logger import log


class L2SlotExtractor:
    """
    L2 参数探查器。

    仅对需要参数校验的意图执行 Active Probing，其余放行。

    保留类结构以维持 PROBING_INTENTS 和 ENRICHMENT_INTENTS 两个类属性，
    供外部模块引用意图集合配置。
    """

    # 需要 L2 探查的意图集合（仅这两个意图需要参数完整性校验）
    PROBING_INTENTS: Set[IntentType] = {
        IntentType.EXPLICIT_EXEC,
        IntentType.SKILL_FORGE,
    }

    # 需要 L2 上下文自动填充的意图集合（比探查集合宽，DATA_PROBE 也需要自动注入文件）
    ENRICHMENT_INTENTS: Set[IntentType] = {
        IntentType.SKILL_FORGE,
        IntentType.EXPLICIT_EXEC,
        IntentType.DATA_PROBE,
    }


async def check_task_parameters(
    task: TaskNode,
    context: Dict[str, Any],
    skill_registry: Any = None
) -> ProbingRequest:
    """
    L2 层核心逻辑：对齐系统参数，探测缺失项。

    执行流程：
    1. 判断意图是否需要探查（PROBING_INTENTS），不需要则直接放行
    2. 尝试从工作区上下文自动填充参数（ENRICHMENT_INTENTS）
    3. 根据意图类型调用对应的参数完整性检查

    Args:
        task: L1 解构器输出的 TaskNode
        context: 工作区上下文（含 active_file、selected_cells 等）
        skill_registry: 技能注册表（用于拉取 schema.yaml 的 required 参数）

    Returns:
        ProbingRequest: 参数探查结果
            - is_missing=False: 参数完整，可放行
            - is_missing=True: 参数缺失，前端需渲染表单收集
    """
    if task.intent not in L2SlotExtractor.PROBING_INTENTS:
        log.debug(f"[L2] 意图 {task.intent.value} 无需探查，放行")
        return ProbingRequest(is_missing=False)

    # 先尝试上下文自动填充
    enrichments = _enrich_from_context(task.intent, context)
    # 合并参数：task.parameters 为 L1 提取的初值，enrichments 为上下文补充值
    merged_params = {**task.parameters, **enrichments}

    log.info(f"[L2] 探查意图 {task.intent.value}，合并参数: {list(merged_params.keys())}")

    # EXPLICIT_EXEC 意图：从 skill_registry 拉取 required 参数
    if task.intent == IntentType.EXPLICIT_EXEC:
        return await _check_explicit_exec_params(task, merged_params, skill_registry)

    # SKILL_FORGE 意图：检查关键分析参数
    if task.intent == IntentType.SKILL_FORGE:
        return _check_skill_forge_params(task, merged_params)

    return ProbingRequest(is_missing=False)


async def _check_explicit_exec_params(
    task: TaskNode,
    merged_params: Dict[str, Any],
    skill_registry: Any
) -> ProbingRequest:
    """
    检查显式技能执行的参数完整性。

    阶段一：使用通用关键参数检查（species、input_file）
    阶段二（待实现）：从 skill_registry 拉取 schema.yaml 的 required 参数，
                     根据技能定义动态生成 ui_schema 表单

    Args:
        task: L1 解构器输出的 TaskNode
        merged_params: 已合并上下文自动填充的参数
        skill_registry: 技能注册表（阶段二使用）

    Returns:
        ProbingRequest: 参数探查结果
    """
    # 阶段一：通用关键参数检查
    required_keys = ["species", "input_file"]
    missing = [key for key in required_keys if key not in merged_params or not merged_params[key]]

    if missing:
        log.info(f"[L2] EXPLICIT_EXEC 缺失参数: {missing}")
        return ProbingRequest(
            is_missing=True,
            missing_params=missing,
            ui_schema={
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "title": "物种 (Species)",
                        "enum": ["Human", "Mouse", "Rat", "Zebrafish"],
                        "default": "Human"
                    },
                    "input_file": {
                        "type": "string",
                        "title": "输入文件路径",
                    }
                },
                "required": missing
            },
            message_to_user="执行该分析需要补充以下核心参数，请确认："
        )

    # 阶段二：从 skill_registry 获取技能定义的 required 参数
    # TODO: 当 skill_registry 接口就绪后，根据 task.parameters.get("skill_id")
    #       拉取 SKILL.md 的动态参数定义，生成对应的 ui_schema
    # if skill_registry and task.parameters.get("skill_id"):
    #     skill_schema = await skill_registry.get_skill_schema(task.parameters["skill_id"])
    #     ...

    log.debug("[L2] EXPLICIT_EXEC 参数完整，放行")
    return ProbingRequest(is_missing=False)


def _check_skill_forge_params(
    task: TaskNode,
    merged_params: Dict[str, Any]
) -> ProbingRequest:
    """
    检查代码锻造的关键参数。

    代码锻造对 species 和 input_file 的要求较宽松（可用示例数据），
    仅在明确需要特定物种时才追问。当前实现直接放行。

    Args:
        task: L1 解构器输出的 TaskNode
        merged_params: 已合并上下文自动填充的参数

    Returns:
        ProbingRequest: 参数探查结果（当前始终放行）
    """
    # 代码锻造场景下，缺失参数不会阻塞执行（可使用示例数据兜底）
    # 未来可根据 SKILL.md 定义增加更精细的参数探查
    log.debug("[L2] SKILL_FORGE 参数检查通过（宽松模式），放行")
    return ProbingRequest(is_missing=False)


def _enrich_from_context(
    intent: IntentType, context: Dict[str, Any]
) -> Dict[str, str]:
    """
    从工作区上下文自动填充参数。

    当上下文中存在 active_file 时，自动注入为 input_file。
    当存在 selected_cells 时，注入为 cell_count。
    仅对 ENRICHMENT_INTENTS 中的意图执行自动填充。

    Args:
        intent: 当前意图类型
        context: 前端注入的工作区上下文

    Returns:
        自动填充的参数键值对
    """
    enrichments: Dict[str, str] = {}

    if intent in L2SlotExtractor.ENRICHMENT_INTENTS:
        active_file = context.get("active_file")
        if active_file:
            enrichments["input_file"] = active_file

        selected_cells = context.get("selected_cells")
        if selected_cells:
            enrichments["cell_count"] = str(selected_cells)

    return enrichments
