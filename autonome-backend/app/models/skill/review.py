"""
技能评价模型

包含技能评价模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# SKILL 评价模型 (SkillReview)
# ==========================================
class SkillReview(SQLModel, table=True):
    """SKILL 评价表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="评价的技能 ID")
    user_id: int = Field(index=True, foreign_key="user.id")
    rating: int = Field(ge=1, le=5, description="评分 1-5 星")
    comment: Optional[str] = Field(default=None, description="评价内容")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)