"""
反思自循环 LangGraph 节点 — 代码硬检查 + 条件回退重写。

程序说明：
作为独立的 LangGraph 节点插入到 skill_forge_node 之后、l3_executor_node 之前。
对生成的代码运行硬检查规则（run_hard_checks），不通过则设置 reflection_critique
并回退到 skill_forge_node 触发 LLM 重写，形成 生成→校验→重写 的闭环。

与 adhoc_analysis_node 中内联的 SSE 路径反思不同，此节点工作在 LangGraph 层面，
可在 Graph 中形成循环边，无需阻塞 SSE 流。

设计原则：
- 硬检查规则复用 code_validator.py 中的 run_hard_checks()
- 失败时将批评文本写入 AgentState.reflection_critique，skill_forge_node 读取后注入 prompt
- 最多重试 MAX_REFLECTION_RETRIES 次，超过后放行（附加警告）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


# 反思自循环最大重试次数（与 code_validator.py 保持一致）
MAX_REFLECTION_RETRIES = 2


async def code_validator_node(
    state: AgentState,
    config: RunnableConfig,
) -> Dict[str, Any]:
    """
    反思自循环校验节点：对当前生成的代码进行硬检查。

    执行流程：
    1. 从 state 中获取当前 TaskNode 的 adhoc_metadata 或 execution_result 中的 code
    2. 运行 run_hard_checks()
    3. 如果通过 → 清空 reflection_critique，继续到执行节点
    4. 如果不通过 → 将结构化批评写入 reflection_critique，skill_forge_node 重写

    Args:
        state: LangGraph AgentState
        config: Runnable 配置

    Returns:
        更新后的 state 片段字典
    """
    from app.services.code_validator import run_hard_checks

    # 获取当前生成的代码
    code = ""
    language = "python"

    # 尝试从多个来源获取代码
    # 1. 从当前 TaskNode 的 adhoc_metadata 获取
    dag = state.get("dag", {})
    if dag:
        idx = state.get("current_task_idx", 0)
        nodes = dag.get("nodes", [])
        if idx < len(nodes):
            current_node = nodes[idx]
            adhoc_meta = current_node.get("adhoc_metadata", {})
            if adhoc_meta:
                code = adhoc_meta.get("code", "")
                language = adhoc_meta.get("code_language", "python")

    # 2. 从 execution_result 获取
    if not code:
        exec_result = state.get("execution_result", {})
        if exec_result:
            code = exec_result.get("code", "")
            language = exec_result.get("code_language", "python")

    # 3. 从 task_results 查找最近的成功代码
    if not code:
        task_results = state.get("task_results", {})
        for task_id, result in task_results.items():
            if isinstance(result, dict) and result.get("code"):
                code = result["code"]
                language = result.get("code_language", "python")
                break

    if not code:
        log.info("[code_validator_node] 未找到待校验代码，跳过硬检查")
        return {
            "reflection_critique": None,
            "reflection_attempts": 0,
            "hard_check_results": {"passed": True, "skipped": True},
        }

    # 获取当前重试次数
    reflection_attempts = state.get("reflection_attempts", 0)

    # 运行硬检查
    hard_check_result = run_hard_checks(code=code, language=language)

    if hard_check_result.passed:
        log.info(
            f"[code_validator_node] 硬检查通过 "
            f"(attempt {reflection_attempts}, warnings={hard_check_result.warnings})"
        )
        return {
            "reflection_critique": None,
            "reflection_attempts": 0,  # 重置计数器
            "hard_check_results": {
                "passed": True,
                "warnings": hard_check_result.warnings,
            },
        }

    # 硬检查未通过
    reflection_attempts += 1

    if reflection_attempts <= MAX_REFLECTION_RETRIES:
        log.warning(
            f"[code_validator_node] 硬检查未通过，回退重写 "
            f"(attempt {reflection_attempts}/{MAX_REFLECTION_RETRIES}): "
            f"failed_checks={hard_check_result.failed_checks}"
        )
        return {
            "reflection_critique": hard_check_result.critique,
            "reflection_attempts": reflection_attempts,
            "hard_check_results": {
                "passed": False,
                "failed_checks": hard_check_result.failed_checks,
                "critique": hard_check_result.critique,
            },
        }
    else:
        # 超过最大重试次数，放行但附加警告
        log.warning(
            f"[code_validator_node] 超过最大重试次数 ({MAX_REFLECTION_RETRIES})，放行代码: "
            f"failed_checks={hard_check_result.failed_checks}"
        )
        return {
            "reflection_critique": None,
            "reflection_attempts": 0,
            "hard_check_results": {
                "passed": False,
                "exceeded_max_retries": True,
                "failed_checks": hard_check_result.failed_checks,
                "warning": f"代码未通过硬检查但已达最大重试次数: {hard_check_result.failed_checks}",
            },
        }


def _route_after_validation(state: AgentState) -> str:
    """
    条件路由：根据硬检查结果决定下一步。

    通过 → l3_executor_node（继续执行）
    不通过且未超过重试次数 → skill_forge_node（回退重写）
    不通过且超过重试次数 → l3_executor_node（放行）

    注意：此函数在 graph.py 的 conditional_edges 中被引用。
    """
    hard_check_results = state.get("hard_check_results")
    reflection_attempts = state.get("reflection_attempts", 0)

    if not hard_check_results:
        return "l3_executor_node"

    if hard_check_results.get("passed"):
        return "l3_executor_node"

    if hard_check_results.get("exceeded_max_retries"):
        log.warning("[code_validator_node] 超过最大重试次数，放行到 l3_executor_node")
        return "l3_executor_node"

    if reflection_attempts <= MAX_REFLECTION_RETRIES:
        return "skill_forge_node"

    return "l3_executor_node"
