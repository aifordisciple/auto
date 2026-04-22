"""
安全工具模块

设计日期: 2026-03-22
更新日期: 2026-04-21（阶段2：新增 Refresh Token 和 Cookie 工具函数）

功能：
- JWT Token 生成与验证
- 密码哈希与验证（bcrypt）
- Refresh Token 生成与哈希
- Cookie 设置辅助函数
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Response
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ==========================================
# JWT 算法常量（向后兼容，供 deps.py 等模块导入）
# ==========================================

ALGORITHM = settings.ALGORITHM


# ==========================================
# 密码哈希（bcrypt）
# ==========================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


# ==========================================
# JWT Access Token
# ==========================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT Access Token

    Args:
        data: 载荷数据（通常包含 sub: user_id）
        expires_delta: 自定义过期时间增量
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_short_access_token(data: dict) -> str:
    """
    创建短命 JWT Access Token（15 分钟）

    用于新认证端点（SMS 登录、密码登录、Refresh 刷新）
    与旧端点的 7 天 Token 分离，配合 Refresh Token 使用
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_SHORT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """
    验证 JWT Token，返回载荷或 None

    注意：此函数接受所有合法的 JWT（包括 scoped token）。
    对于业务 API 鉴权，请使用 verify_access_token() 以拒绝 scoped token。
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[dict]:
    """
    验证业务访问 Token，拒绝 scoped token（bind_only / reset_password / verify_email）

    仅用于 deps.py 中的 get_current_user 依赖，防止 scoped token
    被当作普通 access_token 使用而绕过授权。
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # 拒绝任何带 scope 声明的 token（它们仅用于特定流程，不能用于业务 API）
        if payload.get("scope") is not None:
            return None
        return payload
    except JWTError:
        return None


# ==========================================
# Refresh Token
# ==========================================

import secrets
import hashlib


def generate_refresh_token() -> str:
    """
    生成 Refresh Token

    使用 secrets.token_urlsafe 生成 64 字节随机令牌
    仅存储其 SHA-256 摘要到数据库，不存明文
    """
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """
    计算 Refresh Token 的 SHA-256 摘要

    数据库仅存储摘要，防止脱库后 Token 被滥用
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_refresh_token_expires_at() -> datetime:
    """
    获取 Refresh Token 过期时间

    基于 settings.REFRESH_TOKEN_EXPIRE_DAYS 计算
    """
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


# ==========================================
# Bind Token（OAuth 强制手机号绑定凭证）
# ==========================================

def create_bind_token(
    provider: str,
    provider_account_id: str,
    email: str | None = None,
    name: str | None = None,
    avatar_url: str | None = None,
) -> str:
    """
    创建 OAuth 绑定 Token

    当第三方 OAuth 账号未关联已有用户时，签发此 Token。
    前端收到后弹出强制绑定手机号模态框，绑定成功后才下发正式 Token。

    Token 有效期 10 分钟，scope=bind_only，不可用于调用业务 API。
    """
    data = {
        "sub": f"bind:{provider}:{provider_account_id}",
        "scope": "bind_only",
        "provider": provider,
        "provider_account_id": provider_account_id,
        "email": email or "",
        "name": name or "",
        "avatar_url": avatar_url or "",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_bind_token(token: str) -> dict | None:
    """
    验证 OAuth 绑定 Token

    Returns:
        解析后的载荷字典，包含 provider, provider_account_id 等；
        若 Token 无效、过期或 scope 不是 bind_only，返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != "bind_only":
            return None
        return payload
    except JWTError:
        return None


# ==========================================
# Password Reset Token（忘记密码重置凭证）
# ==========================================

def create_reset_token(user_id: int) -> str:
    """
    创建密码重置 Token

    用户通过手机验证码确认身份后，下发此 Token。
    前端携带此 Token 提交新密码，完成重置。

    Token 有效期 10 分钟，scope=reset_password。
    """
    data = {
        "sub": str(user_id),
        "scope": "reset_password",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_reset_token(token: str) -> dict | None:
    """
    验证密码重置 Token

    Returns:
        解析后的载荷字典，包含 sub(user_id)；
        若 Token 无效、过期或 scope 不是 reset_password，返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != "reset_password":
            return None
        return payload
    except JWTError:
        return None


# ==========================================
# Email Verification Token（邮箱绑定验证凭证）
# ==========================================

def create_email_verification_token(user_id: int, email: str) -> str:
    """
    创建邮箱验证 Token

    用户请求绑定邮箱后，此 Token 嵌入验证链接发送到邮箱。
    用户点击链接后，前端携带此 Token 调用验证端点。

    Token 有效期 15 分钟，scope=verify_email。
    """
    data = {
        "sub": str(user_id),
        "scope": "verify_email",
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_email_verification_token(token: str) -> dict | None:
    """
    验证邮箱验证 Token

    Returns:
        解析后的载荷字典，包含 sub(user_id) 和 email；
        若 Token 无效、过期或 scope 不是 verify_email，返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != "verify_email":
            return None
        return payload
    except JWTError:
        return None


# ==========================================
# Cookie 辅助函数
# ==========================================

def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """
    设置认证 Cookie（httpOnly, SameSite=Lax）

    两个 Cookie：
    - access_token: 短命（15 分钟），Path=/api
    - refresh_token: 长命（7 天），Path=/api/auth/refresh

    安全属性：
    - HttpOnly: JS 无法读取，防 XSS
    - Secure: 生产环境要求 HTTPS
    - SameSite=Lax: 防 CSRF
    """
    secure = settings.SECURE_COOKIES

    # Access Token Cookie（短命，15 分钟）
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_SHORT_EXPIRE_MINUTES * 60,
        path="/api",
        httponly=True,
        secure=secure,
        samesite="lax",
    )

    # Refresh Token Cookie（长命，7 天，仅 /api/auth/refresh 路径可访问）
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/auth/refresh",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    """
    清除认证 Cookie

    登出时调用，将 Cookie 的 max_age 设为 0 使其立即失效
    """
    secure = settings.SECURE_COOKIES

    response.set_cookie(
        key="access_token",
        value="",
        max_age=0,
        path="/api",
        httponly=True,
        secure=secure,
        samesite="lax",
    )

    response.set_cookie(
        key="refresh_token",
        value="",
        max_age=0,
        path="/api/auth/refresh",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
