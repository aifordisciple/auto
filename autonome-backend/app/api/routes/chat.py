"""
聊天 API - 核心聊天流（纯 LLM 对话模式）

简化版：用户发消息 → LLM 直接流式回复
无意图分类、无技能匹配、无 Agent 编排、无工具调用

拆分说明：
- 会话管理 API → chat_session.py
- 消息收藏 API → chat_bookmark.py
- 会话标签 API → chat_tags.py
- 对话搜索 API → chat_search.py
- Pydantic 模型 → schemas/chat.py
"""

import json
from http import HTTPStatus
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_session, engine
from app.models.domain import (
    ChatSession, ChatMessage, RoleEnum, Project, User,
)
from app.core.logger import log
from app.api.deps import get_current_user
from app.core.content_filter import filter_thinking_content, StreamContentFilter

from app.schemas.chat import ChatRequest


router = APIRouter()


# ==========================================
# 系统提示词
# ==========================================

SYSTEM_PROMPT = """你是一个专业的生物信息学AI助手，名为 Autonome。你可以帮助用户解答生物信息学相关的问题，包括数据分析方法、工具使用、实验设计等。

核心原则：
- 用中文回答问题
- 回答要准确、专业
- 如果不确定，请诚实说明
- 对于用户的提问，始终直接给出专业、详细的回答，这是最重要的规则

身份相关：
- 不要提及你的训练来源、模型身份或开发机构（如 Google、OpenAI 等）
- 当且仅当用户明确询问"你是谁"或"你是什么"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接回答用户的问题"""


# ==========================================
# 核心聊天流 API
# ==========================================

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    核心聊天流 - 纯 LLM SSE 流式对话

    处理流程：
    1. 安全校验和计费检查
    2. 会话创建/恢复
    3. 持久化用户消息
    4. 加载对话历史
    5. LLM 流式调用
    6. 持久化助手消息 + 扣费
    """
    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id)
    if not billing_service.check_available(wallet, min_amount=1.0):
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用大模型与沙箱服务。"
        )

    # 3. 会话创建/恢复
    if request.session_id:
        chat_session = session.get(ChatSession, request.session_id)
        if not chat_session or chat_session.project_id != request.project_id:
            raise HTTPException(status_code=404, detail="会话不存在或已删除")
        is_new_session = False
    else:
        temp_title = request.message[:15] + "..." if len(request.message) > 15 else request.message
        chat_session = ChatSession(project_id=request.project_id, title=temp_title)
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)
        is_new_session = True

    # 4. 持久化用户消息
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=RoleEnum.user,
        content=request.message,
    )
    session.add(user_msg)
    session.commit()
    session_id_for_ai = chat_session.id
    user_id = current_user.id

    # 5. 加载 LLM 配置（共享工具：per-user override → system global → env fallback）
    from app.utils.llm_config import get_llm_config, _is_local_model
    llm_cfg = get_llm_config(session, user_id=current_user.id)
    api_key = llm_cfg.api_key
    base_url = llm_cfg.base_url
    model_name = llm_cfg.model_name
    is_local_model = _is_local_model(base_url)

    # 6. 加载对话历史
    history_messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id_for_ai)
        .order_by(ChatMessage.id)
    ).all()

    # 构建 LangChain 消息列表
    lc_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history_messages:
        if msg.role == RoleEnum.user:
            lc_messages.append({"role": "user", "content": msg.content})
        elif msg.role == RoleEnum.assistant:
            lc_messages.append({"role": "assistant", "content": msg.content})

    # 7. SSE 流式响应
    async def event_generator():
        # 推送 session_id 给前端
        yield {
            "event": "session_info",
            "data": json.dumps({"session_id": session_id_for_ai, "is_new": is_new_session})
        }

        # 检查 API Key
        if not is_local_model and not api_key:
            yield {
                "event": "message",
                "data": json.dumps({"type": "text", "content": "⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。"})
            }
            yield {"event": "done", "data": "[DONE]"}
            return

        # 直接 LLM 流式调用
        from langchain_openai import ChatOpenAI

        ai_full_response = ""
        cost_credits = 1.0
        content_filter = StreamContentFilter()

        try:
            direct_llm = ChatOpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                model=model_name,
                streaming=True,
            )

            async for chunk in direct_llm.astream(lc_messages):
                content = chunk.content
                if content:
                    # 过滤思考标签等内容
                    filtered_content = content_filter.filter_chunk(content)
                    if filtered_content:
                        ai_full_response += filtered_content
                        yield {
                            "event": "message",
                            "data": json.dumps({"type": "text", "content": filtered_content})
                        }

        except StopAsyncIteration:
            raise
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Chat] LLM 调用失败: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
            ai_full_response += err_msg
            yield {"event": "message", "data": json.dumps({"type": "text", "content": err_msg})}

        finally:
            # 持久化助手消息 + 扣费
            with Session(engine) as final_db_session:
                cleaned_response = filter_thinking_content(ai_full_response, model_name=model_name)
                ai_msg = ChatMessage(
                    session_id=session_id_for_ai,
                    role=RoleEnum.assistant,
                    content=cleaned_response,
                )
                final_db_session.add(ai_msg)

                final_balance = 0
                db_user = final_db_session.get(User, user_id)
                if db_user:
                    try:
                        from app.services.billing_service import BillingService
                        bs = BillingService(final_db_session)
                        bs.deduct_credits(
                            wallet_id=wallet.wallet_id,
                            amount=cost_credits,
                            transaction_type="consume_chat",
                            description="聊天消息消费",
                        )
                        final_db_session.refresh(wallet)
                        final_balance = wallet.credits_balance
                    except Exception as e:
                        log.warning(f"扣费失败: {e}")
                        if db_user.billing:
                            db_user.billing.credits_balance -= cost_credits
                            if db_user.billing.credits_balance < 0:
                                db_user.billing.credits_balance = 0
                            final_balance = db_user.billing.credits_balance if db_user.billing else 0

                final_db_session.commit()

                yield {"event": "ai_message_id", "data": json.dumps({"message_id": ai_msg.id})}
                yield {"event": "ai_message_content", "data": json.dumps({"content": cleaned_response})}
                yield {"event": "billing", "data": json.dumps({"cost": cost_credits, "balance": final_balance})}

            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator(), ping=15)
