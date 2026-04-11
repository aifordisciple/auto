"""
排错节点 (Troubleshooting Node)

V2 架构：当 Router 判断为 TROUBLESHOOT 意图时调用。
处理报错排查与故障诊断请求。
"""

import os
from typing import Annotated

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log


def build_troubleshooting_llm():
    """构建排错专用 LLM"""
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


# 排错节点 Prompt
TROUBLESHOOTING_PROMPT = """你是一个生信系统的故障诊断专家。

【任务】
分析用户提供的错误信息，定位问题根源并提供解决方案。

【输入】
用户消息：{user_message}

【错误信息】
{error_info}

【输出要求】
1. 分析错误类型和可能的原因
2. 提供解决步骤
3. 如果需要，可以输出修复代码

请用友好的方式解释问题并给出解决方案。
"""


async def troubleshooting_node(state: dict) -> dict:
    """
    排错节点入口

    当 Router 判断为 TROUBLESHOOT 意图时调用。
    分析错误信息，提供解决方案。

    Args:
        state: 包含 messages 和 intent 的状态

    Returns:
        dict: 包含解决方案的消息
    """
    messages = state.get("messages", [])

    if not messages:
        log.warning("🔧 [Troubleshooting] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有看到错误信息，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"🔧 [Troubleshooting] 分析问题: {user_message[:50]}...")

    try:
        # 提取错误信息
        error_info = ""
        if "error" in user_message.lower() or "错误" in user_message:
            error_info = user_message
        else:
            error_info = "用户未提供具体错误信息"

        # 构建 Prompt
        prompt = TROUBLESHOOTING_PROMPT.format(
            user_message=user_message,
            error_info=error_info
        )

        # 调用 LLM
        llm = build_troubleshooting_llm()
        response = await llm.ainvoke(prompt)

        content = response.content if hasattr(response, "content") else str(response)

        log.info(f"🔧 [Troubleshooting] 分析完成")

        return {
            "messages": [AIMessage(content=content)],
            "next": "end"
        }

    except Exception as e:
        log.error(f"🔧 [Troubleshooting] 分析失败: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，分析问题失败：{str(e)[:100]}")],
            "next": "end"
        }


log.info("🔧 [Troubleshooting] 排错节点已加载")
