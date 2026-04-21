"""
认证风控服务模块

设计日期: 2026-04-21
更新日期: 2026-04-21（阶段2：SMS/登录风控）

功能：
- SMS 发送频率限制（60秒冷却、每日10条/手机、每小时5条/IP）
- OTP 验证（生成、存储、常量时间比对、3次错误销毁）
- 登录暴力破解防护（5次失败锁定30分钟）
- Redis 存储所有风控数据，自动过期
"""

import hmac
import random

from app.services.cache_service import RedisCache


# ==========================================
# Redis Key 命名规范
# ==========================================

# SMS 验证码：auth:sms:code:{phone} → OTP 明文（5分钟 TTL）
# SMS 错误计数：auth:sms:err:{phone} → 错误次数（5分钟 TTL）
# SMS 冷却锁：risk:sms:lock:{phone} → "1"（60秒 TTL）
# SMS 每日计数：risk:sms:daily:{phone} → 当日发送次数（当日结束过期）
# SMS IP 计数：risk:sms:ip:{ip} → 该 IP 当小时发送次数（1小时 TTL）
# 登录失败计数：risk:login:fail:{phone} → 失败次数（30分钟 TTL）
# 登录锁定：risk:login:lock:{phone} → "1"（30分钟 TTL）


# ==========================================
# SMS 风控
# ==========================================

def check_sms_rate_limit(phone: str, ip: str) -> tuple[bool, str]:
    """
    检查 SMS 发送频率限制

    Returns:
        (allowed, reason): allowed=True 表示通过，reason 为拒绝原因
    """
    cache = RedisCache()

    # 1. 60秒冷却锁
    lock_key = f"risk:sms:lock:{phone}"
    if cache.get(lock_key):
        return False, "发送过于频繁，请60秒后重试"

    # 2. 每日限制（10条/手机/天）
    daily_key = f"risk:sms:daily:{phone}"
    daily_count = cache.get(daily_key)
    if daily_count and int(daily_count) >= 10:
        return False, "今日验证码发送次数已达上限"

    # 3. IP 限制（5条/IP/小时）
    ip_key = f"risk:sms:ip:{ip}"
    ip_count = cache.get(ip_key)
    if ip_count and int(ip_count) >= 5:
        return False, "该IP发送次数过多，请稍后重试"

    return True, ""


def record_sms_sent(phone: str, ip: str) -> None:
    """
    记录 SMS 发送成功，更新计数器
    """
    cache = RedisCache()

    # 设置60秒冷却锁
    cache.set(f"risk:sms:lock:{phone}", "1", ttl=60)

    # 递增每日计数（TTL 到当日结束）
    daily_key = f"risk:sms:daily:{phone}"
    current = cache.get(daily_key)
    if current:
        cache.set(daily_key, str(int(current) + 1), ttl=86400)
    else:
        cache.set(daily_key, "1", ttl=86400)

    # 递增 IP 计数
    ip_key = f"risk:sms:ip:{ip}"
    ip_current = cache.get(ip_key)
    if ip_current:
        cache.set(ip_key, str(int(ip_current) + 1), ttl=3600)
    else:
        cache.set(ip_key, "1", ttl=3600)


def release_sms_lock(phone: str) -> None:
    """
    释放 SMS 冷却锁（发送失败时调用，允许重试）
    """
    cache = RedisCache()
    cache.delete(f"risk:sms:lock:{phone}")


# ==========================================
# OTP 验证
# ==========================================

def generate_otp(phone: str) -> str:
    """
    生成 6 位 OTP 并存入 Redis（5分钟有效）

    Args:
        phone: 手机号（用于构建 Redis key）

    Returns:
        明文 OTP（用于发送给用户）
    """
    code = f"{random.randint(0, 999999):06d}"
    cache = RedisCache()
    # 存储 OTP，5分钟有效
    cache.set(f"auth:sms:code:{phone}", code, ttl=300)
    # 重置错误计数
    cache.delete(f"auth:sms:err:{phone}")
    return code


def verify_otp(phone: str, input_code: str) -> tuple[bool, str]:
    """
    验证 OTP（常量时间比对，3次错误销毁）

    Args:
        phone: 手机号
        input_code: 用户输入的验证码

    Returns:
        (valid, reason): valid=True 表示验证通过
    """
    cache = RedisCache()

    code_key = f"auth:sms:code:{phone}"
    err_key = f"auth:sms:err:{phone}"

    stored_code = cache.get(code_key)
    if not stored_code:
        return False, "验证码已过期，请重新发送"

    # 常量时间比对，防时序攻击
    if hmac.compare_digest(stored_code, input_code):
        # 验证成功，删除 OTP 和错误计数
        cache.delete(code_key)
        cache.delete(err_key)
        return True, ""

    # 验证失败，递增错误计数
    err_count = cache.get(err_key)
    new_count = (int(err_count) + 1) if err_count else 1

    if new_count >= 3:
        # 3次错误，销毁 OTP
        cache.delete(code_key)
        cache.delete(err_key)
        return False, "验证码错误次数过多，请重新发送"

    cache.set(err_key, str(new_count), ttl=300)
    return False, f"验证码错误，还剩{3 - new_count}次机会"


# ==========================================
# 登录暴力破解防护
# ==========================================

def check_login_risk(phone: str) -> tuple[bool, str]:
    """
    检查登录风险（账户是否被锁定）

    Returns:
        (safe, reason): safe=True 表示可以尝试登录
    """
    cache = RedisCache()

    lock_key = f"risk:login:lock:{phone}"
    if cache.get(lock_key):
        return False, "登录失败次数过多，账户已锁定30分钟"

    return True, ""


def record_login_failure(phone: str) -> None:
    """
    记录登录失败，5次失败后锁定30分钟
    """
    cache = RedisCache()

    fail_key = f"risk:login:fail:{phone}"
    current = cache.get(fail_key)
    new_count = (int(current) + 1) if current else 1

    if new_count >= 5:
        # 锁定30分钟
        cache.set(f"risk:login:lock:{phone}", "1", ttl=1800)
        cache.delete(fail_key)
    else:
        cache.set(fail_key, str(new_count), ttl=1800)


def clear_login_failure(phone: str) -> None:
    """
    登录成功后清除失败计数
    """
    cache = RedisCache()
    cache.delete(f"risk:login:fail:{phone}")
