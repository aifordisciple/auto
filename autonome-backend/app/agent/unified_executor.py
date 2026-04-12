"""
统一执行器 (Unified Executor)

融合常规 Agent 模式与超级执行者模式，根据意图自动选择执行路径。

V2 执行路径：
├── CHAT → 闲聊节点 (直接响应)
├── EXPLICIT_SKILL → 技能执行节点 → 技能表单构建
├── VAGUE_ANALYSIS → 沙箱规划器 (V2, 门控) → 超级执行者 V4 (回退)
├── TROUBLESHOOT → 排错节点
├── SYSTEM_ACTION → 系统操作节点
│   └── sub_intent="ui_update" → 参数更新节点
"""

import os
import json
from typing import Annotated, Optional, AsyncGenerator, Dict, Any, TypedDict
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages

from app.core.logger import log
from app.agent.schemas import IntentClassification
from app.agent.nodes.chat import chat_node
from app.agent.nodes.retrieval import retrieval_node
from app.agent.nodes.troubleshooting import troubleshooting_node
from app.agent.nodes.system_action import system_action_node
from app.agent.nodes.blueprint import blueprint_node
from app.agent.nodes.param_update import param_update_node
from app.agent.nodes.skill_form_builder import skill_form_builder_node
from app.agent.nodes.skill_execute import skill_execute_node


# 超级执行者 V4 导入
try:
    from app.agent.super_executor_v4 import SuperExecutorV4
    SUPER_EXECUTOR_AVAILABLE = True
except ImportError as e:
    log.warning(f"⚠️ [UnifiedExecutor] 无法导入 SuperExecutorV4: {e}")
    SUPER_EXECUTOR_AVAILABLE = False

# V2: 沙箱规划器导入
try:
    from app.agent.nodes.sandbox_planner import (
        SandboxPlanner, is_sandbox_planner_enabled, sandbox_planner_node
    )
    SANDBOX_PLANNER_AVAILABLE = True
except ImportError as e:
    log.warning(f"⚠️ [UnifiedExecutor] 无法导入 SandboxPlanner: {e}")
    SANDBOX_PLANNER_AVAILABLE = False


class UnifiedExecutorState(TypedDict):
    """统一执行器状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    intent: IntentClassification
    next: str
    physical_file_info: str
    skill_id: str
    skill_params: dict
    project_id: int
    user_id: int


# V2: VAGUE_ANALYSIS 统一走超级执行者（沙箱规划器在 chat.py 层分流）
SUPER_EXECUTOR_INTENTS = {"VAGUE_ANALYSIS"}


async def super_executor_node(state: UnifiedExecutorState) -> dict:
    """
    超级执行者节点

    当意图为 VAGUE_ANALYSIS 或 PIPELINE_BUILD 时调用。
    执行 SuperExecutorV4 三步流程：探查 → 安装 → 执行

    Args:
        state: 包含 messages, intent, project_id, user_id 等的状态

    Returns:
        dict: 包含执行结果的消息
    """
    if not SUPER_EXECUTOR_AVAILABLE:
        log.error("❌ [UnifiedExecutor] SuperExecutorV4 不可用")
        return {
            "messages": [AIMessage(content="抱歉，超级执行者模式暂不可用。")],
            "next": "end"
        }

    messages = state.get("messages", [])
    project_id = state.get("project_id", 0)
    user_id = state.get("user_id", 0)

    if not messages:
        log.warning("📋 [UnifiedExecutor] 超级执行者收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的需求，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"🚀 [UnifiedExecutor] 启动超级执行者 V4: {user_message[:50]}...")

    try:
        # 创建超级执行者实例
        executor = SuperExecutorV4(
            raw_input=user_message,
            project_id=str(project_id),
            user_id=user_id,
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            model_name=os.environ.get("MODEL_NAME", "gpt-4o")
        )

        # 收集所有事件
        all_events = []
        async for event in executor.run():
            all_events.append(event)
            # 可以在这里处理 SSE 事件流

        # 从事件中提取最终结果
        final_content = "执行完成，请查看结果。"
        for event in reversed(all_events):
            event_type = event.get("event", "")
            # SuperExecutorV4 使用 execution_output / status_update / battle_report 事件类型
            if event_type in ("execution_output", "status_update", "message"):
                try:
                    data = json.loads(event.get("data", "{}"))
                    content = data.get("content", "")
                    if content:
                        final_content = content
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
            elif event_type == "battle_report":
                # 如果有战报，格式化输出
                battle_data = json.loads(event.get("data", "{}"))
                final_content = f"""✅ 执行完成！

**输出目录**: `{battle_data.get('task_out_dir', '')}`
**执行时间**: {battle_data.get('execution_time', 0):.2f} 秒
**生成文件数**: {len(battle_data.get('generated_files', []))} 个
"""
                break

        return {
            "messages": [AIMessage(content=final_content)],
            "next": "end"
        }

    except Exception as e:
        log.error(f"❌ [UnifiedExecutor] 超级执行者异常: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，执行过程中出现错误：{str(e)[:200]}")],
            "next": "end"
        }


async def unified_agent_node(state: UnifiedExecutorState) -> dict:
    """
    统一执行器主节点

    V2: 内联完成意图分类和路由执行：
    - VAGUE_ANALYSIS → 沙箱规划器 (门控) → 超级执行者 V4 (回退)
    - CHAT → 闲聊节点
    - EXPLICIT_SKILL → 技能执行节点
    - SYSTEM_ACTION + sub_intent="ui_update" → 参数更新节点
    - 其他 → 相应专业节点

    Args:
        state: 包含 messages, intent 的状态

    Returns:
        dict: 包含执行结果的消息
    """
    from app.agent.nodes.router import router_node_logic

    messages = state.get("messages", [])
    physical_file_info = state.get("physical_file_info", "")
    project_id = state.get("project_id", 0)
    user_id = state.get("user_id", 0)
    intent = None  # 初始化，确保异常处理中可安全引用

    try:
        # 1. 意图分类
        intent_result = await router_node_logic(messages, physical_file_info)
        intent = intent_result.get("intent")
        next_node = intent_result.get("next", "chat")

        if intent:
            intent_type = intent.intent if hasattr(intent, "intent") else str(intent)
            sub_intent = getattr(intent, 'sub_intent', None)
            log.info(f"🤖 [UnifiedExecutor] 意图类型: {intent_type}, sub_intent: {sub_intent}, 路由到: {next_node}")

            # 检查是否有闲聊响应（提前返回）
            if "messages" in intent_result and intent_result["messages"]:
                return {
                    "messages": intent_result["messages"],
                    "intent": intent
                }

            # 2. 根据意图类型执行相应逻辑
            if intent_type == "CHAT":
                # 闲聊节点 — chat_node 是同步函数，直接调用
                user_msg = messages[-1].content if messages and hasattr(messages[-1], "content") else ""
                result_text = chat_node(user_msg)
                return {
                    "messages": [AIMessage(content=result_text)],
                    "intent": intent
                }

            elif intent_type == "EXPLICIT_SKILL":
                # 技能执行节点
                result = await skill_execute_node(state)
                return result

            elif intent_type in SUPER_EXECUTOR_INTENTS:
                # V2: VAGUE_ANALYSIS → 沙箱规划器 (门控) → 超级执行者 V4 (回退)
                if SANDBOX_PLANNER_AVAILABLE and is_sandbox_planner_enabled():
                    log.info(f"📋 [UnifiedExecutor] 沙箱规划器已启用，尝试沙箱规划")
                    planner_result = await sandbox_planner_node(state)

                    # 沙箱规划成功
                    if not planner_result.get("fallback"):
                        return planner_result

                    # 沙箱规划失败，回退到超级执行者 V4
                    log.warning(f"📋 [UnifiedExecutor] 沙箱规划失败，回退到超级执行者 V4: {planner_result.get('planner_error', '')}")

                # 超级执行者 V4（直接或回退）
                return await super_executor_node(state)

            elif intent_type == "TROUBLESHOOT":
                result = await troubleshooting_node(state)
                return result

            elif intent_type == "SYSTEM_ACTION":
                # V2: SYSTEM_ACTION + sub_intent="ui_update" → 参数更新节点
                if sub_intent == "ui_update":
                    result = await param_update_node(state)
                    return result
                result = await system_action_node(state)
                return result

            else:
                # 默认走 retrieval
                result = await retrieval_node(state)
                return result

        # 无意图结果，默认闲聊
        result = await chat_node(state)
        return result

    except Exception as e:
        log.error(f"❌ [UnifiedExecutor] 执行异常: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，执行过程中出现错误：{str(e)[:200]}")],
            "intent": intent
        }


def build_unified_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    physical_file_info: str,
    user_id: int,
    project_id: int,
    selected_skill_id: Optional[str] = None,
    vision_config: Optional[dict] = None,
    task_mode: Optional[str] = None
):
    """
    构建统一执行器

    V2 融合常规 Agent 模式与超级执行者模式：
    - CHAT → 闲聊节点
    - EXPLICIT_SKILL → 技能执行节点
    - VAGUE_ANALYSIS → 沙箱规划器 (门控) → 超级执行者 V4 (回退)
    - SYSTEM_ACTION + sub_intent="ui_update" → 参数更新节点
    - 其他 → 相应专业节点

    Args:
        api_key: API 密钥
        base_url: API 基础 URL
        model_name: 模型名称
        physical_file_info: 物理文件信息
        user_id: 用户 ID
        project_id: 项目 ID
        selected_skill_id: 选中的技能 ID (可选)
        vision_config: 视觉模型配置 (可选)
        task_mode: 任务模式 (可选)

    Returns:
        编译后的 LangGraph 工作流
    """
    log.info(f"🤖 [UnifiedExecutor] 构建统一执行器 - API: {base_url}, Model: {model_name}")

    # 定义状态类型
    class UnifiedState(TypedDict):
        messages: Annotated[list[BaseMessage], add_messages]
        intent: IntentClassification
        next: str
        physical_file_info: str
        skill_id: str
        skill_params: dict
        project_id: int
        user_id: int

    # ✨ 简化架构：只使用 unified 一个节点，直接调用各专业模块
    # 不再使用 LangGraph 多节点架构，避免状态类型冲突
    workflow = StateGraph(UnifiedState)
    workflow.add_node("unified", unified_agent_node)

    # 设置入口边和出口
    workflow.add_edge(START, "unified")
    workflow.add_edge("unified", END)

    log.info("🔀 [UnifiedExecutor] 统一执行器工作流已构建")

    return workflow.compile()


# ✨ 便捷函数：根据意图判断是否使用超级执行者
def should_use_super_executor(intent_type: str) -> bool:
    """判断意图类型是否应使用超级执行者"""
    return intent_type in SUPER_EXECUTOR_INTENTS


# ✨ 获取执行模式描述
def get_executor_mode_description(intent_type: str) -> str:
    """获取执行模式的描述"""
    descriptions = {
        "CHAT": "闲聊模式 - 直接响应",
        "EXPLICIT_SKILL": "技能执行模式 - 执行指定技能",
        "VAGUE_ANALYSIS": "沙箱规划模式 - 智能规划（回退到超级执行者）",
        "TROUBLESHOOT": "排错模式 - 诊断并解决问题",
        "SYSTEM_ACTION": "系统操作模式 - 执行系统命令",
    }
    return descriptions.get(intent_type, "未知模式")


log.info("🤖 [UnifiedExecutor] 统一执行器模块已加载")
