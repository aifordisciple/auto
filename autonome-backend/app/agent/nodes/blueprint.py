"""
蓝图节点 (Blueprint Node)

V2 架构：当 Router 判断为 PIPELINE_BUILD 意图时调用。
处理复杂多步骤任务的蓝图规划。
"""

import os
from typing import Annotated

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log


def build_blueprint_llm():
    """构建蓝图规划专用 LLM"""
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


# 蓝图节点 Prompt
BLUEPRINT_PROMPT = """你是一个生信系统的蓝图规划专家。

【任务】
分析用户的多步骤复杂需求，规划完整的分析流程。

【输入】
用户消息：{user_message}

【当前工作区】
{workspace_info}

【输出要求】
将复杂任务拆解为多个步骤的 DAG 蓝图。
输出 json_blueprint 格式：

```json_blueprint
{{
  "project_goal": "任务总体目标",
  "is_complex_task": true,
  "tasks": [
    {{
      "task_id": "task_1",
      "name": "任务名称",
      "tool": "使用的工具",
      "depends_on": [],
      "instruction": "具体执行指令"
    }}
  ]
}}
```

【规划原则】
1. 颗粒度要细：每个任务应该是一个独立的可执行单元
2. 上下文传递：下游任务的 input 应来自上游任务的 output
3. 探针先行：数据探查任务应作为第一步
4. 路径明确：确保任务之间的依赖关系清晰
"""


async def blueprint_node(state: dict) -> dict:
    """
    蓝图节点入口

    当 Router 判断为 PIPELINE_BUILD 意图时调用。
    规划复杂多步骤任务的执行蓝图。

    Args:
        state: 包含 messages 和 intent 的状态

    Returns:
        dict: 包含蓝图的消息
    """
    messages = state.get("messages", [])
    physical_file_info = state.get("physical_file_info", "")

    if not messages:
        log.warning("📋 [Blueprint] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的需求，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"📋 [Blueprint] 规划蓝图: {user_message[:50]}...")

    try:
        # 构建 Prompt
        prompt = BLUEPRINT_PROMPT.format(
            user_message=user_message,
            workspace_info=physical_file_info or "无"
        )

        # 调用 LLM
        llm = build_blueprint_llm()
        response = await llm.ainvoke(prompt)

        content = response.content if hasattr(response, "content") else str(response)

        log.info(f"📋 [Blueprint] 蓝图规划完成")

        return {
            "messages": [AIMessage(content=content)],
            "next": "end"
        }

    except Exception as e:
        log.error(f"📋 [Blueprint] 规划失败: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，规划蓝图失败：{str(e)[:100]}")],
            "next": "end"
        }


log.info("📋 [Blueprint] 蓝图节点已加载")
