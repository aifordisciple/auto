"""
技能收藏模型

包含技能收藏模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# SKILL 收藏模型 (SkillFavorite)
# ==========================================
class SkillFavorite(SQLModel, table=True):
    """SKILL 收藏表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="收藏的技能 ID")
    user_id: int = Field(index=True, foreign_key="user.id")
    created_at: datetime = Field(default_factory=get_utc_now)

    class Config:
        # 联合唯一约束：同一用户不能重复收藏同一技能
        # 注：实际约束需要在数据库层面通过 migration 实现
        pass