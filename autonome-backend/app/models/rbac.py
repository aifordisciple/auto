"""
RBAC 角色权限模型

阶段四：基于角色的访问控制（Role-Based Access Control）

数据模型：
- Role: 角色表，admin / researcher / viewer 等预设角色
- Permission: 权限表，细粒度权限码（如 project:read, skill:execute）
- AuditLog: 审计日志，记录敏感操作
- role_permissions: 角色-权限关联表（多对多）
- user_roles: 用户-角色关联表（多对多，主角色通过 User.role_id 外键）
"""

from datetime import datetime
from typing import List, Optional

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Integer, Text, Table, ForeignKey, Index


# ──────────────────────────────────────────────
# 关联表（多对多）
# ──────────────────────────────────────────────

# 角色-权限关联表
role_permissions = Table(
    "role_permissions",
    SQLModel.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# 用户-角色关联表（主角色通过 User.role_id，此表存储额外角色）
user_roles = Table(
    "user_roles",
    SQLModel.metadata,
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ──────────────────────────────────────────────
# 角色模型
# ──────────────────────────────────────────────

class Role(SQLModel, table=True):
    """角色表"""
    __tablename__ = "roles"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, unique=True, index=True)
    description: Optional[str] = Field(default=None, max_length=255)
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 反向关系：主角色用户（User.role_id 指向此表）
    users_primary: List["User"] = Relationship(
        back_populates="primary_role",
        sa_relationship_kwargs={"foreign_keys": "[User.role_id]", "lazy": "selectin"},
    )

    # 多对多关系：角色拥有的权限（通过 role_permissions 关联表）
    permissions: List["Permission"] = Relationship(
        back_populates="roles",
        sa_relationship_kwargs={
            "secondary": role_permissions,
            "lazy": "selectin",
        },
    )


# ──────────────────────────────────────────────
# 权限模型
# ──────────────────────────────────────────────

class Permission(SQLModel, table=True):
    """权限表"""
    __tablename__ = "permissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=100, unique=True, index=True)
    name: str = Field(max_length=100)
    module: str = Field(max_length=50, index=True)
    description: Optional[str] = Field(default=None, max_length=255)

    # 多对多关系：拥有此权限的角色
    roles: List["Role"] = Relationship(
        back_populates="permissions",
        sa_relationship_kwargs={
            "secondary": role_permissions,
            "lazy": "selectin",
        },
    )


# ──────────────────────────────────────────────
# 审计日志模型
# ──────────────────────────────────────────────

class AuditLog(SQLModel, table=True):
    """审计日志表 — 记录所有敏感操作"""
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    action: str = Field(max_length=100)
    resource_type: Optional[str] = Field(default=None, max_length=50)
    resource_id: Optional[str] = Field(default=None, max_length=100)
    detail: Optional[str] = Field(default=None, sa_column=Column(Text))
    ip_address: Optional[str] = Field(default=None, max_length=45)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 复合索引：按用户+操作查询
    __table_args__ = (
        Index("ix_audit_logs_user_action", "user_id", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
