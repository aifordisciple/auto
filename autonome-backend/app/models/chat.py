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


# ==========================================
# 即席分析历史记录模型 (AdhocAnalysisRecord)
# ==========================================
class AdhocAnalysisRecord(SQLModel, table=True):
    """
    即席分析历史记录表

    每次用户在即席分析卡片上确认执行后，自动保存策略、参数、执行结果等完整信息。
    用户可在数据中心查看历史分析列表，支持回溯、重执行、对比和删除。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    # 关联标识：message_id 用于关联 Redis 策略包和聊天消息
    message_id: str = Field(index=True, description="策略包/消息唯一标识")
    project_id: str = Field(foreign_key="project.id", index=True, description="所属项目ID")
    user_id: int = Field(foreign_key="user.id", index=True, description="执行用户ID")
    # 策略信息
    strategy: str = Field(description="分析策略描述文本")
    code_language: str = Field(default="python", description="代码语言: python / r")
    code_snapshot: str = Field(description="用户确认执行时的代码快照")
    parameters: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB), description="执行参数")
    # 输出信息
    output_dir: Optional[str] = Field(default=None, description="输出目录路径（相对项目目录）")
    output_files: Optional[List[str]] = Field(default=None, sa_column=Column(JSONB), description="输出文件列表")
    # 状态与结果
    status: str = Field(default="running", index=True, description="执行状态: running / success / failed")
    output_text: Optional[str] = Field(default=None, description="脚本标准输出")
    error_text: Optional[str] = Field(default=None, description="错误信息")
    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now, index=True)
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")

    # ==========================================
    # 复合索引定义（性能优化）
    # ==========================================
    __table_args__ = (
        # 按项目+创建时间降序（历史列表高频查询）
        Index('ix_adhoc_record_project_time', 'project_id', 'created_at'),
        # 按用户+时间（用户维度查询）
        Index('ix_adhoc_record_user_time', 'user_id', 'created_at'),
    )