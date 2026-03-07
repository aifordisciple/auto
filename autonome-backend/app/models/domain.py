from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column
import uuid

# ✨ 引入 pgvector 的 Vector 类型
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # 如果 pgvector 未安装，提供一个 dummy Vector 类型
    class Vector:
        def __init__(self, dimension=None):
            self.dimension = dimension


# ==========================================
# ✨ UUID 生成函数 (商业级 ID)
# ==========================================
def generate_project_id():
    return f"proj_{uuid.uuid4().hex[:12]}"

def generate_session_id():
    return f"chat_{uuid.uuid4().hex[:12]}"

def generate_msg_id():
    return f"msg_{uuid.uuid4().hex[:16]}"


# ==========================================
# 0. 定义枚举 (规范字段)
# ==========================================
class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


def get_utc_now():
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    return datetime.now(timezone.utc)


# ==========================================
# -1. 用户表 (User - Multi-tenant)
# ==========================================
class User(SQLModel, table=True):
    """User - Multi-tenant SaaS 用户表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=get_utc_now)
    
    # 关系：一个用户可以有多个项目
    projects: List["Project"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    # 关系：一个用户只有一个计费账户
    billing: Optional["BillingAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# -2. 计费账户表 (BillingAccount)
# ==========================================
class BillingAccount(SQLModel, table=True):
    """BillingAccount - 用户计费与算力余额"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    credits_balance: float = Field(default=100.0)  # 初始送 100 点算力
    total_consumed: float = Field(default=0.0)    # 历史累计消耗
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
    
    user: Optional[User] = Relationship(back_populates="billing")


# ==========================================
# 1. 项目表 (Project/Workspace)
# ==========================================
class Project(SQLModel, table=True):
    # ✨ 修改为主键字符串，使用默认工厂函数自动生成
    id: str = Field(default_factory=generate_project_id, primary_key=True, index=True)
    name: str = Field(index=True, max_length=100)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

    # ✨ 多租户：增加项目所有者
    owner_id: int = Field(foreign_key="user.id", index=True)
    
    # ✨ 分享与公开状态字段 (Growth Hacker 病毒传播)
    is_public: bool = Field(default=False)
    share_token: Optional[str] = Field(default=None, index=True)
    
    owner: Optional[User] = Relationship(back_populates="projects")
    
    # ✨ 增加级联删除
    sessions: List["ChatSession"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    files: List["DataFile"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 2. 会话表 (Chat Session)
# ==========================================
class ChatSession(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_session_id, primary_key=True, index=True)
    title: str = Field(default="默认分析会话", max_length=200)
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)
    
    project: Optional[Project] = Relationship(back_populates="sessions")
    messages: List["ChatMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 3. 聊天记录表 (ChatMessage)
# ==========================================
class ChatMessage(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_msg_id, primary_key=True, index=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)  # ✨ 外键改为 str
    role: RoleEnum
    content: str
    created_at: datetime = Field(default_factory=get_utc_now)
    
    session: Optional["ChatSession"] = Relationship(back_populates="messages")


# ==========================================
# 4. 文件表 (Data File Meta)
# ==========================================
class DataFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  # 文件ID保持int
    filename: str
    file_path: str
    file_size: int
    file_type: Optional[str] = None
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    uploaded_at: datetime = Field(default_factory=get_utc_now)
    
    project: Optional[Project] = Relationship(back_populates="files")


# ==========================================
# 5. 任务记录表 (Task Record)
# ==========================================
class TaskRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    tool_id: str
    parameters: str
    status: str = Field(index=True)
    result: Optional[str] = None
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)
    completed_at: Optional[datetime] = None


# ==========================================
# 6. 系统全局配置表 (System Settings)
# ==========================================
class SystemConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    openai_api_key: Optional[str] = None
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    default_model: str = Field(default="gpt-3.5-turbo")
    theme: str = Field(default="dark")
    updated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 7. 公共数据集 (PublicDataset)
# ==========================================
class PublicDataset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    accession: str = Field(index=True)
    title: str
    summary: str
    organism: Optional[str] = None
    source_url: str
    owner_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
