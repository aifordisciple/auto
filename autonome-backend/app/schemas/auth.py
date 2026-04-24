"""
身份验证相关 Pydantic Schema 模块

从 auth.py 路由文件中提取的独立 schema 定义，
遵循关注点分离原则，便于复用和维护。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ============================================================
# 用户注册 & 登录
# ============================================================

class UserCreate(BaseModel):
    """用户注册请求（邮箱+密码）"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    username: Optional[str] = None


class EmailLoginRequest(BaseModel):
    """邮箱+密码登录"""
    email: EmailStr
    password: str


class SMSLoginRequest(BaseModel):
    """手机号+短信验证码登录"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6 位验证码")


class PasswordLoginRequest(BaseModel):
    """手机号+密码登录"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")
    password: str = Field(..., min_length=8, description="密码")


# ============================================================
# 短信验证码
# ============================================================

class SendSMSRequest(BaseModel):
    """发送短信验证码请求"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")
    purpose: Optional[str] = Field(
        default="login",
        description="验证码用途: login(登录), change_phone(修改手机号)"
    )
    captcha_token: Optional[str] = Field(
        default=None,
        description="Turnstile 人机验证通过凭证（未配置 Turnstile 时可不传）"
    )


# ============================================================
# Token & 会话
# ============================================================

class LoginResponse(BaseModel):
    """登录成功响应（包含 access_token，Cookie 自动设置 refresh_token）"""
    access_token: str
    token_type: str = "bearer"
    user: dict
    status: Optional[str] = None  # "success" 或 "requires_2fa"
    mfa_token: Optional[str] = None  # 2FA 挑战时返回的临时 token


class RefreshResponse(BaseModel):
    """刷新 Token 响应"""
    access_token: str
    token_type: str = "bearer"


class ActiveSessionOut(BaseModel):
    """活跃会话信息"""
    session_id: int
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    created_at: datetime
    last_active_at: datetime
    is_revoked: bool

    class Config:
        from_attributes = True


# ============================================================
# 手机号绑定
# ============================================================

class BindPhoneRequest(BaseModel):
    """OAuth 绑定手机号请求 — 前端提交手机号 + 验证码 + bind_ref（Redis 引用键）"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    otp_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")
    bind_ref: str = Field(..., min_length=1, description="OAuth 绑定引用键（替代 bind_token，防 URL 泄露）")


# ============================================================
# 邮箱绑定 & 验证
# ============================================================

class BindEmailRequest(BaseModel):
    """绑定安全邮箱请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    current_password: str = Field(..., min_length=1, description="当前密码（本人校验）")


class VerifyEmailRequest(BaseModel):
    """验证邮箱请求"""
    token: str = Field(..., min_length=1, description="邮箱验证凭证")


# ============================================================
# 忘记密码 & 重置密码
# ============================================================

class ForgotPasswordSendRequest(BaseModel):
    """忘记密码 — 发送验证码请求"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")


class ForgotPasswordVerifyRequest(BaseModel):
    """忘记密码 — 验证码校验请求"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    otp_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")


class ResetPasswordRequest(BaseModel):
    """忘记密码 — 重置密码请求"""
    reset_token: str = Field(..., min_length=1, description="密码重置凭证")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")


# ============================================================
# 修改密码（已登录用户）
# ============================================================

class ChangePasswordRequest(BaseModel):
    """已登录用户修改密码请求"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# ============================================================
# 修改手机号（已登录用户，需SMS验证）
# ============================================================

class ChangePhoneRequest(BaseModel):
    """修改手机号请求（需验证新手机号 + 当前密码）"""
    new_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="新手机号")
    otp_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")
    current_password: str = Field(..., min_length=1, description="当前密码（本人校验）")


# ============================================================
# 2FA / TOTP
# ============================================================

class TwoFASetupResponse(BaseModel):
    """2FA 设置响应（包含 TOTP 密钥和 QR 码 URI）"""
    secret: str
    qr_uri: str


class TwoFAVerifyRequest(BaseModel):
    """验证并启用 2FA 请求"""
    secret: str
    totp_code: str = Field(..., min_length=6, max_length=6)


class TwoFADisableRequest(BaseModel):
    """禁用 2FA 请求"""
    totp_code: str = Field(..., min_length=6, max_length=6)


class TwoFALoginRequest(BaseModel):
    """2FA 登录验证请求"""
    mfa_token: str
    totp_code: str = Field(..., min_length=6, max_length=6)
