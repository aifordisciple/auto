"""
UUID 生成函数模块

提供各种实体的唯一 ID 生成函数
"""

import uuid
from datetime import datetime, timezone


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    return datetime.now(timezone.utc)


def generate_project_id() -> str:
    """生成项目唯一 ID"""
    return f"proj_{uuid.uuid4().hex[:12]}"


def generate_session_id() -> str:
    """生成会话唯一 ID"""
    return f"chat_{uuid.uuid4().hex[:12]}"


def generate_msg_id() -> str:
    """生成消息唯一 ID"""
    return f"msg_{uuid.uuid4().hex[:16]}"


def generate_skill_id() -> str:
    """生成技能唯一 ID"""
    return f"skill_{uuid.uuid4().hex[:8]}"


def generate_share_token() -> str:
    """生成分享令牌"""
    return f"share_{uuid.uuid4().hex[:12]}"


def generate_experience_id() -> str:
    """生成经验资产唯一 ID"""
    return f"exp_{uuid.uuid4().hex[:8]}"


def generate_package_id() -> str:
    """生成用户包唯一 ID"""
    return f"pkg_{uuid.uuid4().hex[:8]}"


def generate_system_skill_id() -> str:
    """生成系统技能唯一 ID"""
    return f"sys_skill_{uuid.uuid4().hex[:8]}"