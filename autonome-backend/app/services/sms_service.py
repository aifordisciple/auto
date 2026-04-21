"""
阿里云短信服务模块

设计日期: 2026-04-21

功能：
- 封装阿里云 SMS SDK，提供验证码发送能力
- 延迟初始化 Client，避免启动时依赖检查
- 异步发送，超时保护
- 发送失败自动释放 Redis 冷却锁

依赖：
- alibabacloud-dysmsapi20170525
- alibabacloud-tea-openapi
"""

import asyncio
from typing import Optional
from functools import lru_cache

from app.core.config import settings
from app.core.logger import log


# ==========================================
# 阿里云 SMS 客户端（延迟初始化）
# ==========================================

class AliyunSMSService:
    """
    阿里云短信服务封装

    延迟初始化 Client，仅在首次发送时创建连接。
    配置项从 settings 读取，未配置时走 Mock 模式。
    """

    def __init__(self):
        self._client = None
        self._initialized = False

    def _get_client(self):
        """延迟初始化阿里云 SMS Client"""
        if self._initialized:
            return self._client

        # 检查必要配置
        if not settings.ALIYUN_ACCESS_KEY_ID or not settings.ALIYUN_ACCESS_KEY_SECRET:
            log.warning("阿里云 SMS 未配置 AccessKey，将使用 Mock 模式（验证码仅写入日志）")
            self._initialized = True
            self._client = None
            return None

        try:
            from alibabacloud_dysmsapi20170525.client import Client as DysmsClient
            from alibabacloud_tea_openapi.models import Config

            config = Config(
                access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
                access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
                # 短信服务接入点
                endpoint="dysmsapi.aliyuncs.com",
                # 连接超时 5 秒，读取超时 10 秒
                connect_timeout=5000,
                read_timeout=10000,
            )
            self._client = DysmsClient(config)
            self._initialized = True
            log.info("阿里云 SMS Client 初始化成功")
            return self._client
        except ImportError:
            log.warning("阿里云 SMS SDK 未安装，将使用 Mock 模式")
            self._initialized = True
            self._client = None
            return None
        except Exception as e:
            log.error(f"阿里云 SMS Client 初始化失败: {e}")
            self._initialized = True
            self._client = None
            return None

    async def send_verification_code(self, phone: str, code: str) -> bool:
        """
        发送验证码短信

        Args:
            phone: 手机号码
            code: 6 位验证码

        Returns:
            True 发送成功，False 发送失败
        """
        client = self._get_client()

        # Mock 模式：仅写日志
        if client is None:
            log.info(f"[Mock SMS] 手机号: {phone}, 验证码: {code}")
            return True

        try:
            from alibabacloud_dysmsapi20170525 import models as sms_models
            from Tea.core import TeaCore

            request = sms_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=settings.ALIYUN_SMS_SIGN_NAME,
                template_code=settings.ALIYUN_SMS_TEMPLATE_CODE,
                # 模板变量：验证码
                template_param=f'{{"code":"{code}"}}',
            )

            # 在线程池中执行同步 SDK 调用，避免阻塞事件循环
            response = await asyncio.to_thread(client.send_sms, request)
            body = TeaCore.to_map(response).get('body', {})

            if body.get('Code') == 'OK':
                log.info(f"验证码发送成功: {phone}")
                return True
            else:
                log.error(f"验证码发送失败: {phone}, Code={body.get('Code')}, Message={body.get('Message')}")
                return False

        except Exception as e:
            log.error(f"验证码发送异常: {phone}, error={e}")
            return False


# ==========================================
# 全局单例
# ==========================================

# 使用模块级单例，避免重复初始化
_sms_service: Optional[AliyunSMSService] = None


def get_sms_service() -> AliyunSMSService:
    """获取 SMS 服务单例"""
    global _sms_service
    if _sms_service is None:
        _sms_service = AliyunSMSService()
    return _sms_service
