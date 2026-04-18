# -*- coding: utf-8 -*-
"""
容器执行计量器

用于 Docker 容器沙箱执行的计费，支持：
- 执行时长监控
- CPU/内存使用统计
- 超时自动停止并计费
"""

import threading
import time
from typing import Any, Dict, List, Optional

from app.core.logger import log

from app.services.meters.base import BaseMeter, MeteringResult


class ExecutorMeter(BaseMeter):
    """Docker 容器执行计量器

    计费策略：
    1. 记录容器启动时间
    2. 后台线程定期采样容器资源使用（CPU、内存）
    3. 容器停止后计算总费用

    使用示例：
        meter = ExecutorMeter(billing_service, flavor)
        meter.start_metering(record_id, {"container_id": "abc123", "timeout": 3600})

        # ... 容器执行 ...

        result = meter.stop_metering(record_id)
        print(f"费用: {result.cost_credits} CU")
    """

    def __init__(
        self,
        billing_service: Optional["BillingService"] = None,
        flavor: Optional["ResourceFlavor"] = None,
    ):
        """初始化容器计量器

        Args:
            billing_service: 计费服务实例
            flavor: 资源规格实例
        """
        super().__init__(billing_service, flavor)
        self.container_id: Optional[str] = None
        self.timeout: int = 3600  # 默认超时 1 小时
        self.stats_samples: List[Dict[str, Any]] = []
        self.collector_thread: Optional[threading.Thread] = None
        self._stop_collector = threading.Event()

    def start_metering(self, record_id: str, context: Dict[str, Any]) -> None:
        """开始计量

        记录开始时间，启动后台资源采样线程。

        Args:
            record_id: 计算记录 ID
            context: 计量上下文
                - container_id: 容器 ID（可选，后续可设置）
                - timeout: 超时时间（秒）
                - user_id: 用户 ID
                - project_id: 项目 ID
        """
        self._record_start(record_id, context)

        self.container_id = context.get("container_id")
        self.timeout = context.get("timeout", 3600)

        # 清空之前的采样数据
        self.stats_samples = []
        self._stop_collector.clear()

        # 如果已有容器 ID，启动采样线程
        if self.container_id:
            self._start_stats_collector()

        log.info(
            f"容器计量开始: record_id={record_id}, container_id={self.container_id}"
        )

    def set_container_id(self, container_id: str) -> None:
        """设置容器 ID（用于容器创建后设置）

        Args:
            container_id: 容器 ID
        """
        self.container_id = container_id
        if self.start_time and not self.collector_thread:
            self._start_stats_collector()

    def _start_stats_collector(self) -> None:
        """启动后台资源采样线程"""

        def collect():
            """采样循环"""
            while not self._stop_collector.is_set() and self.container_id:
                try:
                    stats = self._get_container_stats()
                    if stats:
                        self.stats_samples.append(stats)
                except Exception as e:
                    log.warning(f"获取容器统计失败: {e}")
                    # 容器可能已停止，退出采样
                    break

                # 每 5 秒采样一次
                self._stop_collector.wait(5)

        self.collector_thread = threading.Thread(target=collect, daemon=True)
        self.collector_thread.start()
        log.debug(f"资源采样线程已启动: container_id={self.container_id}")

    def _get_container_stats(self) -> Optional[Dict[str, Any]]:
        """获取容器资源使用统计

        通过 Docker API 获取容器的 CPU 和内存使用情况。

        Returns:
            Dict: 统计数据，包含 cpu_percent 和 memory_mb
        """
        if not self.container_id:
            return None

        try:
            import docker

            client = docker.from_env(timeout=10)
            container = client.containers.get(self.container_id)
            stats = container.stats(stream=False)

            # 计算 CPU 使用率
            cpu_percent = self._calc_cpu_percent(stats)

            # 获取内存使用量（MB）
            memory_stats = stats.get("memory_stats", {})
            memory_mb = memory_stats.get("usage", 0) / (1024 * 1024)

            return {
                "timestamp": time.time(),
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
            }

        except Exception as e:
            log.warning(f"获取容器统计失败: {e}")
            return None

    def _calc_cpu_percent(self, stats: Dict) -> float:
        """计算 CPU 使用率

        Args:
            stats: Docker stats 返回的数据

        Returns:
            float: CPU 使用率（百分比）
        """
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_usage = cpu_stats.get("cpu_usage", {})
        precpu_usage = precpu_stats.get("cpu_usage", {})

        cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )

        if system_delta > 0 and cpu_delta > 0:
            # 考虑 CPU 核数
            online_cpus = cpu_stats.get("online_cpus", 1)
            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
            return round(cpu_percent, 2)

        return 0.0

    def stop_metering(self, record_id: str) -> MeteringResult:
        """停止计量

        停止采样线程，计算执行时长和费用。

        Args:
            record_id: 计算记录 ID

        Returns:
            MeteringResult: 计量结果
        """
        # 停止采样线程
        self._stop_collector.set()
        if self.collector_thread and self.collector_thread.is_alive():
            self.collector_thread.join(timeout=5)

        # 计算执行时长
        duration = self._calculate_duration()

        # 计算峰值内存
        memory_peak = 0.0
        if self.stats_samples:
            memory_peak = max(s.get("memory_mb", 0) for s in self.stats_samples)

        # 计算 CPU 时间（简化：时长 × 平均 CPU 使用率 / 100）
        cpu_seconds = 0.0
        if self.stats_samples:
            avg_cpu = sum(s.get("cpu_percent", 0) for s in self.stats_samples) / len(
                self.stats_samples
            )
            cpu_seconds = duration * (avg_cpu / 100)

        # 创建结果
        result = MeteringResult(
            duration_seconds=duration,
            cpu_seconds=cpu_seconds,
            memory_peak_mb=memory_peak,
            cost_credits=0.0,  # 先计算费用
            details={
                "container_id": self.container_id,
                "samples_count": len(self.stats_samples),
                "avg_cpu_percent": round(avg_cpu, 2) if self.stats_samples else 0,
                "timeout": self.timeout,
            },
        )

        # 计算费用
        result.cost_credits = self.calculate_cost(result)

        log.info(
            f"容器计量结束: record_id={record_id}, "
            f"duration={duration:.1f}s, cost={result.cost_credits} CU"
        )

        return result

    def calculate_cost(self, result: MeteringResult) -> float:
        """计算费用

        按执行时长计费，应用最低收费规则。

        Args:
            result: 计量结果

        Returns:
            float: 费用（CU）
        """
        duration_minutes = result.duration_seconds / 60.0
        price_per_minute = self.get_price_per_minute("sandbox")
        min_minutes = self.get_min_charge_minutes("sandbox")

        # 应用最低收费
        actual_minutes = max(duration_minutes, min_minutes)

        # 基础费用
        cost = price_per_minute * actual_minutes

        # 应用折扣
        cost = self._apply_discount(cost)

        return cost

    def check_timeout(self) -> bool:
        """检查是否超时

        Returns:
            bool: True 表示已超时
        """
        if self.start_time is None:
            return False

        elapsed = time.time() - self.start_time
        return elapsed > self.timeout

    def get_current_cost(self) -> float:
        """获取当前累计费用（用于实时显示）

        Returns:
            float: 当前费用（CU）
        """
        duration = self._calculate_duration()
        duration_minutes = duration / 60.0
        price_per_minute = self.get_price_per_minute("sandbox")

        return round(price_per_minute * duration_minutes, 2)