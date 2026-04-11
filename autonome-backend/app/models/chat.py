"""
聊天模型模块

包含会话、消息、收藏、标签等模型
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.models.uuid import generate_session_id, generate_msg_id
from app.models.enums import RoleEnum


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 会话表 (Chat Session)
# ==========================================
class ChatSession(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_session_id, primary_key=True, index=True)
    title: str = Field(default="默认分析会话", max_length=200)
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)

    project: Optional["Project"] = Relationship(back_populates="sessions")
    messages: List["ChatMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 聊天记录表 (ChatMessage)
# ==========================================
class ChatMessage(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_msg_id, primary_key=True, index=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)  # ✨ 外键改为 str
    role: RoleEnum
    content: str
    created_at: datetime = Field(default_factory=get_utc_now)

    # ✨ 消息附件信息（JSON 格式存储）
    # 格式: {"files": [...], "images": [...], "pastedFiles": [...], "skill": {"skill_id": "...", "name": "..."}}
    # 用于记录用户发送消息时附带的文件、图片、技能等，在聊天界面显示标记
    attachments: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))

    session: Optional["ChatSession"] = Relationship(back_populates="messages")

    # ==========================================
    # 复合索引定义（性能优化）
    # ==========================================
    __table_args__ = (
        # 消息列表按会话+时间排序（高频查询）
        Index('ix_chat_message_session_time', 'session_id', 'created_at'),
        # JSONB attachments 字段 GIN 索引（附件搜索）
        Index('ix_chat_message_attachments_gin', 'attachments', postgresql_using='gin'),
    )


# ==========================================
# 消息收藏模型 (MessageBookmark)
# ==========================================
class MessageBookmark(SQLModel, table=True):
    """消息收藏表 - 用于收藏重要消息并添加笔记"""
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(foreign_key="chatmessage.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    note: Optional[str] = Field(default=None, description="收藏笔记")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 会话摘要缓存模型 (SessionSummaryCache)
# ==========================================
class SessionSummaryCache(SQLModel, table=True):
    """会话摘要缓存表 - 存储 AI 生成的会话摘要"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", unique=True, index=True)
    summary: str = Field(description="会话摘要内容")
    key_points: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="关键要点列表")
    generated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 会话标签模型 (ChatSessionTag)
# ==========================================
class ChatSessionTag(SQLModel, table=True):
    """会话标签表 - 用户自定义标签"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, index=True, description="标签名称")
    color: str = Field(default="#3B82F6", description="标签颜色")
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 会话标签关联模型 (SessionTagRelation)
# ==========================================
class SessionTagRelation(SQLModel, table=True):
    """会话标签关联表 - 多对多关系"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    tag_id: int = Field(foreign_key="chatsessiontag.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)