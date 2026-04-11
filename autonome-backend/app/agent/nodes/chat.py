"""
闲聊节点 (Chat Node)

专门处理闲聊/问候，直接流式输出，无 JSON/代码。
解决"问你好却夹杂代码"的问题。
"""

from typing import Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI

from app.core.logger import log


class ChatState(dict):
    """闲聊状态"""
    messages: list


# 闲聊回复模板
CASUAL_RESPONSES = {
    "greeting": [
        "你好！有什么我可以帮助你的吗？",
        "嗨！我是 Autonome 生信分析助手，可以帮你处理生物信息学数据。",
        "你好！可以问我关于数据分析、代码编写等问题。",
    ],
    "thanks": [
        "不客气！还有什么需要帮忙的吗？",
        "很高兴帮到你！有其他问题随时问我。",
        "不用谢！继续加油！",
    ],
    "bye": [
        "再见！有需要随时回来。",
        "拜拜！祝工作顺利！",
        "下次见！",
    ],
    "help": [
        "我可以帮你：\n1. 分析生物数据\n2. 编写 Python/R 代码\n3. 执行 SKILL 工作流\n4. 生成可视化图表\n\n有什么具体需求吗？",
        "需要帮忙吗？我可以：\n- 处理测序数据\n- 编写数据处理脚本\n- 生成分析报告\n\n说说你的需求吧！",
    ],
    "default": [
        "明白，请说。",
        "好的，我在听。",
        "了解，请继续。",
    ],
}


def _match_casual_type(message: str) -> str:
    """匹配闲聊类型"""
    msg = message.strip().lower()

    if any(kw in msg for kw in ["你好", "hi", "hello", "嗨", "您好", "hey"]):
        return "greeting"
    if any(kw in msg for kw in ["谢谢", "thanks", "thx"]):
        return "thanks"
    if any(kw in msg for kw in ["再见", "bye", "拜拜"]):
        return "bye"
    if any(kw in msg for kw in ["帮忙", "help", "帮帮我", "请问", "question"]):
        return "help"
    return "default"


def build_chat_agent():
    """
    构建闲聊 Agent

    极简 Prompt，直接回复，无 JSON/代码输出。
    """
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",  # 使用轻量模型，速度快
        temperature=0.7,
        streaming=True,
        max_retries=2,
    )

    system_prompt = """你是 Autonome 生信平台的友好助手。

回复要求：
1. 简洁、自然、友好
2. 不要输出任何代码块、JSON 或格式化标记
3. 直接用自然语言回复
4. 如果用户问工作相关问题，可以引导到具体功能
"""

    def _get_response(state: ChatState) -> dict:
        """生成闲聊回复"""
        messages = state.get("messages", [])
        if not messages:
            return {"messages": []}

        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # 匹配类型
        casual_type = _match_casual_type(user_message)
        response_text = CASUAL_RESPONSES.get(casual_type, CASUAL_RESPONSES["default"])[0]

        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content=response_text)]}

    workflow = StateGraph(ChatState)
    workflow.add_node("chat", _get_response)
    workflow.add_edge(START, "chat")
    workflow.add_edge("chat", END)

    return workflow.compile()


# 全局闲聊 Agent 实例
_chat_agent = None


def get_chat_agent():
    """获取闲聊 Agent（延迟初始化）"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = build_chat_agent()
        log.info("💬 [Chat] 闲聊节点已初始化")
    return _chat_agent


async def handle_casual_chat(message: str) -> str:
    """
    处理闲聊请求

    Args:
        message: 用户消息

    Returns:
        闲聊回复文本
    """
    agent = get_chat_agent()

    from langchain_core.messages import HumanMessage
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})

    final_msg = result["messages"][-1]
    return final_msg.content if hasattr(final_msg, "content") else str(final_msg)


# 直接同步版本（用于简单场景）
def chat_node(message: str) -> str:
    """
    闲聊节点入口（同步版本）

    Args:
        message: 用户消息

    Returns:
        回复文本
    """
    casual_type = _match_casual_type(message)
    return CASUAL_RESPONSES.get(casual_type, CASUAL_RESPONSES["default"])[0]


log.info("💬 [Chat] 闲聊节点模块已加载")
