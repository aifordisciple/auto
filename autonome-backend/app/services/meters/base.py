# -*- coding: utf-8 -*-
"""
计量引擎基础模块

定义计量器的统一接口和通用数据结构。
所有具体计量器（Nextflow、容器、终端）都继承自 BaseMeter。
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from loguru import logger

if TYPE_CHECKING:
    from app.models.billing import ResourceFlavor
    from app.services.billing_service import BillingService


@dataclass
class MeteringResult:
    """计量结果数据类

    记录一次计量周期的资源消耗和费用信息。

    Attributes:
        duration_seconds: 执行时长（秒）
        cpu_seconds: CPU 时间（秒），用于多核累计
        memory_peak_mb: 峰值内存使用（MB）
        gpu_seconds: GPU 时间（秒）
        cost_credits: 计算出的费用（CU）
        details: 额外详细信息，如任务列表、采样数据等
    """

    duration_seconds: float = 0.0
    cpu_seconds: float = 0.0
    memory_peak_mb: float = 0.0
    gpu_seconds: float = 0.0
    cost_credits: float = 0.0
    details: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于存储到 ComputeRecord.execution_details"""
        return {
            "duration_seconds": self.duration_seconds,
            "cpu_seconds": self.cpu_seconds,
            "memory_peak_mb": self.memory_peak_mb,
            "gpu_seconds": self.gpu_seconds,
            "cost_credits": self.cost_credits,
            "details": self.details,
        }


class BaseMeter(ABC):
    """计量器抽象基类

    定义计量器的统一接口。所有具体计量器必须实现以下方法：
    - start_metering: 开始计量，记录初始状态
    - stop_metering: 停止计量，返回计量结果
    - calculate_cost: 根据计量结果计算费用

    Attributes:
        billing_service: 计费服务实例，用于获取定价信息
        flavor: 资源规格实例，用于差异化定价
        record_id: 当前计量的计算记录 ID
        start_time: 计量开始时间（时间戳）
    """

    # 默认定价配置（无 flavor 时使用）
    DEFAULT_PRICING = {
        "sandbox": {"price_per_minute": 0.1, "min_charge_minutes": 1},
        "terminal": {"price_per_minute": 0.05, "min_charge_minutes": 5},
        "blueprint": {"price_per_minute": 0.2, "min_charge_minutes": 1},
    }

    def __init__(
        self,
        billing_service: Optional["BillingService"] = None,
        flavor: Optional["ResourceFlavor"] = None,
    ):
        """初始化计量器

        Args:
            billing_service: 计费服务实例
            flavor: 资源规格实例（可选）
        """
        self.billing_service = billing_service
        self.flavor = flavor
        self.record_id: Optional[str] = None
        self.start_time: Optional[float] = None
        self.context: Dict[str, Any] = {}

    @abstractmethod
    def start_metering(self, record_id: str, context: Dict[str, Any]) -> None:
        """开始计量

        记录计量开始时间和初始状态。

        Args:
            record_id: 计算记录 ID
            context: 计量上下文，包含任务相关信息
                - user_id: 用户 ID
                - project_id: 项目 ID
                - task_type: 任务类型
                - 其他任务特定信息
        """
        pass

    @abstractmethod
    def stop_metering(self, record_id: str) -> MeteringResult:
        """停止计量并返回结果

        计算本次计量的资源消耗和费用。

        Args:
            record_id: 计算记录 ID

        Returns:
            MeteringResult: 计量结果
        """
        pass

    @abstractmethod
    def calculate_cost(self, result: MeteringResult) -> float:
        """计算费用

        根据计量结果和定价规则计算费用。

        Args:
            result: 计量结果

        Returns:
            float: 费用（CU）
        """
        pass

    def get_price_per_minute(self, task_type: str = "sandbox") -> float:
        """获取每分钟价格

        优先使用 flavor 定价，否则使用默认定价。

        Args:
            task_type: 任务类型，用于查找默认定价

        Returns:
            float: 每分钟价格（CU）
        """
        if self.flavor:
            return self.flavor.price_per_minute

        pricing = self.DEFAULT_PRICING.get(task_type, self.DEFAULT_PRICING["sandbox"])
        return pricing.get("price_per_minute", 0.1)

    def get_min_charge_minutes(self, task_type: str = "sandbox") -> int:
        """获取最低收费分钟数

        Args:
            task_type: 任务类型

        Returns:
            int: 最低收费分钟数
        """
        if self.flavor:
            return self.flavor.min_charge_minutes

        pricing = self.DEFAULT_PRICING.get(task_type, self.DEFAULT_PRICING["sandbox"])
        return pricing.get("min_charge_minutes", 1)

    def _record_start(self, record_id: str, context: Dict[str, Any]) -> None:
        """记录开始状态（内部方法）

        子类应在 start_metering 中调用此方法。

        Args:
            record_id: 计算记录 ID
            context: 计量上下文
        """
        self.record_id = record_id
        self.context = context
        self.start_time = time.time()
        logger.debug(f"计量开始: record_id={record_id}, context={context}")

    def _calculate_duration(self) -> float:
        """计算执行时长（内部方法）

        Returns:
            float: 执行时长（秒）
        """
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def _apply_discount(self, cost: float) -> float:
        """应用折扣（内部方法）

        如果有 flavor 且定义了折扣率，则应用折扣。

        Args:
            cost: 原始费用

        Returns:
            float: 折扣后费用
        """
        if self.flavor and self.flavor.discount_rate > 0:
            discount_amount = cost * self.flavor.discount_rate
            logger.info(f"应用折扣: 原价 {cost:.2f} CU, 折扣 {discount_amount:.2f} CU")
            cost -= discount_amount
        return round(cost, 2)