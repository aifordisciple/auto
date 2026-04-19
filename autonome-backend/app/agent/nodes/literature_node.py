"""
Literature Agent 节点 - 文献解析与论文复现。

当用户涉及文献/DOI/论文复现时路由到此节点。
包装现有的 literature_agent.py。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def literature_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Literature Agent 节点。

    处理文献解析请求，包装现有 literature_agent。
    """
    intent_data = state.get("intent_data", {})

    log.info("[literature_node] 处理文献请求")

    return {
        "intent_data": {**intent_data, "node": "literature_node"}
    }
