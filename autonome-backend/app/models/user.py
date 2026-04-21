"""
用户模型模块

包含用户、OAuth 账号关联、活跃会话和计费账户模型
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
    """用户模型 - 支持邮箱和手机号双通道认证"""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    # nullable=True 支持未来纯验证码用户（无密码登录场景）
    hashed_password: Optional[str] = Field(default=None)

    # ✨ 基础信息
    full_name: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=500, description="头像 URL（支持 Gravatar 或自定义上传）")
    organization: Optional[str] = Field(default=None, max_length=200, description="所属组织/机构")
    # 手机号：支持手机号+验证码登录，nullable 允许老用户暂未绑定手机
    phone_number: Optional[str] = Field(
        default=None, max_length=20, unique=True, index=True, description="手机号码（唯一标识）"
    )
    bio: Optional[str] = Field(default=None, max_length=500, description="个人简介")

    # ==========================================
    # 🤖 用户级 AI 模型配置（覆盖系统全局配置）
    # ==========================================
    llm_api_key: Optional[str] = Field(default=None, max_length=500, description="用户自定义 LLM API Key")
    llm_base_url: Optional[str] = Field(default=None, max_length=500, description="用户自定义 LLM Base URL")
    llm_model_name: Optional[str] = Field(default=None, max_length=100, description="用户自定义模型名称")

    # ✨ 安全相关
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    last_password_change: Optional[datetime] = Field(default=None, description="上次密码修改时间")
    # 邮箱验证状态：用于未来邮箱验证流程
    is_email_verified: bool = Field(default=False, description="邮箱是否已验证")
    # 双因素认证：预留 TOTP 支持
    is_2fa_enabled: bool = Field(default=False, description="是否开启了 2FA")
    two_factor_secret: Optional[str] = Field(default=None, max_length=255, description="TOTP 密钥")

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
    # 关系：一个用户可以绑定多个第三方账号 (GitHub/微信等)
    oauth_accounts: List["OAuthAccount"] = Relationship(back_populates="user")
    # 关系：一个用户可以有多个活跃会话 (用于 Refresh Token 管控)
    sessions: List["ActiveSession"] = Relationship(back_populates="user")


# ==========================================
# 第三方 OAuth 账号关联表
# ==========================================
class OAuthAccount(SQLModel, table=True):
    """第三方 OAuth 账号关联 - 支持 GitHub/微信等第三方登录"""

    __tablename__ = "oauth_accounts"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # OAuth 提供商标识：github / wechat 等
    provider: str = Field(max_length=20)
    # 提供商侧的用户唯一 ID
    provider_account_id: str = Field(max_length=255, index=True)
    access_token: Optional[str] = Field(default=None, max_length=1024)
    refresh_token: Optional[str] = Field(default=None, max_length=1024)
    created_at: datetime = Field(default_factory=get_utc_now)

    user: Optional[User] = Relationship(back_populates="oauth_accounts")


# ==========================================
# 活跃会话管理表
# ==========================================
class ActiveSession(SQLModel, table=True):
    """活跃会话管理 - 支持多端登录管控和会话撤销"""

    __tablename__ = "active_sessions"
    session_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # refresh token 的 SHA-256 摘要，不存储明文（防脱库泄露）
    refresh_token_hash: str = Field(max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_type: Optional[str] = Field(default=None, max_length=50)
    created_at: datetime = Field(default_factory=get_utc_now)
    # 会话过期时间，必须设置，用于定期清理过期会话
    expires_at: datetime
    last_active_at: datetime = Field(default_factory=get_utc_now)
    # 标记会话是否已主动撤销（如用户登出或踢下线）
    is_revoked: bool = False

    user: Optional[User] = Relationship(back_populates="sessions")


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
