"""
项目模型模块

包含项目、数据文件、项目更新模型
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime

from app.models.uuid import generate_project_id


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 项目表 (Project/Workspace)
# ==========================================
class Project(SQLModel, table=True):
    # ✨ 修改为主键字符串，使用默认工厂函数自动生成
    id: str = Field(default_factory=generate_project_id, primary_key=True, index=True)
    name: str = Field(index=True, max_length=100)
    description: Optional[str] = None
    # ✨ 新增字段
    icon: str = Field(default="📁")
    status: str = Field(default="active", index=True)  # "active" 或 "archived"
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # ✨ 多租户：增加项目所有者
    owner_id: int = Field(foreign_key="user.id", index=True)

    # ✨ 分享与公开状态字段 (Growth Hacker 病毒传播)
    is_public: bool = Field(default=False)
    share_token: Optional[str] = Field(default=None, index=True)

    owner: Optional["User"] = Relationship(back_populates="projects")

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
# 文件表 (Data File Meta)
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
# 项目更新 Schema
# ==========================================
class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    status: Optional[str] = None


# ==========================================
# 公共数据集 (PublicDataset)
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