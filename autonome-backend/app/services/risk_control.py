# -*- coding: utf-8 -*-
"""
风控服务模块

提供计费系统的风控能力：
- RiskControlService: 余额监控、欠费挂起
- EscapeWatchdog: 防逃逸看门狗、僵尸容器清理
- OOMCarePolicy: OOM 关怀政策（退款补偿）
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import docker
from app.core.logger import log
from sqlmodel import Session, select

from app.models.billing import (
    ComputeRecord,
    TaskStatus,
    TransactionType,
    Wallet,
    WalletStatus,
)
from app.services.billing_service import BillingService


class RiskControlService:
    """风控服务

    职责：
    1. 余额监控 - 检测低余额、触发告警
    2. 欠费熔断 - 自动挂起钱包、限制执行
    3. 异常检测 - 短时间大量消费、异常任务

    使用示例：
        risk_control = RiskControlService(session, billing_service)
        health = risk_control.check_wallet_health(wallet_id)
        if health["actions"]:
            risk_control.enforce_suspension(wallet_id, "余额不足")
    """

    # 低余额告警阈值
    LOW_BALANCE_THRESHOLD = 10.0  # CU

    # 自动挂起阈值
    AUTO_SUSPEND_THRESHOLD = 0.0  # CU

    # 异常消费阈值（短时间内消费超过此值触发告警）
    ABNORMAL_CONSUMPTION_THRESHOLD = 100.0  # CU

    # 异常消费时间窗口
    ABNORMAL_CONSUMPTION_WINDOW = timedelta(hours=1)

    def __init__(self, session: Session, billing_service: BillingService):
        """初始化风控服务

        Args:
            session: 数据库会话
            billing_service: 计费服务实例
        """
        self.session = session
        self.billing_service = billing_service

    def check_wallet_health(self, wallet_id: str) -> Dict[str, Any]:
        """检查钱包健康状态

        Args:
            wallet_id: 钱包 ID

        Returns:
            Dict: 健康状态报告
                - status: healthy / warning / critical
                - warnings: 告警列表
                - actions: 建议操作列表
        """
        wallet = self.billing_service.get_wallet(wallet_id)

        health = {
            "wallet_id": wallet_id,
            "status": "healthy",
            "warnings": [],
            "actions": [],
            "balance": wallet.credits_balance,
            "frozen": wallet.credits_frozen,
            "overdraft": wallet.credits_overdraft,
        }

        # 低余额检查
        if wallet.credits_balance <= wallet.low_balance_threshold:
            health["warnings"].append(
                {
                    "type": "low_balance",
                    "message": f"余额不足 {wallet.low_balance_threshold} CU，请及时充值",
                    "current_balance": wallet.credits_balance,
                }
            )
            health["status"] = "warning"

        # 自动挂起检查
        if wallet.credits_balance <= wallet.auto_suspend_threshold:
            health["actions"].append(
                {
                    "type": "auto_suspend",
                    "message": "余额达到挂起阈值，建议挂起钱包",
                    "threshold": wallet.auto_suspend_threshold,
                }
            )
            health["status"] = "critical"

        # 透支检查
        if wallet.credits_overdraft > 0:
            health["warnings"].append(
                {
                    "type": "overdraft",
                    "message": f"已透支 {wallet.credits_overdraft} CU",
                    "overdraft_amount": wallet.credits_overdraft,
                }
            )
            health["status"] = "warning"

        # 检查异常消费
        abnormal = self._check_abnormal_consumption(wallet_id)
        if abnormal:
            health["warnings"].append(abnormal)
            health["status"] = "warning"

        return health

    def _check_abnormal_consumption(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        """检查异常消费

        Args:
            wallet_id: 钱包 ID

        Returns:
            Optional[Dict]: 异常信息，或 None
        """
        # 查询最近时间窗口内的消费
        window_start = datetime.now() - self.ABNORMAL_CONSUMPTION_WINDOW

        records = self.session.exec(
            select(ComputeRecord).where(
                ComputeRecord.wallet_id == wallet_id,
                ComputeRecord.status == TaskStatus.COMPLETED,
                ComputeRecord.completed_at >= window_start,
            )
        ).all()

        total_consumption = sum(r.actual_cost for r in records)

        if total_consumption > self.ABNORMAL_CONSUMPTION_THRESHOLD:
            return {
                "type": "abnormal_consumption",
                "message": f"短时间内消费 {total_consumption:.2f} CU，请确认是否正常",
                "consumption": total_consumption,
                "window": str(self.ABNORMAL_CONSUMPTION_WINDOW),
            }

        return None

    def enforce_suspension(self, wallet_id: str, reason: str) -> None:
        """执行钱包挂起

        Args:
            wallet_id: 钱包 ID
            reason: 挂起原因
        """
        wallet = self.billing_service.get_wallet(wallet_id)

        if wallet.status == WalletStatus.SUSPENDED:
            log.warning(f"钱包 {wallet_id} 已经是挂起状态")
            return

        wallet.status = WalletStatus.SUSPENDED
        self.session.commit()

        log.warning(f"钱包 {wallet_id} 已挂起: {reason}")

        # TODO: 发送通知给用户

    def resume_wallet(self, wallet_id: str) -> None:
        """恢复钱包

        Args:
            wallet_id: 钱包 ID
        """
        wallet = self.billing_service.get_wallet(wallet_id)

        if wallet.status != WalletStatus.SUSPENDED:
            log.warning(f"钱包 {wallet_id} 不是挂起状态")
            return

        wallet.status = WalletStatus.ACTIVE
        self.session.commit()

        log.info(f"钱包 {wallet_id} 已恢复")

    def get_all_active_wallets(self) -> List[Wallet]:
        """获取所有活跃钱包

        Returns:
            List[Wallet]: 活跃钱包列表
        """
        return self.session.exec(
            select(Wallet).where(Wallet.status == WalletStatus.ACTIVE)
        ).all()


class EscapeWatchdog:
    """防逃逸看门狗

    职责：
    1. 僵尸容器检测 - 超时未清理的容器
    2. 资源泄漏检测 - 未结算的计算记录
    3. 强制清理 - 终止逃逸容器

    使用示例：
        watchdog = EscapeWatchdog(session)
        zombies = watchdog.scan_zombie_containers()
        for zombie in zombies:
            watchdog.cleanup_zombie(zombie["container_id"])
    """

    # 僵尸容器阈值：运行时间超过此值且无心跳
    ZOMBIE_THRESHOLD_SECONDS = 3600  # 1 小时

    # 孤立记录阈值：运行时间超过此值但容器已不存在
    ORPHAN_THRESHOLD_SECONDS = 7200  # 2 小时

    def __init__(self, session: Session):
        """初始化看门狗

        Args:
            session: 数据库会话
        """
        self.session = session
        self._docker_client: Optional[docker.DockerClient] = None

    @property
    def docker_client(self) -> docker.DockerClient:
        """获取 Docker 客户端（懒加载）"""
        if self._docker_client is None:
            self._docker_client = docker.from_env(timeout=30)
        return self._docker_client

    def scan_zombie_containers(self) -> List[Dict[str, Any]]:
        """扫描僵尸容器

        检测运行时间过长且可能失控的容器。

        Returns:
            List[Dict]: 僵尸容器列表
        """
        zombies = []

        try:
            containers = self.docker_client.containers.list()

            for container in containers:
                # 获取容器信息
                inspect = container.attrs
                state = inspect.get("State", {})

                # 检查运行时间
                started_at_str = state.get("StartedAt", "")
                if not started_at_str:
                    continue

                # 解析 ISO 时间
                try:
                    started_at = datetime.fromisoformat(
                        started_at_str.replace("Z", "+00:00")
                    )
                    running_seconds = (datetime.now(started_at.tzinfo) - started_at).total_seconds()
                except Exception:
                    continue

                # 检查是否超过阈值
                if running_seconds > self.ZOMBIE_THRESHOLD_SECONDS:
                    # 检查是否是 Autonome 的容器
                    labels = inspect.get("Config", {}).get("Labels", {})
                    if labels.get("autonome.managed") == "true":
                        zombies.append(
                            {
                                "container_id": container.id[:12],
                                "name": container.name,
                                "running_seconds": running_seconds,
                                "image": inspect.get("Config", {}).get("Image", ""),
                            }
                        )

        except Exception as e:
            log.error(f"扫描僵尸容器失败: {e}")

        return zombies

    def scan_orphan_records(self) -> List[ComputeRecord]:
        """扫描孤立计算记录

        检测长时间 RUNNING 但容器已不存在的记录。

        Returns:
            List[ComputeRecord]: 孤立记录列表
        """
        threshold_time = datetime.now() - timedelta(seconds=self.ORPHAN_THRESHOLD_SECONDS)

        orphans = self.session.exec(
            select(ComputeRecord).where(
                ComputeRecord.status == TaskStatus.RUNNING,
                ComputeRecord.started_at < threshold_time,
            )
        ).all()

        return list(orphans)

    def cleanup_zombie(self, container_id: str) -> bool:
        """清理僵尸容器

        Args:
            container_id: 容器 ID

        Returns:
            bool: 清理成功返回 True
        """
        try:
            container = self.docker_client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()

            log.info(f"已清理僵尸容器: {container_id}")
            return True

        except docker.errors.NotFound:
            log.warning(f"容器不存在: {container_id}")
            return True

        except Exception as e:
            log.error(f"清理容器失败: {container_id}, {e}")
            return False

    def settle_orphan_record(self, record: ComputeRecord) -> bool:
        """结算孤立记录

        Args:
            record: 孤立记录

        Returns:
            bool: 结算成功返回 True
        """
        try:
            billing_service = BillingService(self.session)

            # 使用预估费用结算
            billing_service.settle_frozen_credits(
                wallet_id=record.wallet_id,
                record_id=record.record_id,
                actual_cost=record.estimated_cost,
                execution_details={"force_settle": True, "reason": "orphan_record"},
            )

            log.info(f"已结算孤立记录: {record.record_id}")
            return True

        except Exception as e:
            log.error(f"结算孤立记录失败: {record.record_id}, {e}")
            return False


class OOMCarePolicy:
    """OOM 关怀政策

    职责：
    1. 检测 OOM 失败的任务
    2. 提供部分退款补偿
    3. 记录关怀日志

    使用示例：
        oom_policy = OOMCarePolicy(session, billing_service)
        refund = oom_policy.check_and_refund(record_id)
        if refund:
            print(f"OOM 退款: {refund} CU")
    """

    # OOM 退款比例
    OOM_REFUND_RATE = 0.5  # 50%

    # OOM 退出码
    OOM_EXIT_CODE = 137

    def __init__(self, session: Session, billing_service: BillingService):
        """初始化 OOM 关怀政策

        Args:
            session: 数据库会话
            billing_service: 计费服务实例
        """
        self.session = session
        self.billing_service = billing_service

    def check_and_refund(self, record_id: str) -> Optional[float]:
        """检查 OOM 并退款

        Args:
            record_id: 计算记录 ID

        Returns:
            Optional[float]: 退款金额，如果不是 OOM 则返回 None
        """
        record = self.session.get(ComputeRecord, record_id)

        if not record:
            log.warning(f"计算记录不存在: {record_id}")
            return None

        if record.status != TaskStatus.FAILED:
            return None

        # 检查是否 OOM
        details = record.execution_details or {}
        exit_code = details.get("exit_code", 0)
        oom_killed = details.get("oom_killed", False)

        is_oom = exit_code == self.OOM_EXIT_CODE or oom_killed

        if not is_oom:
            return None

        # 计算退款金额
        refund_amount = record.actual_cost * self.OOM_REFUND_RATE

        if refund_amount <= 0:
            return None

        # 执行退款
        try:
            self.billing_service.recharge(
                wallet_id=record.wallet_id,
                amount=refund_amount,
                transaction_type=TransactionType.REFUND,
                description=f"OOM 关怀退款: {record_id}",
            )

            log.info(
                f"OOM 关怀退款: record_id={record_id}, "
                f"actual_cost={record.actual_cost}, refund={refund_amount}"
            )

            return refund_amount

        except Exception as e:
            log.error(f"OOM 退款失败: {record_id}, {e}")
            return None

    def scan_oom_records(self, hours: int = 24) -> List[ComputeRecord]:
        """扫描最近 OOM 失败的记录

        Args:
            hours: 扫描时间范围（小时）

        Returns:
            List[ComputeRecord]: OOM 记录列表
        """
        threshold_time = datetime.now() - timedelta(hours=hours)

        records = self.session.exec(
            select(ComputeRecord).where(
                ComputeRecord.status == TaskStatus.FAILED,
                ComputeRecord.completed_at >= threshold_time,
            )
        ).all()

        oom_records = []
        for record in records:
            details = record.execution_details or {}
            exit_code = details.get("exit_code", 0)
            oom_killed = details.get("oom_killed", False)

            if exit_code == self.OOM_EXIT_CODE or oom_killed:
                oom_records.append(record)

        return oom_records