"""
RBAC 权限模型

阶段四：基于角色的访问控制（Role-Based Access Control）

数据模型：
- Role: 角色（admin, researcher, viewer）
- Permission: 权限（project:create, skill:execute 等）
- role_permissions: 角色-权限多对多关联
- user_roles: 用户-角色多对多关联
- AuditLog: 审计日志

设计原则：
- 角色-权限二级模型，简单高效
- admin 角色硬编码为超级管理员，拥有所有权限
- researcher 为新用户默认角色
- User 模型通过 role_id 字段关联主角色，user_roles 支持附加角色
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    Table, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


# ──────────────────────────────────────────────
# 角色-权限关联表（多对多）
# ──────────────────────────────────────────────

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# ──────────────────────────────────────────────
# 用户-角色关联表（多对多，附加角色）
# ──────────────────────────────────────────────

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ──────────────────────────────────────────────
# Role 角色
# ──────────────────────────────────────────────

class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True, comment="角色名")
    description = Column(String(200), nullable=True, comment="角色描述")
    is_default = Column(Boolean, default=False, nullable=False, comment="是否新用户默认角色")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关联
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles", lazy="selectin")
    users_primary = relationship("User", back_populates="primary_role", foreign_keys="User.role_id")

    def __repr__(self):
        return f"<Role(id={self.id}, name='{self.name}')>"


# ──────────────────────────────────────────────
# Permission 权限
# ──────────────────────────────────────────────

class Permission(Base):
    """权限表"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True, comment="权限码，如 project:create")
    name = Column(String(100), nullable=False, comment="显示名称")
    module = Column(String(50), nullable=False, index=True, comment="所属模块")
    description = Column(String(200), nullable=True, comment="权限描述")

    # 关联
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions", lazy="selectin")

    def __repr__(self):
        return f"<Permission(id={self.id}, code='{self.code}')>"


# ──────────────────────────────────────────────
# AuditLog 审计日志
# ──────────────────────────────────────────────

class AuditLog(Base):
    """审计日志表 — 记录关键操作"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="操作用户")
    action = Column(String(100), nullable=False, index=True, comment="操作类型")
    resource_type = Column(String(50), nullable=True, comment="资源类型")
    resource_id = Column(String(50), nullable=True, comment="资源ID")
    detail = Column(Text, nullable=True, comment="操作详情（JSON）")
    ip_address = Column(String(50), nullable=True, comment="IP 地址")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # 关联
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_audit_logs_user_action", "user_id", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}')>"
