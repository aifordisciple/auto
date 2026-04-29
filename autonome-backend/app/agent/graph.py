"""
LangGraph 多 Agent 编排图 V2.0。

支持 DAG 多任务循环调度和 Active Probing 挂起/恢复。

Graph 结构:
    [Entry] → intent_router_node → determine_next_step
        → ask_user_node → probing_response_node → route_after_probing
            → l3_executor_node (参数补全后执行)
        → orchestrator_node → task_advance_or_end
        → skill_forge_node → task_advance_or_end
        → explicit_exec_node → task_advance_or_end
        → version_control_node → task_advance_or_end
        → ui_state_node → task_advance_or_end
        → data_probe_node → task_advance_or_end
        → literature_node → task_advance_or_end
        → system_asset_node → task_advance_or_end
        → collaboration_node → task_advance_or_end
        → diagnostic_node → task_advance_or_end
        → chat_node → task_advance_or_end
        → system_macro_node → task_advance_or_end
        → adhoc_analysis_node → ask_user_node (挂起等待用户确认)
        → l3_executor_node → route_after_execution
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.agent.nodes.chat_node import chat_node
from app.agent.nodes.data_probe_node import data_probe_node
from app.agent.nodes.diagnostic_node import diagnostic_node
from app.agent.nodes.explicit_exec_node import explicit_exec_node
from app.agent.nodes.literature_node import literature_node
from app.agent.nodes.skill_forge_node import skill_forge_node
from app.agent.nodes.orchestrator_node import orchestrator_node
from app.agent.nodes.ui_state_node import ui_state_node
from app.agent.nodes.system_asset_node import system_asset_node
from app.agent.nodes.version_control_node import version_control_node
from app.agent.nodes.collaboration_node import collaboration_node
from app.agent.nodes.system_macro_node import system_macro_node
from app.agent.nodes.adhoc_analysis_node import adhoc_analysis_node
from app.agent.nodes.code_validator_node import code_validator_node, _route_after_validation
from app.agent.router.nodes.probing_response_node import probing_response_node
from app.agent.router.nodes.l3_executor_node import l3_executor_node
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import (
    AgentState, IntentType, INTENT_NODE_MAP,
    TaskDAG, TaskNode, ProbingRequest, RouteResult, DAGCondition
)
from app.core.logger import log


async def intent_router_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    LangGraph 入口节点：调用路由引擎，获取 TaskDAG + ProbingRequest。

    session 和 user_id 通过 configurable 注入：
    graph.invoke(state, config={"configurable": {"session": ..., "user_id": ...}})
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent_data": {"intent": "INTENT_GENERAL_CHAT", "routing_target": "chat_node"},
            "dag": None,
            "current_task_idx": 0,
            "active_probing": None,
            "task_results": {},
        }

    query = messages[-1].content
    context = state.get("context", {})

    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    if not session or not user_id:
        log.warning("[intent_router_node] 缺少 session 或 user_id，降级为 chat")
        return {
            "intent_data": {"intent": "INTENT_GENERAL_CHAT", "routing_target": "chat_node"},
            "dag": None,
            "current_task_idx": 0,
            "active_probing": None,
            "task_results": {},
        }

    # 调用路由引擎
    engine = IntentRouterEngine(session, user_id)
    route_result: RouteResult = await engine.route(query, context)

    # 存储 DAG 和探查结果
    dag_dict = route_result.dag.model_dump()
    probing_dict = route_result.probing.model_dump() if route_result.probing else None

    # 提取首个任务的意图数据（兼容下游 chat.py）
    first_intent = route_result.dag.nodes[0].intent if route_result.dag.nodes else IntentType.GENERAL_CHAT
    intent_data = {
        "intent": first_intent.value,
        "routing_target": INTENT_NODE_MAP.get(first_intent, "chat_node"),
    }

    return {
        "intent_data": intent_data,
        "dag": dag_dict,
        "current_task_idx": 0,
        "active_probing": probing_dict,
        "task_results": {},
    }


async def ask_user_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """向前端抛出参数补全表单或即席分析卡片的节点（Active Probing 挂起点）。

    根据 ProbingRequest.render_type 决定发送的 ToolCall 类型：
    - render_type="adhoc_card" → 发送 render_adhoc_card ToolCall，前端渲染即席分析策略卡片
    - 其他（默认）→ 发送 request_parameters ToolCall，前端渲染参数补全表单
    """
    probing_dict = state.get("active_probing")
    if not probing_dict:
        return {}

    probing = ProbingRequest(**probing_dict) if isinstance(probing_dict, dict) else probing_dict
    current_idx = state.get("current_task_idx", 0)

    # 根据 render_type 决定 ToolCall 类型
    render_type = getattr(probing, "render_type", None) or (probing_dict.get("render_type") if isinstance(probing_dict, dict) else None)

    if render_type == "adhoc_card":
        # 即席分析策略卡片：发送 render_adhoc_card ToolCall
        tool_call = {
            "name": "render_adhoc_card",
            "args": {
                "strategy": probing.adhoc_card_data.get("strategy", ""),
                "code": probing.adhoc_card_data.get("code", ""),
                "code_language": probing.adhoc_card_data.get("code_language", "python"),
                "parameter_schema": probing.adhoc_card_data.get("parameter_schema", {}),
                "input_mapping": probing.adhoc_card_data.get("input_mapping", {}),
                "message": probing.message_to_user,
                "message_id": probing.adhoc_card_data.get("message_id", ""),
            },
            "id": f"call_adhoc_{probing.adhoc_card_data.get('message_id', current_idx)}",
        }
        log.info(f"[ask_user_node] 发送即席分析策略卡片: render_type=adhoc_card")
    else:
        # 默认参数补全表单
        tool_call = {
            "name": "request_parameters",
            "args": {
                "message": probing.message_to_user,
                "schema": probing.ui_schema,
            },
            "id": f"call_probe_{current_idx}",
        }
        log.info(f"[ask_user_node] 发送参数补全请求: missing={probing.missing_params}")

    message = AIMessage(content="", tool_calls=[tool_call])

    return {"messages": [message]}


def determine_next_step(state: AgentState) -> str:
    """条件边：决定图的下一步走向。"""
    # 最高优先级：用户提交了 Probing 参数，恢复执行
    probing_response = state.get("probing_response")
    if probing_response:
        return "probing_response_node"

    # 次高优先级：L2 探查器发现缺参数
    probing_dict = state.get("active_probing")
    if probing_dict and probing_dict.get("is_missing"):
        return "ask_user_node"

    # 检查 DAG 是否有任务
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx >= len(nodes):
        return END

    # 根据原子意图分发到 Worker 节点
    intent_str = nodes[idx].get("intent", "INTENT_GENERAL_CHAT")
    try:
        intent = IntentType(intent_str)
        # EXPLICIT_EXEC 且有 skill_id 时走 L3 执行器
        if intent == IntentType.EXPLICIT_EXEC:
            task_params = nodes[idx].get("parameters", {})
            if task_params.get("skill_id") or state.get("skill_id"):
                return "l3_executor_node"
        return INTENT_NODE_MAP.get(intent, "chat_node")
    except ValueError:
        return "chat_node"


def route_after_l2(state: AgentState) -> str:
    """
    L2 参数探查后的路由判断。

    程序说明：
    如果 L2 发现参数缺失（active_probing.is_missing=True），
    路由到 ask_user_node 挂起等待前端参数补全。
    否则路由到 l3_executor_node 执行技能。
    """
    probing_dict = state.get("active_probing")
    if probing_dict and probing_dict.get("is_missing"):
        return "ask_user_node"

    # 参数齐全，前进到执行
    return "l3_executor_node"


def route_after_probing(state: AgentState) -> str:
    """
    Active Probing 参数回注后的路由判断。

    程序说明：
    用户提交参数后，probing_response_node 已将参数合并到 TaskNode。
    此处判断是否需要再次 L2 检查（参数可能仍不完整），
    或直接前进到 L3 执行。

    当前策略：直接前进到 L3，信任用户提交的参数。
    未来可增加二次 L2 校验。
    """
    # 直接前进到执行
    return "l3_executor_node"


def route_after_execution(state: AgentState) -> str:
    """
    L3 执行后的路由判断。

    程序说明：
    检查 DAG 中是否还有未完成的任务节点。
    有 → 回到 intent_router 继续调度下一个任务。
    无 → 结束。
    """
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])

    # 还有未执行的任务
    if idx < len(nodes):
        return "intent_router"

    # 所有任务已执行完毕
    return END


def task_advance_or_end(state: AgentState) -> str:
    """Worker 节点执行完毕后：推进任务指针或结束。

    V2.5 新增：当 Worker 节点设置了 active_probing 挂起（如 adhoc_analysis_node
    生成的策略卡片等待用户确认），不推进任务指针，回到 intent_router 让
    determine_next_step 路由到 ask_user_node 发送 ToolCall 给前端。
    """
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    # V2.5: 如果有 active_probing 挂起（如 adhoc_analysis_node 生成的策略卡片），
    # 回到 intent_router 让 determine_next_step 路由到 ask_user_node
    if state.get("active_probing"):
        return "intent_router"

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx + 1 >= len(nodes):
        return END

    # 还有未完成的任务，回到路由判断
    return "intent_router"


# 条件运算符实现映射
_OPERATOR_FN = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
}


def evaluate_condition_and_route(state: AgentState) -> str:
    """
    V2.4: data_probe_node 执行完毕后的条件路由判断。

    检查当前 TaskNode 是否定义了 condition（条件探针分支）。
    若存在条件：
      1. 从 task_results 中获取 source_task_id 的 probe_report.fields 实际值
      2. 执行比较运算
      3. 根据 on_true/on_false 返回路由目标
    若无条件 → 降级为 task_advance_or_end（顺序推进）。

    路由目标：
      - 'stop' → END（停止 DAG 执行）
      - 'continue' → intent_router（推进到下一个任务）
      - 具体 task_id → intent_router（当前仅支持 stop/continue）
    """
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx >= len(nodes):
        return END

    current_node = nodes[idx]
    condition_dict = current_node.get("condition")

    # 无条件定义 → 降级为标准顺序推进
    if not condition_dict:
        return task_advance_or_end(state)

    try:
        condition = DAGCondition(**condition_dict)
    except Exception as e:
        log.warning(f"[evaluate_condition_and_route] DAGCondition 解析失败: {e}，降级为顺序推进")
        return task_advance_or_end(state)

    # 1. 从 task_results 获取实际值
    task_results = state.get("task_results", {})
    source_result = task_results.get(condition.source_task_id, {})
    probe_report = source_result.get("probe_report")
    if not probe_report or not probe_report.get("fields"):
        log.warning(
            f"[evaluate_condition_and_route] source_task_id={condition.source_task_id} "
            f"probe_report 为空，降级为 END"
        )
        return END

    actual_value = probe_report["fields"].get(condition.field)
    if actual_value is None:
        log.warning(
            f"[evaluate_condition_and_route] probe_report.fields 中未找到 "
            f"'{condition.field}'，降级为 END"
        )
        return END

    # 2. 执行比较运算
    op_fn = _OPERATOR_FN.get(condition.operator)
    if not op_fn:
        log.warning(f"[evaluate_condition_and_route] 不支持的运算符: {condition.operator}，降级为 END")
        return END

    try:
        result_is_true = op_fn(actual_value, condition.value)
    except TypeError as e:
        log.warning(f"[evaluate_condition_and_route] 比较运算失败: {e}，降级为 END")
        return END

    # 3. 根据比较结果选择路由目标
    target = condition.on_true if result_is_true else condition.on_false

    log.info(
        f"[evaluate_condition_and_route] 条件评估: "
        f"{condition.field}({actual_value}) {condition.operator} {condition.value} "
        f"→ {result_is_true}, 路由目标={target}"
    )

    if target == "stop":
        return END
    elif target == "continue":
        return "intent_router"
    else:
        # 当前仅支持 stop/continue 两个路径
        log.warning(
            f"[evaluate_condition_and_route] 不支持的路由目标: {target}，降级为 END"
        )
        return END


def build_intent_graph() -> StateGraph:
    """构建意图路由 LangGraph V2.0。"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("ask_user_node", ask_user_node)
    workflow.add_node("probing_response_node", probing_response_node)
    workflow.add_node("l3_executor_node", l3_executor_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("skill_forge_node", skill_forge_node)
    workflow.add_node("explicit_exec_node", explicit_exec_node)
    workflow.add_node("diagnostic_node", diagnostic_node)
    workflow.add_node("literature_node", literature_node)
    workflow.add_node("data_probe_node", data_probe_node)
    workflow.add_node("orchestrator_node", orchestrator_node)
    workflow.add_node("ui_state_node", ui_state_node)
    workflow.add_node("system_asset_node", system_asset_node)
    workflow.add_node("version_control_node", version_control_node)
    workflow.add_node("collaboration_node", collaboration_node)
    workflow.add_node("system_macro_node", system_macro_node)
    workflow.add_node("adhoc_analysis_node", adhoc_analysis_node)
    workflow.add_node("code_validator_node", code_validator_node)

    # 设置入口
    workflow.set_entry_point("intent_router")

    # 条件路由边：intent_router → 各节点
    all_worker_nodes = [
        "ask_user_node", "probing_response_node", "chat_node", "skill_forge_node",
        "explicit_exec_node", "diagnostic_node", "literature_node", "data_probe_node",
        "orchestrator_node", "ui_state_node", "system_asset_node",
        "version_control_node", "collaboration_node", "system_macro_node",
        "adhoc_analysis_node",
        "l3_executor_node",
    ]
    workflow.add_conditional_edges(
        "intent_router",
        determine_next_step,
        {node: node for node in all_worker_nodes} | {END: END}
    )

    # --- Active Probing 闭环边 ---
    # ask_user_node → END（挂起，等待前端参数补全后重新调用图）
    workflow.add_edge("ask_user_node", END)
    # probing_response_node → 条件路由：参数回注后前进到 L3 执行
    workflow.add_conditional_edges(
        "probing_response_node",
        route_after_probing,
        {"l3_executor_node": "l3_executor_node", "ask_user_node": "ask_user_node"}
    )

    # --- L3 执行器闭环边 ---
    # l3_executor_node → 条件路由：执行后推进 DAG 或结束
    workflow.add_conditional_edges(
        "l3_executor_node",
        route_after_execution,
        {"intent_router": "intent_router", END: END}
    )

    # --- 反思自循环边 ---
    # skill_forge_node → code_validator_node（硬检查）
    workflow.add_edge("skill_forge_node", "code_validator_node")
    # code_validator_node → skill_forge_node (retry) or l3_executor_node (pass)
    workflow.add_conditional_edges(
        "code_validator_node",
        _route_after_validation,
        {
            "l3_executor_node": "l3_executor_node",
            "skill_forge_node": "skill_forge_node",
        }
    )

    # 各 Worker 节点 → task_advance_or_end
    # 排除：有自己独立边或条件路由的节点
    worker_only = [n for n in all_worker_nodes if n not in (
        "ask_user_node", "probing_response_node", "l3_executor_node",
        "data_probe_node", "code_validator_node", "skill_forge_node"
    )]
    for node in worker_only:
        workflow.add_conditional_edges(
            node,
            task_advance_or_end,
            {"intent_router": "intent_router", END: END}
        )

    # V2.4: data_probe_node → evaluate_condition_and_route（支持条件探针分支）
    workflow.add_conditional_edges(
        "data_probe_node",
        evaluate_condition_and_route,
        {"intent_router": "intent_router", END: END}
    )

    return workflow.compile()
