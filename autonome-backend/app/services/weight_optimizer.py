"""
权重优化引擎服务

实现反馈驱动的动态权重调整：
1. 从行为反馈计算权重因子
2. 动态调整技能推荐权重
3. 时间衰减处理
4. 批量优化和历史追踪

设计原则：
- 多因子权重：成功率、点击率、评分、时间衰减
- 置信度调制：低置信度数据不轻易调整
- 渐进式调整：避免权重剧烈波动
- 可追溯性：记录所有权重变化
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from sqlmodel import Session, select

from app.core.logger import log
from app.models.feedback_weight import (
    WeightFactorType,
    WeightFactor,
    TimeDecayConfig,
    FeedbackDrivenWeight,
    WeightAdjustmentRecord,
    FeedbackWeightRecord,
)


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 权重优化配置
# ==========================================

class WeightOptimizerConfig:
    """权重优化引擎配置"""

    # 数据量阈值
    MIN_EXECUTIONS_FOR_ADJUSTMENT: int = 5  # 最少执行次数才调整
    MIN_CLICKS_FOR_ADJUSTMENT: int = 10  # 最少点击次数才调整
    MIN_RATINGS_FOR_ADJUSTMENT: int = 3  # 最少评分次数才调整

    # 置信度阈值
    MIN_CONFIDENCE_FOR_ADJUSTMENT: float = 0.3  # 最低调整置信度

    # 因子权重
    SUCCESS_RATE_WEIGHT: float = 0.4
    CLICK_RATE_WEIGHT: float = 0.15
    FEEDBACK_SCORE_WEIGHT: float = 0.25
    USER_PREFERENCE_WEIGHT: float = 0.1
    TIME_DECAY_WEIGHT: float = 0.1

    # 权重边界
    MIN_WEIGHT: float = 0.1
    MAX_WEIGHT: float = 2.0
    NEUTRAL_WEIGHT: float = 1.0

    # 调整限制
    MAX_ADJUSTMENT_PER_DAY: float = 0.3  # 每天最大调整幅度

    # 成功率阈值
    HIGH_SUCCESS_RATE_THRESHOLD: float = 0.9
    MEDIUM_SUCCESS_RATE_THRESHOLD: float = 0.7
    LOW_SUCCESS_RATE_THRESHOLD: float = 0.5

    # 评分阈值
    HIGH_RATING_THRESHOLD: float = 4.5
    MEDIUM_RATING_THRESHOLD: float = 4.0
    LOW_RATING_THRESHOLD: float = 3.0


# ==========================================
# 权重优化引擎
# ==========================================

class WeightOptimizer:
    """
    权重优化引擎

    负责从反馈数据计算和调整技能推荐权重：
    1. 计算成功率因子
    2. 计算点击率因子
    3. 计算评分因子
    4. 应用时间衰减
    5. 聚合各因子得到最终权重

    使用方式：
    ```python
    optimizer = WeightOptimizer(session)

    # 优化单个技能权重
    weight = optimizer.optimize_skill_weight("skill-deseq2")

    # 批量优化
    results = optimizer.batch_optimize()

    # 获取技能权重
    weight = optimizer.get_skill_weight("skill-deseq2")
    ```
    """

    def __init__(
        self,
        session: Session,
        config: Optional[WeightOptimizerConfig] = None,
    ):
        """
        初始化权重优化引擎

        Args:
            session: 数据库会话
            config: 配置参数（可选）
        """
        self.session = session
        self.config = config or WeightOptimizerConfig()

        # 权重缓存
        self._weight_cache: Dict[str, FeedbackDrivenWeight] = {}

        # 统计计数器
        self._stats = {
            "skills_optimized": 0,
            "adjustments_made": 0,
            "adjustments_skipped": 0,
        }

    # ==========================================
    # 核心优化方法
    # ==========================================

    def optimize_skill_weight(
        self,
        skill_id: str,
        stats: Optional[Dict[str, Any]] = None,
    ) -> FeedbackDrivenWeight:
        """
        优化单个技能的权重

        Args:
            skill_id: 技能 ID
            stats: 统计数据（可选，不提供则从数据库获取）

        Returns:
            优化后的权重配置
        """
        log.debug(f"[WeightOptimizer] 优化技能权重: {skill_id}")

        # 获取或加载权重配置
        weight = self._load_or_create_weight(skill_id)

        # 获取统计数据
        if stats is None:
            stats = self._get_skill_stats(skill_id)

        # 计算各因子
        self._calculate_success_rate_factor(weight, stats)
        self._calculate_click_rate_factor(weight, stats)
        self._calculate_feedback_score_factor(weight, stats)
        self._calculate_time_decay_factor(weight, stats)

        # 更新统计
        weight.total_clicks = stats.get("total_clicks", 0)
        weight.total_executions = stats.get("total_executions", 0)
        weight.successful_executions = stats.get("successful_executions", 0)
        weight.failed_executions = stats.get("failed_executions", 0)
        weight.avg_rating = stats.get("avg_rating")

        # 保存
        self._save_weight(weight)

        self._stats["skills_optimized"] += 1

        return weight

    def batch_optimize(
        self,
        skill_ids: Optional[List[str]] = None,
        min_executions: int = 5,
    ) -> List[FeedbackDrivenWeight]:
        """
        批量优化技能权重

        Args:
            skill_ids: 指定技能列表（可选）
            min_executions: 最少执行次数过滤

        Returns:
            优化后的权重列表
        """
        log.info(f"[WeightOptimizer] 开始批量优化: skills={len(skill_ids) if skill_ids else 'all'}")

        # 获取所有需要优化的技能
        if skill_ids is None:
            skill_ids = self._get_skills_with_feedback(min_executions)

        results = []
        for skill_id in skill_ids:
            try:
                weight = self.optimize_skill_weight(skill_id)
                results.append(weight)
            except Exception as e:
                log.error(f"[WeightOptimizer] 优化技能 {skill_id} 失败: {e}")

        log.info(f"[WeightOptimizer] 批量优化完成: {len(results)} 个技能")
        return results

    def get_skill_weight(self, skill_id: str) -> FeedbackDrivenWeight:
        """
        获取技能权重

        Args:
            skill_id: 技能 ID

        Returns:
            权重配置
        """
        return self._load_or_create_weight(skill_id)

    def apply_weight_to_skill(
        self,
        skill_id: str,
        recommendation_score: float,
    ) -> float:
        """
        将权重应用到推荐分数

        Args:
            skill_id: 技能 ID
            recommendation_score: 原始推荐分数

        Returns:
            调整后的推荐分数
        """
        weight = self.get_skill_weight(skill_id)
        final_score = recommendation_score * weight.final_weight

        # 确保分数在合理范围
        return max(0.0, min(1.0, final_score))

    # ==========================================
    # 因子计算方法
    # ==========================================

    def _calculate_success_rate_factor(
        self,
        weight: FeedbackDrivenWeight,
        stats: Dict[str, Any],
    ) -> None:
        """
        计算成功率因子

        Args:
            weight: 权重配置
            stats: 统计数据
        """
        total_executions = stats.get("total_executions", 0)
        successful_executions = stats.get("successful_executions", 0)

        if total_executions < self.config.MIN_EXECUTIONS_FOR_ADJUSTMENT:
            # 数据不足，使用中性因子
            factor_value = 1.0
        else:
            success_rate = successful_executions / total_executions

            if success_rate >= self.config.HIGH_SUCCESS_RATE_THRESHOLD:
                factor_value = 1.3  # 高加成
            elif success_rate >= self.config.MEDIUM_SUCCESS_RATE_THRESHOLD:
                factor_value = 1.15  # 中等加成
            elif success_rate >= self.config.LOW_SUCCESS_RATE_THRESHOLD:
                factor_value = 1.0  # 中性
            else:
                # 低成功率惩罚
                factor_value = max(0.5, 0.5 + success_rate)

        weight.update_factor(
            WeightFactorType.SUCCESS_RATE,
            factor_value,
            self.config.SUCCESS_RATE_WEIGHT,
        )

    def _calculate_click_rate_factor(
        self,
        weight: FeedbackDrivenWeight,
        stats: Dict[str, Any],
    ) -> None:
        """
        计算点击率因子

        Args:
            weight: 权重配置
            stats: 统计数据
        """
        total_clicks = stats.get("total_clicks", 0)

        if total_clicks < self.config.MIN_CLICKS_FOR_ADJUSTMENT:
            factor_value = 1.0
        else:
            # 假设展示次数为点击次数的 5 倍
            estimated_impressions = total_clicks * 5
            click_rate = total_clicks / estimated_impressions

            if click_rate > 0.5:
                factor_value = 1.2
            elif click_rate > 0.3:
                factor_value = 1.1
            elif click_rate > 0.15:
                factor_value = 1.0
            else:
                factor_value = 0.85

        weight.update_factor(
            WeightFactorType.CLICK_RATE,
            factor_value,
            self.config.CLICK_RATE_WEIGHT,
        )

    def _calculate_feedback_score_factor(
        self,
        weight: FeedbackDrivenWeight,
        stats: Dict[str, Any],
    ) -> None:
        """
        计算反馈评分因子

        Args:
            weight: 权重配置
            stats: 统计数据
        """
        avg_rating = stats.get("avg_rating")
        rating_count = stats.get("rating_count", 0)

        if avg_rating is None or rating_count < self.config.MIN_RATINGS_FOR_ADJUSTMENT:
            factor_value = 1.0
        else:
            if avg_rating >= self.config.HIGH_RATING_THRESHOLD:
                factor_value = 1.3
            elif avg_rating >= self.config.MEDIUM_RATING_THRESHOLD:
                factor_value = 1.1
            elif avg_rating >= self.config.LOW_RATING_THRESHOLD:
                factor_value = 1.0
            else:
                factor_value = max(0.5, avg_rating / 5.0)

        weight.update_factor(
            WeightFactorType.FEEDBACK_SCORE,
            factor_value,
            self.config.FEEDBACK_SCORE_WEIGHT,
        )

    def _calculate_time_decay_factor(
        self,
        weight: FeedbackDrivenWeight,
        stats: Dict[str, Any],
    ) -> None:
        """
        计算时间衰减因子

        Args:
            weight: 权重配置
            stats: 统计数据
        """
        last_feedback_at = stats.get("last_feedback_at")

        if last_feedback_at is None:
            factor_value = 1.0
        else:
            # 计算距今天数
            days_ago = (get_utc_now() - last_feedback_at).total_seconds() / 86400
            factor_value = weight.time_decay.calculate_decay(days_ago)

        weight.update_factor(
            WeightFactorType.TIME_DECAY,
            factor_value,
            self.config.TIME_DECAY_WEIGHT,
        )

    # ==========================================
    # 数据加载和保存
    # ==========================================

    def _load_or_create_weight(self, skill_id: str) -> FeedbackDrivenWeight:
        """加载或创建权重配置"""
        # 检查缓存
        if skill_id in self._weight_cache:
            return self._weight_cache[skill_id]

        # 查询数据库
        record = self.session.exec(
            select(FeedbackWeightRecord).where(
                FeedbackWeightRecord.skill_id == skill_id
            )
        ).first()

        if record:
            weight = record.to_weight()
        else:
            # 创建新配置
            weight = FeedbackDrivenWeight(skill_id=skill_id)

        self._weight_cache[skill_id] = weight
        return weight

    def _save_weight(self, weight: FeedbackDrivenWeight) -> None:
        """保存权重配置"""
        # 检查是否已存在
        existing = self.session.exec(
            select(FeedbackWeightRecord).where(
                FeedbackWeightRecord.skill_id == weight.skill_id
            )
        ).first()

        if existing:
            # 更新
            record = FeedbackWeightRecord.from_weight(weight)
            record.id = existing.id
            for key, value in record.model_dump(exclude={"id"}).items():
                setattr(existing, key, value)
            self.session.add(existing)
        else:
            # 创建
            record = FeedbackWeightRecord.from_weight(weight)
            self.session.add(record)

        self.session.commit()

        # 更新缓存
        self._weight_cache[weight.skill_id] = weight

    def _get_skill_stats(self, skill_id: str) -> Dict[str, Any]:
        """获取技能统计数据"""
        # 从 BehaviorRecord 聚合统计
        # 这里返回基础结构，实际实现需要查询行为数据
        return {
            "total_clicks": 0,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_rating": None,
            "rating_count": 0,
            "last_feedback_at": None,
        }

    def _get_skills_with_feedback(self, min_executions: int) -> List[str]:
        """获取有足够反馈数据的技能列表"""
        # 查询有足够执行记录的技能
        # 这里返回空列表，实际实现需要查询数据库
        return []

    # ==========================================
    # 权重调整记录
    # ==========================================

    def record_adjustment(
        self,
        skill_id: str,
        weight_before: float,
        weight_after: float,
        reason: str,
        trigger: str,
        data_points: int = 0,
        confidence: float = 0.5,
    ) -> WeightAdjustmentRecord:
        """
        记录权重调整

        Args:
            skill_id: 技能 ID
            weight_before: 调整前权重
            weight_after: 调整后权重
            reason: 调整原因
            trigger: 触发因素
            data_points: 涉及数据点数量
            confidence: 调整置信度

        Returns:
            调整记录
        """
        record_id = f"adj-{skill_id}-{get_utc_now().strftime('%Y%m%d%H%M%S')}"

        record = WeightAdjustmentRecord(
            record_id=record_id,
            skill_id=skill_id,
            weight_before=weight_before,
            weight_after=weight_after,
            adjustment_delta=weight_after - weight_before,
            reason=reason,
            trigger=trigger,
            data_points=data_points,
            confidence=confidence,
        )

        self._stats["adjustments_made"] += 1

        return record

    # ==========================================
    # 工具方法
    # ==========================================

    def calculate_confidence(
        self,
        data_points: int,
        success_rate: Optional[float] = None,
    ) -> float:
        """
        计算调整置信度

        Args:
            data_points: 数据点数量
            success_rate: 成功率

        Returns:
            置信度值（0-1）
        """
        # 基于数据量计算基础置信度
        if data_points < 5:
            base_confidence = 0.2
        elif data_points < 20:
            base_confidence = 0.5
        elif data_points < 100:
            base_confidence = 0.7
        else:
            base_confidence = 0.9

        # 成功率稳定性加成
        if success_rate is not None:
            # 成功率接近 0.5 时不确定性高
            stability = 1.0 - abs(0.5 - success_rate)
            base_confidence = base_confidence * (0.7 + 0.3 * stability)

        return min(1.0, base_confidence)

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "skills_optimized": 0,
            "adjustments_made": 0,
            "adjustments_skipped": 0,
        }

    def clear_cache(self) -> None:
        """清除缓存"""
        self._weight_cache.clear()


# ==========================================
# 便捷函数
# ==========================================

def update_skill_weight(
    session: Session,
    skill_id: str,
    stats: Optional[Dict[str, Any]] = None,
) -> FeedbackDrivenWeight:
    """
    更新单个技能权重（便捷函数）

    Args:
        session: 数据库会话
        skill_id: 技能 ID
        stats: 统计数据

    Returns:
        更新后的权重配置
    """
    optimizer = WeightOptimizer(session)
    return optimizer.optimize_skill_weight(skill_id, stats)


def get_skill_weight(
    session: Session,
    skill_id: str,
) -> FeedbackDrivenWeight:
    """
    获取技能权重（便捷函数）

    Args:
        session: 数据库会话
        skill_id: 技能 ID

    Returns:
        权重配置
    """
    optimizer = WeightOptimizer(session)
    return optimizer.get_skill_weight(skill_id)


# ==========================================
# 导出
# ==========================================

__all__ = [
    "WeightOptimizer",
    "WeightOptimizerConfig",
    "update_skill_weight",
    "get_skill_weight",
]