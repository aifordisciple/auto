# -*- coding: utf-8 -*-
"""
Web Terminal 计量器

用于 Web Terminal WebSocket 连接的计费，支持：
- 心跳包累计时长
- 实时余额检查
- 会话结束时结算
"""

import asyncio
import time
from typing import Any, Dict, Optional

from loguru import logger

from app.services.meters.base import BaseMeter, MeteringResult


class TerminalMeter(BaseMeter):
    """Web Terminal 计量器

    计费策略：
    1. 连接建立时开始计量
    2. 定期记录心跳包（每 60 秒）
    3. 可实时检查余额，余额不足时断开连接
    4. 会话结束时结算费用

    使用示例：
        meter = TerminalMeter(billing_service, session_id)

        # 连接建立
        meter.start_metering(record_id, {"project_id": "proj_123"})

        # 心跳循环
        while connected:
            await asyncio.sleep(60)
            cost = await meter.record_heartbeat()
            if cost > wallet_balance:
                await websocket.close(code=4002, reason="余额不足")

        # 连接断开
        result = meter.stop_metering(record_id)
    """

    # 心跳间隔（秒）
    HEARTBEAT_INTERVAL = 60

    # 默认定价
    DEFAULT_PRICE_PER_MINUTE = 0.05  # CU/分钟
    DEFAULT_MIN_CHARGE_MINUTES = 5  # 最低收费 5 分钟

    def __init__(
        self,
        billing_service: Optional["BillingService"] = None,
        flavor: Optional["ResourceFlavor"] = None,
        session_id: Optional[str] = None,
    ):
        """初始化终端计量器

        Args:
            billing_service: 计费服务实例
            flavor: 资源规格实例
            session_id: WebSocket 会话 ID
        """
        super().__init__(billing_service, flavor)
        self.session_id = session_id
        self.heartbeat_count: int = 0
        self.project_id: Optional[str] = None
        self.cols: int = 80
        self.rows: int = 24

    def start_metering(self, record_id: str, context: Dict[str, Any]) -> None:
        """开始计量

        记录会话开始时间。

        Args:
            record_id: 计算记录 ID
            context: 计量上下文
                - session_id: WebSocket 会话 ID
                - project_id: 项目 ID
                - user_id: 用户 ID
                - cols: 终端列数
                - rows: 终端行数
        """
        self._record_start(record_id, context)

        self.session_id = context.get("session_id", self.session_id)
        self.project_id = context.get("project_id")
        self.cols = context.get("cols", 80)
        self.rows = context.get("rows", 24)

        logger.info(
            f"终端计量开始: record_id={record_id}, session_id={self.session_id}"
        )

    async def record_heartbeat(self) -> float:
        """记录心跳

        每 HEARTBEAT_INTERVAL 秒调用一次，返回当前累计费用。
        可用于实时检查余额。

        Returns:
            float: 当前累计费用（CU）
        """
        self.heartbeat_count += 1
        current_cost = self.get_current_cost()

        logger.debug(
            f"终端心跳: session_id={self.session_id}, "
            f"heartbeat=#{self.heartbeat_count}, cost={current_cost} CU"
        )

        return current_cost

    def stop_metering(self, record_id: str) -> MeteringResult:
        """停止计量

        计算会话时长和费用。

        Args:
            record_id: 计算记录 ID

        Returns:
            MeteringResult: 计量结果
        """
        duration = self._calculate_duration()

        # 创建结果
        result = MeteringResult(
            duration_seconds=duration,
            cost_credits=0.0,  # 先计算费用
            details={
                "session_id": self.session_id,
                "project_id": self.project_id,
                "heartbeat_count": self.heartbeat_count,
                "terminal_size": f"{self.cols}x{self.rows}",
            },
        )

        # 计算费用
        result.cost_credits = self.calculate_cost(result)

        logger.info(
            f"终端计量结束: record_id={record_id}, "
            f"duration={duration:.1f}s, heartbeats={self.heartbeat_count}, "
            f"cost={result.cost_credits} CU"
        )

        return result

    def calculate_cost(self, result: MeteringResult) -> float:
        """计算费用

        按时长计费，应用最低收费规则。

        Args:
            result: 计量结果

        Returns:
            float: 费用（CU）
        """
        duration_minutes = result.duration_seconds / 60.0

        # 获取定价
        price_per_minute = self.get_price_per_minute("terminal")
        min_minutes = self.get_min_charge_minutes("terminal")

        # 应用最低收费
        actual_minutes = max(duration_minutes, min_minutes)

        # 基础费用
        cost = price_per_minute * actual_minutes

        # 应用折扣
        cost = self._apply_discount(cost)

        return cost

    def get_current_cost(self) -> float:
        """获取当前累计费用

        Returns:
            float: 当前费用（CU）
        """
        duration = self._calculate_duration()
        duration_minutes = duration / 60.0
        price_per_minute = self.get_price_per_minute("terminal")

        # 注意：不应用最低收费，返回实际费用
        return round(price_per_minute * duration_minutes, 2)

    def check_balance(self, wallet_balance: float) -> bool:
        """检查余额是否充足

        用于实时判断是否需要断开连接。

        Args:
            wallet_balance: 钱包可用余额

        Returns:
            bool: True 表示余额充足
        """
        current_cost = self.get_current_cost()
        return wallet_balance >= current_cost

    def get_estimated_cost_for_duration(self, duration_minutes: float) -> float:
        """预估指定时长的费用

        Args:
            duration_minutes: 时长（分钟）

        Returns:
            float: 预估费用（CU）
        """
        price_per_minute = self.get_price_per_minute("terminal")
        min_minutes = self.get_min_charge_minutes("terminal")

        actual_minutes = max(duration_minutes, min_minutes)
        return round(price_per_minute * actual_minutes, 2)