"""
用户组和技能分享模型

包含用户组、用户组成员、技能分享等模型
"""

from typing import Optional, List
from sqlmodel import SQLModel, Field
from datetime import datetime

from app.models.enums import PermissionLevel


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 用户组模型 (UserGroup)
# ==========================================
class UserGroup(SQLModel, table=True):
    """用户组表 - 用于团队协作"""
    __tablename__ = "usergroup"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, description="组名称")
    description: Optional[str] = Field(default=None, description="组描述")
    owner_id: int = Field(foreign_key="user.id", index=True, description="组创建者")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class UserGroupMember(SQLModel, table=True):
    """用户组成员关联表"""
    __tablename__ = "usergroupmember"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="usergroup.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    role: str = Field(default="member", description="角色: owner/admin/member")
    joined_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 技能分享模型 (SkillShare)
# ==========================================
class SkillShare(SQLModel, table=True):
    """技能分享表 - 分享给特定用户"""
    __tablename__ = "skillshare"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="技能 ID")
    shared_with_user_id: int = Field(foreign_key="user.id", index=True, description="被分享用户")
    permission_level: str = Field(default="READ", description="权限级别: READ/WRITE/ADMIN")
    shared_by: int = Field(foreign_key="user.id", description="分享者")
    created_at: datetime = Field(default_factory=get_utc_now)


class SkillShareGroup(SQLModel, table=True):
    """技能分享给用户组表"""
    __tablename__ = "skillsharegroup"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="技能 ID")
    group_id: int = Field(foreign_key="usergroup.id", index=True, description="用户组")
    permission_level: str = Field(default="READ", description="权限级别")
    shared_by: int = Field(foreign_key="user.id", description="分享者")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 请求/响应模型
# ==========================================
class SkillShareCreate(SQLModel):
    """创建技能分享请求"""
    skill_id: str
    user_ids: List[int] = Field(default_factory=list, description="分享给用户列表")
    group_ids: List[int] = Field(default_factory=list, description="分享给用户组列表")
    permission_level: str = Field(default="READ", description="权限级别")


class SkillShareUpdate(SQLModel):
    """更新权限请求"""
    permission_level: str


class SkillSharePublic(SQLModel):
    """技能分享公开信息"""
    id: int
    skill_id: str
    shared_with_user_id: Optional[int] = None
    group_id: Optional[int] = None
    permission_level: str
    shared_by: int
    created_at: datetime