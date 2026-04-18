"""
聊天 API - 核心聊天流（意图感知模式）

处理流程：
1. 安全校验和计费检查
2. 会话创建/恢复
3. 意图分类（代码生成 / 技能匹配 / 一般问答）
4. 根据意图选择系统提示词
5. LLM 流式调用
6. 持久化助手消息 + 扣费

拆分说明：
- 会话管理 API → chat_session.py
- 消息收藏 API → chat_bookmark.py
- 会话标签 API → chat_tags.py
- 对话搜索 API → chat_search.py
- Pydantic 模型 → schemas/chat.py
"""

import json
import asyncio
from http import HTTPStatus
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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

# 一般问答模式：知识解答
SYSTEM_PROMPT_CHAT = """你是一个专业的生物信息学AI助手，名为 Autonome。你可以帮助用户解答生物信息学相关的问题，包括数据分析方法、工具使用、实验设计等。

核心原则：
- 用中文回答问题
- 回答要准确、专业
- 如果不确定，请诚实说明
- 对于用户的提问，始终直接给出专业、详细的回答，这是最重要的规则

身份相关：
- 不要提及你的训练来源、模型身份或开发机构（如 Google、OpenAI 等）
- 当且仅当用户明确询问"你是谁"或"你是什么"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接回答用户的问题"""

# 代码生成模式：编写可执行代码
SYSTEM_PROMPT_CODE = """你是一个专业的生物信息学编程助手，名为 Autonome。你的核心职责是为用户编写可执行的数据分析代码。

核心原则：
- 用中文解释思路，但代码本身使用英文变量名和注释
- 始终直接输出可执行的代码，不要只解释概念或方法
- 优先使用 Python + scanpy/pandas/matplotlib/seaborn 等生信常用库
- 代码必须完整可运行，包含数据读取、处理、分析、可视化和结果保存
- 使用环境变量 TASK_OUT_DIR 获取输出目录，将结果保存到该目录
- 如果用户没有指定输入文件，使用示例数据演示分析流程
- 代码中不要硬编码路径，使用相对路径或环境变量

输出格式：
1. 先用简短的中文说明分析思路（2-3句话）
2. 然后输出完整的 Python 代码块（```python ... ```）
3. 代码中包含关键步骤的中文注释

身份相关：
- 不要提及你的训练来源、模型身份或开发机构
- 当且仅当用户明确询问"你是谁"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接编写代码"""


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
    核心聊天流 - 意图感知 SSE 流式对话

    处理流程：
    1. 安全校验和计费检查
    2. 会话创建/恢复
    3. 持久化用户消息
    4. 意图分类（代码生成 / 技能匹配 / 一般问答）
    5. 根据意图选择系统提示词
    6. LLM 流式调用
    7. 持久化助手消息 + 扣费
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

    # 6. 意图分类：判断用户是要求写代码还是一般问答
    # 使用 SkillMatcher 进行快速规则匹配，区分代码生成请求和一般问题
    intent_type = "general_question"  # 默认为一般问答
    try:
        from app.services.skill_matcher import SkillMatcher, IntentType
        matcher = SkillMatcher()
        match_result = await matcher.match(request.message, context={"project_id": request.project_id})
        intent_type = match_result.get("intent_type", IntentType.GENERAL_QUESTION)
        log.info(f"[Chat] 意图分类: intent={intent_type}, query='{request.message[:50]}...'")
    except Exception as e:
        log.warning(f"[Chat] 意图分类失败，回退到一般问答模式: {e}")

    # 根据意图选择系统提示词
    # LIVE_CODING / IMPLICIT_SKILL / EXPLICIT_SKILL → 代码生成模式
    # GENERAL_QUESTION → 一般问答模式
    if intent_type in (IntentType.LIVE_CODING, IntentType.IMPLICIT_SKILL, IntentType.EXPLICIT_SKILL):
        system_prompt = SYSTEM_PROMPT_CODE
        log.info(f"[Chat] 使用代码生成模式 (intent={intent_type})")
    else:
        system_prompt = SYSTEM_PROMPT_CHAT
        log.info(f"[Chat] 使用一般问答模式 (intent={intent_type})")

    # 7. 加载对话历史
    history_messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id_for_ai)
        .order_by(ChatMessage.id)
    ).all()

    # 构建 LangChain 消息列表（根据意图使用不同的系统提示词）
    lc_messages = [{"role": "system", "content": system_prompt}]
    for msg in history_messages:
        if msg.role == RoleEnum.user:
            lc_messages.append({"role": "user", "content": msg.content})
        elif msg.role == RoleEnum.assistant:
            lc_messages.append({"role": "assistant", "content": msg.content})

    # 8. SSE 流式响应
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
                    # 🔍 调试日志：记录每个 chunk 的大小
                    log.info(f"[Chat] SSE chunk: len={len(content)}, preview={content[:50]!r}")
                    # ✨ 过滤思考标签等内容，返回 (content, type) 元组
                    # type: "text" = 正常回复, "thinking" = 思考过程
                    filtered_content, content_type = content_filter.filter_chunk(content)
                    if filtered_content:
                        if content_type == "thinking":
                            # ✨ 思考过程通过 thinking 事件类型推送给前端
                            yield {
                                "event": "thinking",
                                "data": json.dumps({"type": "thinking", "content": filtered_content})
                            }
                        else:
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

    # 防缓冲头：确保 SSE 流不被 nginx/CDN 等中间代理缓冲
    # X-Accel-Buffering: no 是 nginx 专用头，告诉 nginx 禁用此响应的代理缓冲
    return EventSourceResponse(
        event_generator(),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==========================================
# 队列驱动的 SSE 流式响应
# ==========================================

class QueueStreamRequest(BaseModel):
    """队列流请求"""
    session_id: str
    project_id: str


@router.post("/stream/queue")
async def chat_stream_queue(
    request: QueueStreamRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    队列驱动的 SSE 流式响应

    订阅 Redis pub/sub channel，转发 Celery worker 处理队列项时推送的 SSE 事件。
    前端在消息入队后调用此端点，接收所有队列项的流式回复。
    """
    # 安全校验
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    chat_session = session.get(ChatSession, request.session_id)
    if not chat_session or chat_session.project_id != request.project_id:
        raise HTTPException(status_code=404, detail="会话不存在或已删除")

    session_id = request.session_id

    async def queue_event_generator():
        """
        订阅 Redis pub/sub channel，转发 Celery worker 的 SSE 事件给前端

        流程：
        1. 推送 session_info 确认连接
        2. 订阅 chat_stream:{session_id} channel
        3. 转发所有事件直到收到 queue_done
        """
        # 确认连接
        yield {
            "event": "session_info",
            "data": json.dumps({"session_id": session_id, "is_new": False})
        }

        # 订阅 Redis pub/sub
        import redis.asyncio as aioredis
        from app.core.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        channel = f"chat_stream:{session_id}"

        try:
            await pubsub.subscribe(channel)
            log.info(f"队列 SSE 订阅已建立: session_id={session_id}")

            # 监听事件
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=300,  # 5分钟超时
                )
                if message and message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        event_type = event_data.get("event", "message")
                        event_payload = event_data.get("data", {})

                        # 转发 SSE 事件
                        yield {
                            "event": event_type,
                            "data": json.dumps(event_payload, ensure_ascii=False),
                        }

                        # queue_done 表示所有队列项处理完毕，关闭连接
                        if event_type == "queue_done":
                            yield {"event": "done", "data": "[DONE]"}
                            break

                    except json.JSONDecodeError as e:
                        log.warning(f"Redis 消息解析失败: {e}")
                        continue

        except asyncio.CancelledError:
            log.info(f"队列 SSE 连接被取消: session_id={session_id}")
        except Exception as e:
            log.error(f"队列 SSE 异常: session_id={session_id}, error={e}")
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()
            log.info(f"队列 SSE 订阅已关闭: session_id={session_id}")

    # 防缓冲头
    return EventSourceResponse(
        queue_event_generator(),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
