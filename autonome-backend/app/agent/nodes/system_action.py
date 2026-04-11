"""
系统操作节点 (System Action Node)

V2 架构：当 Router 判断为 SYSTEM_ACTION 意图时调用。
处理系统级工作区/文件指令。
"""

import os
from typing import Annotated

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log


def build_system_action_llm():
    """构建系统操作专用 LLM"""
    api_key = os.environ.get("OPENAI_API_KEY", "ollama-local")
    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
    model_name = os.environ.get("ROUTER_MODEL", "gpt-3.5-turbo")

    if api_key == "ollama-local" or not api_key:
        return ChatOpenAI(
            api_key="ollama-local",
            base_url=base_url,
            model=model_name,
            temperature=0.1,
            streaming=False,
            max_retries=2,
        )

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=False,
        max_retries=2,
    )


# 系统操作节点 Prompt
SYSTEM_ACTION_PROMPT = """你是一个生信系统的系统操作助手。

【任务】
处理用户对系统文件的操作请求。

【输入】
用户消息：{user_message}

【当前工作区】
{workspace_info}

【输出要求】
根据用户请求执行相应的系统操作：
- 列出目录 -> 返回目录结构
- 查看文件 -> 返回文件内容摘要
- 清空临时文件 -> 确认操作结果
- 其他系统操作 -> 执行并返回结果

请简洁明了地返回操作结果。
"""


async def system_action_node(state: dict) -> dict:
    """
    系统操作节点入口

    当 Router 判断为 SYSTEM_ACTION 意图时调用。
    处理系统级文件操作请求。

    Args:
        state: 包含 messages 和 intent 的状态

    Returns:
        dict: 包含操作结果的消息
    """
    messages = state.get("messages", [])
    physical_file_info = state.get("physical_file_info", "")

    if not messages:
        log.warning("⚙️ [SystemAction] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的指令，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"⚙️ [SystemAction] 执行系统操作: {user_message[:50]}...")

    try:
        # 构建 Prompt
        prompt = SYSTEM_ACTION_PROMPT.format(
            user_message=user_message,
            workspace_info=physical_file_info or "无"
        )

        # 调用 LLM
        llm = build_system_action_llm()
        response = await llm.ainvoke(prompt)

        content = response.content if hasattr(response, "content") else str(response)

        log.info(f"⚙️ [SystemAction] 操作完成")

        return {
            "messages": [AIMessage(content=content)],
            "next": "end"
        }

    except Exception as e:
        log.error(f"⚙️ [SystemAction] 操作失败: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，执行系统操作失败：{str(e)[:100]}")],
            "next": "end"
        }


log.info("⚙️ [SystemAction] 系统操作节点已加载")
