"""
用户模型模块

包含用户和计费账户模型
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime

from app.models.uuid import generate_project_id
from app.models.enums import RoleEnum


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 用户表 (User - Multi-tenant)
# ==========================================
class User(SQLModel, table=True):
    """User - Multi-tenant SaaS 用户表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    hashed_password: str

    # ✨ 基础信息
    full_name: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=500, description="头像 URL（支持 Gravatar 或自定义上传）")
    organization: Optional[str] = Field(default=None, max_length=200, description="所属组织/机构")
    phone: Optional[str] = Field(default=None, max_length=20, description="手机号码")
    bio: Optional[str] = Field(default=None, max_length=500, description="个人简介")

    # ✨ 安全相关
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    last_password_change: Optional[datetime] = Field(default=None, description="上次密码修改时间")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

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
# 计费账户表 (BillingAccount)
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