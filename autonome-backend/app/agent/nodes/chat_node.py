"""
Chat Agent 节点 - 通用对话和概念解释。

使用 ChatOpenAI.astream() 进行流式输出，
复用现有 chat.py 中的 SYSTEM_PROMPT_CHAT 逻辑。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def chat_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Chat Agent 节点。

    处理通用对话请求，使用 LLM 流式生成回复。
    实际的 LLM 流式调用在 chat.py 的 SSE 循环中完成，
    此节点只标记意图已路由到 chat_node。
    """
    messages = state.get("messages", [])
    intent_data = state.get("intent_data", {})

    log.info(f"[chat_node] 处理对话请求, entities={intent_data.get('entities', {})}")

    return {
        "intent_data": {**intent_data, "node": "chat_node"}
    }
