"""
反馈驱动权重模型

定义动态权重调整相关数据结构：
1. WeightFactorType - 权重因子类型枚举
2. WeightFactor - 权重因子模型
3. TimeDecayConfig - 时间衰减配置
4. FeedbackDrivenWeight - 反馈驱动权重模型
5. WeightAdjustmentRecord - 权重调整记录

设计原则：
- 多因子权重：成功率、点击率、用户偏好、时间衰减等
- 动态调整：基于实时反馈自动调整
- 时间衰减：近期反馈权重更高
- 边界约束：权重在合理范围内（0.1-2.0）
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
# 权重因子类型枚举
# ==========================================

class WeightFactorType(str, Enum):
    """
    权重因子类型枚举

    定义影响技能推荐权重的因子：
    - SUCCESS_RATE: 成功率因子（执行成功率）
    - CLICK_RATE: 点击率因子（用户点击比例）
    - USER_PREFERENCE: 用户偏好因子（个性化偏好）
    - TIME_DECAY: 时间衰减因子（近期优先）
    - CATEGORY_BOOST: 分类加成因子（分类热度）
    - FEEDBACK_SCORE: 反馈评分因子（用户评分）
    """
    SUCCESS_RATE = "success_rate"
    CLICK_RATE = "click_rate"
    USER_PREFERENCE = "user_preference"
    TIME_DECAY = "time_decay"
    CATEGORY_BOOST = "category_boost"
    FEEDBACK_SCORE = "feedback_score"


# ==========================================
# 权重因子模型
# ==========================================

class WeightFactor(BaseModel):
    """
    权重因子模型

    单个权重因子的值和配置：
    - factor_type: 因子类型
    - value: 因子值（通常 0.5-2.0）
    - weight: 因子权重（对最终结果的贡献比例）

    贡献计算：contribution = value × weight
    """
    factor_type: WeightFactorType = Field(description="因子类型")
    value: float = Field(ge=0.0, le=2.0, description="因子值")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="因子权重")
    last_updated: datetime = Field(default_factory=get_utc_now, description="最后更新时间")

    @property
    def contribution(self) -> float:
        """计算因子贡献值"""
        return self.value * self.weight


# ==========================================
# 时间衰减配置
# ==========================================

class TimeDecayConfig(BaseModel):
    """
    时间衰减配置

    控制权重随时间的衰减行为：
    - enabled: 是否启用时间衰减
    - half_life_days: 半衰期（衰减到一半所需天数）
    - min_factor: 最小衰减因子
    - max_factor: 最大衰减因子

    衰减公式：factor = 0.5^(days_ago / half_life_days)
    """
    enabled: bool = Field(default=True, description="是否启用时间衰减")
    half_life_days: float = Field(default=30.0, description="半衰期（天）")
    min_factor: float = Field(default=0.1, ge=0.0, le=1.0, description="最小衰减因子")
    max_factor: float = Field(default=1.0, ge=0.0, le=1.0, description="最大衰减因子")

    def calculate_decay(self, days_ago: float) -> float:
        """
        计算时间衰减因子

        Args:
            days_ago: 距今天数

        Returns:
            衰减因子值
        """
        if not self.enabled:
            return 1.0

        if days_ago <= 0:
            return self.max_factor

        # 指数衰减: factor = 0.5^(days_ago / half_life)
        decay = 0.5 ** (days_ago / self.half_life_days)
        return max(self.min_factor, min(self.max_factor, decay))


# ==========================================
# 反馈驱动权重模型
# ==========================================

class FeedbackDrivenWeight(BaseModel):
    """
    反馈驱动权重模型

    存储技能的动态权重配置：
    - 基础权重（来自技能元数据）
    - 动态因子（来自反馈数据）
    - 最终权重 = 基础权重 × 各因子贡献的乘积

    权重计算公式：
    final_weight = base_weight
                   × success_rate_factor
                   × click_rate_factor
                   × user_preference_factor
                   × time_decay_factor

    使用场景：
    1. 技能推荐排序
    2. 个性化权重调整
    3. 热门技能识别
    """
    skill_id: str = Field(description="技能 ID")
    skill_name: Optional[str] = Field(default=None, description="技能名称")
    category: Optional[str] = Field(default=None, description="分类")

    # 基础权重
    base_weight: float = Field(default=1.0, ge=0.0, le=2.0, description="基础权重")

    # 权重因子
    factors: List[WeightFactor] = Field(
        default_factory=list,
        description="权重因子列表"
    )

    # 统计数据
    total_clicks: int = Field(default=0, ge=0, description="总点击次数")
    total_executions: int = Field(default=0, ge=0, description="总执行次数")
    successful_executions: int = Field(default=0, ge=0, description="成功执行次数")
    failed_executions: int = Field(default=0, ge=0, description="失败执行次数")
    avg_rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="平均评分")

    # 时间衰减配置
    time_decay: TimeDecayConfig = Field(
        default_factory=TimeDecayConfig,
        description="时间衰减配置"
    )

    # 最后更新时间
    last_feedback_at: Optional[datetime] = Field(default=None, description="最后反馈时间")
    updated_at: datetime = Field(default_factory=get_utc_now, description="更新时间")

    @property
    def success_rate(self) -> float:
        """
        计算成功率

        Returns:
            成功率（0-1），无数据时返回 0.5
        """
        if self.total_executions == 0:
            return 0.5  # 无数据时默认中等
        return self.successful_executions / self.total_executions

    @property
    def click_rate(self) -> float:
        """
        计算点击率（相对于展示）

        假设展示次数 ≈ 点击次数 × 5

        Returns:
            点击率（0-1）
        """
        if self.total_clicks == 0:
            return 0.0
        # 假设每 5 次展示产生 1 次点击
        estimated_impressions = self.total_clicks * 5
        return min(1.0, self.total_clicks / estimated_impressions)

    @property
    def final_weight(self) -> float:
        """
        计算最终权重

        公式: final_weight = base_weight × Π(factor.contribution)

        Returns:
            最终权重值（0.1-2.0）
        """
        weight = self.base_weight

        for factor in self.factors:
            weight *= factor.contribution

        # 确保权重在合理范围内
        return max(0.1, min(2.0, weight))

    def get_factor(self, factor_type: WeightFactorType) -> Optional[WeightFactor]:
        """
        获取指定类型的因子

        Args:
            factor_type: 因子类型

        Returns:
            因子对象，不存在则返回 None
        """
        for factor in self.factors:
            if factor.factor_type == factor_type:
                return factor
        return None

    def update_factor(self, factor_type: WeightFactorType, value: float, weight: float = 1.0) -> None:
        """
        更新或创建因子

        Args:
            factor_type: 因子类型
            value: 因子值
            weight: 因子权重
        """
        existing = self.get_factor(factor_type)
        if existing:
            existing.value = value
            existing.weight = weight
            existing.last_updated = get_utc_now()
        else:
            self.factors.append(WeightFactor(
                factor_type=factor_type,
                value=value,
                weight=weight,
            ))
        self.updated_at = get_utc_now()

    def reset_factors(self) -> None:
        """重置所有因子（恢复默认权重）"""
        self.factors = []
        self.updated_at = get_utc_now()


# ==========================================
# 权重调整记录
# ==========================================

class WeightAdjustmentRecord(BaseModel):
    """
    权重调整记录

    记录每次权重调整的详细信息：
    - 调整前后权重
    - 调整原因
    - 触发因素
    - 置信度

    用于：
    1. 权重变化追溯
    2. 调整效果分析
    3. 异常检测
    """
    record_id: str = Field(description="记录 ID")
    skill_id: str = Field(description="技能 ID")

    # 调整前后的权重
    weight_before: float = Field(description="调整前权重")
    weight_after: float = Field(description="调整后权重")
    adjustment_delta: float = Field(description="调整幅度")

    # 调整原因
    reason: str = Field(description="调整原因")
    trigger: str = Field(description="触发因素: feedback, execution, rating, manual")

    # 相关数据
    data_points: int = Field(default=0, description="涉及数据点数量")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="调整置信度")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now, description="创建时间")


# ==========================================
# 数据库持久化模型
# ==========================================

class FeedbackWeightRecord(SQLModel, table=True):
    """
    反馈权重记录表

    持久化存储技能的权重配置
    """
    __tablename__ = "feedbackweightrecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    skill_id: str = SQLField(unique=True, index=True, description="技能 ID")
    skill_name: Optional[str] = SQLField(default=None, description="技能名称")
    category: Optional[str] = SQLField(default=None, index=True, description="分类")

    # 基础权重
    base_weight: float = SQLField(default=1.0, description="基础权重")

    # JSON 字段
    factors_json: Optional[List[Dict[str, Any]]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="权重因子列表"
    )

    # 统计数据
    total_clicks: int = SQLField(default=0, description="总点击次数")
    total_executions: int = SQLField(default=0, description="总执行次数")
    successful_executions: int = SQLField(default=0, description="成功执行次数")
    failed_executions: int = SQLField(default=0, description="失败执行次数")
    avg_rating: Optional[float] = SQLField(default=None, description="平均评分")

    # 时间衰减配置
    time_decay_enabled: bool = SQLField(default=True, description="启用时间衰减")
    time_decay_half_life: float = SQLField(default=30.0, description="半衰期")

    # 时间戳
    last_feedback_at: Optional[datetime] = SQLField(default=None, description="最后反馈时间")
    created_at: datetime = SQLField(default_factory=get_utc_now, description="创建时间")
    updated_at: datetime = SQLField(default_factory=get_utc_now, description="更新时间")

    def to_weight(self) -> FeedbackDrivenWeight:
        """转换为 FeedbackDrivenWeight"""
        factors = []
        if self.factors_json:
            for f in self.factors_json:
                factors.append(WeightFactor(
                    factor_type=WeightFactorType(f["factor_type"]),
                    value=f["value"],
                    weight=f.get("weight", 1.0),
                ))

        return FeedbackDrivenWeight(
            skill_id=self.skill_id,
            skill_name=self.skill_name,
            category=self.category,
            base_weight=self.base_weight,
            factors=factors,
            total_clicks=self.total_clicks,
            total_executions=self.total_executions,
            successful_executions=self.successful_executions,
            failed_executions=self.failed_executions,
            avg_rating=self.avg_rating,
            time_decay=TimeDecayConfig(
                enabled=self.time_decay_enabled,
                half_life_days=self.time_decay_half_life,
            ),
            last_feedback_at=self.last_feedback_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_weight(cls, weight: FeedbackDrivenWeight) -> "FeedbackWeightRecord":
        """从 FeedbackDrivenWeight 创建记录"""
        factors_json = [
            {
                "factor_type": f.factor_type.value,
                "value": f.value,
                "weight": f.weight,
            }
            for f in weight.factors
        ]

        return cls(
            skill_id=weight.skill_id,
            skill_name=weight.skill_name,
            category=weight.category,
            base_weight=weight.base_weight,
            factors_json=factors_json if factors_json else None,
            total_clicks=weight.total_clicks,
            total_executions=weight.total_executions,
            successful_executions=weight.successful_executions,
            failed_executions=weight.failed_executions,
            avg_rating=weight.avg_rating,
            time_decay_enabled=weight.time_decay.enabled,
            time_decay_half_life=weight.time_decay.half_life_days,
            last_feedback_at=weight.last_feedback_at,
            updated_at=get_utc_now(),
        )


# ==========================================
# 导出
# ==========================================

__all__ = [
    "WeightFactorType",
    "WeightFactor",
    "TimeDecayConfig",
    "FeedbackDrivenWeight",
    "WeightAdjustmentRecord",
    "FeedbackWeightRecord",
]