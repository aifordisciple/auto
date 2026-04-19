"""
LangGraph 多 Agent 编排图。

意图路由节点 (intent_router_node) 作为入口，
根据 IntentRouterEngine 的结果通过条件边分发到 6 个 Agent 节点。

Graph 结构:
    [Entry] → intent_router_node → conditional_edge → chat_node → END
                                               ├→ skill_forge_node → END
                                               ├→ explicit_skill_node → END
                                               ├→ diagnostic_node → END
                                               ├→ literature_node → END
                                               └→ data_probe_node → END
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.agent.nodes.chat_node import chat_node
from app.agent.nodes.data_probe_node import data_probe_node
from app.agent.nodes.diagnostic_node import diagnostic_node
from app.agent.nodes.explicit_skill_node import explicit_skill_node
from app.agent.nodes.literature_node import literature_node
from app.agent.nodes.skill_forge_node import skill_forge_node
from app.agent.router.engine import IntentRouterEngine
from app.agent.router.schemas import AgentState
from app.core.logger import log


async def intent_router_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    LangGraph 入口节点：调用意图引擎，将提取的实体注入 State。

    session 和 user_id 通过 configurable 注入：
    graph.invoke(state, config={"configurable": {"session": ..., "user_id": ...}})
    """
    messages = state.get("messages", [])
    if not messages:
        return {"intent_data": {"intent": "chat", "routing_target": "chat_node"}}

    query = messages[-1].content
    context = state.get("context", {})

    # 从 configurable 注入 session 和 user_id
    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    if not session or not user_id:
        log.warning("[intent_router_node] 缺少 session 或 user_id，降级为 chat")
        return {"intent_data": {"intent": "chat", "routing_target": "chat_node"}}

    # 调用意图识别引擎
    engine = IntentRouterEngine(session, user_id)
    intent_result = await engine.route(query, context)

    # 追问拦截：不唤醒昂贵的 Agent，直接返回追问消息
    if intent_result.requires_followup and intent_result.followup_question:
        log.info(f"[intent_router_node] 追问拦截: {intent_result.followup_question}")
        return {
            "messages": [AIMessage(content=intent_result.followup_question)],
            "intent_data": intent_result.model_dump()
        }

    return {"intent_data": intent_result.model_dump()}


def route_by_intent(state: AgentState) -> str:
    """
    条件边：根据 intent_data 中的 routing_target 分发到对应 Agent 节点。

    如果 requires_followup 为 True，直接返回 END（追问已在入口节点处理）。
    """
    intent_data = state.get("intent_data", {})
    if intent_data.get("requires_followup"):
        return END
    return intent_data.get("routing_target", "chat_node")


def build_intent_graph() -> StateGraph:
    """
    构建意图路由 LangGraph。

    Returns:
        编译后的 StateGraph，可直接调用 .invoke() 或 .astream()
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("skill_forge_node", skill_forge_node)
    workflow.add_node("explicit_skill_node", explicit_skill_node)
    workflow.add_node("diagnostic_node", diagnostic_node)
    workflow.add_node("literature_node", literature_node)
    workflow.add_node("data_probe_node", data_probe_node)

    # 设置入口
    workflow.set_entry_point("intent_router")

    # 条件路由边：intent_router → 各 Agent 节点
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "chat_node": "chat_node",
            "skill_forge_node": "skill_forge_node",
            "explicit_skill_node": "explicit_skill_node",
            "diagnostic_node": "diagnostic_node",
            "literature_node": "literature_node",
            "data_probe_node": "data_probe_node",
            END: END,
        }
    )

    # 各 Agent 节点 → END
    workflow.add_edge("chat_node", END)
    workflow.add_edge("skill_forge_node", END)
    workflow.add_edge("explicit_skill_node", END)
    workflow.add_edge("diagnostic_node", END)
    workflow.add_edge("literature_node", END)
    workflow.add_edge("data_probe_node", END)

    return workflow.compile()
