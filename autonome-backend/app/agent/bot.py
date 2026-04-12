"""
Agent 模块 - V2 架构清理版

V1 的 build_bio_agent / build_bio_agent_v2 / build_bio_agent_v2_simple 已删除。
当前活跃的 Agent 构建器是 unified_executor.build_unified_agent。

此文件仅保留共享的工具函数和类型定义。
"""

from typing import Annotated, TypedDict, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.agent.pi_agent import is_complex_task


class AgentState(TypedDict):
    """Agent 状态类型（共享）"""
    messages: Annotated[list[BaseMessage], add_messages]
    next: str


def should_use_pi_agent(user_request: str) -> bool:
    """判断是否需要使用 PI Agent（复杂任务蓝图）"""
    return is_complex_task(user_request)
