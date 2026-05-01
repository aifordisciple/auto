"""
Claude Agent 模式数据模型

包含：
- ClaudeSession: Claude 会话 (对应 Project)
- ClaudeConversation: Claude 对话 (Session 下的对话轮次)
- ClaudeMessage: Claude 消息 (含完整事件流 JSON)
- ClaudeTask: Claude 重型任务追踪
- ClaudeContainer: Claude 容器池管理
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID as SA_UUID
from uuid import UUID


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    from datetime import timezone
    return datetime.now(timezone.utc)


class ClaudeSession(SQLModel, table=True):
    """Claude 会话 — 用户的一个完整协作单元"""
    __tablename__ = "claude_session"

    id: Optional[UUID] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key='"user".id', index=True)
    title: str = Field(default="新会话", max_length=500)
    status: str = Field(default="active", max_length=20)
    container_id: Optional[str] = Field(default=None, max_length=100)
    meta_info: Optional[Dict[str, Any]] = Field(default={}, sa_column=Column(JSONB, name="metadata"))
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    conversations: List["ClaudeConversation"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ClaudeConversation(SQLModel, table=True):
    """Claude 对话 — Session 下的独立对话轮次"""
    __tablename__ = "claude_conversation"

    id: Optional[UUID] = Field(default=None, primary_key=True)
    session_id: Optional[UUID] = Field(default=None, foreign_key="claude_session.id", index=True)
    title: Optional[str] = Field(default=None, max_length=500)
    claude_session_id: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    session: Optional[ClaudeSession] = Relationship(back_populates="conversations")
    messages: List["ClaudeMessage"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ClaudeMessage(SQLModel, table=True):
    """Claude 消息 — 含完整事件流 JSON"""
    __tablename__ = "claude_message"

    id: Optional[UUID] = Field(default=None, primary_key=True)
    conversation_id: Optional[UUID] = Field(default=None, foreign_key="claude_conversation.id", index=True)
    role: str = Field(max_length=20)
    content: Optional[str] = None
    events_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSONB))
    plan_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    code_snapshot: Optional[str] = None
    task_ids: Optional[List[UUID]] = Field(default=[], sa_column=Column(ARRAY(SA_UUID)))
    usage_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=get_utc_now)

    conversation: Optional[ClaudeConversation] = Relationship(back_populates="messages")


class ClaudeTask(SQLModel, table=True):
    """Claude 重型任务追踪"""
    __tablename__ = "claude_task"

    id: Optional[UUID] = Field(default=None, primary_key=True)
    message_id: Optional[UUID] = Field(default=None, foreign_key="claude_message.id")
    session_id: Optional[UUID] = Field(default=None, foreign_key="claude_session.id", index=True)
    celery_task_id: Optional[str] = Field(default=None, max_length=200, index=True)
    skill_id: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="pending", max_length=20)
    code: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    output_files: Optional[List[Dict[str, Any]]] = Field(default=[], sa_column=Column(JSONB))
    error_text: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=get_utc_now)


class ClaudeContainer(SQLModel, table=True):
    """Claude 容器池管理"""
    __tablename__ = "claude_container"

    id: Optional[UUID] = Field(default=None, primary_key=True)
    container_id: str = Field(max_length=100)
    status: str = Field(default="idle", max_length=20, index=True)
    user_id: Optional[int] = Field(default=None, foreign_key='"user".id')
    session_id: Optional[UUID] = Field(default=None, foreign_key="claude_session.id")
    last_used_at: datetime = Field(default_factory=get_utc_now)
    created_at: datetime = Field(default_factory=get_utc_now)
