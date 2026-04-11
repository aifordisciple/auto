"""
Claude 执行器模型

包含 Claude 执行器权限和会话模型
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.enums import ClaudeCodeSessionStatus


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# Claude 执行器权限模型 (ClaudeExecutorPermission)
# ==========================================
class ClaudeExecutorPermission(SQLModel, table=True):
    """
    Claude Code 执行器权限表 - 控制用户对 Claude Code 模式的访问

    核心设计理念：
    - 管理员授权机制：只有授权用户才能使用 Claude Code 模式
    - 细粒度权限控制：区分宿主机模式和容器模式
    - 可选过期时间：支持临时授权

    授权流程：
    1. 管理员在设置面板授权用户
    2. 用户在前端选择 Claude Code 模式时检查权限
    3. 根据授权的模式类型决定是否允许执行
    """
    __tablename__ = "claudeexecutorpermission"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True, description="被授权用户 ID")

    # 权限配置
    # allowed_modes 存储 JSON 数组，如 ["host", "container"]
    allowed_modes: List[str] = Field(
        default_factory=lambda: ["container"],
        sa_column=Column(JSONB),
        description="允许的执行模式: host(宿主机) / container(容器)"
    )

    # 授权信息
    granted_by: int = Field(foreign_key="user.id", description="授权管理员 ID")
    granted_at: datetime = Field(default_factory=get_utc_now, description="授权时间")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间（可选）")

    # 元数据
    notes: Optional[str] = Field(default=None, description="授权备注")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class ClaudeExecutorPermissionCreate(SQLModel):
    """创建 Claude 执行器权限请求"""
    user_id: int = Field(description="被授权用户 ID")
    allowed_modes: List[str] = Field(
        default_factory=lambda: ["container"],
        description="允许的执行模式"
    )
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    notes: Optional[str] = Field(default=None, description="授权备注")


class ClaudeExecutorPermissionUpdate(SQLModel):
    """更新 Claude 执行器权限请求"""
    allowed_modes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    notes: Optional[str] = None


class ClaudeExecutorPermissionPublic(SQLModel):
    """Claude 执行器权限公开信息"""
    id: int
    user_id: int
    allowed_modes: List[str]
    granted_by: int
    granted_at: datetime
    expires_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ==========================================
# Claude Code 会话持久化模型
# 用于保持多轮对话的上下文连续性
# ==========================================
class ClaudeCodeSession(SQLModel, table=True):
    """
    Claude Code 会话持久化表 - 支持多轮对话的上下文连续性

    核心设计理念：
    - 会话恢复：通过 claude --resume <session_id> 恢复上下文
    - 项目隔离：不同项目的会话独立管理
    - 自动过期：24小时后自动过期，避免上下文过长

    会话生命周期：
    1. 用户首次请求 → 启动新会话 → 保存 session_id
    2. 后续请求 → 使用 --resume 恢复会话
    3. 会话过期/用户清除 → 启动新会话
    """
    __tablename__ = "claudecodesession"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, description="用户 ID")
    project_id: str = Field(foreign_key="project.id", index=True, description="项目 ID")
    chat_session_id: str = Field(index=True, description="关联的 ChatSession ID")

    # Claude Code CLI 返回的 session_id（用于 --resume）
    claude_session_id: str = Field(unique=True, index=True, description="Claude Code CLI 会话 ID")

    # 会话状态
    status: str = Field(default=ClaudeCodeSessionStatus.ACTIVE.value, index=True, description="会话状态")
    last_message_at: datetime = Field(default_factory=get_utc_now, description="最后消息时间")

    # 元数据
    message_count: int = Field(default=0, description="会话消息计数")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class ClaudeCodeSessionCreate(SQLModel):
    """创建 Claude Code 会话请求"""
    user_id: int
    project_id: str
    chat_session_id: str
    claude_session_id: str


class ClaudeCodeSessionUpdate(SQLModel):
    """更新 Claude Code 会话请求"""
    status: Optional[str] = None
    last_message_at: Optional[datetime] = None
    message_count: Optional[int] = None


class ClaudeCodeSessionPublic(SQLModel):
    """Claude Code 会话公开信息"""
    id: int
    user_id: int
    project_id: str
    chat_session_id: str
    claude_session_id: str
    status: str
    last_message_at: datetime
    message_count: int
    created_at: datetime
    updated_at: datetime