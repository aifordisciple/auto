"""
L3 技能执行器节点。

从 AgentState 中提取当前 TaskNode 的 skill_id 和 parameters，
委托给现有 skill_executor.py 执行 Docker 沙箱任务，
将执行结果写回 AgentState.task_results。

此节点在以下场景被触发：
1. determine_next_step 检测到 EXPLICIT_EXEC + skill_id → 直接路由
2. route_after_probing 参数补全后 → 路由到执行
3. route_after_l2 L2 参数齐全后 → 路由到执行
"""
import asyncio
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState, TaskResult
from app.core.logger import log


async def l3_executor_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    L3 执行器：调用 skill_executor 执行当前 TaskNode 对应的技能。

    程序说明：
    1. 从 DAG 中取当前 TaskNode，提取 skill_id 和 parameters
    2. 调用 SkillExecutor(skill_id, params, project_id) 在 Docker 沙箱中执行
    3. 将结果写入 task_results，推进 current_task_idx
    4. 如果执行失败，记录错误但不中断 DAG（由 route_after_execution 决定后续）
    """
    dag_dict = state.get("dag")
    idx = state.get("current_task_idx", 0)

    if not dag_dict or not dag_dict.get("nodes"):
        log.warning("[l3_executor_node] 无 DAG 或无任务节点，跳过执行")
        return {"execution_status": "completed"}

    nodes = dag_dict["nodes"]
    if idx >= len(nodes):
        log.warning(f"[l3_executor_node] current_task_idx={idx} 超出 DAG 范围")
        return {"execution_status": "completed"}

    current_task = nodes[idx]
    task_id = current_task.get("task_id", f"task_{idx}")
    skill_id = current_task.get("parameters", {}).get("skill_id") or state.get("skill_id")
    parameters = current_task.get("parameters", {})

    if not skill_id:
        log.warning(f"[l3_executor_node] 任务 {task_id} 缺少 skill_id，无法执行")
        task_result = TaskResult(
            task_id=task_id,
            status="failed",
            error="缺少 skill_id，无法执行技能",
        )
        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        return {
            "task_results": task_results,
            "execution_status": "failed",
        }

    log.info(f"[l3_executor_node] 开始执行 task={task_id}, skill={skill_id}")

    try:
        from app.services.skill_executor import SkillExecutor

        configurable = config.get("configurable", {})
        session = configurable.get("session")
        user_id = configurable.get("user_id")

        # SkillExecutor 是同步接口，用 run_in_executor 包装为异步
        executor = SkillExecutor(
            skill_id=skill_id,
            params=parameters,
            project_id=session or "default",
            task_id=task_id,
            user_id=int(user_id) if user_id else None,
        )

        # 同步执行 → 异步包装，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, executor.execute)

        # 记录执行结果
        success = result.get("success", False)
        task_result = TaskResult(
            task_id=task_id,
            skill_id=skill_id,
            status="success" if success else "failed",
            output=result.get("output") or result.get("result"),
            error=result.get("error"),
            execution_time_seconds=result.get("execution_time", 0.0),
        )

        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}

        # 推进任务指针
        new_idx = idx + 1

        # 构造结果消息
        result_msg = f"技能 {skill_id} 执行{'成功' if success else '失败'}"
        if task_result.output:
            result_msg += f"\n结果: {str(task_result.output)[:500]}"

        log.info(f"[l3_executor_node] task={task_id} 执行完成: status={task_result.status}")

        return {
            "task_results": task_results,
            "current_task_idx": new_idx,
            "execution_status": "running" if new_idx < len(nodes) else "completed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content=result_msg)],
        }

    except Exception as e:
        log.error(f"[l3_executor_node] 执行异常: task={task_id}, error={str(e)}")

        task_result = TaskResult(
            task_id=task_id,
            skill_id=skill_id,
            status="failed",
            error=str(e),
        )
        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        new_idx = idx + 1

        return {
            "task_results": task_results,
            "current_task_idx": new_idx,
            "execution_status": "failed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content=f"技能 {skill_id} 执行失败: {str(e)}")],
        }
