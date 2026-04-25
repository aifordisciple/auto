"""
Active Probing 参数回注节点。

用户通过前端 ParameterProbingCard 提交参数后，
此节点从 AgentState.probing_response 读取用户提交的参数，
回注到当前 TaskNode 的 parameters 中，
并清除 active_probing 以解除挂起状态。

V2.2 扩展：支持即席分析卡片 (AdhocAnalysisCard) 的参数回注。
当 render_type == "adhoc_card" 时，用户提交的参数包含
action='execute' 和 payload（含 parameters、inputs、code_snapshot），
需将代码快照和最终参数一并存入 TaskNode.parameters。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def probing_response_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    处理用户提交的 Active Probing 参数。

    程序说明：
    从 AgentState.probing_response 读取用户提交的参数，
    合并到当前 TaskNode 的 parameters 中，
    清除 active_probing 和 probing_response 以解除挂起。

    V2.2 扩展：支持即席分析卡片的参数回注。
    当 render_type == "adhoc_card" 时，用户提交的参数包含
    action='execute' 和 payload（含 parameters、inputs、code_snapshot），
    需要将代码快照和最终参数一并存入 TaskNode.parameters。
    """
    probing_response = state.get("probing_response")
    if not probing_response:
        log.warning("[probing_response_node] 无 probing_response，跳过")
        return {"active_probing": None, "probing_response": None}

    # 提取用户提交的参数
    user_params = probing_response.get("parameters", {})
    message_id = probing_response.get("message_id", "")

    # 检查是否为即席分析的参数回注
    # 即席分析时，user_params 包含 action 和 payload
    action = user_params.get("action", "")
    is_adhoc_execute = action == "execute"

    if is_adhoc_execute:
        payload = user_params.get("payload", {})
        log.info(f"[probing_response_node] 收到即席分析执行请求: action={action}, params={list(payload.get('parameters', {}).keys())}")
    else:
        log.info(f"[probing_response_node] 收到用户参数: message_id={message_id}, params={list(user_params.keys())}")

    # 将用户参数合并到当前 TaskNode
    dag_dict = state.get("dag")
    idx = state.get("current_task_idx", 0)
    if dag_dict and dag_dict.get("nodes"):
        nodes = dag_dict["nodes"]
        if idx < len(nodes):
            existing_params = nodes[idx].get("parameters", {})

            if is_adhoc_execute:
                # 即席分析：合并 payload 中的参数、输入映射和代码快照
                payload = user_params.get("payload", {})
                merged_params = {
                    **existing_params,
                    **payload.get("inputs", {}),
                    **payload.get("parameters", {}),
                    "code_snapshot": payload.get("code_snapshot", ""),
                    "code_language": nodes[idx].get("adhoc_metadata", {}).get("code_language", "python"),
                }
            else:
                # 原有逻辑：用户提交的参数优先级最高
                merged_params = {**existing_params, **user_params}

            nodes[idx]["parameters"] = merged_params
            log.info(f"[probing_response_node] 参数已回注到 task_{idx}: {list(merged_params.keys())}")

    # 清除挂起状态，允许继续执行
    return {
        "dag": dag_dict,
        "active_probing": None,
        "probing_response": None,
        "execution_status": "pending",
    }
