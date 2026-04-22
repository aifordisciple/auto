"""
消息队列 Celery Task

从 Redis 队列中顺序消费消息，调用 LLM 流式生成，
通过 Redis pub/sub 将 SSE 事件推送给前端。

处理流程：
1. 获取 session 的 Redis 锁（防止并发处理）
2. 从队列中取出下一个 pending 项
3. 更新状态为 processing
4. 调用 LLM 流式生成
5. 通过 Redis pub/sub 推送每个 SSE 事件
6. 更新状态为 completed
7. 递归调度下一个队列项
"""

import json
from datetime import datetime
from typing import Optional

from celery import shared_task
from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.core.config import settings
from app.models.chat_queue import ChatQueueItem, QueueItemStatus
from app.models.chat import ChatSession, ChatMessage
from app.models.enums import RoleEnum
from app.models.domain import User
from app.services import chat_queue_service
from app.core.content_filter import filter_thinking_content, StreamContentFilter
from app.core.vercel_stream import VercelDataStreamEncoder


# ==========================================
# 核心 Celery Task
# ==========================================

@shared_task(
    name="process_chat_queue_item",
    bind=True,
    max_retries=2,
    soft_time_limit=3600,   # 1小时软超时
    time_limit=7200,         # 2小时硬超时
)
def process_chat_queue_item(self, session_id: str):
    """
    处理会话的消息队列项

    从队列中取出下一个 pending 项，调用 LLM 流式生成，
    通过 Redis pub/sub 推送 SSE 事件给前端。
    """
    r = chat_queue_service.get_redis()
    lock_k = chat_queue_service.lock_key(session_id)

    # 获取 Redis 锁（TTL 2小时，防止死锁）
    lock_acquired = r.set(lock_k, "1", nx=True, ex=7200)
    if not lock_acquired:
        log.debug(f"队列处理跳过: session_id={session_id}，锁已被占用")
        return

    try:
        # 获取下一个 pending 项
        item = chat_queue_service.get_next_pending_item(session_id)
        if not item:
            log.debug(f"队列为空: session_id={session_id}")
            return

        item_id = item.id
        log.info(f"开始处理队列项: item_id={item_id}, session_id={session_id}")

        # 检查是否已被取消
        with Session(engine) as db:
            fresh_item = db.get(ChatQueueItem, item_id)
            if not fresh_item or fresh_item.status == QueueItemStatus.CANCELLED:
                log.info(f"队列项已取消，跳过: item_id={item_id}")
                # 继续处理下一个
                _schedule_next(session_id)
                return

        # 更新状态为 processing
        chat_queue_service.update_item_status(item_id, QueueItemStatus.PROCESSING)

        # 创建 Vercel 编码器
        encoder = VercelDataStreamEncoder()

        # 推送 queue_start 事件
        pending_items = chat_queue_service.get_queue_status(session_id)
        total_count = len(pending_items)
        processing_position = 1
        for i, pi in enumerate(pending_items):
            if pi.id == item_id:
                processing_position = i + 1
                break

        chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_start", {
            "queue_item_id": item_id,
            "user_message": item.message,
        }))
        chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_progress", {
            "queue_item_id": item_id,
            "position": processing_position,
            "total": total_count,
        }))

        # 执行 LLM 流式调用
        _process_item_with_llm(session_id, item)

        # 继续处理下一个队列项
        _schedule_next(session_id)

    except Exception as e:
        log.error(f"队列处理异常: session_id={session_id}, error={e}")
        # 标记当前项为 failed
        if item:
            chat_queue_service.update_item_status(
                item.id, QueueItemStatus.FAILED, error=str(e)
            )
            encoder = VercelDataStreamEncoder()
            chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_error", {
                "queue_item_id": item.id,
                "error": str(e),
            }))
        # 继续处理下一个
        _schedule_next(session_id)

    finally:
        # 释放 Redis 锁
        r.delete(lock_k)


# ==========================================
# LLM 流式处理
# ==========================================

def _process_item_with_llm(session_id: str, item: ChatQueueItem):
    """
    对单个队列项执行 LLM 流式调用

    通过 Redis pub/sub 将 Vercel Data Stream 协议行推送给前端
    """
    encoder = VercelDataStreamEncoder()
    with Session(engine) as db:
        # 持久化用户消息到 ChatMessage
        user_msg = ChatMessage(
            session_id=session_id,
            role=RoleEnum.user,
            content=item.message,
            attachments=item.attachments,
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)

        # 加载 LLM 配置
        from app.utils.llm_config import get_llm_config, _is_local_model
        llm_cfg = get_llm_config(db, user_id=item.user_id)
        api_key = llm_cfg.api_key
        base_url = llm_cfg.base_url
        model_name = llm_cfg.model_name
        is_local_model = _is_local_model(base_url)

        # 检查 API Key
        if not is_local_model and not api_key:
            chat_queue_service.publish_vercel_event(session_id, encoder.text_start())
            chat_queue_service.publish_vercel_event(session_id, encoder.text_chunk(
                "⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。"
            ))
            chat_queue_service.publish_vercel_event(session_id, encoder.text_end())
            chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_complete", {
                "queue_item_id": item.id,
            }))
            chat_queue_service.update_item_status(
                item.id, QueueItemStatus.FAILED, error="API Key 未配置"
            )
            return

        # 意图分类
        intent_type = "general_question"
        try:
            from app.services.skill_matcher import SkillMatcher
            from app.agent.router.schemas import IntentType
            matcher = SkillMatcher()
            # 同步调用 match（在 Celery worker 中运行）
            import asyncio
            loop = asyncio.get_event_loop()
            match_result = loop.run_until_complete(
                matcher.match(item.message, context={"project_id": item.project_id})
            )
            intent_type = match_result.get("intent_type", IntentType.GENERAL_CHAT)
        except Exception as e:
            log.warning(f"意图分类失败: {e}")

        # 选择系统提示词
        from app.api.routes.chat import SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_CODE
        try:
            from app.agent.router.schemas import IntentType
            if intent_type in (IntentType.SKILL_FORGE, IntentType.EXPLICIT_EXEC):
                system_prompt = SYSTEM_PROMPT_CODE
            else:
                system_prompt = SYSTEM_PROMPT_CHAT
        except Exception:
            system_prompt = SYSTEM_PROMPT_CHAT

        # 加载对话历史
        history_messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        ).all()

        lc_messages = [{"role": "system", "content": system_prompt}]
        for msg in history_messages:
            if msg.role == RoleEnum.user:
                lc_messages.append({"role": "user", "content": msg.content})
            elif msg.role == RoleEnum.assistant:
                lc_messages.append({"role": "assistant", "content": msg.content})

    # LLM 流式调用
    from langchain_openai import ChatOpenAI
    ai_full_response = ""
    content_filter = StreamContentFilter()
    cost_credits = 1.0
    ai_msg_id = None
    text_started = False  # 跟踪是否已发送 text-start

    try:
        direct_llm = ChatOpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            model=model_name,
            streaming=True,
        )

        # 使用同步迭代（Celery worker 中运行）
        for chunk in direct_llm.stream(lc_messages):
            content = chunk.content
            if content:
                # ✨ 过滤思考标签等内容，返回 (content, type) 元组
                # type: "text" = 正常回复, "thinking" = 思考过程
                filtered_content, content_type = content_filter.filter_chunk(content)
                if filtered_content:
                    if content_type == "thinking":
                        # ✨ 思考过程通过 data 事件推送给前端
                        chat_queue_service.publish_vercel_event(session_id, encoder.from_thinking(filtered_content))
                    else:
                        # 首个文本块前发送 text-start
                        if not text_started:
                            text_started = True
                            chat_queue_service.publish_vercel_event(session_id, encoder.text_start())
                        ai_full_response += filtered_content
                        # 通过 Redis pub/sub 推送 Vercel 文本块
                        chat_queue_service.publish_vercel_event(session_id, encoder.text_chunk(filtered_content))

    except Exception as e:
        import traceback
        log.error(f"LLM 调用失败: {e}\n{traceback.format_exc()}")
        err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
        ai_full_response += err_msg
        if not text_started:
            text_started = True
            chat_queue_service.publish_vercel_event(session_id, encoder.text_start())
        chat_queue_service.publish_vercel_event(session_id, encoder.text_chunk(err_msg))

    # 持久化助手消息 + 扣费
    with Session(engine) as final_db:
        cleaned_response = filter_thinking_content(ai_full_response, model_name=model_name)
        ai_msg = ChatMessage(
            session_id=session_id,
            role=RoleEnum.assistant,
            content=cleaned_response,
        )
        final_db.add(ai_msg)
        final_db.commit()
        final_db.refresh(ai_msg)
        ai_msg_id = ai_msg.id

        # 扣费
        final_balance = 0
        db_user = final_db.get(User, item.user_id)
        if db_user:
            try:
                from app.services.billing_service import BillingService
                bs = BillingService(final_db)
                wallet = bs.get_user_wallet(item.user_id)
                bs.deduct_credits(
                    wallet_id=wallet.wallet_id,
                    amount=cost_credits,
                    transaction_type="consume_chat",
                    description="聊天消息消费",
                )
                final_db.refresh(wallet)
                final_balance = wallet.credits_balance
            except Exception as e:
                log.warning(f"扣费失败: {e}")

    # 推送完成事件
    # 发送 text-end（如果之前有 text-start）
    if text_started:
        chat_queue_service.publish_vercel_event(session_id, encoder.text_end())
    chat_queue_service.publish_vercel_event(session_id, encoder.from_ai_message_id(str(ai_msg_id)))
    chat_queue_service.publish_vercel_event(session_id, encoder.from_ai_message_content(cleaned_response))
    chat_queue_service.publish_vercel_event(session_id, encoder.from_billing(cost_credits, final_balance))
    chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_complete", {
        "queue_item_id": item.id,
        "result_message_id": ai_msg_id,
    }))

    # 更新队列项状态
    chat_queue_service.update_item_status(
        item.id,
        QueueItemStatus.COMPLETED,
        result_message_id=ai_msg_id,
    )

    log.info(f"队列项处理完成: item_id={item.id}, ai_msg_id={ai_msg_id}")


# ==========================================
# 调度下一个队列项
# ==========================================

def _schedule_next(session_id: str):
    """调度处理下一个队列项"""
    next_item = chat_queue_service.get_next_pending_item(session_id)
    if next_item:
        # 延迟 0.5 秒后处理下一个（避免过快连续调用）
        process_chat_queue_item.apply_async(
            args=[session_id],
            countdown=0.5,
        )
        log.info(f"调度下一个队列项: session_id={session_id}, next_item_id={next_item.id}")
    else:
        # 队列为空，推送 queue_done 事件（Vercel finish 信号）
        encoder = VercelDataStreamEncoder()
        chat_queue_service.publish_vercel_event(session_id, encoder.from_queue_event("queue_done", {}))
        log.info(f"队列处理完毕: session_id={session_id}")