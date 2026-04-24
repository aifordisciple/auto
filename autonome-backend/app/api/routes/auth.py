"""
认证 API 路由

设计日期: 2026-03-22
更新日期: 2026-04-23（阶段3：2FA/TOTP + 修改密码 + 修改手机号）

## API 端点列表

### 旧端点（保持不变）
- POST   /api/auth/register        - 邮箱注册
- GET    /api/auth/me              - 获取当前用户信息

### 阶段2端点
- POST   /api/auth/login           - 邮箱密码登录（OAuth2PasswordRequestForm，已对齐新认证流程）
- POST   /api/auth/send-sms        - 发送短信验证码
- POST   /api/auth/login/sms       - 验证码登录（自动注册）
- POST   /api/auth/login/password  - 手机号+密码登录
- POST   /api/auth/refresh         - Refresh Token 无感刷新
- POST   /api/auth/logout          - 登出（撤销会话 + 清 Cookie）
- GET    /api/auth/sessions        - 查看在线设备列表
- POST   /api/auth/sessions/{id}/revoke - 踢设备下线

### 阶段3端点（2FA + 密码修改 + 手机号修改）
- POST   /api/auth/2fa/setup       - 生成 TOTP 密钥（2FA 设置第一步）
- POST   /api/auth/2fa/verify      - 验证并启用 2FA（2FA 设置第二步）
- POST   /api/auth/2fa/disable     - 禁用 2FA
- POST   /api/auth/2fa/login       - 2FA 登录验证
- POST   /api/auth/change-password - 已登录用户修改密码
- POST   /api/auth/change-phone    - 已登录用户修改手机号

### 阶段4端点（人机验证 + 会话管理增强）
- POST   /api/auth/sessions/revoke-others - 撤销除当前会话外的所有会话
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from datetime import datetime, timezone
from typing import Optional

from app.core.database import get_session
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_short_access_token, verify_token,
    generate_refresh_token, hash_refresh_token, get_refresh_token_expires_at,
    set_auth_cookies, clear_auth_cookies,
    create_bind_token, verify_bind_token,
    create_reset_token, verify_reset_token,
    create_email_verification_token, verify_email_verification_token,
    create_mfa_token, verify_mfa_token,
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
from app.services.turnstile_service import verify_turnstile_token
from app.schemas.auth import (
    UserCreate, SMSLoginRequest, PasswordLoginRequest,
    SendSMSRequest, LoginResponse, RefreshResponse,
    ActiveSessionOut,
    BindPhoneRequest, ForgotPasswordSendRequest, ForgotPasswordVerifyRequest,
    ResetPasswordRequest, BindEmailRequest, VerifyEmailRequest,
    ChangePasswordRequest, ChangePhoneRequest,
    TwoFASetupResponse, TwoFAVerifyRequest, TwoFADisableRequest, TwoFALoginRequest,
)

router = APIRouter()


# ==========================================
# 内部工具：用户信息构建
# ==========================================

def _build_user_info(user: User) -> dict:
    """从 User 模型构建统一格式的用户信息字典"""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "organization": user.organization,
        "phone_number": user.phone_number,
        "bio": user.bio,
        "is_superuser": user.is_superuser,
        "is_email_verified": user.is_email_verified,
        "is_2fa_enabled": user.is_2fa_enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_password_change": user.last_password_change.isoformat() if user.last_password_change else None,
    }


# ==========================================
# 旧端点实现（register 保持不变，login 已对齐新流程）
# ==========================================

@router.post("/register")
async def register(
    user_create: UserCreate,
    session: Session = Depends(get_session),
):
    """
    用户注册（支持两种方式）

    方式一：邮箱 + 密码注册
      - 检查邮箱唯一性 → 创建用户 → 签发 Token

    方式二：手机号 + 短信验证码 + 密码注册
      - 验证 OTP（verify_otp）→ 检查手机号唯一性 → 创建用户（虚拟邮箱） → 签发 Token
      - 虚拟邮箱格式：{phone}@phone.placeholder（与 login/sms 自动注册逻辑一致）

    两种方式均支持 full_name 字段。
    """
    # ---- 判断注册方式 ----
    is_phone_register = user_create.phone_number is not None

    if is_phone_register:
        # ============================================================
        # 手机号 + 验证码注册
        # 为什么先验证 OTP 再检查唯一性：
        # - OTP 验证有次数限制（3次错误销毁），先验证可尽早消耗 OTP
        # - 避免手机号已注册时暴露"该手机号已注册"信息给未验证 OTP 的请求
        # ============================================================
        valid, reason = verify_otp(user_create.phone_number, user_create.sms_code)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

        # 检查手机号唯一性
        existing = session.exec(
            select(User).where(User.phone_number == user_create.phone_number)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该手机号已注册",
            )

        # 创建用户：虚拟邮箱 + 手机号 + 密码
        # 为什么使用虚拟邮箱：User 模型 email 字段有唯一约束，不能为空，
        # 手机号注册时无真实邮箱，故用占位符格式，与 login/sms 自动注册逻辑一致
        user = User(
            email=f"{user_create.phone_number}@phone.placeholder",
            phone_number=user_create.phone_number,
            hashed_password=get_password_hash(user_create.password),
            full_name=user_create.full_name,
        )
    else:
        # ============================================================
        # 邮箱 + 密码注册（保留原有逻辑）
        # ============================================================
        # 检查邮箱唯一性
        existing = session.exec(
            select(User).where(User.email == user_create.email)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已注册",
            )

        # 创建用户
        user = User(
            email=user_create.email,
            hashed_password=get_password_hash(user_create.password),
            full_name=user_create.full_name,
        )

    session.add(user)
    session.commit()
    session.refresh(user)

    # 生成 Token
    access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _build_user_info(user),
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    http_request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """
    邮箱密码登录（OAuth2 兼容）

    使用 OAuth2PasswordRequestForm，username 字段传入 email

    流程（与 /login/password 对齐）：
    1. 风控检查（防爆破）
    2. 查找用户并验证密码
    3. 2FA 检查
    4. 签发双 Token（AT + RT）
    5. 设置 httpOnly Cookie
    """
    # form_data.username 当作 email 使用
    email = form_data.username

    # 风控检查：用 email 作为风控键
    safe, reason = check_login_risk(email)
    if not safe:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
        )

    # 查找用户
    user = session.exec(select(User).where(User.email == email)).first()

    if not user or not user.hashed_password:
        record_login_failure(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    # 验证密码
    if not verify_password(form_data.password, user.hashed_password):
        record_login_failure(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    # 登录成功，清除失败记录
    clear_login_failure(email)

    # 2FA 检查：如果用户已启用 2FA，不下发正式 Token，返回 MFA 挑战
    if user.is_2fa_enabled:
        mfa_token = create_mfa_token(user_id=user.id)
        return LoginResponse(
            access_token="",
            user=_build_user_info(user),
            status="requires_2fa",
            mfa_token=mfa_token,
        )

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
        user=_build_user_info(user),
    )


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户信息

    返回用户基础信息，包含阶段1新增的安全字段
    """
    return _build_user_info(current_user)


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

    流程：人机验证 → 风控检查 → 生成 OTP → Redis 存储 → 异步发送 SMS

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

    # [安全防线 L0] Cloudflare Turnstile 人机验证
    if request.captcha_token:
        if not await verify_turnstile_token(request.captcha_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

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

    # 2FA 检查：如果用户已启用 2FA，不下发正式 Token，返回 MFA 挑战
    if user.is_2fa_enabled:
        mfa_token = create_mfa_token(user_id=user.id)
        return LoginResponse(
            access_token="",
            user=_build_user_info(user),
            status="requires_2fa",
            mfa_token=mfa_token,
        )

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
        user=_build_user_info(user),
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

    # 2FA 检查：如果用户已启用 2FA，不下发正式 Token，返回 MFA 挑战
    if user.is_2fa_enabled:
        mfa_token = create_mfa_token(user_id=user.id)
        return LoginResponse(
            access_token="",
            user=_build_user_info(user),
            status="requires_2fa",
            mfa_token=mfa_token,
        )

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
        user=_build_user_info(user),
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


@router.get("/sessions", response_model=list[ActiveSessionOut])
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    列出当前用户的所有活跃会话（设备管理）

    通过比对当前请求的 refresh_token Cookie 哈希值，
    标记 is_current 字段以区分当前设备和其他设备。
    使用 ActiveSessionOut schema 确保响应结构类型安全。
    """
    now = datetime.now(timezone.utc)
    sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,  # noqa: E712
            ActiveSession.expires_at > now,
        ).order_by(ActiveSession.last_active_at.desc())
    ).all()

    # 从 Cookie 中提取 refresh_token，计算哈希以匹配当前会话
    current_rt_hash = None
    rt_cookie = request.cookies.get("refresh_token")
    if rt_cookie:
        current_rt_hash = hash_refresh_token(rt_cookie)

    return [
        ActiveSessionOut(
            session_id=s.session_id,
            user_agent=s.user_agent,
            ip_address=s.ip_address,
            device_type=s.device_type,
            created_at=s.created_at,
            last_active_at=s.last_active_at,
            is_revoked=s.is_revoked,
            is_current=(s.refresh_token_hash == current_rt_hash),
        )
        for s in sessions
    ]


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


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    http_request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    撤销除当前会话外的所有其他会话（一键下线其他设备）

    流程：
    1. 从 Cookie 中提取当前 refresh_token 的哈希值
    2. 撤销该用户所有非当前、非已撤销的 ActiveSession
    3. 返回撤销数量
    """
    # 从 Cookie 中识别当前会话
    current_rt_hash = None
    rt_cookie = http_request.cookies.get("refresh_token")
    if rt_cookie:
        current_rt_hash = hash_refresh_token(rt_cookie)

    # 查找所有活跃会话
    now = datetime.now(timezone.utc)
    active_sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,  # noqa: E712
            ActiveSession.expires_at > now,
        )
    ).all()

    revoked_count = 0
    for s in active_sessions:
        # 跳过当前会话（通过 RT 哈希匹配）
        if current_rt_hash and s.refresh_token_hash == current_rt_hash:
            continue
        s.is_revoked = True
        session.add(s)
        revoked_count += 1

    session.commit()

    return {"status": "success", "revoked_count": revoked_count, "message": f"已下线 {revoked_count} 台设备"}


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

    # 1. 从 Redis 取出 bind_token（bind_ref 是不透明引用键，防 URL 泄露）
    from app.services.cache_service import RedisCache
    cache = RedisCache()
    bind_token = cache.get(f"auth:bind_ref:{request.bind_ref}")
    if not bind_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="绑定凭证无效或已过期，请重新登录",
        )
    # 一次性使用：取出后立即删除引用键
    cache.delete(f"auth:bind_ref:{request.bind_ref}")

    # 2. 验证 bind_token
    bind_payload = verify_bind_token(bind_token)
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
        user=_build_user_info(user),
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

    # 仅对已注册号码发送真实短信（节省短信成本），未注册号码仅记录 OTP 但不发送
    otp = generate_otp(request.phone)
    record_sms_sent(request.phone, client_ip)

    if user:
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
# 会话内修改密码（工作流 F）
# ==========================================

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    已登录用户修改密码

    流程：
    1. 验证旧密码
    2. 密码强度验证
    3. 更新密码
    4. 撤销所有其他会话（保留当前会话，安全动作）
    """
    # 验证旧密码
    if not current_user.hashed_password or not verify_password(
        request.old_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )

    # 新旧密码不能相同
    if verify_password(request.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与当前密码相同",
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
    current_user.hashed_password = get_password_hash(request.new_password)
    current_user.last_password_change = datetime.now(timezone.utc)
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)

    # 【安全动作】撤销该用户所有 ActiveSession（密码已变，旧 Token 全部失效）
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

    return {"status": "success", "message": "密码修改成功，请重新登录"}


# ==========================================
# 修改手机号（工作流 H）
# ==========================================

@router.post("/change-phone")
async def change_phone(
    request: ChangePhoneRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    已登录用户修改手机号

    流程：
    1. 验证当前密码（本人校验）
    2. 验证新手机号的 SMS OTP
    3. 检查新手机号是否已被其他用户使用
    4. 更新手机号
    """
    # 本人校验：验证当前密码
    if not current_user.hashed_password or not verify_password(
        request.current_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )

    # 验证新手机号的 SMS OTP
    valid, reason = verify_otp(request.new_phone, request.otp_code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason,
        )

    # 检查新手机号是否已被其他用户使用
    existing = session.exec(
        select(User).where(User.phone_number == request.new_phone)
    ).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该手机号已被其他用户使用",
        )

    # 更新手机号
    current_user.phone_number = request.new_phone
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()

    return {"status": "success", "message": "手机号修改成功"}


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

    # 防止竞态：检查邮箱是否已被其他用户占用（从 bind-email 到 verify-email 之间有 15 分钟窗口）
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing and existing.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被其他用户使用，请重新绑定",
        )

    # 更新邮箱和验证状态
    user.email = email
    user.is_email_verified = True
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    return {"status": "success", "message": "邮箱绑定成功"}


# ==========================================
# 2FA / TOTP 双因素认证（工作流 C 步骤5）
# ==========================================

@router.post("/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    生成 TOTP 密钥（2FA 设置第一步）

    流程：
    1. 生成随机 TOTP 密钥
    2. 暂存到 Redis（5分钟TTL，防止用户放弃设置导致脏数据）
    3. 返回密钥和 QR 码 URI，前端渲染 QR 码供用户扫描
    """
    if current_user.is_2fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 已启用，如需重新设置请先禁用",
        )

    import pyotp
    from app.services.cache_service import RedisCache

    # 生成随机 TOTP 密钥
    secret = pyotp.random_base32()

    # 构建 QR 码 URI（Authenticator App 扫码识别）
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(
        name=current_user.email or str(current_user.id),
        issuer_name="Autonome Studio",
    )

    # 暂存到 Redis，5 分钟 TTL（不直接写入数据库，防止用户放弃设置导致脏数据）
    cache = RedisCache()
    cache.set(f"2fa:setup:{current_user.id}", secret, ttl=300)

    return TwoFASetupResponse(secret=secret, qr_uri=qr_uri)


@router.post("/2fa/verify")
async def verify_and_enable_2fa(
    request: TwoFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    验证并启用 2FA（2FA 设置第二步）

    流程：
    1. 从 Redis 取出暂存的 TOTP 密钥
    2. 验证用户输入的 6 位 TOTP 码
    3. 验证通过：写入数据库，启用 2FA
    4. 生成备用恢复码（10 个随机 8 位码）
    """
    import pyotp
    from app.services.cache_service import RedisCache

    # 从 Redis 取出暂存密钥
    cache = RedisCache()
    stored_secret = cache.get(f"2fa:setup:{current_user.id}")
    if not stored_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设置凭证已过期，请重新获取",
        )

    # 校验密钥一致性（防止用户篡改）
    if stored_secret != request.secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密钥不匹配，请重新获取",
        )

    # 验证 TOTP 码
    totp = pyotp.TOTP(request.secret)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误，请重试",
        )

    # 验证通过：写入数据库，启用 2FA
    current_user.two_factor_secret = request.secret
    current_user.is_2fa_enabled = True
    session.add(current_user)
    session.commit()

    # 删除 Redis 暂存密钥
    cache.delete(f"2fa:setup:{current_user.id}")

    # 生成备用恢复码（10 个随机 8 位码，用户应保存）
    import secrets as _secrets
    recovery_codes = [_secrets.token_hex(4).upper() for _ in range(10)]

    # 将恢复码哈希存入 Redis（用于后续验证）
    from app.core.security import get_password_hash
    hashed_codes = [get_password_hash(code) for code in recovery_codes]
    # 存储为 JSON 列表，TTL 无限期（直到用户重新生成或禁用 2FA）
    import json
    cache.set(f"2fa:recovery:{current_user.id}", json.dumps(hashed_codes), ttl=86400 * 365)

    return {
        "status": "success",
        "message": "2FA 已启用",
        "recovery_codes": recovery_codes,
    }


@router.post("/2fa/disable")
async def disable_2fa(
    request: TwoFADisableRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    禁用 2FA

    安全要求：必须验证当前 TOTP 码，防止他人未经授权禁用
    """
    import pyotp

    if not current_user.is_2fa_enabled or not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用",
        )

    # 验证 TOTP 码
    totp = pyotp.TOTP(current_user.two_factor_secret)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误，无法禁用 2FA",
        )

    # 禁用 2FA
    current_user.is_2fa_enabled = False
    current_user.two_factor_secret = None
    session.add(current_user)
    session.commit()

    # 清除恢复码
    from app.services.cache_service import RedisCache
    cache = RedisCache()
    cache.delete(f"2fa:recovery:{current_user.id}")

    return {"status": "success", "message": "2FA 已禁用"}


@router.post("/2fa/login", response_model=LoginResponse)
async def login_with_2fa(
    request: TwoFALoginRequest,
    http_request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    2FA 登录验证

    流程：
    1. 验证 MFA Token（5 分钟临时凭证）
    2. 查找用户并验证 TOTP 码
    3. 验证通过：签发正式双 Token
    """
    import pyotp

    # 验证 MFA Token
    mfa_payload = verify_mfa_token(request.mfa_token)
    if not mfa_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA 凭证无效或已过期，请重新登录",
        )

    user_id = int(mfa_payload["sub"])
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    if not user.is_2fa_enabled or not user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户未启用 2FA",
        )

    # 验证 TOTP 码
    totp = pyotp.TOTP(user.two_factor_secret)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    # 验证通过：签发正式双 Token
    access_token, refresh_token_val = _issue_tokens(
        user_id=user.id,
        http_request=http_request,
        session=session,
    )
    set_auth_cookies(response, access_token, refresh_token_val)

    return LoginResponse(
        access_token=access_token,
        user=_build_user_info(user),
    )


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
