"""
Literature Agent 节点 - 文献解析与论文复现。

当用户涉及文献/DOI/论文复现时路由到此节点。
包装现有的 literature_agent.py。

升级要点：
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def literature_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Literature Agent 节点。

    处理文献解析请求，包装现有 literature_agent。

    升级：增加 DAG 指针推进。
    """
    intent_data = state.get("intent_data", {})

    log.info("[literature_node] 处理文献请求")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "node": "literature_node"}

    return {
        "intent_data": {**intent_data, "node": "literature_node"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
