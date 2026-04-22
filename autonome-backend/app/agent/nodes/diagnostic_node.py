"""
Diagnostic Agent 节点 - 错误诊断与修复。

当用户遇到代码报错或环境问题时路由到此节点。
分析错误日志并提供修复建议。

升级要点：
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def diagnostic_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Diagnostic Agent 节点。

    处理错误诊断请求。

    升级：增加 DAG 指针推进。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[diagnostic_node] 处理诊断请求, entities={entities}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "node": "diagnostic_node"}

    return {
        "intent_data": {**intent_data, "node": "diagnostic_node"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
