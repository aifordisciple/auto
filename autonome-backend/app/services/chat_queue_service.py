"""
消息队列服务模块

管理用户消息队列的完整生命周期：
- 添加消息到队列（前端发送时调用）
- 队列 CRUD 操作（查看、编辑、删除、排序、清空）
- 队列调度（触发 Celery task 处理下一个队列项）
- Redis 队列操作（BLPOP 阻塞消费）
- Redis pub/sub 推送 SSE 事件（Celery worker → SSE 连接进程）
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlmodel import Session, select, col
from app.core.logger import log
from app.core.database import engine
from app.models.chat_queue import (
    ChatQueueItem,
    QueueItemStatus,
    generate_queue_item_id,
)
from app.core.config import settings

# Redis 客户端（延迟导入避免循环依赖）
_redis = None


def get_redis():
    """获取 Redis 客户端（延迟初始化）"""
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis


# ==========================================
# Redis Key 定义
# ==========================================
def queue_key(session_id: str) -> str:
    """会话级队列的 Redis List key"""
    return f"chat_queue:{session_id}"


def stream_key(session_id: str) -> str:
    """SSE 事件推送的 Redis pub/sub channel"""
    return f"chat_stream:{session_id}"


def lock_key(session_id: str) -> str:
    """会话级处理锁的 Redis key"""
    return f"chat_queue_lock:{session_id}"


# ==========================================
# 队列容量限制
# ==========================================
MAX_QUEUE_SIZE = 20  # 每个会话最多排队消息数


# ==========================================
# 添加消息到队列
# ==========================================
async def add_to_queue(
    session_id: str,
    project_id: str,
    user_id: int,
    message: str,
    attachments: Optional[Dict[str, Any]] = None,
) -> ChatQueueItem:
    """
    添加消息到队列

    流程：
    1. 检查队列容量
    2. 计算位置（当前最大 position + 1）
    3. 创建 ChatQueueItem 记录
    4. 推入 Redis List
    5. 触发队列调度（如果没有正在处理的项）
    """
    with Session(engine) as db:
        # 检查队列容量
        pending_count = db.exec(
            select(ChatQueueItem)
            .where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.status == QueueItemStatus.PENDING,
            )
        ).all()
        if len(pending_count) >= MAX_QUEUE_SIZE:
            raise ValueError(f"队列已满（最多 {MAX_QUEUE_SIZE} 条），请等待当前消息处理完成")

        # 计算位置
        existing = db.exec(
            select(ChatQueueItem)
            .where(ChatQueueItem.session_id == session_id)
            .order_by(col(ChatQueueItem.position).desc())
            .limit(1)
        ).first()
        next_position = (existing.position + 1) if existing else 0

        # 创建队列项
        item = ChatQueueItem(
            id=generate_queue_item_id(),
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            message=message,
            attachments=attachments,
            position=next_position,
            status=QueueItemStatus.PENDING,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

    # 推入 Redis List
    r = get_redis()
    r.rpush(queue_key(session_id), item.id)

    log.info(f"消息入队: item_id={item.id}, session_id={session_id}, position={next_position}")

    # 触发队列调度
    await schedule_queue_processing(session_id)

    return item


# ==========================================
# 队列调度
# ==========================================
async def schedule_queue_processing(session_id: str):
    """
    调度队列处理

    如果当前没有正在处理的项，触发 Celery task 处理下一个 pending 项。
    使用 Redis 锁防止并发处理。
    """
    r = get_redis()
    lock = lock_key(session_id)

    # 检查是否有正在处理的项（Redis 锁）
    if r.get(lock):
        log.debug(f"队列调度跳过: session_id={session_id}，已有处理中的项")
        return

    # 检查数据库中是否有 processing 项
    with Session(engine) as db:
        processing = db.exec(
            select(ChatQueueItem).where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.status == QueueItemStatus.PROCESSING,
            )
        ).first()
        if processing:
            log.debug(f"队列调度跳过: session_id={session_id}，数据库中有 processing 项")
            return

    # 触发 Celery task
    try:
        from app.tasks.chat_queue_task import process_chat_queue_item
        process_chat_queue_item.delay(session_id)
        log.info(f"队列调度触发: session_id={session_id}")
    except Exception as e:
        log.error(f"队列调度失败: session_id={session_id}, error={e}")


# ==========================================
# 获取队列状态
# ==========================================
def get_queue_status(session_id: str) -> List[ChatQueueItem]:
    """获取会话的队列状态（按 position 排序）"""
    with Session(engine) as db:
        items = db.exec(
            select(ChatQueueItem)
            .where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.status.in_([
                    QueueItemStatus.PENDING,
                    QueueItemStatus.PROCESSING,
                ]),
            )
            .order_by(col(ChatQueueItem.position))
        ).all()
        return items


# ==========================================
# 编辑队列项
# ==========================================
def update_queue_item(item_id: str, user_id: int, message: Optional[str] = None, attachments: Optional[Dict] = None) -> Optional[ChatQueueItem]:
    """编辑排队中的消息（仅 pending 状态可编辑）"""
    with Session(engine) as db:
        item = db.get(ChatQueueItem, item_id)
        if not item:
            raise ValueError(f"队列项不存在: {item_id}")
        if item.user_id != user_id:
            raise PermissionError("无权编辑此队列项")
        if item.status != QueueItemStatus.PENDING:
            raise ValueError(f"仅排队中的消息可编辑，当前状态: {item.status}")

        if message is not None:
            item.message = message
        if attachments is not None:
            item.attachments = attachments

        db.add(item)
        db.commit()
        db.refresh(item)
        return item


# ==========================================
# 删除队列项
# ==========================================
def delete_queue_item(item_id: str, user_id: int) -> bool:
    """
    删除队列项

    - pending: 直接删除
    - processing: 取消处理（标记 cancelled）
    - completed/failed/cancelled: 不允许删除（已处理完毕）
    """
    with Session(engine) as db:
        item = db.get(ChatQueueItem, item_id)
        if not item:
            raise ValueError(f"队列项不存在: {item_id}")
        if item.user_id != user_id:
            raise PermissionError("无权删除此队列项")

        if item.status == QueueItemStatus.PENDING:
            # 从 Redis List 移除
            r = get_redis()
            r.lrem(queue_key(item.session_id), 0, item_id)
            # 标记为 cancelled
            item.status = QueueItemStatus.CANCELLED
            item.completed_at = datetime.utcnow()
            db.add(item)
            db.commit()
            log.info(f"队列项已删除: item_id={item_id}")
            return True

        elif item.status == QueueItemStatus.PROCESSING:
            # 标记为 cancelled（Celery task 会检查并中断）
            item.status = QueueItemStatus.CANCELLED
            item.completed_at = datetime.utcnow()
            db.add(item)
            db.commit()
            # 通知 SSE 连接中断当前处理
            from app.core.vercel_stream import VercelDataStreamEncoder
            encoder = VercelDataStreamEncoder()
            publish_vercel_event(item.session_id, encoder.from_queue_event("queue_error", {
                "queue_item_id": item_id,
                "error": "用户取消了此消息的处理",
            }))
            log.info(f"队列项已取消: item_id={item_id}")
            return True

        else:
            raise ValueError(f"无法删除已处理完毕的队列项，当前状态: {item.status}")


# ==========================================
# 调整队列顺序
# ==========================================
def reorder_queue(session_id: str, user_id: int, item_ids: List[str]) -> List[ChatQueueItem]:
    """
    调整队列中消息的顺序

    item_ids: 按新顺序排列的队列项 ID 列表
    仅 pending 状态的项可调整顺序
    """
    with Session(engine) as db:
        items = db.exec(
            select(ChatQueueItem).where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.user_id == user_id,
                ChatQueueItem.status == QueueItemStatus.PENDING,
            )
        ).all()

        item_map = {item.id: item for item in items}

        # 验证所有 item_ids 都是有效的 pending 项
        for iid in item_ids:
            if iid not in item_map:
                raise ValueError(f"无效的队列项 ID 或非 pending 状态: {iid}")

        # 更新位置
        for idx, iid in enumerate(item_ids):
            item_map[iid].position = idx
            db.add(item_map[iid])

        db.commit()

        # 重建 Redis List 顺序
        r = get_redis()
        qk = queue_key(session_id)
        r.delete(qk)
        for iid in item_ids:
            r.rpush(qk, iid)

        log.info(f"队列顺序已调整: session_id={session_id}, 新顺序={item_ids}")

        # 返回更新后的队列
        return get_queue_status(session_id)


# ==========================================
# 清空队列
# ==========================================
def clear_queue(session_id: str, user_id: int) -> int:
    """
    清空会话的所有 pending 队列项

    返回清除的数量
    """
    with Session(engine) as db:
        pending_items = db.exec(
            select(ChatQueueItem).where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.user_id == user_id,
                ChatQueueItem.status == QueueItemStatus.PENDING,
            )
        ).all()

        count = 0
        for item in pending_items:
            item.status = QueueItemStatus.CANCELLED
            item.completed_at = datetime.utcnow()
            db.add(item)
            count += 1

        db.commit()

    # 清空 Redis List
    r = get_redis()
    r.delete(queue_key(session_id))

    log.info(f"队列已清空: session_id={session_id}, 清除 {count} 项")
    return count


# ==========================================
# 获取下一个待处理项
# ==========================================
def get_next_pending_item(session_id: str) -> Optional[ChatQueueItem]:
    """获取会话中下一个 pending 的队列项"""
    with Session(engine) as db:
        item = db.exec(
            select(ChatQueueItem).where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.status == QueueItemStatus.PENDING,
            )
            .order_by(col(ChatQueueItem.position))
            .limit(1)
        ).first()
        return item


# ==========================================
# 更新队列项状态
# ==========================================
def update_item_status(
    item_id: str,
    status: str,
    error: Optional[str] = None,
    result_message_id: Optional[str] = None,
) -> Optional[ChatQueueItem]:
    """更新队列项状态"""
    with Session(engine) as db:
        item = db.get(ChatQueueItem, item_id)
        if not item:
            return None

        item.status = status

        if status == QueueItemStatus.PROCESSING:
            item.started_at = datetime.utcnow()
        elif status in (QueueItemStatus.COMPLETED, QueueItemStatus.FAILED, QueueItemStatus.CANCELLED):
            item.completed_at = datetime.utcnow()

        if error is not None:
            item.error = error
        if result_message_id is not None:
            item.result_message_id = result_message_id

        db.add(item)
        db.commit()
        db.refresh(item)
        return item


# ==========================================
# Redis pub/sub SSE 事件推送
# ==========================================
def publish_sse_event(session_id: str, event_type: str, data: Dict[str, Any]):
    """
    通过 Redis pub/sub 推送 SSE 事件

    Celery worker 调用此方法将事件发布到 Redis channel，
    SSE 连接进程订阅该 channel 并转发给前端。
    """
    r = get_redis()
    event = {
        "event": event_type,
        "data": data,
    }
    r.publish(stream_key(session_id), json.dumps(event, ensure_ascii=False))
    log.debug(f"SSE 事件已推送: session_id={session_id}, event={event_type}")


def publish_vercel_event(session_id: str, vercel_line: str):
    """
    通过 Redis pub/sub 推送 Vercel Data Stream 协议行

    与 publish_sse_event 不同，此方法直接推送 Vercel 协议格式字符串
    （如 0:"chunk"\\n 或 data:[{"type":"thinking",...}]\\n），
    而非 SSE 事件字典。queue_event_generator 直接透传这些行。
    """
    r = get_redis()
    r.publish(stream_key(session_id), vercel_line)
    log.debug(f"Vercel 事件已推送: session_id={session_id}, line_prefix={vercel_line[:50]}")


# ==========================================
# 恢复中断的队列
# ==========================================
async def recover_queue(session_id: str):
    """
    恢复中断的队列（SSE 重连后调用）

    检查是否有 processing 状态的项（可能因断线而中断），
    如果有则重新触发处理。
    """
    with Session(engine) as db:
        processing = db.exec(
            select(ChatQueueItem).where(
                ChatQueueItem.session_id == session_id,
                ChatQueueItem.status == QueueItemStatus.PROCESSING,
            )
        ).first()

        if processing:
            # 将 processing 项重置为 pending（允许重试）
            processing.status = QueueItemStatus.PENDING
            processing.started_at = None
            db.add(processing)
            db.commit()
            log.info(f"队列恢复: 重置 processing 项 {processing.id} 为 pending")

    # 触发调度
    await schedule_queue_processing(session_id)