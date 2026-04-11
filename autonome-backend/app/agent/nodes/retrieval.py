"""
检索节点 (Retrieval Node)

V2 架构：当 Router 判断为 VAGUE_ANALYSIS 意图时调用。
负责检索和匹配相关技能，返回推荐结果供用户选择。
"""

import os
from typing import Annotated

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.agent.schemas import IntentClassification


def build_retrieval_llm():
    """构建检索专用 LLM"""
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


# 检索节点 Prompt
RETRIEVAL_PROMPT = """你是一个生信系统的技能检索助手。

【任务】
根据用户需求，检索最相关的技能。

【输入】
用户消息：{user_message}

【技能目录】
{skill_catalog}

【输出要求】
从技能目录中选择最匹配的技能（最多3个），并给出匹配理由。
输出 json_action_menu 格式：

```json_action_menu
{{
  "title": "推荐操作",
  "message": "根据您的需求，我推荐以下操作：",
  "options": [
    {{
      "skill_id": "技能ID",
      "name": "技能名称",
      "match_score": 0.85,
      "match_reason": "匹配理由"
    }}
  ]
}}
```
"""


async def retrieval_node(state: dict) -> dict:
    """
    检索节点入口

    当 Router 判断为 VAGUE_ANALYSIS 意图时调用。
    检索相关技能，返回推荐选项供用户选择。

    Args:
        state: 包含 messages 和 intent 的状态

    Returns:
        dict: 包含推荐选项的消息
    """
    messages = state.get("messages", [])
    physical_file_info = state.get("physical_file_info", "")

    if not messages:
        log.warning("🔍 [Retrieval] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的需求，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"🔍 [Retrieval] 检索技能: {user_message[:50]}...")

    try:
        # 加载技能目录
        from app.agent.context_builder import build_skill_catalog_md
        skill_catalog, _ = build_skill_catalog_md(user_id=0, query=user_message, top_k=5)

        # 构建 Prompt
        prompt = RETRIEVAL_PROMPT.format(
            user_message=user_message,
            skill_catalog=skill_catalog
        )

        # 调用 LLM
        llm = build_retrieval_llm()
        response = await llm.ainvoke(prompt)

        content = response.content if hasattr(response, "content") else str(response)

        log.info(f"🔍 [Retrieval] 检索完成")

        return {
            "messages": [AIMessage(content=content)],
            "next": "end"
        }

    except Exception as e:
        log.error(f"🔍 [Retrieval] 检索失败: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，检索技能失败：{str(e)[:100]}")],
            "next": "end"
        }


log.info("🔍 [Retrieval] 检索节点已加载")
