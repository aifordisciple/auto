"""
认证依赖模块

设计日期: 2026-03-22
更新日期: 2026-04-21（阶段2：支持 Cookie 认证 + Bearer Token 双模式）

功能：
- get_current_user: 核心认证拦截器（Cookie 优先 → Bearer Token 回退）
- verify_token_and_get_user: 从 token 字符串验证（SSE 等场景）
- get_current_superuser: 超级管理员权限检查
"""

from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from typing import Optional

from sqlmodel import Session

from app.core.database import get_session
from app.core.config import settings
from app.core.security import verify_access_token, ALGORITHM
from app.models.domain import User

# FastAPI OAuth2 密码流配置（告知 Swagger UI 登录接口在哪里）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    session: Session = Depends(get_session),
) -> User:
    """
    核心认证拦截器

    Token 获取优先级：
    1. Authorization: Bearer <token> 请求头（SSE/WebSocket/第三方客户端）
    2. access_token Cookie（浏览器自动携带）

    两种方式都支持，Cookie 模式下前端无需手动注入 header
    """
    # 优先使用 Bearer Token，回退到 Cookie
    actual_token = token or access_token_cookie

    if not actual_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证 JWT（拒绝 scoped token，仅接受业务 access_token）
    payload = verify_access_token(actual_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查找用户
    user = session.get(User, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账户已被封禁",
        )

    return user


def verify_token_and_get_user(token: str, session: Session) -> User:
    """
    从 token 字符串验证用户（用于 SSE 等不支持自定义 header 的场景）

    Args:
        token: JWT token 字符串
        session: 数据库会话

    Returns:
        验证通过的用户对象

    Raises:
        HTTPException: 认证失败时抛出 401 错误
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败或 Token 已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = session.get(User, int(user_id))
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=400, detail="该账户已被封禁")

    return user


def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    超级管理员权限检查

    在 get_current_user 基础上，额外要求 is_superuser=True
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="越权警告：您的账号级别不足以访问系统级控制台。",
        )
    return current_user
