"""
A/B 测试框架服务

提供实验管理和变体分配：
1. 实验创建和状态管理
2. 用户变体分配（一致性哈希）
3. 转化记录和统计
4. 实验结果分析

设计原则：
- 同一用户始终分配到同一变体
- 变体分配基于权重平衡
- 实验状态流转验证
- 统计结果实时计算
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 实验状态枚举
# ==========================================

class ExperimentStatus(str, Enum):
    """实验状态"""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# ==========================================
# 实验变体数据类
# ==========================================

@dataclass
class ExperimentVariant:
    """实验变体"""
    variant_id: str
    name: str
    weight: float = 0.5
    assignment_count: int = 0
    conversion_count: int = 0
    conversion_values: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "weight": self.weight,
            "assignment_count": self.assignment_count,
            "conversion_count": self.conversion_count,
            "conversion_values": self.conversion_values,
        }


# ==========================================
# 实验数据类
# ==========================================

@dataclass
class Experiment:
    """实验"""
    experiment_id: str
    name: str
    variants: List[ExperimentVariant]
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = field(default_factory=get_utc_now)
    user_assignments: Dict[int, str] = field(default_factory=dict)  # user_id -> variant_id

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status.value,
            "variants": [v.to_dict() for v in self.variants],
            "created_at": self.created_at.isoformat(),
            "user_assignments": len(self.user_assignments),
        }


# ==========================================
# A/B 测试服务
# ==========================================

class ABTestingService:
    """
    A/B 测试服务

    提供完整的实验管理：
    - 创建实验
    - 分配用户到变体
    - 记录转化
    - 获取统计结果
    """

    def __init__(self):
        """初始化服务"""
        self._experiments: Dict[str, Experiment] = {}

    def create_experiment(
        self,
        experiment_id: str,
        name: str,
        variants: List[Dict[str, Any]],
    ) -> Experiment:
        """
        创建实验并注册到服务

        Args:
            experiment_id: 实验ID
            name: 实验名称
            variants: 变体配置列表

        Returns:
            实验对象
        """
        # 创建变体对象
        variant_objects = []
        for v in variants:
            variant_objects.append(ExperimentVariant(
                variant_id=v["variant_id"],
                name=v["name"],
                weight=v.get("weight", 0.5),
            ))

        # 创建实验
        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            variants=variant_objects,
            status=ExperimentStatus.DRAFT,
        )

        # 注册到服务
        self._experiments[experiment_id] = experiment

        log.info(f"[ABTesting] 创建实验: {experiment_id}, 变体数: {len(variant_objects)}")
        return experiment

    def assign_variant(self, experiment_id: str, user_id: int) -> str:
        """
        分配用户到变体

        Args:
            experiment_id: 实验ID
            user_id: 用户ID

        Returns:
            分配的变体ID
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        # 检查实验状态
        if experiment.status != ExperimentStatus.RUNNING:
            raise ValueError(f"Experiment '{experiment_id}' is not running")

        # 检查是否已分配
        if user_id in experiment.user_assignments:
            return experiment.user_assignments[user_id]

        # 使用一致性哈希确保同一用户始终分配到同一变体
        variant_id = self._consistent_hash_assign(experiment, user_id)

        # 记录分配
        experiment.user_assignments[user_id] = variant_id

        # 更新变体计数
        for variant in experiment.variants:
            if variant.variant_id == variant_id:
                variant.assignment_count += 1
                break

        log.info(f"[ABTesting] 用户 {user_id} 分配到变体 {variant_id}")
        return variant_id

    def _consistent_hash_assign(self, experiment: Experiment, user_id: int) -> str:
        """
        使用一致性哈希分配用户

        基于用户ID和实验ID的哈希值，结合权重分配变体
        """
        # 生成哈希值
        hash_input = f"{experiment.experiment_id}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)

        # 根据权重分配
        total_weight = sum(v.weight for v in experiment.variants)
        normalized_hash = (hash_value % 10000) / 10000.0 * total_weight

        cumulative = 0.0
        for variant in experiment.variants:
            cumulative += variant.weight
            if normalized_hash <= cumulative:
                return variant.variant_id

        # 默认返回最后一个
        return experiment.variants[-1].variant_id

    def start_experiment(self, experiment_id: str):
        """
        启动实验

        Args:
            experiment_id: 实验ID
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        # 验证变体存在
        if len(experiment.variants) == 0:
            raise ValueError("Cannot start experiment without variants")

        # 更新状态
        experiment.status = ExperimentStatus.RUNNING
        log.info(f"[ABTesting] 启动实验: {experiment_id}")

    def pause_experiment(self, experiment_id: str):
        """
        暂停实验

        Args:
            experiment_id: 实验ID
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        experiment.status = ExperimentStatus.PAUSED
        log.info(f"[ABTesting] 暂停实验: {experiment_id}")

    def complete_experiment(self, experiment_id: str):
        """
        完成实验

        Args:
            experiment_id: 实验ID
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        experiment.status = ExperimentStatus.COMPLETED
        log.info(f"[ABTesting] 完成实验: {experiment_id}")

    def record_conversion(
        self,
        experiment_id: str,
        user_id: int,
        conversion_value: float = 1.0,
    ):
        """
        记录转化

        Args:
            experiment_id: 实验ID
            user_id: 用户ID
            conversion_value: 转化值
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        # 获取用户分配的变体
        variant_id = experiment.user_assignments.get(user_id)
        if not variant_id:
            log.warning(f"[ABTesting] 用户 {user_id} 未分配到任何变体")
            return

        # 更新变体转化统计
        for variant in experiment.variants:
            if variant.variant_id == variant_id:
                variant.conversion_count += 1
                variant.conversion_values.append(conversion_value)
                break

        log.info(f"[ABTesting] 用户 {user_id} 转化，变体 {variant_id}")

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        """
        获取实验结果

        Args:
            experiment_id: 实验ID

        Returns:
            实验结果统计
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        # 计算总转化数
        total_conversions = sum(v.conversion_count for v in experiment.variants)

        # 计算各变体结果
        variant_results = {}
        for variant in experiment.variants:
            conversion_rate = 0.0
            if variant.assignment_count > 0:
                conversion_rate = variant.conversion_count / variant.assignment_count

            avg_value = 0.0
            if variant.conversion_values:
                avg_value = sum(variant.conversion_values) / len(variant.conversion_values)

            variant_results[variant.variant_id] = {
                "assignment_count": variant.assignment_count,
                "conversion_count": variant.conversion_count,
                "conversion_rate": conversion_rate,
                "average_value": avg_value,
            }

        return {
            "experiment_id": experiment_id,
            "status": experiment.status.value,
            "total_conversions": total_conversions,
            "total_assignments": len(experiment.user_assignments),
            "variant_results": variant_results,
        }

    def get_variant_statistics(self, experiment_id: str) -> Dict[str, Dict[str, Any]]:
        """
        获取变体统计

        Args:
            experiment_id: 实验ID

        Returns:
            各变体统计信息
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found")

        stats = {}
        for variant in experiment.variants:
            stats[variant.variant_id] = {
                "assignment_count": variant.assignment_count,
                "conversion_count": variant.conversion_count,
                "weight": variant.weight,
            }

        return stats


# ==========================================
# 导出
# ==========================================

__all__ = [
    "ExperimentStatus",
    "ExperimentVariant",
    "Experiment",
    "ABTestingService",
]