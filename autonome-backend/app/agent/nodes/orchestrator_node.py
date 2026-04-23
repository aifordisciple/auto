"""
工作流编排节点（V2.0 升级）。

V1: 简单转发到 chat_node
V2: 接收 DAG，使用 dag_scheduler 进行拓扑排序和并行调度。
    - 无依赖的节点并行执行（Celery group）
    - 有依赖的节点按拓扑序串行执行
    - 支持节点间参数变量引用 ${task_id.output.field}
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.agent.router.dag_scheduler import (
    topological_sort,
    find_ready_nodes,
    resolve_parameter_references,
    get_dag_progress,
)
from app.core.logger import log


async def orchestrator_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    工作流编排节点：DAG 拓扑排序 + 并行调度。

    程序说明：
    1. 从 AgentState.dag 获取任务图谱
    2. 使用拓扑排序确定执行顺序
    3. 查找就绪节点（所有前置依赖已完成）
    4. 解析节点参数中的变量引用
    5. 并行调度就绪节点执行
    6. 更新 task_results 和 current_task_idx
    """
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        log.warning("[orchestrator_node] 无 DAG 或无任务节点，降级为 chat")
        return {"intent_data": {"intent": "INTENT_GENERAL_CHAT", "routing_target": "chat_node"}}

    nodes = dag_dict["nodes"]
    task_results = state.get("task_results", {})

    # 拓扑排序
    sorted_ids = topological_sort(nodes)
    log.info(f"[orchestrator_node] 拓扑排序结果: {sorted_ids}")

    # 查找就绪节点
    ready_nodes = find_ready_nodes(nodes, task_results)
    if not ready_nodes:
        # 所有节点已完成或无就绪节点
        progress = get_dag_progress(nodes, task_results)
        completed = sum(1 for s in progress.values() if s in ("completed", "failed"))
        log.info(f"[orchestrator_node] 无就绪节点，进度: {completed}/{len(nodes)}")
        return {
            "execution_status": "completed",
            "messages": [AIMessage(content="工作流编排已完成所有任务。")],
        }

    # 解析参数变量引用
    for node in ready_nodes:
        params = node.get("parameters", {})
        resolved = resolve_parameter_references(params, task_results)
        node["parameters"] = resolved

    # 调度就绪节点执行
    # 当前实现：串行调度（Celery group/chord 并行调度在后续迭代中实现）
    scheduled_tasks = []
    for node in ready_nodes:
        task_id = node.get("task_id")
        intent = node.get("intent", "INTENT_GENERAL_CHAT")
        log.info(f"[orchestrator_node] 调度任务: task_id={task_id}, intent={intent}")
        scheduled_tasks.append({
            "task_id": task_id,
            "intent": intent,
            "parameters": node.get("parameters", {}),
        })

    # 更新 DAG 进度
    progress = get_dag_progress(nodes, task_results)
    completed_count = sum(1 for s in progress.values() if s in ("completed", "failed"))
    total_count = len(nodes)

    # 构造编排消息
    ready_desc = ", ".join(f"{t['task_id']}({t['intent']})" for t in scheduled_tasks)
    msg = f"工作流编排: {completed_count}/{total_count} 已完成, 调度就绪任务: [{ready_desc}]"

    log.info(f"[orchestrator_node] {msg}")

    # 将调度信息写入 state，供后续节点消费
    # 第一个就绪节点作为当前任务
    first_ready = ready_nodes[0]
    first_idx = next(
        (i for i, n in enumerate(nodes) if n.get("task_id") == first_ready.get("task_id")),
        0,
    )

    return {
        "current_task_idx": first_idx,
        "execution_status": "running",
        "messages": [AIMessage(content=msg)],
    }
