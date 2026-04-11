"""
结果分享模型

包含结果分享模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime

from app.models.uuid import generate_share_token


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 结果分享模型 (ResultShare)
# ==========================================
class ResultShare(SQLModel, table=True):
    """结果分享表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True, description="关联的任务 ID")
    share_token: str = Field(default_factory=generate_share_token, unique=True, index=True)
    created_by: int = Field(foreign_key="user.id", index=True)
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    access_count: int = Field(default=0, description="访问次数")
    created_at: datetime = Field(default_factory=get_utc_now)