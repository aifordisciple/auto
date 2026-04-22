"""
认证 API 路由

设计日期: 2026-03-22
更新日期: 2026-04-21（阶段2：新增双通道认证 + Refresh Token 体系）

## API 端点列表

### 旧端点（保持不变）
- POST   /api/auth/register        - 邮箱注册
- POST   /api/auth/login           - 邮箱密码登录（OAuth2PasswordRequestForm）
- GET    /api/auth/me              - 获取当前用户信息

### 新端点（阶段2新增）
- POST   /api/auth/send-sms        - 发送短信验证码
- POST   /api/auth/login/sms       - 验证码登录（自动注册）
- POST   /api/auth/login/password  - 手机号+密码登录
- POST   /api/auth/refresh         - Refresh Token 无感刷新
- POST   /api/auth/logout          - 登出（撤销会话 + 清 Cookie）
- GET    /api/auth/sessions        - 查看在线设备列表
- POST   /api/auth/sessions/{id}/revoke - 踢设备下线
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone

from app.core.database import get_session
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_short_access_token, verify_token,
    generate_refresh_token, hash_refresh_token, get_refresh_token_expires_at,
    set_auth_cookies, clear_auth_cookies,
    create_bind_token, verify_bind_token,
    create_reset_token, verify_reset_token,
    create_email_verification_token, verify_email_verification_token,
)
from app.core.config import settings
from app.models.domain import User, ActiveSession
from app.api.deps import get_current_user
from app.services.auth_risk_control import (
    check_sms_rate_limit, record_sms_sent, release_sms_lock,
    generate_otp, verify_otp,
    check_login_risk, record_login_failure, clear_login_failure,
)
from app.services.sms_service import get_sms_service

router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

# --- 旧端点模型（保持不变）---

class UserCreate(BaseModel):
    """邮箱注册请求"""
    email: EmailStr
    password: str = Field(..., min_length=8)


class Token(BaseModel):
    """JWT Token 响应"""
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    """用户信息响应"""
    id: int
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    organization: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    is_superuser: bool = False
    is_email_verified: bool = False
    is_2fa_enabled: bool = False
    created_at: Optional[datetime] = None


# --- 新端点模型（阶段2新增）---

class SendSMSRequest(BaseModel):
    """发送验证码请求"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")


class SMSLoginRequest(BaseModel):
    """验证码登录请求"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6 位验证码")


class PasswordLoginRequest(BaseModel):
    """手机号+密码登录请求"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号码")
    password: str = Field(..., min_length=8, description="密码")


class RefreshResponse(BaseModel):
    """Token 刷新响应"""
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


class LoginResponse(BaseModel):
    """登录成功响应（包含 access_token，Cookie 自动设置 refresh_token）"""
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


# --- OAuth 绑定手机号模型 ---

class BindPhoneRequest(BaseModel):
    """OAuth 绑定手机号请求 — 前端提交手机号 + 验证码 + bind_token"""
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="手机号")
    otp_code: str = Field(..., min_length=4, max_length=6, description="短信验证码")
    bind_token: str = Field(..., min_length=1, description="OAuth 绑定凭证")


# --- 忘记密码模型 ---

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


# --- 邮箱绑定模型 ---

class BindEmailRequest(BaseModel):
    """绑定安全邮箱请求"""
    email: str = Field(..., description="邮箱地址")
    current_password: str = Field(..., min_length=1, description="当前密码（本人校验）")


class VerifyEmailRequest(BaseModel):
    """验证邮箱请求"""
    token: str = Field(..., min_length=1, description="邮箱验证凭证")


# ==========================================
# 旧端点实现（保持不变）
# ==========================================

@router.post("/register", response_model=Token)
async def register(
    user_create: UserCreate,
    session: Session = Depends(get_session)
):
    """
    邮箱注册

    创建新用户并返回 JWT Token
    """
    # 检查邮箱是否已注册
    existing = session.exec(select(User).where(User.email == user_create.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已注册"
        )

    # 创建用户
    user = User(
        email=user_create.email,
        hashed_password=get_password_hash(user_create.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # 生成 Token
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """
    邮箱密码登录（OAuth2 兼容）

    使用 OAuth2PasswordRequestForm，username 字段传入 email
    返回长命 JWT（7天，向后兼容旧前端）
    """
    # form_data.username 当作 email 使用
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱或密码错误"
        )

    # 签发长命 JWT（7天，向后兼容旧端点）
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户信息

    返回用户基础信息，包含阶段1新增的安全字段
    """
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        organization=current_user.organization,
        phone_number=current_user.phone_number,
        bio=current_user.bio,
        is_superuser=current_user.is_superuser,
        is_email_verified=current_user.is_email_verified,
        is_2fa_enabled=current_user.is_2fa_enabled,
        created_at=current_user.created_at,
    )


# ==========================================
# 新端点实现（阶段2新增）
# ==========================================

@router.post("/send-sms")
async def send_sms(
    request: SendSMSRequest,
    http_request: Request,
):
    """
    发送短信验证码

    流程：风控检查 → 生成 OTP → Redis 存储 → 异步发送 SMS

    限流策略：
    - 60 秒内不可重发
    - 同一手机号每天最多 10 条
    - 同一 IP 每小时最多 5 条
    """
    # 获取客户端 IP
    client_ip = http_request.client.host if http_request.client else "unknown"
    # 优先使用 X-Forwarded-For（反向代理场景）
    forwarded = http_request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    # 风控检查
    allowed, reason = check_sms_rate_limit(request.phone_number, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
        )

    # 生成 6 位验证码并存入 Redis
    otp = generate_otp(request.phone_number)

    # 记录发送计数（含冷却锁、每日计数、IP 计数）
    record_sms_sent(request.phone_number, client_ip)

    # 异步发送 SMS
    sms_service = get_sms_service()
    success = await sms_service.send_verification_code(request.phone_number, otp)

    if not success:
        # 发送失败，释放冷却锁允许重试
        release_sms_lock(request.phone_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证码发送失败，请稍后重试",
        )

    return {"status": "success", "message": "验证码已发送"}


@router.post("/login/sms", response_model=LoginResponse)
async def login_with_sms(
    request: SMSLoginRequest,
    http_request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    验证码登录（自动注册）

    流程：
    1. 验证 OTP 验证码
    2. 查找手机号对应用户，不存在则自动注册
    3. 签发双 Token（AT + RT）
    4. 设置 httpOnly Cookie
    """
    # 验证 OTP
    valid, reason = verify_otp(request.phone_number, request.otp_code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    # 查找或创建用户
    user = session.exec(
        select(User).where(User.phone_number == request.phone_number)
    ).first()

    if not user:
        # 自动注册：手机号即账号
        user = User(
            email=f"{request.phone_number}@phone.placeholder",
            phone_number=request.phone_number,
            hashed_password=None,  # 纯验证码用户，无密码
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    # 签发双 Token
    access_token, refresh_token_val = _issue_tokens(
        user_id=user.id,
        http_request=http_request,
        session=session,
    )

    # 设置 Cookie
    set_auth_cookies(response, access_token, refresh_token_val)

    return LoginResponse(
        access_token=access_token,
        user=UserInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            organization=user.organization,
            phone_number=user.phone_number,
            bio=user.bio,
            is_superuser=user.is_superuser,
            is_email_verified=user.is_email_verified,
            is_2fa_enabled=user.is_2fa_enabled,
            created_at=user.created_at,
        ),
    )


@router.post("/login/password", response_model=LoginResponse)
async def login_with_password(
    request: PasswordLoginRequest,
    http_request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    手机号+密码登录

    流程：
    1. 风控检查（防爆破）
    2. 查找用户并验证密码
    3. 签发双 Token
    4. 设置 httpOnly Cookie
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    forwarded = http_request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    # 风控检查
    safe, reason = check_login_risk(request.phone_number)
    if not safe:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
        )

    # 查找用户
    user = session.exec(
        select(User).where(User.phone_number == request.phone_number)
    ).first()

    if not user or not user.hashed_password:
        record_login_failure(request.phone_number)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误",
        )

    # 验证密码
    if not verify_password(request.password, user.hashed_password):
        record_login_failure(request.phone_number)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误",
        )

    # 登录成功，清除失败记录
    clear_login_failure(request.phone_number)

    # 签发双 Token
    access_token, refresh_token_val = _issue_tokens(
        user_id=user.id,
        http_request=http_request,
        session=session,
    )

    # 设置 Cookie
    set_auth_cookies(response, access_token, refresh_token_val)

    return LoginResponse(
        access_token=access_token,
        user=UserInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            organization=user.organization,
            phone_number=user.phone_number,
            bio=user.bio,
            is_superuser=user.is_superuser,
            is_email_verified=user.is_email_verified,
            is_2fa_enabled=user.is_2fa_enabled,
            created_at=user.created_at,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    http_request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    session: Session = Depends(get_session),
):
    """
    Refresh Token 无感刷新

    流程：
    1. 从 Cookie 读取 refresh_token
    2. 计算哈希，查找 active_sessions 记录
    3. 验证会话有效性（未过期、未撤销）
    4. 签发新 Access Token
    5. 更新会话 last_active_at
    6. 设置新 Cookie
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Refresh Token",
        )

    # 计算 RT 哈希，查找会话记录
    rt_hash = hash_refresh_token(refresh_token)
    active_session = session.exec(
        select(ActiveSession).where(ActiveSession.refresh_token_hash == rt_hash)
    ).first()

    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Refresh Token",
        )

    # 验证会话有效性
    now = datetime.now(timezone.utc)
    if active_session.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="会话已撤销",
        )
    if active_session.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="会话已过期",
        )

    # 查找用户
    user = session.get(User, active_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    # 签发新 Access Token
    new_access_token = create_short_access_token(data={"sub": str(user.id)})

    # 更新会话活跃时间
    active_session.last_active_at = now
    session.add(active_session)
    session.commit()

    # 设置新 Cookie（刷新 AT Cookie）
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        max_age=settings.ACCESS_TOKEN_SHORT_EXPIRE_MINUTES * 60,
        path="/api",
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="lax",
    )

    return RefreshResponse(access_token=new_access_token)


@router.post("/logout")
async def logout(
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    session: Session = Depends(get_session),
):
    """
    登出

    流程：
    1. 撤销当前用户的所有活跃会话
    2. 清除认证 Cookie
    """
    # 撤销当前用户的所有活跃会话
    active_sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,
        )
    ).all()

    for s in active_sessions:
        s.is_revoked = True
        session.add(s)

    session.commit()

    # 清除 Cookie
    clear_auth_cookies(response)

    return {"status": "success", "message": "已登出"}


@router.get("/sessions", response_model=List[ActiveSessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    查看当前用户的在线设备列表

    返回所有未撤销且未过期的会话
    """
    now = datetime.now(timezone.utc)
    sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,
            ActiveSession.expires_at > now,
        )
    ).all()

    return [ActiveSessionOut(
        session_id=s.session_id,
        user_agent=s.user_agent,
        ip_address=s.ip_address,
        device_type=s.device_type,
        created_at=s.created_at,
        last_active_at=s.last_active_at,
        is_revoked=s.is_revoked,
    ) for s in sessions]


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    踢设备下线

    撤销指定会话，该设备下次请求时将收到 401
    """
    active_session = session.get(ActiveSession, session_id)

    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    # 安全检查：只能撤销自己的会话
    if active_session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此会话",
        )

    active_session.is_revoked = True
    session.add(active_session)
    session.commit()

    return {"status": "success", "message": "设备已下线"}


# ==========================================
# OAuth 强制绑定手机号（工作流 B 闭环）
# ==========================================

@router.post("/bind-phone", response_model=LoginResponse)
async def bind_phone(
    request: BindPhoneRequest,
    http_request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    OAuth 绑定手机号 — 第三方登录后强制绑定手机号

    流程：
    1. 验证 bind_token（解析 provider, provider_account_id 等信息）
    2. 验证手机号 SMS OTP
    3. 查找手机号对应用户：
       - 已存在：将 OAuth 账号关联到该用户（冲突检查）
       - 不存在：创建新 User + OAuthAccount
    4. 签发双 Token
    """
    from app.models.user import OAuthAccount

    # 1. 验证 bind_token
    bind_payload = verify_bind_token(request.bind_token)
    if not bind_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="绑定凭证无效或已过期，请重新登录",
        )

    provider = bind_payload["provider"]
    provider_account_id = bind_payload["provider_account_id"]
    oauth_email = bind_payload.get("email") or None
    oauth_name = bind_payload.get("name") or None
    oauth_avatar = bind_payload.get("avatar_url") or None

    # 2. 验证 SMS OTP
    valid, reason = verify_otp(request.phone, request.otp_code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    # 3. 查找手机号对应用户
    user = session.exec(
        select(User).where(User.phone_number == request.phone)
    ).first()

    if user:
        # 手机号已存在 → 检查该用户是否已绑定同类型 OAuth
        existing_oauth = session.exec(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user.id,
                OAuthAccount.provider == provider,
            )
        ).first()
        if existing_oauth:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"该手机号已绑定其他 {provider} 账号，请联系管理员",
            )
        # 关联 OAuth 账号到已有用户
        oauth_account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_name=oauth_name,
            provider_avatar_url=oauth_avatar,
        )
        session.add(oauth_account)
        session.commit()
    else:
        # 手机号是新号 → 创建新用户 + OAuthAccount
        user = User(
            email=oauth_email or f"{request.phone}@phone.placeholder",
            phone_number=request.phone,
            hashed_password=None,
            full_name=oauth_name,
            avatar_url=oauth_avatar,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_name=oauth_name,
            provider_avatar_url=oauth_avatar,
        )
        session.add(oauth_account)
        session.commit()

    # 4. 签发双 Token
    access_token, refresh_token_val = _issue_tokens(
        user_id=user.id,
        http_request=http_request,
        session=session,
    )
    set_auth_cookies(response, access_token, refresh_token_val)

    return LoginResponse(
        access_token=access_token,
        user=UserInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            organization=user.organization,
            phone_number=user.phone_number,
            bio=user.bio,
            is_superuser=user.is_superuser,
            is_email_verified=user.is_email_verified,
            is_2fa_enabled=user.is_2fa_enabled,
            created_at=user.created_at,
        ),
    )


# ==========================================
# 忘记密码 / 密码重置（工作流 G）
# ==========================================

@router.post("/forgot-password/send")
async def forgot_password_send(
    request: ForgotPasswordSendRequest,
    http_request: Request,
    session: Session = Depends(get_session),
):
    """
    忘记密码 — 发送验证码

    流程：风控检查 → 查找用户 → 生成 OTP → 发送 SMS
    """
    # 风控检查
    client_ip = http_request.client.host if http_request.client else "unknown"
    forwarded = http_request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    allowed, reason = check_sms_rate_limit(request.phone, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
        )

    # 查找用户（不暴露用户是否存在的信息，统一返回"已发送"）
    user = session.exec(
        select(User).where(User.phone_number == request.phone)
    ).first()

    # 生成 OTP 并发送（即使用户不存在也发送，防止枚举攻击）
    otp = generate_otp(request.phone)
    record_sms_sent(request.phone, client_ip)

    sms_service = get_sms_service()
    success = await sms_service.send_verification_code(request.phone, otp)

    if not success:
        release_sms_lock(request.phone)
        # 不暴露发送失败细节，防止信息泄露
        pass

    # 无论用户是否存在，统一返回成功（防枚举）
    return {"status": "success", "message": "如果该手机号已注册，验证码已发送"}


@router.post("/forgot-password/verify")
async def forgot_password_verify(
    request: ForgotPasswordVerifyRequest,
    session: Session = Depends(get_session),
):
    """
    忘记密码 — 验证码校验，下发 reset_token

    流程：验证 OTP → 查找用户 → 下发 reset_token
    """
    # 验证 OTP
    valid, reason = verify_otp(request.phone, request.otp_code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    # 查找用户
    user = session.exec(
        select(User).where(User.phone_number == request.phone)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该手机号未注册",
        )

    # 下发 reset_token
    reset_token = create_reset_token(user_id=user.id)

    return {"status": "success", "reset_token": reset_token}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    session: Session = Depends(get_session),
):
    """
    忘记密码 — 重置密码

    流程：验证 reset_token → 密码强度验证 → 更新密码 → 撤销所有会话
    """
    # 验证 reset_token
    payload = verify_reset_token(request.reset_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="重置凭证无效或已过期，请重新操作",
        )

    user_id = int(payload["sub"])
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在",
        )

    # 密码强度验证
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度至少 8 位",
        )
    has_letter = any(c.isalpha() for c in request.new_password)
    has_digit = any(c.isdigit() for c in request.new_password)
    if not (has_letter and has_digit):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码需包含字母和数字",
        )

    # 更新密码
    user.hashed_password = get_password_hash(request.new_password)
    user.last_password_change = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)

    # 【安全动作】撤销该用户所有 ActiveSession（密码已变，旧 Token 全部失效）
    active_sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == user.id,
            ActiveSession.is_revoked == False,
        )
    ).all()
    for s in active_sessions:
        s.is_revoked = True
        session.add(s)

    session.commit()

    return {"status": "success", "message": "密码重置成功，请使用新密码登录"}


# ==========================================
# 安全邮箱绑定（工作流 E）
# ==========================================

@router.post("/bind-email")
async def bind_email(
    request: BindEmailRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    绑定安全邮箱 — 已登录用户请求绑定邮箱

    流程：验证当前密码 → 生成验证 Token → 发送验证邮件
    """
    # 本人校验：验证当前密码
    if not current_user.hashed_password or not verify_password(
        request.current_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )

    # 检查邮箱是否已被其他用户使用
    existing = session.exec(
        select(User).where(User.email == request.email)
    ).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被其他用户使用",
        )

    # 生成验证 Token
    verification_token = create_email_verification_token(
        user_id=current_user.id, email=request.email
    )

    # 发送验证邮件（异步，通过 Celery 或直接调用）
    try:
        from app.services.email_service import get_email_service
        email_service = get_email_service()
        await email_service.send_verification_email(
            to_email=request.email,
            token=verification_token,
            user_name=current_user.full_name or current_user.email,
        )
    except Exception as e:
        from app.core.logger import log
        log.error(f"验证邮件发送失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证邮件发送失败，请稍后重试",
        )

    return {"status": "success", "message": "验证邮件已发送，请查收邮箱"}


@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    session: Session = Depends(get_session),
):
    """
    验证邮箱 — 用户点击邮件中的验证链接后调用

    流程：验证 token → 更新 email 和 is_email_verified
    """
    payload = verify_email_verification_token(request.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证凭证无效或已过期",
        )

    user_id = int(payload["sub"])
    email = payload["email"]

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在",
        )

    # 更新邮箱和验证状态
    user.email = email
    user.is_email_verified = True
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    return {"status": "success", "message": "邮箱绑定成功"}


# ==========================================
# 内部工具函数
# ==========================================

def _issue_tokens(user_id: int, http_request: Request, session: Session) -> tuple[str, str]:
    """
    签发双 Token 并创建会话记录

    Args:
        user_id: 用户 ID
        http_request: HTTP 请求（提取设备信息）
        session: 数据库会话

    Returns:
        (access_token, refresh_token) 元组
    """
    # 签发短命 Access Token（15 分钟）
    access_token = create_short_access_token(data={"sub": str(user_id)})

    # 签发长命 Refresh Token（7 天）
    refresh_token_val = generate_refresh_token()
    rt_hash = hash_refresh_token(refresh_token_val)
    expires_at = get_refresh_token_expires_at()

    # 提取设备信息
    user_agent = http_request.headers.get("User-Agent", "")[:512]
    client_ip = http_request.client.host if http_request.client else None
    forwarded = http_request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    # 简易设备类型判断
    device_type = _detect_device_type(user_agent)

    # 创建会话记录
    active_session = ActiveSession(
        user_id=user_id,
        refresh_token_hash=rt_hash,
        user_agent=user_agent,
        ip_address=client_ip,
        device_type=device_type,
        expires_at=expires_at,
    )
    session.add(active_session)
    session.commit()

    return access_token, refresh_token_val


def _detect_device_type(user_agent: str) -> str:
    """
    根据 User-Agent 判断设备类型

    简易判断逻辑，覆盖主流场景
    """
    ua_lower = user_agent.lower()
    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        return "mobile"
    elif "ipad" in ua_lower or "tablet" in ua_lower:
        return "tablet"
    elif "bot" in ua_lower or "crawl" in ua_lower:
        return "bot"
    else:
        return "desktop"
