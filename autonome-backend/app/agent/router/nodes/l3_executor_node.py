"""
L3 技能执行器节点。

从 AgentState 中提取当前 TaskNode 的 skill_id 和 parameters，
委托给现有 skill_executor.py 执行 Docker 沙箱任务，
将执行结果写回 AgentState.task_results。

此节点在以下场景被触发：
1. determine_next_step 检测到 EXPLICIT_EXEC + skill_id → 直接路由
2. route_after_probing 参数补全后 → 路由到执行
3. route_after_l2 L2 参数齐全后 → 路由到执行
4. 即席分析用户确认后 → 路由到执行（adhoc_metadata 或 code_snapshot 存在时）
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
    adhoc_metadata = current_task.get("adhoc_metadata")

    # 即席分析执行路径：adhoc_metadata 存在或 parameters 中有 code_snapshot
    code_snapshot = parameters.get("code_snapshot", "")
    if adhoc_metadata or code_snapshot:
        return await _execute_adhoc_analysis(state, config, current_task, task_id, idx, nodes)

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

        # SkillExecutor 是同步接口，用 asyncio.to_thread 包装为异步
        executor = SkillExecutor(
            skill_id=skill_id,
            params=parameters,
            project_id=session or "default",
            task_id=task_id,
            user_id=int(user_id) if user_id else None,
        )

        # 同步执行 → 异步包装，避免阻塞事件循环
        result = await asyncio.to_thread(executor.execute)

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


async def _execute_adhoc_analysis(
    state: AgentState,
    config: RunnableConfig,
    current_task: Dict[str, Any],
    task_id: str,
    idx: int,
    nodes: list,
) -> Dict[str, Any]:
    """
    即席分析的 Docker 沙箱执行路径。

    程序说明：
    从 parameters.code_snapshot 获取代码内容，
    写入临时文件，使用 run_container 在 Docker 沙箱中执行，
    返回执行结果。

    Args:
        state: LangGraph 状态
        config: Runnable 配置
        current_task: 当前 TaskNode 字典
        task_id: 任务 ID
        idx: 当前任务索引
        nodes: DAG 节点列表

    Returns:
        状态更新字典
    """
    import tempfile
    import os
    from app.tools.bio_tools import run_container

    parameters = current_task.get("parameters", {})
    code_snapshot = parameters.get("code_snapshot", "")
    code_language = parameters.get("code_language", "python")

    if not code_snapshot:
        log.error(f"[l3_executor_node] 即席分析缺少 code_snapshot，无法执行")
        task_result = TaskResult(
            task_id=task_id,
            status="failed",
            error="即席分析缺少代码快照，无法执行",
        )
        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        return {
            "task_results": task_results,
            "current_task_idx": idx + 1,
            "execution_status": "failed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content="即席分析执行失败：缺少代码快照")],
        }

    log.info(f"[l3_executor_node] 即席分析执行: task={task_id}, language={code_language}")

    try:
        # 将代码写入临时文件
        suffix = ".py" if code_language == "python" else ".R"
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(code_snapshot)
            script_path = f.name

        # 构建执行命令
        if code_language == "python":
            cmd = ["python", script_path]
        else:
            cmd = ["Rscript", script_path]

        # 构建命令行参数（从 parameters 中提取，排除内部字段）
        for key, value in parameters.items():
            if key.startswith("_") or key in ("code_snapshot", "code_language", "skill_id"):
                continue
            if value is None:
                continue
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.append(f"--{key}")
                cmd.append(str(value))

        log.info(f"[l3_executor_node] 即席分析命令: {' '.join(cmd)}")

        # 获取用户 ID
        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")

        # 在 Docker 沙箱中执行
        output, exit_code = run_container(
            image='autonome-tool-env',
            command=cmd,
            language=code_language,
            environment={
                "TASK_OUT_DIR": parameters.get("TASK_OUT_DIR", "/workspace/results/default"),
                "PROJECT_ID": parameters.get("PROJECT_ID", "default"),
            },
            timeout=3600,
            cli_mode=True,
            user_id=int(user_id) if user_id else None,
        )

        # 清理临时文件
        try:
            os.unlink(script_path)
        except OSError:
            pass

        # 解析执行结果
        success = exit_code == 0
        task_result = TaskResult(
            task_id=task_id,
            skill_id="adhoc_analysis",
            status="success" if success else "failed",
            output=output[:5000] if success else None,
            error=output[:2000] if not success else None,
            execution_time_seconds=0.0,
        )

        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        new_idx = idx + 1

        result_msg = f"即席分析执行{'成功' if success else '失败'}"
        if success and task_result.output:
            result_msg += f"\n结果: {str(task_result.output)[:500]}"

        log.info(f"[l3_executor_node] 即席分析 task={task_id} 执行完成: status={task_result.status}")

        return {
            "task_results": task_results,
            "current_task_idx": new_idx,
            "execution_status": "running" if new_idx < len(nodes) else "completed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content=result_msg)],
        }

    except Exception as e:
        log.error(f"[l3_executor_node] 即席分析执行异常: task={task_id}, error={str(e)}")

        # 清理临时文件（如果存在）
        try:
            if 'script_path' in locals():
                os.unlink(script_path)
        except OSError:
            pass

        task_result = TaskResult(
            task_id=task_id,
            skill_id="adhoc_analysis",
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
            "messages": [AIMessage(content=f"即席分析执行失败: {str(e)}")],
        }
