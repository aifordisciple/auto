"""
技能推荐模型

包含技能推荐日志和匹配反馈模型
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
# SKILL 推荐日志模型 (SkillRecommendationLog)
# ==========================================
class SkillRecommendationLog(SQLModel, table=True):
    """SKILL 推荐日志表 - 记录技能推荐与接受情况"""
    __tablename__ = "skillrecommendationlog"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id", description="用户 ID")
    session_id: str = Field(index=True, foreign_key="chatsession.id", description="聊天会话 ID")
    query: str = Field(description="用户原始查询")
    intent_type: str = Field(max_length=50, description="识别的意图类型")
    recommended_skills: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="推荐的技能 ID 列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    accepted_skill: Optional[str] = Field(default=None, description="用户最终选择的技能 ID")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# SKILL 匹配反馈模型 (SkillMatchingFeedback)
# ==========================================
class SkillMatchingFeedback(SQLModel, table=True):
    """
    SKILL 匹配反馈表 - 记录匹配结果反馈，用于持续优化推荐系统

    设计理念:
    - 记录每次匹配的详细信息（来源、置信度、推荐结果）
    - 追踪用户反馈（接受/拒绝、选择的技能）
    - 支持推荐效果分析和模型优化

    数据流:
    1. 技能匹配时创建记录
    2. 用户选择技能后更新 accepted 字段
    3. 定期分析反馈数据优化匹配策略
    """
    __tablename__ = "skillmatchingfeedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, description="用户 ID")
    session_id: str = Field(index=True, description="聊天会话 ID")

    # 匹配信息
    query: str = Field(description="用户原始查询")
    match_source: str = Field(
        max_length=20,
        description="匹配来源: rule(规则) | vector(向量) | llm(LLM) | hybrid(混合)"
    )
    recommended_skill_ids: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="推荐的技能 ID 列表"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="匹配置信度"
    )

    # 用户反馈
    accepted: bool = Field(default=False, description="用户是否接受推荐")
    accepted_skill_id: Optional[str] = Field(
        default=None,
        description="用户选择的技能 ID（如果接受）"
    )
    rejected_skills: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="用户明确拒绝的技能 ID 列表"
    )

    # 元数据
    match_details: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
        description="匹配详情（用于分析）"
    )
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)