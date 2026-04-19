"""
Data Probe Agent 节点 - 数据预览与探查。

当用户需要查看数据结构、预览数据内容时路由到此节点。
调用 probe_tools.py 中的工具。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def data_probe_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Data Probe Agent 节点。

    处理数据探查请求，调用 probe_tools。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[data_probe_node] 处理数据探查请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "data_probe_node"}
    }