"""
用户偏好模型

定义用户偏好画像相关数据结构：
1. ExpertiseLevel - 用户专家水平枚举
2. FrequentSkill - 常用技能记录
3. CategoryPreference - 分类偏好权重
4. ParameterPattern - 参数使用模式
5. UserPreferenceProfile - 用户偏好画像

设计原则：
- 学习维度：常用技能、偏好分类、参数模式、活跃时段、专家水平
- 更新频率：每日自动更新
- 用途：个性化推荐、参数推断、用户体验优化
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 用户专家水平枚举
# ==========================================

class ExpertiseLevel(str, Enum):
    """
    用户专家水平

    推断依据：
    - 执行次数和成功率
    - 参数自定义率
    - 使用的技能复杂度

    影响：
    - 推荐结果的复杂度
    - 参数推断的详细程度
    - 帮助提示的详细程度
    """
    BEGINNER = "beginner"        # 新手：执行 < 10 次，成功率 < 50%
    INTERMEDIATE = "intermediate"  # 中级：执行 10-50 次，成功率 50-80%
    ADVANCED = "advanced"        # 高级：执行 50-100 次，成功率 80-95%
    EXPERT = "expert"            # 专家：执行 > 100 次，成功率 > 95%


# ==========================================
# 常用技能模型
# ==========================================

class FrequentSkill(BaseModel):
    """
    常用技能记录

    记录用户最常使用的技能信息，用于：
    1. 快速推荐（Top Skills）
    2. 相似技能推荐
    3. 用户习惯分析
    """

    skill_id: str = Field(description="技能 ID")
    skill_name: str = Field(description="技能名称")
    execute_count: int = Field(default=0, ge=0, description="执行次数")
    success_count: int = Field(default=0, ge=0, description="成功次数")
    failure_count: int = Field(default=0, ge=0, description="失败次数")
    last_executed_at: Optional[datetime] = Field(default=None, description="最后执行时间")
    avg_execution_time: Optional[float] = Field(default=None, description="平均执行时间（秒）")

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.execute_count == 0:
            return 0.0
        return self.success_count / self.execute_count


# ==========================================
# 分类偏好模型
# ==========================================

class CategoryPreference(BaseModel):
    """
    分类偏好权重

    记录用户对不同技能分类的偏好程度，用于：
    1. 分类过滤和排序
    2. 个性化推荐权重
    3. 首页展示优化
    """

    category: str = Field(description="分类 ID")
    category_name: str = Field(description="分类名称")
    weight: float = Field(default=0.0, ge=0.0, le=1.0, description="偏好权重（0-1）")
    execute_count: int = Field(default=0, ge=0, description="该分类下技能执行次数")
    last_executed_at: Optional[datetime] = Field(default=None, description="最后执行时间")


# ==========================================
# 参数使用模式模型
# ==========================================

class ParameterPattern(BaseModel):
    """
    参数使用模式

    记录用户对特定参数的使用习惯，用于：
    1. 参数默认值推断
    2. 参数建议优化
    3. 减少用户输入
    """

    parameter_name: str = Field(description="参数名")
    parameter_type: str = Field(default="string", description="参数类型")
    common_values: List[Any] = Field(default_factory=list, description="常用值列表（按频率排序）")
    value_counts: Dict[str, int] = Field(default_factory=dict, description="值使用次数统计")
    default_value: Optional[Any] = Field(default=None, description="推断的默认值")
    custom_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="自定义率（非默认值使用率）")
    sample_count: int = Field(default=0, ge=0, description="样本数量")


# ==========================================
# 用户偏好画像模型
# ==========================================

class UserPreferenceProfile(BaseModel):
    """
    用户偏好画像模型

    综合描述用户的偏好特征，用于：
    1. 个性化技能推荐
    2. 智能参数推断
    3. 用户体验优化
    4. 技能复杂度适配

    数据来源：
    - BehaviorRecord 中的用户行为数据
    - SkillExecutionHistory 中的执行记录
    - 实时分析和定期批量计算
    """

    # 用户标识
    user_id: int = Field(description="用户 ID")

    # 常用技能（Top 10）
    frequent_skills: List[FrequentSkill] = Field(
        default_factory=list,
        description="常用技能列表（按执行次数排序，最多 10 个）"
    )

    # 分类偏好
    preferred_categories: List[CategoryPreference] = Field(
        default_factory=list,
        description="分类偏好列表（按权重排序）"
    )

    # 参数模式（按技能分组）
    parameter_patterns: Dict[str, Dict[str, ParameterPattern]] = Field(
        default_factory=dict,
        description="参数模式（skill_id -> {param_name -> ParameterPattern}）"
    )

    # 专家水平
    expertise_level: ExpertiseLevel = Field(
        default=ExpertiseLevel.BEGINNER,
        description="用户专家水平"
    )

    # 活跃时段
    active_hours: List[int] = Field(
        default_factory=list,
        description="活跃时段（小时 0-23，按活跃度排序）"
    )

    # 统计信息
    total_executions: int = Field(default=0, ge=0, description="总执行次数")
    total_successes: int = Field(default=0, ge=0, description="总成功次数")
    total_failures: int = Field(default=0, ge=0, description="总失败次数")
    avg_session_length: float = Field(default=0.0, ge=0.0, description="平均会话长度（分钟）")

    # 推荐偏好
    preferred_match_mode: str = Field(
        default="auto",
        description="偏好的匹配模式: fast | precise | auto"
    )

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now, description="创建时间")
    updated_at: datetime = Field(default_factory=get_utc_now, description="最后更新时间")

    # 版本号（用于乐观锁）
    version: int = Field(default=1, ge=1, description="版本号")

    @property
    def overall_success_rate(self) -> float:
        """计算总体成功率"""
        if self.total_executions == 0:
            return 0.0
        return self.total_successes / self.total_executions

    def get_top_skills(self, limit: int = 5) -> List[FrequentSkill]:
        """获取 Top N 常用技能"""
        return self.frequent_skills[:limit]

    def get_preferred_categories(self, limit: int = 5) -> List[CategoryPreference]:
        """获取 Top N 偏好分类"""
        return sorted(self.preferred_categories, key=lambda x: x.weight, reverse=True)[:limit]


# ==========================================
# 数据库持久化模型
# ==========================================

class UserPreferenceRecord(SQLModel, table=True):
    """
    用户偏好记录表

    持久化存储用户偏好画像
    """
    __tablename__ = "userpreferencerecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(unique=True, index=True, description="用户 ID")

    # 序列化的偏好数据
    frequent_skills_json: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="常用技能 JSON"
    )
    preferred_categories_json: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="分类偏好 JSON"
    )
    parameter_patterns_json: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="参数模式 JSON"
    )
    active_hours_json: Optional[List[int]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="活跃时段 JSON"
    )

    # 简单字段
    expertise_level: str = SQLField(default="beginner", description="专家水平")
    total_executions: int = SQLField(default=0, description="总执行次数")
    total_successes: int = SQLField(default=0, description="总成功次数")
    total_failures: int = SQLField(default=0, description="总失败次数")
    preferred_match_mode: str = SQLField(default="auto", description="偏好匹配模式")

    # 版本和时间戳
    version: int = SQLField(default=1, description="版本号")
    created_at: datetime = SQLField(default_factory=get_utc_now, description="创建时间")
    updated_at: datetime = SQLField(default_factory=get_utc_now, description="更新时间")

    def to_profile(self) -> UserPreferenceProfile:
        """转换为 UserPreferenceProfile"""
        return UserPreferenceProfile(
            user_id=self.user_id,
            frequent_skills=[
                FrequentSkill(**s) for s in (self.frequent_skills_json or {}).get("skills", [])
            ],
            preferred_categories=[
                CategoryPreference(**c) for c in (self.preferred_categories_json or {}).get("categories", [])
            ],
            parameter_patterns=self.parameter_patterns_json or {},
            active_hours=self.active_hours_json or [],
            expertise_level=ExpertiseLevel(self.expertise_level),
            total_executions=self.total_executions,
            total_successes=self.total_successes,
            total_failures=self.total_failures,
            preferred_match_mode=self.preferred_match_mode,
            created_at=self.created_at,
            updated_at=self.updated_at,
            version=self.version,
        )

    @classmethod
    def from_profile(cls, profile: UserPreferenceProfile) -> "UserPreferenceRecord":
        """从 UserPreferenceProfile 创建记录"""
        return cls(
            user_id=profile.user_id,
            frequent_skills_json={
                "skills": [s.model_dump() for s in profile.frequent_skills]
            },
            preferred_categories_json={
                "categories": [c.model_dump() for c in profile.preferred_categories]
            },
            parameter_patterns_json=profile.parameter_patterns,
            active_hours_json=profile.active_hours,
            expertise_level=profile.expertise_level.value,
            total_executions=profile.total_executions,
            total_successes=profile.total_successes,
            total_failures=profile.total_failures,
            preferred_match_mode=profile.preferred_match_mode,
            version=profile.version,
            updated_at=get_utc_now(),
        )


# ==========================================
# 导出
# ==========================================

__all__ = [
    "ExpertiseLevel",
    "FrequentSkill",
    "CategoryPreference",
    "ParameterPattern",
    "UserPreferenceProfile",
    "UserPreferenceRecord",
]