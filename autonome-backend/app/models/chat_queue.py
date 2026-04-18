"""
消息队列模型模块

支持用户连续发送消息，消息进入队列顺序处理。
每个队列项关联一个会话，状态流转：pending → processing → completed/failed/cancelled
"""

from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.models.uuid import get_utc_now


def generate_queue_item_id() -> str:
    """生成队列项唯一 ID"""
    import uuid
    return f"qi_{uuid.uuid4().hex[:12]}"


# ==========================================
# 队列项状态枚举
# ==========================================
class QueueItemStatus:
    """队列项状态常量"""
    PENDING = "pending"          # 排队中，等待处理
    PROCESSING = "processing"    # 正在处理
    COMPLETED = "completed"      # 处理完成
    FAILED = "failed"            # 处理失败
    CANCELLED = "cancelled"      # 用户取消


# ==========================================
# 消息队列项表 (ChatQueueItem)
# ==========================================
class ChatQueueItem(SQLModel, table=True):
    """
    消息队列项 - 用户连续发送的消息按顺序排队处理

    状态流转：pending → processing → completed/failed/cancelled
    每个会话同时只有 1 个 processing 项，保证顺序执行
    """
    __tablename__ = "chat_queue_item"

    id: str = Field(default_factory=generate_queue_item_id, primary_key=True, index=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    # 队列项状态：pending | processing | completed | failed | cancelled
    status: str = Field(default=QueueItemStatus.PENDING, max_length=20)

    # 用户消息内容
    message: str

    # 附件信息（与 ChatMessage.attachments 格式一致）
    # 格式: {"files": [...], "images": [...], "pastedFiles": [...], "skill": {"skill_id": "...", "name": "..."}}
    attachments: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))

    # 队列中的位置（用于排序，值越小越先处理）
    position: int = Field(default=0)

    # 处理完成后关联的 ChatMessage.id
    result_message_id: Optional[str] = Field(default=None)

    # 失败原因
    error: Optional[str] = Field(default=None)

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    # ==========================================
    # 索引定义
    # ==========================================
    __table_args__ = (
        # 按会话+状态查询排队中的项（高频查询）
        Index('ix_queue_item_session_status', 'session_id', 'status'),
        # 按会话+位置排序（队列顺序查询）
        Index('ix_queue_item_session_position', 'session_id', 'position'),
    )
