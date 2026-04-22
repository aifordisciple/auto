"""
Version Control Agent 节点 - 版本控制与代码管理（阶段一 stub）。

当用户涉及版本控制、代码管理时路由到此节点。
阶段一为 stub 实现，返回开发中提示。
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def version_control_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """版本控制节点（阶段一 stub）。"""
    intent_data = state.get("intent_data", {})

    log.info(f"[version_control_node] 版本控制请求, intent_data={intent_data}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "stub", "message": "版本控制功能开发中"}

    return {
        "intent_data": {**intent_data, "node": "version_control_node"},
        "messages": [AIMessage(content="版本控制功能开发中，敬请期待。当前您可以通过文件管理器手动管理代码版本。")],
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
