"""
锻造会话模型 - 用于管理技能锻造的对话式工作流

ForgeSession: 锻造会话，管理整个锻造过程
ForgeMessage: 锻造对话消息，记录用户与AI的对话历史
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
import uuid


# ==========================================
# ID 生成函数
# ==========================================
def generate_forge_session_id():
    """生成锻造会话唯一 ID"""
    return f"forge_{uuid.uuid4().hex[:12]}"


def get_utc_now():
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 枚举定义
# ==========================================
class ForgeStatus(str, Enum):
    """锻造会话状态"""
    DRAFTING = "drafting"      # 锻造中
    TESTING = "testing"        # 测试中
    READY = "ready"            # 准备就绪
    SAVED = "saved"            # 已保存


# ==========================================
# 技能草稿结构（用于 JSONB 存储）
# ==========================================
class SkillDraftSchema(SQLModel):
    """技能草稿结构定义"""
    name: str = ""
    description: str = ""
    executor_type: str = "Python_env"
    script_code: str = ""
    nextflow_code: str = ""
    parameters_schema: Dict[str, Any] = {}
    expert_knowledge: str = ""
    dependencies: List[str] = []
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = []


# ==========================================
# ForgeSession - 锻造会话表
# ==========================================
class ForgeSessionBase(SQLModel):
    """锻造会话基础模型"""
    title: str = Field(default="新技能锻造", max_length=200)
    status: ForgeStatus = Field(default=ForgeStatus.DRAFTING)


class ForgeSession(ForgeSessionBase, table=True):
    """锻造会话数据库表"""
    __tablename__ = "forgesession"

    id: str = Field(default_factory=generate_forge_session_id, primary_key=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True, description="创建者 User ID")

    # 技能草稿 (JSONB)
    skill_draft: Dict[str, Any] = Field(
        default_factory=lambda: SkillDraftSchema().model_dump(),
        sa_column=Column(JSONB),
        description="当前技能草稿"
    )

    # 关联的最终技能
    skill_id: Optional[str] = Field(default=None, index=True, description="最终保存的技能 ID")

    # 执行器类型偏好
    executor_type: str = Field(default="Python_env", max_length=50)

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # 关系
    messages: List["ForgeMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ForgeSessionCreate(SQLModel):
    """创建锻造会话请求体"""
    title: Optional[str] = None
    executor_type: str = "Python_env"


class ForgeSessionUpdate(SQLModel):
    """更新锻造会话请求体"""
    title: Optional[str] = None
    status: Optional[ForgeStatus] = None
    skill_draft: Optional[Dict[str, Any]] = None


class ForgeSessionPublic(ForgeSessionBase):
    """返回给前端的锻造会话公共信息"""
    id: str
    user_id: int
    skill_draft: Dict[str, Any]
    skill_id: Optional[str]
    executor_type: str
    created_at: datetime
    updated_at: datetime
    messages: List["ForgeMessagePublic"] = []


# ==========================================
# ForgeMessage - 锻造对话消息表
# ==========================================
class ForgeMessageBase(SQLModel):
    """锻造消息基础模型"""
    role: str = Field(description="消息角色: user/assistant")
    content: str = Field(description="消息内容")


class ForgeMessage(ForgeMessageBase, table=True):
    """锻造对话消息数据库表"""
    __tablename__ = "forgemessage"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="forgesession.id", index=True)

    # 附件路径列表 (JSONB)
    attachments: List[str] = Field(default_factory=list, sa_column=Column(JSONB))

    created_at: datetime = Field(default_factory=get_utc_now)

    # 关系
    session: Optional[ForgeSession] = Relationship(back_populates="messages")


class ForgeMessageCreate(SQLModel):
    """创建锻造消息请求体"""
    content: str
    attachments: List[str] = []


class ForgeMessagePublic(ForgeMessageBase):
    """返回给前端的锻造消息公共信息"""
    id: int
    session_id: str
    attachments: List[str]
    created_at: datetime


# ==========================================
# 锻造聊天请求
# ==========================================
class ForgeChatRequest(SQLModel):
    """锻造对话请求体"""
    session_id: Optional[str] = Field(default=None, description="会话 ID，不传则创建新会话")
    message: str = Field(description="用户消息内容")
    attachments: List[str] = Field(default_factory=list, description="附件路径列表")
    executor_type: str = Field(default="Python_env", description="执行器类型")


# ==========================================
# 技能草稿更新请求
# ==========================================
class SkillDraftUpdate(SQLModel):
    """技能草稿更新请求体"""
    name: Optional[str] = None
    description: Optional[str] = None
    executor_type: Optional[str] = None
    script_code: Optional[str] = None
    nextflow_code: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    expert_knowledge: Optional[str] = None
    dependencies: Optional[List[str]] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None