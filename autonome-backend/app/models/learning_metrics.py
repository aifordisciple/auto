"""
学习指标模型

定义智能学习系统的效果指标：
1. MetricType - 指标类型枚举
2. MetricDataPoint - 指标数据点
3. LearningMetric - 学习指标模型
4. MetricTrend - 指标趋势
5. LearningReport - 学习报告

设计原则：
- 多维度指标：推荐命中率、参数准确率、执行成功率等
- 趋势分析：短期/中期/长期趋势
- 改进率计算：量化系统成长
- 目标追踪：跟踪指标向目标前进的进度
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from enum import Enum
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 指标类型枚举
# ==========================================

class MetricType(str, Enum):
    """
    指标类型枚举

    定义系统智能成长的各项关键指标：
    - RECOMMENDATION_HIT_RATE: 推荐命中率（用户点击推荐的技能比例）
    - PARAMETER_ACCURACY: 参数推断准确率
    - EXECUTION_SUCCESS_RATE: 执行成功率
    - USER_SATISFACTION: 用户满意度（评分）
    - KNOWLEDGE_GROWTH: 知识库增长率
    - PERSONALIZATION_COVERAGE: 个性化覆盖率
    - FEEDBACK_QUALITY: 反馈质量
    """
    RECOMMENDATION_HIT_RATE = "recommendation_hit_rate"
    PARAMETER_ACCURACY = "parameter_accuracy"
    EXECUTION_SUCCESS_RATE = "execution_success_rate"
    USER_SATISFACTION = "user_satisfaction"
    KNOWLEDGE_GROWTH = "knowledge_growth"
    PERSONALIZATION_COVERAGE = "personalization_coverage"
    FEEDBACK_QUALITY = "feedback_quality"


# ==========================================
# 趋势方向枚举
# ==========================================

class TrendDirection(str, Enum):
    """趋势方向枚举"""
    UP = "up"          # 上升
    DOWN = "down"      # 下降
    STABLE = "stable"  # 稳定


# ==========================================
# 指标数据点
# ==========================================

class MetricDataPoint(BaseModel):
    """
    指标数据点

    单个时间点的指标值：
    - timestamp: 时间戳
    - value: 指标值（0-1）
    - sample_size: 样本量
    """
    timestamp: datetime = Field(description="时间戳")
    value: float = Field(ge=0.0, le=1.0, description="指标值")
    sample_size: int = Field(default=1, ge=1, description="样本量")


# ==========================================
# 学习指标模型
# ==========================================

class LearningMetric(BaseModel):
    """
    学习指标模型

    存储单个指标的完整信息：
    - 当前值和目标值
    - 改进率和趋势
    - 统计置信度

    用于：
    1. 仪表盘展示
    2. 趋势分析
    3. 目标追踪
    """
    metric_type: MetricType = Field(description="指标类型")
    current_value: float = Field(ge=0.0, le=1.0, description="当前值")
    previous_value: Optional[float] = Field(default=None, description="前一周期值")
    target_value: Optional[float] = Field(default=None, description="目标值")

    # 统计信息
    sample_count: int = Field(default=0, ge=0, description="样本数量")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")

    # 趋势
    trend: TrendDirection = Field(default=TrendDirection.STABLE, description="趋势方向")
    improvement_rate: float = Field(default=0.0, description="改进率")

    # 时间范围
    period_start: datetime = Field(description="周期开始时间")
    period_end: datetime = Field(description="周期结束时间")

    @property
    def progress_to_target(self) -> Optional[float]:
        """
        计算到目标的进度

        Returns:
            进度比例（0-1），无目标时返回 None
        """
        if self.target_value is None or self.previous_value is None:
            return None
        if self.target_value == self.previous_value:
            return 1.0
        progress = (self.current_value - self.previous_value) / (self.target_value - self.previous_value)
        return max(0.0, min(1.0, progress))

    @property
    def is_improving(self) -> bool:
        """是否在改进"""
        return self.trend == TrendDirection.UP

    def calculate_improvement_rate(self) -> float:
        """
        计算改进率

        Returns:
            改进率（相对于前一周期）
        """
        if self.previous_value is None or self.previous_value == 0:
            return 0.0
        return (self.current_value - self.previous_value) / self.previous_value

    def get_status(self) -> str:
        """
        获取指标状态

        Returns:
            状态描述
        """
        if self.current_value >= 0.85:
            return "excellent"
        elif self.current_value >= 0.70:
            return "good"
        elif self.current_value >= 0.50:
            return "fair"
        else:
            return "needs_improvement"


# ==========================================
# 指标趋势模型
# ==========================================

class MetricTrend(BaseModel):
    """
    指标趋势模型

    存储指标的历史趋势：
    - 数据点列表
    - 趋势方向和强度
    - 预测能力
    """
    metric_type: MetricType = Field(description="指标类型")
    data_points: List[MetricDataPoint] = Field(default_factory=list, description="数据点列表")
    trend_direction: TrendDirection = Field(default=TrendDirection.STABLE, description="趋势方向")
    trend_strength: float = Field(default=0.0, ge=0.0, le=1.0, description="趋势强度")

    @property
    def average_value(self) -> float:
        """计算平均值"""
        if not self.data_points:
            return 0.0
        return sum(dp.value for dp in self.data_points) / len(self.data_points)

    @property
    def latest_value(self) -> Optional[float]:
        """获取最新值"""
        if not self.data_points:
            return None
        return self.data_points[-1].value

    @property
    def earliest_value(self) -> Optional[float]:
        """获取最早值"""
        if not self.data_points:
            return None
        return self.data_points[0].value

    def predict_next_value(self) -> Optional[float]:
        """
        预测下一个值（简单线性预测）

        Returns:
            预测值
        """
        if len(self.data_points) < 2:
            return self.latest_value

        # 简单线性趋势
        values = [dp.value for dp in self.data_points]
        diff = values[-1] - values[-2]
        predicted = values[-1] + diff

        # 确保在合理范围内
        return max(0.0, min(1.0, predicted))

    def calculate_trend(self) -> TrendDirection:
        """
        计算趋势方向

        Returns:
            趋势方向
        """
        if len(self.data_points) < 2:
            return TrendDirection.STABLE

        earliest = self.earliest_value
        latest = self.latest_value

        if earliest is None or latest is None:
            return TrendDirection.STABLE

        diff = latest - earliest
        threshold = 0.05  # 5% 变化阈值

        if diff > threshold:
            return TrendDirection.UP
        elif diff < -threshold:
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE


# ==========================================
# 学习报告模型
# ==========================================

class LearningReport(BaseModel):
    """
    学习报告模型

    汇总一段时间内的学习效果：
    - 各项指标汇总
    - 总体评估
    - 关键发现和建议

    支持日报、周报、月报
    """
    report_id: str = Field(description="报告 ID")
    report_type: str = Field(description="报告类型: daily, weekly, monthly")
    generated_at: datetime = Field(default_factory=get_utc_now, description="生成时间")

    # 指标汇总
    metrics: List[LearningMetric] = Field(default_factory=list, description="指标列表")

    # 总体评估
    overall_score: float = Field(ge=0.0, le=1.0, description="总体得分")
    overall_trend: TrendDirection = Field(default=TrendDirection.STABLE, description="总体趋势")

    # 关键发现
    highlights: List[str] = Field(default_factory=list, description="关键发现")
    recommendations: List[str] = Field(default_factory=list, description="改进建议")

    # 时间范围
    period_start: datetime = Field(description="周期开始时间")
    period_end: datetime = Field(description="周期结束时间")

    @property
    def improving_metrics_count(self) -> int:
        """改进的指标数量"""
        return sum(1 for m in self.metrics if m.is_improving)

    @property
    def metrics_count(self) -> int:
        """指标总数"""
        return len(self.metrics)

    @property
    def improvement_percentage(self) -> float:
        """改进指标百分比"""
        if not self.metrics:
            return 0.0
        return self.improving_metrics_count / self.metrics_count

    def get_top_improvements(self, limit: int = 3) -> List[LearningMetric]:
        """获取改进最大的指标"""
        improving = [m for m in self.metrics if m.is_improving]
        return sorted(improving, key=lambda m: m.improvement_rate, reverse=True)[:limit]

    def get_needs_attention(self) -> List[LearningMetric]:
        """获取需要关注的指标（下降或低于目标）"""
        attention = []
        for m in self.metrics:
            if m.trend == TrendDirection.DOWN:
                attention.append(m)
            elif m.target_value and m.current_value < m.target_value * 0.8:
                attention.append(m)
        return attention


# ==========================================
# 数据库持久化模型
# ==========================================

class LearningMetricRecord(SQLModel, table=True):
    """
    学习指标记录表

    持久化存储指标数据点
    """
    __tablename__ = "learningmetricrecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    metric_type: str = SQLField(index=True, description="指标类型")
    value: float = SQLField(description="指标值")
    sample_size: int = SQLField(default=1, description="样本量")
    confidence: float = SQLField(default=0.5, description="置信度")

    # 时间
    timestamp: datetime = SQLField(default_factory=get_utc_now, index=True, description="时间戳")
    period_type: str = SQLField(default="hourly", description="周期类型: hourly, daily, weekly")

    # 元数据
    metadata_json: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="元数据"
    )


class LearningReportRecord(SQLModel, table=True):
    """
    学习报告记录表

    持久化存储学习报告
    """
    __tablename__ = "learningreportrecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    report_id: str = SQLField(unique=True, description="报告 ID")
    report_type: str = SQLField(description="报告类型")
    generated_at: datetime = SQLField(default_factory=get_utc_now, description="生成时间")

    # 指标数据
    metrics_json: Optional[List[Dict[str, Any]]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="指标数据"
    )

    # 评估
    overall_score: float = SQLField(description="总体得分")
    overall_trend: str = SQLField(description="总体趋势")

    # 发现和建议
    highlights_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="关键发现"
    )
    recommendations_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="改进建议"
    )

    # 时间范围
    period_start: datetime = SQLField(description="周期开始时间")
    period_end: datetime = SQLField(description="周期结束时间")


# ==========================================
# 导出
# ==========================================

__all__ = [
    "MetricType",
    "TrendDirection",
    "MetricDataPoint",
    "LearningMetric",
    "MetricTrend",
    "LearningReport",
    "LearningMetricRecord",
    "LearningReportRecord",
]