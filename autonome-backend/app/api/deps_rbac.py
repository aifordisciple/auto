"""
RBAC 鉴权依赖

阶段四：基于角色的访问控制 — FastAPI 依赖项

用法：
    @router.post("/projects", dependencies=[Depends(require_permission("project:create"))])
    @router.get("/admin/users", dependencies=[Depends(require_role("admin"))])

核心逻辑：
1. 从 get_current_user 获取当前用户
2. 查用户主角色 + 附加角色
3. 合并所有角色的权限
4. 检查是否包含目标权限/角色
5. admin 角色自动拥有所有权限（硬编码超级管理员）
"""

from functools import lru_cache
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.rbac import Role, Permission, user_roles


# ──────────────────────────────────────────────
# 权限查询
# ──────────────────────────────────────────────

def get_user_roles(user: User, db: Session) -> List[Role]:
    """获取用户所有角色（主角色 + 附加角色）"""
    roles = []

    # 主角色
    if user.primary_role:
        roles.append(user.primary_role)

    # 附加角色（通过 user_roles 关联表）
    additional = db.query(Role).join(user_roles).filter(
        user_roles.c.user_id == user.id,
    ).all()
    roles.extend(additional)

    return roles


def get_user_permissions(user: User, db: Session) -> List[str]:
    """
    获取用户所有权限码

    admin 角色自动拥有所有权限，直接返回 ["*"]
    """
    roles = get_user_roles(user, db)

    # admin 角色拥有所有权限
    if any(r.name == "admin" for r in roles):
        return ["*"]

    # 合并所有角色的权限码
    permission_codes = set()
    for role in roles:
        for perm in role.permissions:
            permission_codes.add(perm.code)

    return list(permission_codes)


def has_permission(user: User, db: Session, permission_code: str) -> bool:
    """检查用户是否拥有指定权限"""
    permissions = get_user_permissions(user, db)
    # admin 通配符
    if "*" in permissions:
        return True
    return permission_code in permissions


def has_role(user: User, db: Session, role_name: str) -> bool:
    """检查用户是否拥有指定角色"""
    roles = get_user_roles(user, db)
    return any(r.name == role_name for r in roles)


# ──────────────────────────────────────────────
# FastAPI 依赖项工厂
# ──────────────────────────────────────────────

def require_permission(code: str):
    """
    权限校验依赖项

    用法：
        @router.post("/projects", dependencies=[Depends(require_permission("project:create"))])
    """
    async def _check_permission(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.is_superuser:
            return  # is_superuser 兼容旧逻辑
        if not has_permission(current_user, db, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {code} 权限",
            )
    return _check_permission


def require_role(name: str):
    """
    角色校验依赖项

    用法：
        @router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
    """
    async def _check_role(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.is_superuser:
            return  # is_superuser 兼容旧逻辑
        if not has_role(current_user, db, name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {name} 角色",
            )
    return _check_role
