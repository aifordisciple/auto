"""
Diagnostic Agent 节点 - 错误诊断与修复。

当用户遇到代码报错或环境问题时路由到此节点。
分析错误日志并提供修复建议。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def diagnostic_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Diagnostic Agent 节点。

    处理错误诊断请求。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[diagnostic_node] 处理诊断请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "diagnostic_node"}
    }
