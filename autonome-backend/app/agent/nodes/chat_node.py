"""
Chat Agent 节点 - 通用对话和概念解释。

使用 ChatOpenAI.astream() 进行流式输出，
复用现有 chat.py 中的 SYSTEM_PROMPT_CHAT 逻辑。

升级要点：
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def chat_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Chat Agent 节点。

    处理通用对话请求，使用 LLM 流式生成回复。
    实际的 LLM 流式调用在 chat.py 的 SSE 循环中完成，
    此节点只标记意图已路由到 chat_node。

    升级：增加 DAG 指针推进。
    """
    messages = state.get("messages", [])
    intent_data = state.get("intent_data", {})

    log.info(f"[chat_node] 处理对话请求, entities={intent_data.get('entities', {})}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "node": "chat_node"}

    return {
        "intent_data": {**intent_data, "node": "chat_node"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
