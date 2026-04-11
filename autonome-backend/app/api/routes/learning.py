"""
学习仪表盘 API 路由

提供学习效果监控接口：
1. GET /learning/metrics - 获取所有指标
2. GET /learning/metrics/{metric_type} - 获取单个指标
3. GET /learning/metrics/{metric_type}/trend - 获取指标趋势
4. GET /learning/report - 生成学习报告
5. GET /learning/alerts - 获取预警信息
6. GET /learning/overall - 获取总体得分
7. POST /learning/predict - 预测指标值

设计原则：
- 统一的响应格式
- 支持多种报告周期
- 预警阈值可配置
- 趋势分析可视化支持
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from enum import Enum

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 枚举定义
# ==========================================

class MetricType(str, Enum):
    """指标类型枚举"""
    RECOMMENDATION_HIT_RATE = "recommendation_hit_rate"
    PARAMETER_ACCURACY = "parameter_accuracy"
    EXECUTION_SUCCESS_RATE = "execution_success_rate"
    USER_SATISFACTION = "user_satisfaction"
    KNOWLEDGE_GROWTH = "knowledge_growth"
    PERSONALIZATION_COVERAGE = "personalization_coverage"
    FEEDBACK_QUALITY = "feedback_quality"


class TrendDirection(str, Enum):
    """趋势方向枚举"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


# ==========================================
# 响应模型
# ==========================================

class MetricResponse(BaseModel):
    """指标响应"""
    metric_type: str
    current_value: float
    previous_value: Optional[float] = None
    target_value: Optional[float] = None
    sample_count: int = 0
    confidence: float = 0.5
    trend: str
    improvement_rate: float = 0.0
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class AllMetricsResponse(BaseModel):
    """所有指标响应"""
    metrics: List[MetricResponse]
    overall_score: float
    overall_trend: str
    generated_at: str


class TrendResponse(BaseModel):
    """趋势响应"""
    metric_type: str
    data_points: List[Dict[str, Any]]
    trend_direction: str
    trend_strength: float
    average_value: Optional[float] = None


class ReportResponse(BaseModel):
    """报告响应"""
    report_id: str
    report_type: str
    generated_at: str
    metrics: List[MetricResponse]
    overall_score: float
    overall_trend: str
    highlights: List[str]
    recommendations: List[str]
    period_start: str
    period_end: str


class AlertResponse(BaseModel):
    """预警响应"""
    metric_type: str
    current_value: float
    threshold: float
    trend: str
    message: str


class AlertsResponse(BaseModel):
    """所有预警响应"""
    alerts: List[AlertResponse]
    has_alerts: bool
    checked_at: str


class OverallScoreResponse(BaseModel):
    """总体得分响应"""
    overall_score: float
    grade: str
    improving_count: int
    declining_count: int
    stable_count: int
    generated_at: str


class PredictResponse(BaseModel):
    """预测响应"""
    metric_type: str
    predicted_value: Optional[float]
    confidence: float
    predicted_at: str


# ==========================================
# 辅助函数
# ==========================================

def calculate_grade(score: float) -> str:
    """
    计算得分等级

    Args:
        score: 得分（0-1）

    Returns:
        等级字符串
    """
    if score >= 0.85:
        return "excellent"
    elif score >= 0.70:
        return "good"
    elif score >= 0.50:
        return "fair"
    else:
        return "needs_improvement"


# ==========================================
# 模拟数据生成器
# ==========================================

class MockMetricsGenerator:
    """模拟指标数据生成器"""

    # 模拟指标数据
    METRICS_DATA = {
        MetricType.RECOMMENDATION_HIT_RATE: {
            "current_value": 0.78,
            "previous_value": 0.72,
            "target_value": 0.85,
            "sample_count": 150,
            "confidence": 0.85,
        },
        MetricType.EXECUTION_SUCCESS_RATE: {
            "current_value": 0.88,
            "previous_value": 0.85,
            "target_value": 0.95,
            "sample_count": 200,
            "confidence": 0.90,
        },
        MetricType.PARAMETER_ACCURACY: {
            "current_value": 0.75,
            "previous_value": 0.70,
            "target_value": 0.85,
            "sample_count": 100,
            "confidence": 0.80,
        },
        MetricType.USER_SATISFACTION: {
            "current_value": 0.82,
            "previous_value": 0.80,
            "target_value": 0.90,
            "sample_count": 50,
            "confidence": 0.75,
        },
        MetricType.KNOWLEDGE_GROWTH: {
            "current_value": 0.65,
            "previous_value": 0.55,
            "target_value": 0.50,
            "sample_count": 30,
            "confidence": 0.85,
        },
        MetricType.PERSONALIZATION_COVERAGE: {
            "current_value": 0.70,
            "previous_value": 0.65,
            "target_value": 0.70,
            "sample_count": 40,
            "confidence": 0.80,
        },
    }

    @classmethod
    def generate_metric_response(
        cls,
        metric_type: MetricType,
        days: int = 7,
    ) -> MetricResponse:
        """生成单个指标响应"""
        data = cls.METRICS_DATA.get(metric_type, {
            "current_value": 0.5,
            "previous_value": 0.5,
            "target_value": 0.7,
            "sample_count": 10,
            "confidence": 0.5,
        })

        period_end = get_utc_now()
        period_start = period_end - timedelta(days=days)

        # 计算趋势
        current = data["current_value"]
        previous = data["previous_value"]
        diff = current - previous

        if diff > 0.05:
            trend = TrendDirection.UP
        elif diff < -0.05:
            trend = TrendDirection.DOWN
        else:
            trend = TrendDirection.STABLE

        # 计算改进率
        improvement_rate = 0.0
        if previous > 0:
            improvement_rate = (current - previous) / previous

        return MetricResponse(
            metric_type=metric_type.value,
            current_value=current,
            previous_value=previous,
            target_value=data["target_value"],
            sample_count=data["sample_count"],
            confidence=data["confidence"],
            trend=trend.value,
            improvement_rate=improvement_rate,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
        )

    @classmethod
    def generate_trend_response(
        cls,
        metric_type: MetricType,
        days: int = 30,
    ) -> TrendResponse:
        """生成指标趋势响应"""
        # 生成模拟数据点
        data_points = []
        now = get_utc_now()
        base_value = cls.METRICS_DATA.get(metric_type, {}).get("current_value", 0.5)

        # 模拟上升趋势
        for i in range(min(days, 10)):
            timestamp = now - timedelta(days=days - i * (days // 10))
            # 添加随机波动
            noise = (i % 3 - 1) * 0.02
            value = max(0, min(1, base_value - 0.1 + i * 0.02 + noise))
            data_points.append({
                "timestamp": timestamp.isoformat(),
                "value": value,
                "sample_size": 10 + i * 2,
            })

        # 计算平均值
        avg_value = sum(dp["value"] for dp in data_points) / len(data_points) if data_points else 0

        return TrendResponse(
            metric_type=metric_type.value,
            data_points=data_points,
            trend_direction=TrendDirection.UP.value,
            trend_strength=0.7,
            average_value=avg_value,
        )

    @classmethod
    def get_trend_direction(cls, metric_type: MetricType) -> TrendDirection:
        """获取指标趋势方向"""
        data = cls.METRICS_DATA.get(metric_type)
        if not data:
            return TrendDirection.STABLE

        diff = data["current_value"] - data["previous_value"]
        if diff > 0.05:
            return TrendDirection.UP
        elif diff < -0.05:
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE

    @classmethod
    def is_improving(cls, metric_type: MetricType) -> bool:
        """判断指标是否在改进"""
        return cls.get_trend_direction(metric_type) == TrendDirection.UP


# ==========================================
# 路由定义
# ==========================================

router = APIRouter(prefix="/learning", tags=["Learning"])


@router.get("/metrics", response_model=AllMetricsResponse)
async def get_all_metrics(
    days: int = Query(default=7, ge=1, le=365, description="统计天数"),
):
    """
    获取所有学习指标

    返回所有指标及其综合评估。
    """
    metrics = []
    improving_count = 0
    declining_count = 0
    stable_count = 0

    for metric_type in MetricType:
        if metric_type == MetricType.FEEDBACK_QUALITY:
            continue  # 暂不包含此类型

        metric = MockMetricsGenerator.generate_metric_response(metric_type, days)
        metrics.append(metric)

        if metric.trend == TrendDirection.UP.value:
            improving_count += 1
        elif metric.trend == TrendDirection.DOWN.value:
            declining_count += 1
        else:
            stable_count += 1

    # 计算总体得分（加权平均）
    weights = {
        MetricType.RECOMMENDATION_HIT_RATE.value: 0.25,
        MetricType.EXECUTION_SUCCESS_RATE.value: 0.25,
        MetricType.PARAMETER_ACCURACY.value: 0.15,
        MetricType.USER_SATISFACTION.value: 0.15,
        MetricType.KNOWLEDGE_GROWTH.value: 0.10,
        MetricType.PERSONALIZATION_COVERAGE.value: 0.10,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for m in metrics:
        w = weights.get(m.metric_type, 0.1)
        weighted_sum += m.current_value * w
        total_weight += w

    overall_score = weighted_sum / total_weight if total_weight > 0 else 0.5

    # 确定总体趋势
    if improving_count > declining_count:
        overall_trend = TrendDirection.UP.value
    elif declining_count > improving_count:
        overall_trend = TrendDirection.DOWN.value
    else:
        overall_trend = TrendDirection.STABLE.value

    return AllMetricsResponse(
        metrics=metrics,
        overall_score=overall_score,
        overall_trend=overall_trend,
        generated_at=get_utc_now().isoformat(),
    )


@router.get("/metrics/{metric_type}", response_model=MetricResponse)
async def get_metric(
    metric_type: str,
    days: int = Query(default=7, ge=1, le=365, description="统计天数"),
):
    """
    获取单个学习指标

    Args:
        metric_type: 指标类型
        days: 统计天数
    """
    try:
        m_type = MetricType(metric_type)
    except ValueError:
        # 返回默认指标
        m_type = MetricType.RECOMMENDATION_HIT_RATE

    return MockMetricsGenerator.generate_metric_response(m_type, days)


@router.get("/metrics/{metric_type}/trend", response_model=TrendResponse)
async def get_metric_trend(
    metric_type: str,
    days: int = Query(default=30, ge=1, le=365, description="趋势天数"),
):
    """
    获取指标趋势

    Args:
        metric_type: 指标类型
        days: 趋势天数
    """
    try:
        m_type = MetricType(metric_type)
    except ValueError:
        m_type = MetricType.RECOMMENDATION_HIT_RATE

    return MockMetricsGenerator.generate_trend_response(m_type, days)


@router.get("/report", response_model=ReportResponse)
async def generate_report(
    report_type: str = Query(default="weekly", description="报告类型: daily, weekly, monthly"),
):
    """
    生成学习报告

    Args:
        report_type: 报告类型
    """
    # 确定周期
    periods = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30,
    }
    days = periods.get(report_type, 7)

    period_end = get_utc_now()
    period_start = period_end - timedelta(days=days)

    # 生成所有指标
    metrics = []
    for metric_type in MetricType:
        if metric_type == MetricType.FEEDBACK_QUALITY:
            continue
        metric = MockMetricsGenerator.generate_metric_response(metric_type, days)
        metrics.append(metric)

    # 计算总体得分
    overall_score = sum(m.current_value for m in metrics) / len(metrics)

    # 确定总体趋势
    improving = sum(1 for m in metrics if m.trend == TrendDirection.UP.value)
    declining = sum(1 for m in metrics if m.trend == TrendDirection.DOWN.value)

    if improving > declining:
        overall_trend = TrendDirection.UP.value
    elif declining > improving:
        overall_trend = TrendDirection.DOWN.value
    else:
        overall_trend = TrendDirection.STABLE.value

    # 生成关键发现
    highlights = []
    for m in metrics:
        if m.improvement_rate > 0.1:
            type_names = {
                MetricType.RECOMMENDATION_HIT_RATE.value: "推荐命中率",
                MetricType.EXECUTION_SUCCESS_RATE.value: "执行成功率",
                MetricType.PARAMETER_ACCURACY.value: "参数准确率",
                MetricType.USER_SATISFACTION.value: "用户满意度",
                MetricType.KNOWLEDGE_GROWTH.value: "知识库增长",
                MetricType.PERSONALIZATION_COVERAGE.value: "个性化覆盖率",
            }
            name = type_names.get(m.metric_type, m.metric_type)
            highlights.append(f"{name}提升 {m.improvement_rate:.1%}")

    # 生成改进建议
    recommendations = []
    for m in metrics:
        if m.current_value < (m.target_value or 0.7):
            type_names = {
                MetricType.RECOMMENDATION_HIT_RATE.value: "推荐命中率",
                MetricType.EXECUTION_SUCCESS_RATE.value: "执行成功率",
                MetricType.PARAMETER_ACCURACY.value: "参数推断",
                MetricType.USER_SATISFACTION.value: "用户满意度",
                MetricType.KNOWLEDGE_GROWTH.value: "知识库",
                MetricType.PERSONALIZATION_COVERAGE.value: "个性化覆盖",
            }
            name = type_names.get(m.metric_type, m.metric_type)
            recommendations.append(f"建议优化{name}相关功能")

    return ReportResponse(
        report_id=f"report-{report_type}-{period_end.strftime('%Y%m%d%H%M%S')}",
        report_type=report_type,
        generated_at=get_utc_now().isoformat(),
        metrics=metrics,
        overall_score=overall_score,
        overall_trend=overall_trend,
        highlights=highlights[:5],
        recommendations=recommendations[:3],
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )


@router.get("/alerts", response_model=AlertsResponse)
async def check_alerts():
    """
    检查预警

    返回所有低于阈值的指标预警。
    """
    # 预警阈值
    thresholds = {
        MetricType.RECOMMENDATION_HIT_RATE.value: 0.50,
        MetricType.EXECUTION_SUCCESS_RATE.value: 0.60,
        MetricType.USER_SATISFACTION.value: 0.50,
    }

    alerts = []
    for metric_type in MetricType:
        if metric_type == MetricType.FEEDBACK_QUALITY:
            continue

        threshold = thresholds.get(metric_type.value)
        if threshold is None:
            continue

        metric = MockMetricsGenerator.generate_metric_response(metric_type)

        if metric.current_value < threshold:
            alerts.append(AlertResponse(
                metric_type=metric_type.value,
                current_value=metric.current_value,
                threshold=threshold,
                trend=metric.trend,
                message=f"{metric_type.value} 低于预警阈值 {threshold:.0%}",
            ))

    return AlertsResponse(
        alerts=alerts,
        has_alerts=len(alerts) > 0,
        checked_at=get_utc_now().isoformat(),
    )


@router.get("/overall", response_model=OverallScoreResponse)
async def get_overall_score():
    """
    获取总体得分

    返回系统整体学习效果评估。
    """
    metrics = []
    improving_count = 0
    declining_count = 0
    stable_count = 0

    for metric_type in MetricType:
        if metric_type == MetricType.FEEDBACK_QUALITY:
            continue

        metric = MockMetricsGenerator.generate_metric_response(metric_type)
        metrics.append(metric)

        if metric.trend == TrendDirection.UP.value:
            improving_count += 1
        elif metric.trend == TrendDirection.DOWN.value:
            declining_count += 1
        else:
            stable_count += 1

    # 计算总体得分
    overall_score = sum(m.current_value for m in metrics) / len(metrics)
    grade = calculate_grade(overall_score)

    return OverallScoreResponse(
        overall_score=overall_score,
        grade=grade,
        improving_count=improving_count,
        declining_count=declining_count,
        stable_count=stable_count,
        generated_at=get_utc_now().isoformat(),
    )


@router.post("/predict", response_model=PredictResponse)
async def predict_metric(
    metric_type: str,
    periods_ahead: int = Query(default=1, ge=1, le=10, description="预测周期数"),
):
    """
    预测指标值

    基于历史趋势预测未来指标值。
    """
    try:
        m_type = MetricType(metric_type)
    except ValueError:
        m_type = MetricType.RECOMMENDATION_HIT_RATE

    # 获取当前指标
    metric = MockMetricsGenerator.generate_metric_response(m_type)
    trend_response = MockMetricsGenerator.generate_trend_response(m_type)

    # 简单线性预测
    predicted_value = None
    confidence = 0.5

    if trend_response.data_points:
        values = [dp["value"] for dp in trend_response.data_points]
        if len(values) >= 2:
            diff = values[-1] - values[-2]
            predicted_value = max(0, min(1, metric.current_value + diff * periods_ahead))
            confidence = 0.7  # 有历史数据时置信度较高

    return PredictResponse(
        metric_type=m_type.value,
        predicted_value=predicted_value,
        confidence=confidence,
        predicted_at=get_utc_now().isoformat(),
    )


log.info("✅ 学习仪表盘 API 路由已加载")