"""
技能执行历史模型

包含技能执行历史记录模型
"""

from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# SKILL 执行历史模型 (SkillExecutionHistory)
# ==========================================
class SkillExecutionHistory(SQLModel, table=True):
    """SKILL 执行历史记录表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="执行的技能 ID")
    skill_name: Optional[str] = Field(default=None, description="技能名称快照")
    user_id: int = Field(index=True, foreign_key="user.id")
    project_id: str = Field(index=True, foreign_key="project.id")
    session_id: Optional[str] = Field(default=None, description="聊天会话 ID")
    parameters: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = Field(default="PENDING", index=True, description="执行状态: PENDING/SUCCESS/FAILURE")
    result_summary: Optional[str] = Field(default=None, description="结果摘要")
    execution_time: Optional[float] = Field(default=None, description="执行耗时（秒）")
    output_dir: Optional[str] = Field(default=None, description="输出目录路径")
    created_at: datetime = Field(default_factory=get_utc_now)