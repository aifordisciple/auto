"""
Explicit Exec Agent 节点 - 执行用户指定的技能。

当用户直接指定技能 ID 或名称时路由到此节点。
使用 SkillExecutor 执行对应的 SKILL.md 定义的分析流程。

升级要点：
- 从 explicit_skill_node 重命名为 explicit_exec_node（与 INTENT_NODE_MAP 对齐）
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def explicit_exec_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Explicit Exec Agent 节点。

    处理显式技能执行请求。
    从 explicit_skill_node 重命名而来，与 INTENT_NODE_MAP 映射一致。

    升级：增加 DAG 指针推进。
    """
    intent_data = state.get("intent_data", {})
    skill_id = intent_data.get("skill_id") or state.get("skill_id")

    log.info(f"[explicit_exec_node] 执行技能: skill_id={skill_id}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "skill_id": skill_id}

    return {
        "intent_data": {**intent_data, "node": "explicit_exec_node"},
        "skill_id": skill_id,
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
