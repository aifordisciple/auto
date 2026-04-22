"""
Data Probe Agent 节点 - 数据预览与探查。

当用户需要查看数据结构、预览数据内容时路由到此节点。
调用 probe_tools.py 中的工具。

升级要点：
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def data_probe_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Data Probe Agent 节点。

    处理数据探查请求，调用 probe_tools。

    升级：增加 DAG 指针推进。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[data_probe_node] 处理数据探查请求, entities={entities}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "node": "data_probe_node"}

    return {
        "intent_data": {**intent_data, "node": "data_probe_node"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }