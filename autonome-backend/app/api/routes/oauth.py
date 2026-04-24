"""
OAuth 第三方登录路由

阶段三：GitHub OAuth + 微信扫码登录
- GitHub 回调端点：code 换 token，自动注册/登录
- 微信扫码登录：获取扫码 URL + 回调处理
- OAuth 账号绑定/解绑管理
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session
from loguru import logger

from app.api.deps import get_current_user
from app.core.database import get_session
from app.core.config import settings
from app.core.security import (
    create_short_access_token,
    generate_refresh_token, hash_refresh_token, get_refresh_token_expires_at,
    set_auth_cookies,
    create_bind_token,
    encrypt_oauth_token,
    decrypt_oauth_token,
)
from app.models.user import User, OAuthAccount
from app.services.auth_risk_control import generate_otp

router = APIRouter(tags=["OAuth"])


# ──────────────────────────────────────────────
# GitHub OAuth
# ──────────────────────────────────────────────

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"
GITHUB_EMAIL_API = "https://api.github.com/user/emails"


def _get_github_client_id() -> str:
    """获取 GitHub Client ID，未配置时抛出异常"""
    if not settings.GITHUB_CLIENT_ID:
        raise ValueError("GitHub OAuth 未配置，请设置 GITHUB_CLIENT_ID 和 GITHUB_CLIENT_SECRET")
    return settings.GITHUB_CLIENT_ID


@router.get("/github/authorize-url")
async def github_authorize_url(request: Request):
    """
    生成 GitHub OAuth 授权跳转 URL

    前端直接跳转到此 URL，用户授权后 GitHub 回调到 /api/oauth/github/callback
    """
    _get_github_client_id()  # 校验配置

    # 生成 state 参数防止 CSRF 攻击
    state = generate_otp()
    callback_url = f"{settings.BASE_URL}/api/oauth/github/callback"

    authorize_url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={callback_url}"
        f"&scope=user:email"
        f"&state={state}"
    )

    return {"authorize_url": authorize_url, "state": state}


@router.get("/github/callback")
async def github_callback(
    code: str = Query(..., description="GitHub 授权码"),
    state: str = Query(None, description="CSRF 防护 state"),
    db: Session = Depends(get_session),
):
    """
    GitHub OAuth 回调端点

    流程：
    1. 用 code 换 access_token
    2. 获取 GitHub 用户信息（id, login, email）
    3. 查找已关联的 OAuthAccount
       - 已关联：签发 AT+RT，设置 Cookie，重定向到前端
       - 未关联：自动创建 User + OAuthAccount，签发 AT+RT，重定向到前端
    """
    import httpx

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return _oauth_error_redirect("GitHub OAuth 未配置")

    # ── 1. code 换 access_token ──
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                logger.warning("GitHub OAuth code 换 token 失败: {}", token_data)
                return _oauth_error_redirect("GitHub 授权失败")
    except Exception as e:
        logger.error("GitHub OAuth token 请求异常: {}", e)
        return _oauth_error_redirect("GitHub 授权异常")

    # ── 2. 获取 GitHub 用户信息 ──
    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                GITHUB_USER_API,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            gh_user = user_resp.json()
            github_id = str(gh_user.get("id", ""))
            github_login = gh_user.get("login", "")
            github_name = gh_user.get("name") or github_login
            github_avatar = gh_user.get("avatar_url", "")

            # GitHub 主邮箱可能为空，需要额外请求 email API
            github_email = gh_user.get("email")
            if not github_email:
                email_resp = await client.get(
                    GITHUB_EMAIL_API,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                emails = email_resp.json()
                # 优先取主邮箱且已验证的
                for e in emails:
                    if e.get("primary") and e.get("verified"):
                        github_email = e.get("email")
                        break
                # 退而求其次取第一个已验证的
                if not github_email:
                    for e in emails:
                        if e.get("verified"):
                            github_email = e.get("email")
                            break
    except Exception as e:
        logger.error("获取 GitHub 用户信息异常: {}", e)
        return _oauth_error_redirect("获取 GitHub 用户信息失败")

    if not github_id:
        return _oauth_error_redirect("GitHub 用户 ID 获取失败")

    # ── 3. 查找已关联的 OAuthAccount 或强制绑定手机号 ──
    oauth_account = db.query(OAuthAccount).filter(
        OAuthAccount.provider == "github",
        OAuthAccount.provider_account_id == github_id,
    ).first()

    if oauth_account:
        # 已关联 → 直接登录
        user = db.query(User).filter(User.id == oauth_account.user_id).first()
        if not user:
            logger.error("OAuthAccount 关联的用户不存在: user_id={}", oauth_account.user_id)
            return _oauth_error_redirect("关联用户不存在")
        # 更新 OAuth 账号信息（access_token 加密存储，防脱库泄露）
        oauth_account.access_token = encrypt_oauth_token(access_token)
        oauth_account.provider_name = github_name
        oauth_account.provider_avatar_url = github_avatar
        db.commit()
    else:
        # 未关联 → 尝试通过邮箱匹配已有用户
        user = None
        if github_email:
            user = db.query(User).filter(User.email == github_email).first()

        if user:
            # 邮箱匹配到已有用户 → 自动绑定 GitHub 账号
            logger.info("GitHub OAuth 邮箱匹配到已有用户: user_id={}", user.id)
            oauth_account = OAuthAccount(
                user_id=user.id,
                provider="github",
                provider_account_id=github_id,
                access_token=encrypt_oauth_token(access_token),
                provider_name=github_name,
                provider_avatar_url=github_avatar,
            )
            db.add(oauth_account)
            db.commit()
        else:
            # 【核心防御】未匹配到已有用户 → 不自动创建 User，下发 Bind_Token
            # 前端必须弹出"绑定手机号"模态框，用户完成手机验证后才创建正式账号
            logger.info("GitHub OAuth 未关联用户，下发 Bind_Token: github_id={}", github_id)
            bind_token = create_bind_token(
                provider="github",
                provider_account_id=github_id,
                email=github_email,
                name=github_name,
                avatar_url=github_avatar,
            )
            return _oauth_bind_redirect(bind_token, github_name)

    # ── 4. 签发 Token + 设置 Cookie + 重定向 ──
    return _issue_tokens_and_redirect(user, db, request)


# ──────────────────────────────────────────────
# 微信 OAuth（预留接口）
# ──────────────────────────────────────────────

WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WECHAT_USER_API = "https://api.weixin.qq.com/sns/userinfo"


@router.get("/wechat/qr-url")
async def wechat_qr_url():
    """
    获取微信扫码登录 URL

    前端展示二维码，用户扫码后微信回调到 /api/oauth/wechat/callback
    """
    if not settings.WECHAT_APP_ID:
        return {"error": "微信 OAuth 未配置", "qr_url": None}

    callback_url = f"{settings.BASE_URL}/api/oauth/wechat/callback"
    state = generate_otp()

    qr_url = (
        f"{WECHAT_AUTHORIZE_URL}"
        f"?appid={settings.WECHAT_APP_ID}"
        f"&redirect_uri={callback_url}"
        f"&response_type=code"
        f"&scope=snsapi_login"
        f"&state={state}"
        f"#wechat_redirect"
    )

    return {"qr_url": qr_url, "state": state}


@router.get("/wechat/callback")
async def wechat_callback(
    code: str = Query(..., description="微信授权码"),
    state: str = Query(None, description="CSRF 防护 state"),
    db: Session = Depends(get_session),
):
    """
    微信 OAuth 回调端点

    流程同 GitHub：code 换 token → 获取用户信息 → 关联/注册
    """
    import httpx

    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        return _oauth_error_redirect("微信 OAuth 未配置")

    # ── 1. code 换 access_token + openid ──
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.get(
                WECHAT_TOKEN_URL,
                params={
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            openid = token_data.get("openid")
            unionid = token_data.get("unionid")  # 开放平台 UnionID

            if not access_token or not openid:
                logger.warning("微信 OAuth code 换 token 失败: {}", token_data)
                return _oauth_error_redirect("微信授权失败")
    except Exception as e:
        logger.error("微信 OAuth token 请求异常: {}", e)
        return _oauth_error_redirect("微信授权异常")

    # ── 2. 获取微信用户信息 ──
    wechat_nickname = ""
    wechat_avatar = ""
    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                WECHAT_USER_API,
                params={
                    "access_token": access_token,
                    "openid": openid,
                },
            )
            wx_user = user_resp.json()
            wechat_nickname = wx_user.get("nickname", "")
            wechat_avatar = wx_user.get("headimgurl", "")
    except Exception as e:
        logger.error("获取微信用户信息异常: {}", e)
        # 微信用户信息获取失败不影响登录，用 openid 作为标识

    # ── 3. 查找已关联的 OAuthAccount 或强制绑定手机号 ──
    # 优先用 unionid（跨应用统一），退而求其次用 openid
    provider_account_id = unionid or openid

    oauth_account = db.query(OAuthAccount).filter(
        OAuthAccount.provider == "wechat",
        OAuthAccount.provider_account_id == provider_account_id,
    ).first()

    if oauth_account:
        user = db.query(User).filter(User.id == oauth_account.user_id).first()
        if not user:
            logger.error("微信 OAuthAccount 关联的用户不存在: user_id={}", oauth_account.user_id)
            return _oauth_error_redirect("关联用户不存在")
        # 更新 OAuth 账号信息（access_token 加密存储，防脱库泄露）
        oauth_account.access_token = encrypt_oauth_token(access_token)
        oauth_account.provider_name = wechat_nickname
        oauth_account.provider_avatar_url = wechat_avatar
        db.commit()
    else:
        # 【核心防御】微信不提供邮箱，无法自动匹配 → 直接下发 Bind_Token
        # 前端必须弹出"绑定手机号"模态框
        logger.info("微信 OAuth 未关联用户，下发 Bind_Token: provider_account_id={}", provider_account_id)
        bind_token = create_bind_token(
            provider="wechat",
            provider_account_id=provider_account_id,
            email=None,
            name=wechat_nickname,
            avatar_url=wechat_avatar,
        )
        return _oauth_bind_redirect(bind_token, wechat_nickname)

    return _issue_tokens_and_redirect(user, db, request)


# ──────────────────────────────────────────────
# OAuth 账号绑定/解绑
# ──────────────────────────────────────────────

@router.post("/bind")
async def bind_oauth_account(
    provider: str,
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    已登录用户绑定 OAuth 账号

    流程：前端跳转 OAuth 授权 → 回调获取 code → 调用此端点绑定
    """
    if provider not in ("github", "wechat"):
        return {"success": False, "message": "不支持的 OAuth 提供商"}

    # 获取 OAuth 用户信息
    oauth_info = await _fetch_oauth_user_info(provider, code)
    if not oauth_info:
        return {"success": False, "message": "OAuth 授权失败"}

    provider_account_id = oauth_info["provider_account_id"]

    # 检查此 OAuth 账号是否已被其他用户绑定
    existing = db.query(OAuthAccount).filter(
        OAuthAccount.provider == provider,
        OAuthAccount.provider_account_id == provider_account_id,
    ).first()

    if existing:
        if existing.user_id == current_user.id:
            return {"success": False, "message": "此 OAuth 账号已绑定到当前用户"}
        else:
            return {"success": False, "message": "此 OAuth 账号已被其他用户绑定"}

    # 检查当前用户是否已绑定同类型 OAuth
    same_provider = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == current_user.id,
        OAuthAccount.provider == provider,
    ).first()
    if same_provider:
        return {"success": False, "message": f"您已绑定 {provider} 账号，请先解绑再绑定新账号"}

    # 创建绑定
    oauth_account = OAuthAccount(
        user_id=current_user.id,
        provider=provider,
        provider_account_id=provider_account_id,
        access_token=encrypt_oauth_token(oauth_info.get("access_token", "")),
        provider_name=oauth_info.get("name", ""),
        provider_avatar_url=oauth_info.get("avatar_url", ""),
    )
    db.add(oauth_account)
    db.commit()

    logger.info("用户 {} 绑定 {} 账号: {}", current_user.id, provider, provider_account_id)
    return {"success": True, "message": f"{provider} 账号绑定成功"}


@router.post("/unbind")
async def unbind_oauth_account(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    已登录用户解绑 OAuth 账号

    安全规则：至少保留一种登录方式（密码或至少一个 OAuth），防止账号无法登录
    """
    oauth_account = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == current_user.id,
        OAuthAccount.provider == provider,
    ).first()

    if not oauth_account:
        return {"success": False, "message": f"未绑定 {provider} 账号"}

    # 检查解绑后是否还有登录方式
    remaining_oauth = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == current_user.id,
        OAuthAccount.provider != provider,
    ).count()

    has_password = bool(current_user.hashed_password)

    if not has_password and remaining_oauth == 0:
        return {"success": False, "message": "解绑后将无法登录，请先设置密码或绑定其他登录方式"}

    db.delete(oauth_account)
    db.commit()

    logger.info("用户 {} 解绑 {} 账号", current_user.id, provider)
    return {"success": True, "message": f"{provider} 账号解绑成功"}


@router.get("/accounts")
async def list_oauth_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """查询当前用户已绑定的 OAuth 账号列表"""
    accounts = db.query(OAuthAccount).filter(
        OAuthAccount.user_id == current_user.id,
    ).all()

    return {
        "accounts": [
            {
                "provider": acc.provider,
                "provider_name": acc.provider_name,
                "provider_avatar_url": acc.provider_avatar_url,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
            }
            for acc in accounts
        ]
    }


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _oauth_error_redirect(error: str):
    """OAuth 错误时重定向到前端 OAuth 回调中间页，携带错误信息"""
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    frontend_url = settings.FRONTEND_URL or "http://localhost:3001"
    params = urlencode({"oauth_error": error})
    return RedirectResponse(url=f"{frontend_url}/oauth/callback?{params}")


def _oauth_bind_redirect(bind_token: str, provider_name: str = ""):
    """
    OAuth 需要绑定手机号时，将 bind_token 存入 Redis 并重定向到前端

    安全设计：bind_token 不直接暴露在 URL 中（防浏览器历史/日志泄露），
    而是生成一个短随机引用键存入 Redis（10 分钟 TTL），前端仅接收引用键。
    绑定手机号时，前端发送引用键，后端从 Redis 取出真实 bind_token。
    """
    import secrets
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    from app.services.cache_service import RedisCache

    # 生成不透明的一次性引用键
    bind_ref = secrets.token_urlsafe(32)

    # 存入 Redis，10 分钟 TTL（与 bind_token 有效期一致）
    cache = RedisCache()
    cache.set(f"auth:bind_ref:{bind_ref}", bind_token, ttl=600)

    frontend_url = settings.FRONTEND_URL or "http://localhost:3001"
    params = urlencode({
        "requires_binding": "true",
        "bind_ref": bind_ref,
        "provider_name": provider_name,
    })
    return RedirectResponse(url=f"{frontend_url}/oauth/callback?{params}")


def _issue_tokens_and_redirect(user: User, db: Session, http_request: Request = None):
    """
    签发 Access Token + Refresh Token，设置 Cookie，重定向到前端

    复用 auth.py 中的 Token 签发逻辑（双 Token + ActiveSession 记录）
    """
    from fastapi.responses import RedirectResponse
    from app.models.user import ActiveSession

    # 签发短命 Access Token（15 分钟）— 与 auth.py _issue_tokens 保持一致
    access_token = create_short_access_token(data={"sub": str(user.id)})

    # 签发长命 Refresh Token（7 天）— 存储哈希而非明文
    refresh_token_val = generate_refresh_token()
    rt_hash = hash_refresh_token(refresh_token_val)
    expires_at = get_refresh_token_expires_at()

    # 提取设备信息（从 OAuth 回调请求中获取）
    user_agent = "oauth-login"
    ip_address = "oauth"
    device_type = "oauth"
    if http_request:
        user_agent = http_request.headers.get("User-Agent", "oauth-login")[:512]
        ip_address = http_request.client.host if http_request.client else "unknown"
        forwarded = http_request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        device_type = _detect_device_type(user_agent)

    # 创建活跃会话记录
    active_session = ActiveSession(
        user_id=user.id,
        refresh_token_hash=rt_hash,
        user_agent=user_agent,
        ip_address=ip_address,
        device_type=device_type,
        expires_at=expires_at,
    )
    db.add(active_session)
    db.commit()

    # 重定向到前端
    frontend_url = settings.FRONTEND_URL or "http://localhost:3001"
    response = RedirectResponse(url=f"{frontend_url}/oauth/callback?status=success")

    # 使用统一的 Cookie 设置函数（与 auth.py /login 保持一致）
    set_auth_cookies(response, access_token, refresh_token_val)

    return response


def _detect_device_type(user_agent: str) -> str:
    """从 User-Agent 检测设备类型"""
    ua = user_agent.lower()
    if any(k in ua for k in ["mobile", "android", "iphone", "ipad"]):
        return "mobile"
    elif "mac" in ua:
        return "mac"
    elif "windows" in ua:
        return "windows"
    elif "linux" in ua:
        return "linux"
    return "desktop"


async def _fetch_oauth_user_info(provider: str, code: str) -> dict | None:
    """
    用 OAuth code 获取第三方用户信息（用于绑定流程）

    返回: {"provider_account_id": str, "access_token": str, "name": str, "avatar_url": str}
    """
    import httpx

    if provider == "github":
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            return None
        try:
            async with httpx.AsyncClient() as client:
                # 换 token
                token_resp = await client.post(
                    GITHUB_TOKEN_URL,
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": settings.GITHUB_CLIENT_ID,
                        "client_secret": settings.GITHUB_CLIENT_SECRET,
                        "code": code,
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return None

                # 获取用户信息
                user_resp = await client.get(
                    GITHUB_USER_API,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                gh_user = user_resp.json()
                return {
                    "provider_account_id": str(gh_user.get("id", "")),
                    "access_token": access_token,
                    "name": gh_user.get("name") or gh_user.get("login", ""),
                    "avatar_url": gh_user.get("avatar_url", ""),
                }
        except Exception as e:
            logger.error("GitHub OAuth 绑定获取用户信息异常: {}", e)
            return None

    elif provider == "wechat":
        if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
            return None
        try:
            async with httpx.AsyncClient() as client:
                token_resp = await client.get(
                    WECHAT_TOKEN_URL,
                    params={
                        "appid": settings.WECHAT_APP_ID,
                        "secret": settings.WECHAT_APP_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                openid = token_data.get("openid")
                unionid = token_data.get("unionid")
                if not access_token:
                    return None

                user_resp = await client.get(
                    WECHAT_USER_API,
                    params={"access_token": access_token, "openid": openid},
                )
                wx_user = user_resp.json()
                return {
                    "provider_account_id": unionid or openid,
                    "access_token": access_token,
                    "name": wx_user.get("nickname", ""),
                    "avatar_url": wx_user.get("headimgurl", ""),
                }
        except Exception as e:
            logger.error("微信 OAuth 绑定获取用户信息异常: {}", e)
            return None

    return None
