"""
LangGraph 多 Agent 编排图 V2.0。

支持 DAG 多任务循环调度和 Active Probing 挂起/恢复。

Graph 结构:
    [Entry] → intent_router_node → determine_next_step
        → ask_user_node → END (挂起，等待前端参数补全)
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
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import (
    AgentState, IntentType, INTENT_NODE_MAP,
    TaskDAG, TaskNode, ProbingRequest, RouteResult
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
    """向前端抛出参数补全表单的节点（Active Probing 挂起点）。"""
    probing_dict = state.get("active_probing")
    if not probing_dict:
        return {}

    probing = ProbingRequest(**probing_dict) if isinstance(probing_dict, dict) else probing_dict
    current_idx = state.get("current_task_idx", 0)

    # 构造 ToolCall，前端 useChat hook 自动解析为 toolInvocations
    tool_call = {
        "name": "request_parameters",
        "args": {
            "message": probing.message_to_user,
            "schema": probing.ui_schema,
        },
        "id": f"call_probe_{current_idx}",
    }

    message = AIMessage(content="", tool_calls=[tool_call])
    log.info(f"[ask_user_node] 发送参数补全请求: missing={probing.missing_params}")

    return {"messages": [message]}


def determine_next_step(state: AgentState) -> str:
    """条件边：决定图的下一步走向。"""
    # 最高优先级：L2 探查器发现缺参数
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
        return INTENT_NODE_MAP.get(intent, "chat_node")
    except ValueError:
        return "chat_node"


def task_advance_or_end(state: AgentState) -> str:
    """Worker 节点执行完毕后：推进任务指针或结束。"""
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx + 1 >= len(nodes):
        return END

    # 还有未完成的任务，回到路由判断
    return "intent_router"


def build_intent_graph() -> StateGraph:
    """构建意图路由 LangGraph V2.0。"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("ask_user_node", ask_user_node)
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

    # 设置入口
    workflow.set_entry_point("intent_router")

    # 条件路由边：intent_router → 各节点
    all_worker_nodes = [
        "ask_user_node", "chat_node", "skill_forge_node", "explicit_exec_node",
        "diagnostic_node", "literature_node", "data_probe_node",
        "orchestrator_node", "ui_state_node", "system_asset_node",
        "version_control_node", "collaboration_node", "system_macro_node",
    ]
    workflow.add_conditional_edges(
        "intent_router",
        determine_next_step,
        {node: node for node in all_worker_nodes} | {END: END}
    )

    # ask_user_node → END（挂起，等待前端参数补全后重新调用）
    workflow.add_edge("ask_user_node", END)

    # 各 Worker 节点 → task_advance_or_end
    worker_only = [n for n in all_worker_nodes if n != "ask_user_node"]
    for node in worker_only:
        workflow.add_conditional_edges(
            node,
            task_advance_or_end,
            {"intent_router": "intent_router", END: END}
        )

    return workflow.compile()
