"""
Cloudflare Turnstile 人机验证服务

设计日期: 2026-04-24

功能：
- 校验前端提交的 Turnstile captcha_token
- 未配置 TURNSTILE_SECRET_KEY 时自动跳过校验（开发环境友好）
- 使用 httpx 异步调用 Turnstile Siteverify API
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Turnstile Siteverify API 端点
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str, remote_ip: str | None = None) -> bool:
    """
    校验 Turnstile captcha_token 的有效性

    Args:
        token: 前端 Turnstile Widget 返回的 captcha_token
        remote_ip: 可选，客户端 IP（Turnstile 可用于额外校验）

    Returns:
        bool: True 表示验证通过，False 表示失败

    降级策略：
        - TURNSTILE_SECRET_KEY 为空时，跳过校验直接返回 True
        - 网络异常时记录日志并返回 False（安全优先：宁可阻止也不放行）
    """
    # 未配置密钥，跳过校验（开发环境）
    if not settings.TURNSTILE_SECRET_KEY:
        logger.debug("[Turnstile] SECRET_KEY 未配置，跳过人机验证")
        return True

    if not token:
        logger.warning("[Turnstile] captcha_token 为空，拒绝请求")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
            }
            # 可选：传入 remote_ip 增强校验
            if remote_ip:
                payload["remoteip"] = remote_ip

            resp = await client.post(TURNSTILE_VERIFY_URL, data=payload)
            result = resp.json()

            if result.get("success"):
                logger.info("[Turnstile] 人机验证通过")
                return True
            else:
                error_codes = result.get("error-codes", [])
                logger.warning(f"[Turnstile] 人机验证失败: {error_codes}")
                return False

    except httpx.HTTPError as e:
        logger.error(f"[Turnstile] 网络请求异常: {e}")
        return False
    except Exception as e:
        logger.error(f"[Turnstile] 未知异常: {e}")
        return False
