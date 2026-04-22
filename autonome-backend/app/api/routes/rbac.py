"""
RBAC 管理 API

阶段四：角色/权限/审计日志管理端点

所有端点仅 admin 角色可访问
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from app.api.deps import get_current_user
from app.api.deps_rbac import require_role, has_role, get_user_roles, get_user_permissions
from app.models.user import User
from app.models.rbac import Role, Permission, AuditLog, role_permissions, user_roles
from app.core.database import get_session

router = APIRouter(tags=["RBAC"])


# ──────────────────────────────────────────────
# Pydantic Schema
# ──────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None

class RolePermissionSet(BaseModel):
    permission_ids: list[int]

class UserRoleSet(BaseModel):
    role_ids: list[int]

class PermissionOut(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None

class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_default: bool
    created_at: datetime
    permissions: list[PermissionOut] = []

class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime


# ──────────────────────────────────────────────
# 审计日志工具
# ──────────────────────────────────────────────

async def audit_log(
    db: Session,
    user_id: Optional[int],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """记录审计日志"""
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error("审计日志写入失败: {}", e)
        db.rollback()


# ──────────────────────────────────────────────
# 角色管理
# ──────────────────────────────────────────────

@router.get("/roles", dependencies=[Depends(require_role("admin"))])
async def list_roles(db: Session = Depends(get_session)):
    """角色列表"""
    roles = db.query(Role).order_by(Role.id).all()
    return {
        "roles": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "is_default": r.is_default,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "permissions": [
                    {"id": p.id, "code": p.code, "name": p.name, "module": p.module}
                    for p in r.permissions
                ],
            }
            for r in roles
        ]
    }


@router.post("/roles", dependencies=[Depends(require_role("admin"))])
async def create_role(
    body: RoleCreate,
    request: Request,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """创建角色"""
    existing = db.query(Role).filter(Role.name == body.name).first()
    if existing:
        return {"success": False, "message": f"角色 '{body.name}' 已存在"}

    role = Role(
        name=body.name,
        description=body.description,
        is_default=body.is_default,
    )
    db.add(role)
    db.commit()
    db.refresh(role)

    await audit_log(
        db, user_id=current_user.id, action="role_create",
        resource_type="role", resource_id=str(role.id),
        detail=f"创建角色: {body.name}",
        ip_address=request.client.host if request.client else None,
    )

    return {"success": True, "role": {"id": role.id, "name": role.name}}


@router.put("/roles/{role_id}", dependencies=[Depends(require_role("admin"))])
async def update_role(
    role_id: int,
    body: RoleUpdate,
    request: Request,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """更新角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return {"success": False, "message": "角色不存在"}

    if body.name is not None:
        # 检查名称是否重复
        existing = db.query(Role).filter(Role.name == body.name, Role.id != role_id).first()
        if existing:
            return {"success": False, "message": f"角色名 '{body.name}' 已被使用"}
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.is_default is not None:
        role.is_default = body.is_default

    db.commit()

    await audit_log(
        db, user_id=current_user.id, action="role_update",
        resource_type="role", resource_id=str(role_id),
        detail=f"更新角色: {role.name}",
        ip_address=request.client.host if request.client else None,
    )

    return {"success": True, "message": "角色更新成功"}


@router.delete("/roles/{role_id}", dependencies=[Depends(require_role("admin"))])
async def delete_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """删除角色（admin 角色不可删除）"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return {"success": False, "message": "角色不存在"}

    if role.name == "admin":
        return {"success": False, "message": "admin 角色不可删除"}

    db.delete(role)
    db.commit()

    await audit_log(
        db, user_id=current_user.id, action="role_delete",
        resource_type="role", resource_id=str(role_id),
        detail=f"删除角色: {role.name}",
        ip_address=request.client.host if request.client else None,
    )

    return {"success": True, "message": "角色删除成功"}


# ──────────────────────────────────────────────
# 权限管理
# ──────────────────────────────────────────────

@router.get("/permissions", dependencies=[Depends(require_role("admin"))])
async def list_permissions(db: Session = Depends(get_session)):
    """权限列表"""
    perms = db.query(Permission).order_by(Permission.module, Permission.code).all()
    return {
        "permissions": [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "module": p.module,
                "description": p.description,
            }
            for p in perms
        ]
    }


@router.put("/roles/{role_id}/permissions", dependencies=[Depends(require_role("admin"))])
async def set_role_permissions(
    role_id: int,
    body: RolePermissionSet,
    request: Request,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """设置角色权限（全量替换）"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        return {"success": False, "message": "角色不存在"}

    # 验证权限 ID 都存在
    perms = db.query(Permission).filter(Permission.id.in_(body.permission_ids)).all()
    if len(perms) != len(body.permission_ids):
        return {"success": False, "message": "部分权限ID不存在"}

    role.permissions = list(perms)
    db.commit()

    perm_codes = [p.code for p in perms]
    await audit_log(
        db, user_id=current_user.id, action="role_permission_change",
        resource_type="role", resource_id=str(role_id),
        detail=f"角色 {role.name} 权限变更: {perm_codes}",
        ip_address=request.client.host if request.client else None,
    )

    return {"success": True, "message": "角色权限更新成功"}


# ──────────────────────────────────────────────
# 用户角色管理
# ──────────────────────────────────────────────

@router.get("/users/{user_id}/roles", dependencies=[Depends(require_role("admin"))])
async def get_user_roles_api(user_id: int, db: Session = Depends(get_session)):
    """查询用户角色"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"success": False, "message": "用户不存在"}

    roles = get_user_roles(user, db)
    permissions = get_user_permissions(user, db)

    return {
        "user_id": user_id,
        "primary_role": {
            "id": user.primary_role.id,
            "name": user.primary_role.name,
        } if user.primary_role else None,
        "roles": [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in roles
        ],
        "permissions": permissions,
    }


@router.put("/users/{user_id}/roles", dependencies=[Depends(require_role("admin"))])
async def set_user_roles_api(
    user_id: int,
    body: UserRoleSet,
    request: Request,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """设置用户角色（主角色取第一个，其余为附加角色）"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return {"success": False, "message": "用户不存在"}

    # 验证角色 ID 都存在
    roles = db.query(Role).filter(Role.id.in_(body.role_ids)).all()
    if len(roles) != len(body.role_ids):
        return {"success": False, "message": "部分角色ID不存在"}

    if not roles:
        return {"success": False, "message": "至少需要分配一个角色"}

    # 第一个角色设为主角色
    target_user.role_id = roles[0].id

    # 清除旧的附加角色关联，重新设置
    db.execute(user_roles.delete().where(user_roles.c.user_id == user_id))
    # 附加角色（跳过第一个，因为已设为主角色）
    for role in roles[1:]:
        db.execute(user_roles.insert().values(user_id=user_id, role_id=role.id))

    db.commit()

    role_names = [r.name for r in roles]
    await audit_log(
        db, user_id=current_user.id, action="user_role_change",
        resource_type="user", resource_id=str(user_id),
        detail=f"用户 {target_user.email} 角色变更: {role_names}",
        ip_address=request.client.host if request.client else None,
    )

    return {"success": True, "message": "用户角色更新成功"}


# ──────────────────────────────────────────────
# 审计日志
# ──────────────────────────────────────────────

@router.get("/audit-logs", dependencies=[Depends(require_role("admin"))])
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
):
    """审计日志查询（分页）"""
    query = db.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "detail": l.detail,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
