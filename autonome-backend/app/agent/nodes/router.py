"""
极速路由节点 (Router Node)

V2 架构核心组件：接收用户输入的第一道网关。
使用轻量级模型，加载最小化上下文（仅最近2-3轮对话+当前高亮文件名），
严禁加载全局文件树或技能库。

输出结构化 IntentClassification，决定后续节点分流。
"""

import os
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.agent.schemas import IntentClassification, IntentType


# 意图类型常量（与 IntentType Literal 对应）
# V2: 精简为 5 种（PIPELINE_BUILD→VAGUE_ANALYSIS, UI_UPDATE→SYSTEM_ACTION）
INTENT_CHAT = "CHAT"
INTENT_EXPLICIT_SKILL = "EXPLICIT_SKILL"
INTENT_VAGUE_ANALYSIS = "VAGUE_ANALYSIS"
INTENT_TROUBLESHOOT = "TROUBLESHOOT"
INTENT_SYSTEM_ACTION = "SYSTEM_ACTION"

# V2: 置信度阈值 — 低于此值回退到 CHAT
CONFIDENCE_THRESHOLD = float(os.environ.get("AUTONOME_ROUTER_CONFIDENCE_THRESHOLD", "0.6"))


class RouterState(TypedDict):
    """路由节点状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    intent: IntentClassification
    next: str


def add_messages(left: list[BaseMessage], right: list[BaseMessage]) -> list[BaseMessage]:
    """消息合并"""
    return left + right


# 闲聊快速响应映射（无需调用 LLM）
CASUAL_RESPONSES = {
    "greeting": "你好！有什么我可以帮助你的吗？可以问我关于数据分析、代码编写、SKILL 执行等问题。",
    "thanks": "不客气！还有什么需要帮忙的吗？",
    "bye": "再见！有需要随时回来。",
    "help": """我可以帮你：
1. 分析生物数据
2. 编写 Python/R 代码
3. 执行 SKILL 工作流
4. 生成可视化图表

有什么具体需求吗？""",
    "default": "明白，请说。",
}

# 理论问答模式关键词（用于区分 casual 和 theory）
THEORY_KEYWORDS = [
    "什么是", "怎么理解", "如何理解", "解释一下", "告诉我", "帮我理解",
    "是什么意思", "是指", "定义", "原理", "概念",
    "有什么区别", "有什么不同", "为什么", "怎样理解", "如何选择",
    "介绍一下", "简单介绍", "简述", "概述", "说明",
    "what is", "how to understand", "explain", "tell me about",
]


def _detect_casual_type(message: str) -> str:
    """
    检测闲聊类型（同步快速检测）

    用于纯闲聊场景的快速拦截。
    """
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


# 极简路由 Prompt（<200 tokens）
# V2: 精简为 5 种意图类型
ROUTER_PROMPT = """你是一个生信系统的极速路由网关。

【核心职责】根据用户输入和当前上下文，判断其核心意图。

【输入上下文】
- 用户消息：{user_message}
- 当前高亮文件：{physical_file_info}

【意图类型定义】（5 种）
- CHAT: 纯理论问答、概念解释、打招呼（直接流式输出，无中断）
- EXPLICIT_SKILL: 用户选择了技能或明确指定调用某工具（如"跑一下 FastQC"）
- VAGUE_ANALYSIS: 模糊的数据分析需求或复杂蓝图构建（如"对这个矩阵做聚类"、"帮我做一个 RNA-seq 分析流程"）
- TROUBLESHOOT: 报错排查与故障诊断
- SYSTEM_ACTION: 系统级指令或 UI 参数修改（如"清空临时文件"、"把分辨率调到 0.4"）

【输出要求】
必须使用 with_structured_output 输出 IntentClassification JSON。
只输出 JSON，不要有其他内容。

【判断规则】
1. 如果是打招呼/感谢/再见，直接 CHAT
2. 如果明确提到技能名（如 FastQC、SCTransform），EXPLICIT_SKILL
3. 如果提到错误信息/报错/异常，TROUBLESHOOT
4. 如果提到系统操作/清空/重置/文件列表，SYSTEM_ACTION
5. 如果用户对策略卡片参数做口语化修改（如"调到xxx"、"改成xxx"），SYSTEM_ACTION（sub_intent=ui_update）
6. 如果是多步骤复杂需求（"帮我做一个 RNA-seq 分析流程"），VAGUE_ANALYSIS（sub_intent=pipeline_build）
7. 其他模糊分析需求，VAGUE_ANALYSIS
"""


def build_router_llm():
    """
    构建路由专用 LLM

    使用轻量级模型，temperature=0.1 保证输出稳定。
    """
    api_key = os.environ.get("OPENAI_API_KEY", "ollama-local")
    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
    model_name = os.environ.get("ROUTER_MODEL", "gpt-3.5-turbo")

    # 如果是 ollama-local，使用本地模型
    if api_key == "ollama-local" or not api_key:
        return ChatOpenAI(
            api_key="ollama-local",
            base_url=base_url,
            model=model_name,
            temperature=0.1,
            streaming=False,  # 路由不需要流式
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


# 全局路由 LLM 实例
_router_llm = None


def get_router_llm():
    """获取路由 LLM（延迟初始化）"""
    global _router_llm
    if _router_llm is None:
        _router_llm = build_router_llm()
        log.info("🔀 [Router] 极速路由节点已初始化")
    return _router_llm


def create_router_node():
    """
    创建带结构化输出的路由节点

    Returns:
        配置好的 LLM，支持 with_structured_output
    """
    llm = get_router_llm()
    return llm.with_structured_output(IntentClassification, method="json_mode")


async def router_node_logic(messages: list, physical_file_info: str) -> dict:
    """
    极速路由核心逻辑（可独立调用）

    职责：
    1. 截取最近 2-3 轮对话
    2. 检测闲聊（快速路径）
    3. 调用 LLM 进行意图分类
    4. 返回分流决策

    Args:
        messages: 消息列表
        physical_file_info: 物理文件信息

    Returns:
        dict: 包含 intent 和 next 节点名称
    """
    if not messages:
        log.warning("🔀 [Router] 收到空消息，跳转到 VAGUE_ANALYSIS")
        return {
            "intent": IntentClassification(intent=INTENT_VAGUE_ANALYSIS, reason="空消息"),
            "next": "retrieval"
        }

    # ========== 闲聊快速检测 ==========
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # ==========================================
    # ✨ UI 隐式指令硬编码路由 (0延迟，免大模型)
    # ==========================================
    # 检测 UI_ACTION 前缀的隐式指令
    if user_message.startswith("[UI_ACTION:"):
        log.info(f"[Router] UI_ACTION 隐式指令检测: message_prefix={user_message.split(']')[0]}]")

    if user_message.startswith("[UI_ACTION:REQUEST_SKILL_PARAMS]"):
        skill_id = user_message.split("]")[1].strip()
        log.info(f"🔀 [Router] 捕获隐式指令: 请求技能参数表单, skill_id={skill_id}")
        return {
            "intent": IntentClassification(
                intent=INTENT_SYSTEM_ACTION,
                reason="拉取参数表单",
                confidence=1.0,
                entities={"skill_id": skill_id}
            ),
            "next": "skill_form_builder"
        }

    if user_message.startswith("[UI_ACTION:EXECUTE_SKILL]"):
        import json
        try:
            payload_str = user_message.split("]", 1)[1].strip()
            payload = json.loads(payload_str)
            skill_id = payload.get("skill_id", "")
            skill_params = payload.get("parameters", {})
            log.info(f"🔀 [Router] 捕获隐式指令: 确定执行技能, skill_id={skill_id}")
            return {
                "intent": IntentClassification(
                    intent=INTENT_EXPLICIT_SKILL,
                    reason="执行技能",
                    confidence=1.0,
                    entities={"skill_id": skill_id, "skill_params": skill_params}
                ),
                "next": "skill_execute",
                "skill_id": skill_id,
                "skill_params": skill_params
            }
        except json.JSONDecodeError as e:
            log.error(f"🔀 [Router] 解析 EXECUTE_SKILL payload 失败: {e}")
            return {
                "intent": IntentClassification(intent=INTENT_VAGUE_ANALYSIS, reason="执行指令解析失败"),
                "next": "retrieval"
            }

    casual_type = _detect_casual_type(user_message)
    # ✨ 只对明确的闲聊类型走快速路径，"default" 需要 LLM 分类
    if casual_type != "default" and casual_type in CASUAL_RESPONSES:
        log.info(f"🔀 [Router] 闲聊快速响应: {casual_type}")
        return {
            "intent": IntentClassification(
                intent=INTENT_CHAT,
                confidence=1.0,
                entities={"casual_type": casual_type},
                reason=f"闲聊类型: {casual_type}",
                chat_subtype="casual"
            ),
            "next": "chat",
            "messages": [AIMessage(content=CASUAL_RESPONSES[casual_type])]
        }

    # ✨ V2: 检测理论问答模式（无需全量 Agent，走轻量 LLM 流式）
    msg_lower = user_message.strip().lower()
    if any(kw in msg_lower for kw in THEORY_KEYWORDS):
        log.info(f"🔀 [Router] 理论问答检测，走轻量 LLM 流式")
        return {
            "intent": IntentClassification(
                intent=INTENT_CHAT,
                confidence=0.85,
                entities={"chat_subtype": "theory"},
                reason="检测到理论知识问答需求",
                chat_subtype="theory"
            ),
            "next": "chat"
        }

    # ========== LLM 结构化意图分类 ==========
    try:
        llm_with_output = create_router_node()

        # 构建极简上下文（仅最近3轮 + 高亮文件）
        recent_messages = messages[-3:] if len(messages) > 3 else messages
        context_user_msgs = []
        for msg in recent_messages:
            if hasattr(msg, "content"):
                context_user_msgs.append(msg.content)

        user_message_combined = "\n".join(context_user_msgs)

        # 填充 Prompt
        prompt = ROUTER_PROMPT.format(
            user_message=user_message_combined,
            physical_file_info=physical_file_info
        )

        # 调用 LLM 获取结构化输出
        intent_result: IntentClassification = await llm_with_output.ainvoke(prompt)

        log.info(f"[Router] 意图分类结果: intent={intent_result.intent}, confidence={intent_result.confidence:.2f}, sub_intent={intent_result.sub_intent}, reason={intent_result.reason}")
        log.debug(f"[Router] 意图分类详情: entities={intent_result.entities}, chat_subtype={intent_result.chat_subtype}")

        # V2: 置信度门控 — 低于阈值回退到 CHAT
        if intent_result.confidence < CONFIDENCE_THRESHOLD:
            log.info(f"[Router] 置信度不足回退: confidence={intent_result.confidence:.2f} < threshold={CONFIDENCE_THRESHOLD}, 原意图={intent_result.intent} → 回退到 CHAT")
            intent_result = IntentClassification(
                intent=INTENT_CHAT,
                confidence=intent_result.confidence,
                entities=intent_result.entities,
                reason=f"置信度不足({intent_result.confidence:.2f})，原意图: {intent_result.intent}",
                chat_subtype="theory"
            )

        # 根据意图决定下一个节点
        next_node = _decide_next_node(intent_result)

        return {
            "intent": intent_result,
            "next": next_node
        }

    except Exception as e:
        log.error(f"🔀 [Router] LLM 调用失败: {e}，默认跳转到 VAGUE_ANALYSIS")
        return {
            "intent": IntentClassification(
                intent=INTENT_VAGUE_ANALYSIS,
                confidence=0.0,
                entities={},
                reason=f"路由失败: {str(e)[:50]}"
            ),
            "next": "retrieval"
        }


async def router_node(state: RouterState) -> dict:
    """
    极速路由节点入口（LangGraph 节点包装器）

    Args:
        state: RouterState，包含 messages 和 physical_file_info

    Returns:
        dict: 包含 intent 和 next 节点名称
    """
    messages = state.get("messages", [])
    physical_file_info = state.get("physical_file_info", "无")
    return await router_node_logic(messages, physical_file_info)


def _decide_next_node(intent: IntentClassification) -> str:
    """
    根据意图类型决定下一个节点

    V2: 5 种意图类型，PIPELINE_BUILD 和 UI_UPDATE 通过 sub_intent 保留语义

    Args:
        intent: 意图分类结果

    Returns:
        下一个节点的名称
    """
    intent_type = intent.intent

    # CHAT -> chat_node (闲聊节点)
    if intent_type == INTENT_CHAT:
        return "chat"

    # EXPLICIT_SKILL -> skill_execute (技能执行节点)
    if intent_type == INTENT_EXPLICIT_SKILL:
        return "skill_execute"

    # VAGUE_ANALYSIS -> super_executor (含原 PIPELINE_BUILD)
    if intent_type == INTENT_VAGUE_ANALYSIS:
        if intent.sub_intent == "pipeline_build":
            log.info(f"[Router] sub_intent 分流: intent=VAGUE_ANALYSIS, sub_intent=pipeline_build → super_executor")
        return "super_executor"

    # TROUBLESHOOT -> troubleshooting (排错节点)
    if intent_type == INTENT_TROUBLESHOOT:
        return "troubleshooting"

    # SYSTEM_ACTION -> system_action (含原 UI_UPDATE，通过 sub_intent 区分)
    if intent_type == INTENT_SYSTEM_ACTION:
        # V2: 如果 sub_intent 是 ui_update，路由到 param_update
        if intent.sub_intent == "ui_update":
            log.info(f"[Router] sub_intent 分流: intent=SYSTEM_ACTION, sub_intent=ui_update → param_update")
            return "param_update"
        log.debug(f"[Router] SYSTEM_ACTION 路由: sub_intent={intent.sub_intent} → system_action")
        return "system_action"

    # 默认跳转到 retrieval
    return "retrieval"


def get_intent_routing_edges() -> dict[str, str]:
    """
    获取意图到节点的映射

    用于 LangGraph conditional_edges。
    V2: 5 种意图类型

    Returns:
        dict: intent -> node_name 映射
    """
    return {
        INTENT_CHAT: "chat",
        INTENT_EXPLICIT_SKILL: "skill_execute",
        INTENT_VAGUE_ANALYSIS: "super_executor",
        INTENT_TROUBLESHOOT: "troubleshooting",
        INTENT_SYSTEM_ACTION: "system_action",  # sub_intent=ui_update 时由 _decide_next_node 路由到 param_update
    }


log.info("🔀 [Router] 极速路由节点模块已加载")
