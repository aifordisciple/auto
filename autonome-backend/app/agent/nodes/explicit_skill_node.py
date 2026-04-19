"""
Explicit Skill Agent 节点 - 执行用户指定的技能。

当用户直接指定技能 ID 或名称时路由到此节点。
使用 SkillExecutor 执行对应的 SKILL.md 定义的分析流程。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def explicit_skill_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Explicit Skill Agent 节点。

    处理显式技能执行请求。
    """
    intent_data = state.get("intent_data", {})
    skill_id = intent_data.get("skill_id") or state.get("skill_id")

    log.info(f"[explicit_skill_node] 执行技能: skill_id={skill_id}")

    return {
        "intent_data": {**intent_data, "node": "explicit_skill_node"},
        "skill_id": skill_id
    }
