"""
参数更新节点 (Param Update Node)

V2 架构：当 Router 判断为 UI_UPDATE 意图时，
解析用户对策略卡片参数的口语化修改，输出 json_param_update 格式。

例如：
- 用户说 "把分辨率调到 0.4" -> 输出 {"resolution": 0.4, "operation": "set"}
- 用户说 "改成 True" -> 输出 {"某个布尔参数": true, "operation": "set"}
"""

import os
import json
from typing import Annotated

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.agent.schemas import IntentClassification, ParamUpdate


def build_param_update_llm():
    """构建参数更新专用 LLM"""
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


# 参数更新 Prompt
PARAM_UPDATE_PROMPT = """你是一个生信系统的参数解析助手。

【任务】
当用户在已有策略卡片的情况下发送消息，你需要解析用户想要修改的参数。

【输入】
用户消息：{user_message}

【输出要求】
必须使用 with_structured_output 输出 ParamUpdate JSON。
只输出 JSON，不要有其他内容。

【解析规则】
1. 从用户消息中提取参数名和值
2. 参数名可能用中文描述（如"分辨率"、"聚类数"）或英文
3. 值可能是数字、布尔值（true/false、是/否）或字符串
4. operation 固定为 "set"

【示例】
用户消息："把分辨率调到 0.4"
输出：{{"param_updates": [{{"key": "resolution", "value": 0.4, "operation": "set"}}], "message": "已将 resolution 设置为 0.4"}}

用户消息："开启去噪"
输出：{{"param_updates": [{{"key": "denoise", "value": true, "operation": "set"}}], "message": "已将 denoise 设置为 true"}}

用户消息："改成 100 个 cluster"
输出：{{"param_updates": [{{"key": "n_clusters", "value": 100, "operation": "set"}}], "message": "已将 n_clusters 设置为 100"}}
"""


async def param_update_node(state: dict) -> dict:
    """
    参数更新节点入口

    当 Router 判断为 UI_UPDATE 意图时调用。
    解析用户的参数修改请求，输出 json_param_update 格式。

    Args:
        state: 包含 messages 和 intent 的状态

    Returns:
        dict: 包含 ParamUpdate JSON 的消息
    """
    messages = state.get("messages", [])

    if not messages:
        log.warning("🔄 [ParamUpdate] 收到空消息")
        return {
            "messages": [AIMessage(content="我没有看到要更新的参数，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"🔄 [ParamUpdate] 解析参数更新请求: {user_message[:50]}...")

    try:
        llm = build_param_update_llm()
        llm_with_output = llm.with_structured_output(ParamUpdate, method="json_mode")

        prompt = PARAM_UPDATE_PROMPT.format(user_message=user_message)

        messages = [HumanMessage(content=prompt)]
        result: ParamUpdate = await llm_with_output.ainvoke(messages)

        log.info(f"🔄 [ParamUpdate] 参数更新: {result.param_updates}")

        # V2: 输出 json_param_update 代码块，供前端 parseParamUpdate 解析
        param_update_json = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        response_content = f"参数已更新：{result.message}\n\n```json_param_update\n{param_update_json}\n```"

        return {
            "messages": [AIMessage(content=response_content)],
            "param_update": result.model_dump(),  # ✨ 传递参数更新数据
            "next": "end"
        }

    except Exception as e:
        log.error(f"🔄 [ParamUpdate] 解析失败: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，解析参数更新请求失败：{str(e)[:100]}")],
            "next": "end"
        }


log.info("🔄 [ParamUpdate] 参数更新节点已加载")
