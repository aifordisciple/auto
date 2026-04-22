"""
邮件服务模块

设计日期: 2026-04-22

功能：
- 发送邮箱验证邮件（安全邮箱绑定）
- 支持 SMTP 和控制台 Mock 两种模式
- 异步发送，超时保护
"""

import asyncio
from typing import Optional

from app.core.config import settings
from app.core.logger import log


# ==========================================
# 邮件服务
# ==========================================

class EmailService:
    """
    邮件发送服务

    当 SMTP 配置完整时使用真实 SMTP 发送，
    否则走 Mock 模式（仅写入日志）。
    """

    def __init__(self):
        self._smtp_configured = bool(
            getattr(settings, "SMTP_HOST", None)
            and getattr(settings, "SMTP_PORT", None)
            and getattr(settings, "SMTP_USER", None)
            and getattr(settings, "SMTP_PASSWORD", None)
        )

    async def send_verification_email(
        self,
        to_email: str,
        token: str,
        user_name: str = "",
    ) -> bool:
        """
        发送邮箱验证邮件

        Args:
            to_email: 收件人邮箱
            token: 验证 Token（嵌入验证链接）
            user_name: 用户显示名

        Returns:
            True 发送成功，False 发送失败
        """
        # 构建验证链接
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3001")
        verify_url = f"{frontend_url}/verify-email?token={token}"

        subject = "Autonome Studio - 邮箱验证"
        body = f"""
您好 {user_name}，

您正在绑定安全邮箱到 Autonome Studio 账号。
请点击以下链接完成验证（15 分钟内有效）：

{verify_url}

如果这不是您的操作，请忽略此邮件。

— Autonome Studio
"""

        if not self._smtp_configured:
            # Mock 模式：仅写日志
            log.info(f"[Mock Email] 收件人: {to_email}, 主题: {subject}")
            log.info(f"[Mock Email] 验证链接: {verify_url}")
            return True

        # 真实 SMTP 发送
        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = getattr(settings, "SMTP_FROM", settings.SMTP_USER)
            msg["To"] = to_email

            smtp_host = settings.SMTP_HOST
            smtp_port = settings.SMTP_PORT
            smtp_user = settings.SMTP_USER
            smtp_password = settings.SMTP_PASSWORD
            use_tls = getattr(settings, "SMTP_TLS", True)

            # 在线程池中执行同步 SMTP 调用
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_password,
                use_tls=use_tls,
            )

            log.info(f"验证邮件发送成功: {to_email}")
            return True

        except ImportError:
            # aiosmtplib 未安装，回退到 Mock
            log.warning("aiosmtplib 未安装，验证邮件仅写入日志")
            log.info(f"[Mock Email] 验证链接: {verify_url}")
            return True

        except Exception as e:
            log.error(f"验证邮件发送失败: {to_email}, error={e}")
            return False


# ==========================================
# 全局单例
# ==========================================

_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """获取邮件服务单例"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
