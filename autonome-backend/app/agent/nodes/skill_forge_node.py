"""
Skill Forge Agent 节点 - 代码生成与执行。

当用户需要生成或执行生信分析代码时路由到此节点。
使用 SkillExecutor 在 Docker 沙箱中执行代码。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def skill_forge_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Skill Forge Agent 节点。

    处理代码生成/执行请求。
    实际的 SkillExecutor 调用和 LLM 代码生成在 chat.py 的 SSE 循环中完成。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[skill_forge_node] 处理代码生成请求, entities={entities}")

    return {
        "intent_data": {**intent_data, "node": "skill_forge_node"}
    }
