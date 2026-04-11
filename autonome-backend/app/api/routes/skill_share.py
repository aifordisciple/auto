"""
技能分享 API 路由 - 提供技能分享、权限管理功能

核心端点:
- POST /share: 分享技能给用户/用户组
- DELETE /share/{share_id}: 取消分享
- PUT /share/{share_id}: 更新权限
- GET /skill/{skill_id}/shares: 获取技能的分享列表
- GET /shared-with-me: 获取分享给我的技能
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, and_, or_
from pydantic import BaseModel, Field

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillStatus,
    UserGroup, UserGroupMember,
    SkillShare, SkillShareGroup, SkillShareCreate, SkillShareUpdate, SkillSharePublic,
    PermissionLevel, get_utc_now
)

router = APIRouter()


# ==========================================
# 辅助函数
# ==========================================
def check_skill_permission(
    session: Session,
    skill_id: str,
    user_id: int,
    required_level: str = "READ"
) -> tuple[SkillAsset, str]:
    """
    检查用户对技能的权限

    Returns:
        (skill, actual_permission_level)
    """
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 所有者拥有全部权限
    if skill.owner_id == user_id:
        return skill, "ADMIN"

    # 检查用户分享
    user_share = session.exec(
        select(SkillShare).where(
            and_(
                SkillShare.skill_id == skill_id,
                SkillShare.shared_with_user_id == user_id
            )
        )
    ).first()

    if user_share:
        return skill, user_share.permission_level

    # 检查用户组分享
    user_groups = session.exec(
        select(UserGroupMember.group_id).where(UserGroupMember.user_id == user_id)
    ).all()

    if user_groups:
        group_share = session.exec(
            select(SkillShareGroup).where(
                and_(
                    SkillShareGroup.skill_id == skill_id,
                    SkillShareGroup.group_id.in_(user_groups)
                )
            )
        ).first()

        if group_share:
            return skill, group_share.permission_level

    # 公开技能可读
    if skill.status == SkillStatus.PUBLISHED:
        return skill, "READ"

    raise HTTPException(status_code=403, detail="无权访问此技能")


def permission_level_value(level: str) -> int:
    """权限级别数值"""
    levels = {"READ": 1, "WRITE": 2, "ADMIN": 3}
    return levels.get(level, 0)


# ==========================================
# POST /share - 分享技能
# ==========================================
class ShareRequest(BaseModel):
    """分享请求"""
    skill_id: str
    user_ids: List[int] = Field(default_factory=list)
    group_ids: List[int] = Field(default_factory=list)
    permission_level: str = Field(default="READ")


class ShareResponse(BaseModel):
    """分享响应"""
    skill_id: str
    shared_users: int
    shared_groups: int
    message: str


@router.post("/share", response_model=ShareResponse)
async def share_skill(
    request: ShareRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    分享技能给用户或用户组

    需要 ADMIN 权限才能分享
    """
    # 检查权限
    skill, perm = check_skill_permission(session, request.skill_id, current_user.id)

    if permission_level_value(perm) < permission_level_value("ADMIN"):
        raise HTTPException(status_code=403, detail="需要 ADMIN 权限才能分享")

    if permission_level_value(request.permission_level) > permission_level_value(perm):
        raise HTTPException(status_code=400, detail="不能授予比自己更高的权限")

    shared_users = 0
    shared_groups = 0

    # 分享给用户
    for user_id in request.user_ids:
        if user_id == current_user.id:
            continue  # 不能分享给自己

        # 检查用户是否存在
        target_user = session.get(User, user_id)
        if not target_user:
            continue

        # 检查是否已分享
        existing = session.exec(
            select(SkillShare).where(
                and_(
                    SkillShare.skill_id == request.skill_id,
                    SkillShare.shared_with_user_id == user_id
                )
            )
        ).first()

        if existing:
            # 更新权限
            existing.permission_level = request.permission_level
            session.add(existing)
        else:
            # 新建分享
            share = SkillShare(
                skill_id=request.skill_id,
                shared_with_user_id=user_id,
                permission_level=request.permission_level,
                shared_by=current_user.id
            )
            session.add(share)
            shared_users += 1

    # 分享给用户组
    for group_id in request.group_ids:
        # 检查用户组是否存在且用户是管理员
        group = session.get(UserGroup, group_id)
        if not group:
            continue

        # 检查是否已分享
        existing = session.exec(
            select(SkillShareGroup).where(
                and_(
                    SkillShareGroup.skill_id == request.skill_id,
                    SkillShareGroup.group_id == group_id
                )
            )
        ).first()

        if existing:
            existing.permission_level = request.permission_level
            session.add(existing)
        else:
            share = SkillShareGroup(
                skill_id=request.skill_id,
                group_id=group_id,
                permission_level=request.permission_level,
                shared_by=current_user.id
            )
            session.add(share)
            shared_groups += 1

    session.commit()

    log.info(f"📤 [SkillShare] 分享技能 {request.skill_id}: {shared_users} 用户, {shared_groups} 用户组")

    return ShareResponse(
        skill_id=request.skill_id,
        shared_users=shared_users,
        shared_groups=shared_groups,
        message=f"已分享给 {shared_users} 个用户和 {shared_groups} 个用户组"
    )


# ==========================================
# DELETE /share/{share_type}/{share_id} - 取消分享
# ==========================================
@router.delete("/share/user/{share_id}")
async def remove_user_share(
    share_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """取消对用户的分享"""
    share = session.get(SkillShare, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享记录不存在")

    # 检查权限
    _, perm = check_skill_permission(session, share.skill_id, current_user.id)
    if permission_level_value(perm) < permission_level_value("ADMIN"):
        raise HTTPException(status_code=403, detail="需要 ADMIN 权限")

    session.delete(share)
    session.commit()

    log.info(f"📤 [SkillShare] 取消用户分享: {share_id}")

    return {"status": "success", "message": "已取消分享"}


@router.delete("/share/group/{share_id}")
async def remove_group_share(
    share_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """取消对用户组的分享"""
    share = session.get(SkillShareGroup, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享记录不存在")

    # 检查权限
    _, perm = check_skill_permission(session, share.skill_id, current_user.id)
    if permission_level_value(perm) < permission_level_value("ADMIN"):
        raise HTTPException(status_code=403, detail="需要 ADMIN 权限")

    session.delete(share)
    session.commit()

    log.info(f"📤 [SkillShare] 取消用户组分享: {share_id}")

    return {"status": "success", "message": "已取消分享"}


# ==========================================
# PUT /share/{share_id} - 更新权限
# ==========================================
@router.put("/share/user/{share_id}")
async def update_user_permission(
    share_id: int,
    request: SkillShareUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """更新用户权限"""
    share = session.get(SkillShare, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享记录不存在")

    # 检查权限
    _, perm = check_skill_permission(session, share.skill_id, current_user.id)
    if permission_level_value(perm) < permission_level_value("ADMIN"):
        raise HTTPException(status_code=403, detail="需要 ADMIN 权限")

    if permission_level_value(request.permission_level) > permission_level_value(perm):
        raise HTTPException(status_code=400, detail="不能授予比自己更高的权限")

    share.permission_level = request.permission_level
    session.add(share)
    session.commit()

    log.info(f"📤 [SkillShare] 更新用户权限: {share_id} -> {request.permission_level}")

    return {"status": "success", "permission_level": request.permission_level}


# ==========================================
# GET /skill/{skill_id}/shares - 获取技能的分享列表
# ==========================================
class ShareDetail(BaseModel):
    """分享详情"""
    id: int
    type: str  # "user" or "group"
    target_id: int
    target_name: str
    permission_level: str
    shared_by: int
    shared_by_name: Optional[str] = None
    created_at: str


class SkillSharesResponse(BaseModel):
    """技能分享列表响应"""
    skill_id: str
    user_shares: List[ShareDetail]
    group_shares: List[ShareDetail]


@router.get("/skill/{skill_id}/shares", response_model=SkillSharesResponse)
async def get_skill_shares(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能的分享列表"""
    # 检查权限
    _, perm = check_skill_permission(session, skill_id, current_user.id)
    if permission_level_value(perm) < permission_level_value("ADMIN"):
        raise HTTPException(status_code=403, detail="需要 ADMIN 权限")

    # 获取用户分享
    user_shares_data = session.exec(
        select(SkillShare).where(SkillShare.skill_id == skill_id)
    ).all()

    user_shares = []
    for share in user_shares_data:
        user = session.get(User, share.shared_with_user_id)
        sharer = session.get(User, share.shared_by)
        user_shares.append(ShareDetail(
            id=share.id,
            type="user",
            target_id=share.shared_with_user_id,
            target_name=user.full_name or user.email if user else "Unknown",
            permission_level=share.permission_level,
            shared_by=share.shared_by,
            shared_by_name=sharer.full_name or sharer.email if sharer else None,
            created_at=share.created_at.isoformat()
        ))

    # 获取用户组分享
    group_shares_data = session.exec(
        select(SkillShareGroup).where(SkillShareGroup.skill_id == skill_id)
    ).all()

    group_shares = []
    for share in group_shares_data:
        group = session.get(UserGroup, share.group_id)
        sharer = session.get(User, share.shared_by)
        group_shares.append(ShareDetail(
            id=share.id,
            type="group",
            target_id=share.group_id,
            target_name=group.name if group else "Unknown",
            permission_level=share.permission_level,
            shared_by=share.shared_by,
            shared_by_name=sharer.full_name or sharer.email if sharer else None,
            created_at=share.created_at.isoformat()
        ))

    return SkillSharesResponse(
        skill_id=skill_id,
        user_shares=user_shares,
        group_shares=group_shares
    )


# ==========================================
# GET /shared-with-me - 获取分享给我的技能
# ==========================================
class SharedSkillSummary(BaseModel):
    """分享给我的技能摘要"""
    skill_id: str
    name: str
    description: Optional[str]
    permission_level: str
    owner_name: Optional[str]
    shared_at: str


@router.get("/shared-with-me", response_model=List[SharedSkillSummary])
async def get_shared_with_me(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取分享给我的技能列表"""
    results = []

    # 获取直接分享给我的技能
    user_shares = session.exec(
        select(SkillShare).where(SkillShare.shared_with_user_id == current_user.id)
    ).all()

    for share in user_shares:
        skill = session.exec(
            select(SkillAsset).where(SkillAsset.skill_id == share.skill_id)
        ).first()

        if skill:
            owner = session.get(User, skill.owner_id)
            results.append(SharedSkillSummary(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                permission_level=share.permission_level,
                owner_name=owner.full_name or owner.email if owner else None,
                shared_at=share.created_at.isoformat()
            ))

    # 获取通过用户组分享给我的技能
    user_groups = session.exec(
        select(UserGroupMember.group_id).where(UserGroupMember.user_id == current_user.id)
    ).all()

    if user_groups:
        group_shares = session.exec(
            select(SkillShareGroup).where(SkillShareGroup.group_id.in_(user_groups))
        ).all()

        # 记录已添加的技能，避免重复
        added_skill_ids = {s.skill_id for s in results}

        for share in group_shares:
            if share.skill_id in added_skill_ids:
                continue

            skill = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == share.skill_id)
            ).first()

            if skill:
                owner = session.get(User, skill.owner_id)
                results.append(SharedSkillSummary(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    description=skill.description,
                    permission_level=share.permission_level,
                    owner_name=owner.full_name or owner.email if owner else None,
                    shared_at=share.created_at.isoformat()
                ))
                added_skill_ids.add(share.skill_id)

    log.info(f"📤 [SkillShare] 获取分享给我的技能: {len(results)} 条, 用户: {current_user.id}")

    return results


# ==========================================
# 用户组管理 API
# ==========================================
class UserGroupCreate(BaseModel):
    """创建用户组请求"""
    name: str
    description: Optional[str] = None
    member_ids: List[int] = Field(default_factory=list)


class UserGroupPublic(BaseModel):
    """用户组公开信息"""
    id: int
    name: str
    description: Optional[str]
    owner_id: int
    member_count: int
    created_at: str


@router.post("/groups", response_model=UserGroupPublic)
async def create_user_group(
    request: UserGroupCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建用户组"""
    group = UserGroup(
        name=request.name,
        description=request.description,
        owner_id=current_user.id
    )
    session.add(group)
    session.commit()
    session.refresh(group)

    # 添加创建者为 owner
    owner_member = UserGroupMember(
        group_id=group.id,
        user_id=current_user.id,
        role="owner"
    )
    session.add(owner_member)

    # 添加成员
    for user_id in request.member_ids:
        if user_id == current_user.id:
            continue
        member = UserGroupMember(
            group_id=group.id,
            user_id=user_id,
            role="member"
        )
        session.add(member)

    session.commit()

    log.info(f"👥 [SkillShare] 创建用户组: {group.name}, 成员: {len(request.member_ids) + 1}")

    return UserGroupPublic(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_id=group.owner_id,
        member_count=len(request.member_ids) + 1,
        created_at=group.created_at.isoformat()
    )


@router.get("/groups", response_model=List[UserGroupPublic])
async def get_my_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取我所属的用户组列表"""
    # 获取用户所属的组
    memberships = session.exec(
        select(UserGroupMember).where(UserGroupMember.user_id == current_user.id)
    ).all()

    group_ids = [m.group_id for m in memberships]
    if not group_ids:
        return []

    groups = session.exec(
        select(UserGroup).where(UserGroup.id.in_(group_ids))
    ).all()

    results = []
    for group in groups:
        member_count = session.exec(
            select(UserGroupMember).where(UserGroupMember.group_id == group.id)
        ).all()
        results.append(UserGroupPublic(
            id=group.id,
            name=group.name,
            description=group.description,
            owner_id=group.owner_id,
            member_count=len(member_count),
            created_at=group.created_at.isoformat()
        ))

    return results


@router.post("/groups/{group_id}/members")
async def add_group_member(
    group_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """添加用户组成员"""
    group = session.get(UserGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有组创建者可以添加成员")

    # 检查用户是否存在
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 检查是否已是成员
    existing = session.exec(
        select(UserGroupMember).where(
            and_(
                UserGroupMember.group_id == group_id,
                UserGroupMember.user_id == user_id
            )
        )
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="用户已是组成员")

    member = UserGroupMember(
        group_id=group_id,
        user_id=user_id,
        role="member"
    )
    session.add(member)
    session.commit()

    log.info(f"👥 [SkillShare] 添加组成员: {group.name} <- {user_id}")

    return {"status": "success", "message": "成员已添加"}


@router.delete("/groups/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """移除用户组成员"""
    group = session.get(UserGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    if group.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有组创建者可以移除成员")

    member = session.exec(
        select(UserGroupMember).where(
            and_(
                UserGroupMember.group_id == group_id,
                UserGroupMember.user_id == user_id
            )
        )
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")

    session.delete(member)
    session.commit()

    log.info(f"👥 [SkillShare] 移除组成员: {group.name} <- {user_id}")

    return {"status": "success", "message": "成员已移除"}


log.info("✅ 技能分享 API 已加载")