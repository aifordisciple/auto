"""
L2 参数探查层 - Active Probing 主动拦截机制。

当 L1 解构器输出的 TaskNode 缺失关键参数时，
L2 挂起路由并生成 ProbingRequest（含 JSON Schema 表单定义），
供前端渲染 Generative UI 表单，用户补全参数后恢复执行。

V2.0 升级要点：
- LLM 调用已消除，仅保留上下文自动填充 + 参数完整性校验
- 新增 ProbingRequest 生成逻辑，支持前端 Generative UI 表单
- 扩展探查意图：EXPLICIT_EXEC + SKILL_FORGE + DATA_PROBE + LITERATURE_MINING

V2.1 升级要点（Phase 2）：
- EXPLICIT_EXEC 支持从 SkillParameterRegistry 动态拉取 SKILL.md 参数 schema
- 无 skill_id 时降级为通用 species/input_file 检查（向后兼容）
- 新增 DATA_PROBE 和 LITERATURE_MINING 的参数探查逻辑

历史说明：
- V1.0 中 L2 使用 LLM 提取槽位（SKILL_FORGE / EXPLICIT_SKILL / DATA_PROBE 三个意图）
- V2.0 将 LLM 提取合并到 L1，L2 退化为纯确定性校验 + ProbingRequest 生成
- 意图从 EXPLICIT_SKILL 更名为 EXPLICIT_EXEC
- V2.1 扩展探查意图至 4 种，并接入 SkillParameterRegistry 动态 schema
"""
from typing import Any, Dict, Optional, Set

from app.agent.router.schemas import IntentType, TaskNode, ProbingRequest
from app.core.logger import log


class L2SlotExtractor:
    """
    L2 参数探查器。

    仅对需要参数校验的意图执行 Active Probing，其余放行。

    保留类结构以维持 PROBING_INTENTS 和 ENRICHMENT_INTENTS 两个类属性，
    供外部模块引用意图集合配置。
    """

    # 需要 L2 探查的意图集合（V2.1 扩展至 4 种意图）
    PROBING_INTENTS: Set[IntentType] = {
        IntentType.EXPLICIT_EXEC,       # 技能执行：检查 skill schema required 参数
        IntentType.SKILL_FORGE,         # 代码锻造：宽松检查（允许示例数据替代）
        IntentType.DATA_PROBE,          # 数据探查：检查 input_file / active_file
        IntentType.LITERATURE_MINING,   # 文献挖掘：检查 pdf_file / doi
    }

    # 需要 L2 上下文自动填充的意图集合（比探查集合宽，DATA_PROBE 也需要自动注入文件）
    ENRICHMENT_INTENTS: Set[IntentType] = {
        IntentType.SKILL_FORGE,
        IntentType.EXPLICIT_EXEC,
        IntentType.DATA_PROBE,
        IntentType.LITERATURE_MINING,
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
        skill_registry: SkillParameterRegistry 实例（用于拉取 SKILL.md 的 required 参数）

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

    # EXPLICIT_EXEC 意图：从 SkillParameterRegistry 拉取 required 参数
    if task.intent == IntentType.EXPLICIT_EXEC:
        return await _check_explicit_exec_params(task, merged_params, skill_registry)

    # SKILL_FORGE 意图：检查关键分析参数（宽松模式）
    if task.intent == IntentType.SKILL_FORGE:
        return _check_skill_forge_params(task, merged_params)

    # DATA_PROBE 意图：检查数据文件目标
    if task.intent == IntentType.DATA_PROBE:
        return _check_data_probe_params(task, context)

    # LITERATURE_MINING 意图：检查文献文档目标
    if task.intent == IntentType.LITERATURE_MINING:
        return _check_literature_params(task, context)

    return ProbingRequest(is_missing=False)


async def _check_explicit_exec_params(
    task: TaskNode,
    merged_params: Dict[str, Any],
    skill_registry: Any
) -> ProbingRequest:
    """
    检查显式技能执行的参数完整性。

    程序说明：
    V2.1 双模式参数探查：
    - 模式 1（动态 schema）：当 skill_id 存在且 skill_registry 可用时，
      从 SKILL.md 的 parameters_schema 动态拉取 required 参数，
      生成对应的前端 JSON Schema 表单。这是主要模式。
    - 模式 2（通用 fallback）：当无 skill_id 或 skill_registry 不可用时，
      降级为通用的 species + input_file 检查，确保向后兼容。

    Args:
        task: L1 解构器输出的 TaskNode
        merged_params: 已合并上下文自动填充的参数
        skill_registry: SkillParameterRegistry 实例

    Returns:
        ProbingRequest: 参数探查结果
    """
    # 模式 1：动态 schema 查询（V2.1 新增）
    skill_id = task.parameters.get("skill_id") or merged_params.get("skill_id")
    if skill_id and skill_registry is not None:
        try:
            schema = await skill_registry.get_parameters_schema(skill_id)
            if schema and schema.get("required"):
                # 检查 merged_params 中是否包含所有 required 参数
                missing = [p for p in schema["required"] if not merged_params.get(p)]
                if missing:
                    # 从技能 schema 动态构建前端表单
                    ui_schema = await skill_registry.build_ui_schema(skill_id, missing)
                    log.info(f"[L2] EXPLICIT_EXEC 动态探查: skill_id={skill_id}, 缺失参数={missing}")
                    return ProbingRequest(
                        is_missing=True,
                        missing_params=missing,
                        ui_schema=ui_schema,
                        message_to_user=f"执行技能 {skill_id} 需要补充以下参数："
                    )
                # 所有必填参数已齐备，放行
                log.debug(f"[L2] EXPLICIT_EXEC 动态探查: skill_id={skill_id}, 参数完整，放行")
                return ProbingRequest(is_missing=False)
        except Exception as e:
            log.warning(f"[L2] EXPLICIT_EXEC 动态探查失败，降级为通用检查: skill_id={skill_id}, error={e}")

    # 模式 2：通用关键参数检查（fallback，向后兼容 V2.0）
    required_keys = ["species", "input_file"]
    missing = [key for key in required_keys if key not in merged_params or not merged_params[key]]

    if missing:
        log.info(f"[L2] EXPLICIT_EXEC 通用探查缺失参数: {missing}")
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

    log.debug("[L2] EXPLICIT_EXEC 通用探查参数完整，放行")
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


def _check_data_probe_params(
    task: TaskNode,
    context: Dict[str, Any]
) -> ProbingRequest:
    """
    检查数据探查的参数完整性。

    程序说明：
    数据探查分两种子意图：
    1. workspace_scan（工作区扫描）：扫描整个目录结构，无需 input_file
    2. 文件探查（inspect/peek）：需要 input_file 或 active_file 指定目标文件

    当 probe_type 为 workspace_scan 时直接放行，否则检查文件目标是否存在。

    Args:
        task: L1 解构器输出的 TaskNode
        context: 工作区上下文

    Returns:
        ProbingRequest: 参数探查结果
    """
    # 工作区扫描子意图：无需 input_file，直接放行
    probe_type = task.parameters.get("probe_type")
    if probe_type == "workspace_scan":
        log.debug("[L2] DATA_PROBE workspace_scan 子意图，无需 input_file，放行")
        return ProbingRequest(is_missing=False)

    # 文件探查子意图：需要 input_file 或 active_file
    has_file = task.parameters.get("input_file") or context.get("active_file")
    if not has_file:
        log.info("[L2] DATA_PROBE 缺失文件目标")
        return ProbingRequest(
            is_missing=True,
            missing_params=["input_file"],
            ui_schema={
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "title": "数据文件路径",
                        "hint": "请输入文件路径"
                    }
                },
                "required": ["input_file"]
            },
            message_to_user="数据探查需要指定目标文件，请选择或输入文件路径："
        )
    log.debug("[L2] DATA_PROBE 参数完整，放行")
    return ProbingRequest(is_missing=False)


def _check_literature_params(
    task: TaskNode,
    context: Dict[str, Any]
) -> ProbingRequest:
    """
    检查文献挖掘的参数完整性。

    程序说明：
    文献挖掘需要文档目标（pdf_file、doi 或 active_file）。
    如果都不存在，生成 ProbingRequest 要求用户上传或指定文献。
    doi 字段为可选，提供 DOI 链接作为替代输入方式。

    Args:
        task: L1 解构器输出的 TaskNode
        context: 工作区上下文

    Returns:
        ProbingRequest: 参数探查结果
    """
    has_doc = (
        task.parameters.get("pdf_file")
        or task.parameters.get("doi")
        or context.get("active_file")
    )
    if not has_doc:
        log.info("[L2] LITERATURE_MINING 缺失文献目标")
        return ProbingRequest(
            is_missing=True,
            missing_params=["pdf_file"],
            ui_schema={
                "type": "object",
                "properties": {
                    "pdf_file": {
                        "type": "string",
                        "title": "文献文件 (PDF)",
                        "hint": "请输入文件路径"
                    },
                    "doi": {
                        "type": "string",
                        "title": "DOI 链接 (可选)"
                    }
                },
                "required": ["pdf_file"]
            },
            message_to_user="文献挖掘需要指定目标文献，请上传或输入文件路径："
        )
    log.debug("[L2] LITERATURE_MINING 参数完整，放行")
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