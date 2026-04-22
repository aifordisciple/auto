"""
System Macro Agent 节点 - 系统宏指令处理。

当用户发送系统级宏指令（如 /status、/help、/clear 等）时路由到此节点。
直接查表返回预设响应，无需 LLM 调用。
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log

# 宏指令预设响应表
MACRO_HANDLERS = {
    "status": "系统状态正常。所有服务运行中。",
    "clear": "对话已清空。（请在前端执行清空操作）",
    "help": "可用指令：/status 查看系统状态 | /clear 清空对话 | /help 查看帮助",
    "reset": "环境已重置。",
    "config": "配置信息请前往设置面板查看。",
}


async def system_macro_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """处理系统宏指令。"""
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})
    macro_name = entities.get("macro_command", "help")
    response_text = MACRO_HANDLERS.get(macro_name, f"未知指令: /{macro_name}")

    log.info(f"[system_macro_node] 处理宏指令: /{macro_name}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "macro": macro_name}

    return {
        "intent_data": {**intent_data, "node": "system_macro_node"},
        "messages": [AIMessage(content=response_text)],
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
