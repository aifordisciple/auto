"""
用户中心 API 路由

设计日期: 2026-03-22

## API 端点列表
- GET    /api/users/me          - 获取当前用户完整资料
- PUT    /api/users/me          - 更新用户资料
- POST   /api/users/me/password - 修改密码
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import hashlib

from app.core.database import get_session
from app.core.security import verify_password, get_password_hash
from app.models.domain import User
from app.api.deps import get_current_user

router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

class UserProfileResponse(BaseModel):
    """用户资料响应"""
    id: int
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    organization: Optional[str]
    phone: Optional[str]
    bio: Optional[str]
    is_superuser: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 计算字段
    role: str  # "admin" | "user"
    gravatar_url: str  # Gravatar 备用头像


class UserProfileUpdate(BaseModel):
    """用户资料更新请求"""
    full_name: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    """密码修改请求"""
    current_password: str
    new_password: str  # 前端需验证密码强度


# ==========================================
# API 端点实现
# ==========================================

@router.get("/me", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户完整资料

    包含：
    - 基础信息
    - 计算字段（role, gravatar_url）
    """
    # 生成 Gravatar URL（邮箱哈希）
    email_hash = hashlib.md5(current_user.email.lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon&s=200"

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        organization=current_user.organization,
        phone=current_user.phone,
        bio=current_user.bio,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        role="admin" if current_user.is_superuser else "user",
        gravatar_url=gravatar_url
    )


@router.put("/me")
async def update_user_profile(
    profile: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    更新用户资料

    可更新字段：
    - full_name: 昵称/全名
    - organization: 组织/机构
    - phone: 手机号
    - bio: 个人简介

    注意：邮箱修改需要单独的验证流程（MVP 阶段暂不支持）
    """
    from loguru import logger

    # 更新字段（仅更新非 None 的字段）
    update_data = profile.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.now(timezone.utc)

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    logger.info(f"用户 {current_user.id} 更新资料成功: {list(update_data.keys())}")

    return {"status": "success", "message": "资料更新成功"}


@router.post("/me/password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    修改密码

    安全验证：
    1. 验证原密码是否正确
    2. 新密码强度验证（前端 + 后端双重验证）
    3. 记录审计日志

    注意：
    - 新密码不能与原密码相同
    - 新密码需满足最小强度要求
    """
    from loguru import logger

    # 1. 验证原密码
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )

    # 2. 验证新密码不能与原密码相同
    if verify_password(request.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与原密码相同"
        )

    # 3. 验证新密码强度（至少 8 位，包含字母和数字）
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少 8 位"
        )

    has_letter = any(c.isalpha() for c in request.new_password)
    has_digit = any(c.isdigit() for c in request.new_password)
    if not (has_letter and has_digit):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码需包含字母和数字"
        )

    # 4. 更新密码
    current_user.hashed_password = get_password_hash(request.new_password)
    current_user.last_password_change = datetime.now(timezone.utc)
    current_user.updated_at = datetime.now(timezone.utc)

    session.add(current_user)
    session.commit()

    logger.info(f"用户 {current_user.id} 修改密码成功")

    return {"status": "success", "message": "密码修改成功"}