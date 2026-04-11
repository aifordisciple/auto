"""
技能版本模型

包含技能版本管理模型
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# SKILL 版本管理模型 (SkillVersion)
# ==========================================
class SkillVersion(SQLModel, table=True):
    """SKILL 版本历史表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="关联的技能 ID")
    version: str = Field(max_length=50, description="版本号")
    script_code: Optional[str] = Field(default=None, description="该版本的代码")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None)
    dependencies: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="依赖列表")
    created_at: datetime = Field(default_factory=get_utc_now)
    created_by: int = Field(foreign_key="user.id", index=True)
    change_log: Optional[str] = Field(default=None, description="版本变更说明")
    # 统计
    usage_count: int = Field(default=0, description="该版本使用次数")