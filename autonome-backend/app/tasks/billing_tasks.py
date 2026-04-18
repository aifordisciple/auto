# -*- coding: utf-8 -*-
"""
计费相关定时任务模块

包含：
- 僵尸容器清理
- 孤立记录结算
- 钱包健康检查
"""

from datetime import datetime

from app.core.logger import log
from sqlmodel import Session

from app.core.database import engine
from app.services.billing_service import BillingService
from app.services.risk_control import (
    EscapeWatchdog,
    OOMCarePolicy,
    RiskControlService,
)


def get_session() -> Session:
    """获取数据库会话"""
    return Session(engine)


# ==========================================
# 定时任务函数
# ==========================================


def cleanup_zombie_containers():
    """清理僵尸容器

    每 30 分钟执行一次。
    扫描运行时间超过阈值的容器并强制清理。
    """
    log.info("[定时任务] 开始扫描僵尸容器...")

    session = get_session()
    try:
        watchdog = EscapeWatchdog(session)
        zombies = watchdog.scan_zombie_containers()

        cleaned = 0
        for zombie in zombies:
            if watchdog.cleanup_zombie(zombie["container_id"]):
                cleaned += 1

        log.info(
            f"[定时任务] 僵尸容器清理完成: 扫描 {len(zombies)} 个, 清理 {cleaned} 个"
        )

    except Exception as e:
        log.error(f"[定时任务] 僵尸容器清理失败: {e}")
    finally:
        session.close()


def settle_orphan_records():
    """结算孤立记录

    每小时执行一次。
    结算长时间 RUNNING 但容器已不存在的计算记录。
    """
    log.info("[定时任务] 开始扫描孤立记录...")

    session = get_session()
    try:
        watchdog = EscapeWatchdog(session)
        orphans = watchdog.scan_orphan_records()

        settled = 0
        for orphan in orphans:
            if watchdog.settle_orphan_record(orphan):
                settled += 1

        log.info(
            f"[定时任务] 孤立记录结算完成: 扫描 {len(orphans)} 个, 结算 {settled} 个"
        )

    except Exception as e:
        log.error(f"[定时任务] 孤立记录结算失败: {e}")
    finally:
        session.close()


def check_wallet_health():
    """检查钱包健康状态

    每 5 分钟执行一次。
    检查所有活跃钱包的余额，自动挂起低余额钱包。
    """
    log.info("[定时任务] 开始检查钱包健康状态...")

    session = get_session()
    try:
        billing_service = BillingService(session)
        risk_control = RiskControlService(session, billing_service)

        wallets = risk_control.get_all_active_wallets()

        suspended = 0
        warned = 0

        for wallet in wallets:
            health = risk_control.check_wallet_health(wallet.wallet_id)

            if health["status"] == "critical":
                # 执行自动挂起
                for action in health["actions"]:
                    if action["type"] == "auto_suspend":
                        risk_control.enforce_suspension(
                            wallet.wallet_id, action["message"]
                        )
                        suspended += 1

            elif health["status"] == "warning":
                warned += 1
                # TODO: 发送告警通知

        log.info(
            f"[定时任务] 钱包健康检查完成: 扫描 {len(wallets)} 个, "
            f"挂起 {suspended} 个, 告警 {warned} 个"
        )

    except Exception as e:
        log.error(f"[定时任务] 钱包健康检查失败: {e}")
    finally:
        session.close()


def process_oom_refunds():
    """处理 OOM 退款

    每小时执行一次。
    扫描最近 OOM 失败的任务并执行退款。
    """
    log.info("[定时任务] 开始处理 OOM 退款...")

    session = get_session()
    try:
        billing_service = BillingService(session)
        oom_policy = OOMCarePolicy(session, billing_service)

        oom_records = oom_policy.scan_oom_records(hours=2)

        refunded = 0
        total_refund = 0.0

        for record in oom_records:
            # 检查是否已退款（通过交易记录判断）
            # TODO: 添加已退款检查逻辑

            refund = oom_policy.check_and_refund(record.record_id)
            if refund:
                refunded += 1
                total_refund += refund

        log.info(
            f"[定时任务] OOM 退款处理完成: 扫描 {len(oom_records)} 个, "
            f"退款 {refunded} 个, 总额 {total_refund:.2f} CU"
        )

    except Exception as e:
        log.error(f"[定时任务] OOM 退款处理失败: {e}")
    finally:
        session.close()


# ==========================================
# Celery 任务包装器
# ==========================================

try:
    from celery import shared_task
    from app.services.celery_app import celery_app

    @shared_task
    def task_cleanup_zombie_containers():
        """Celery 任务：清理僵尸容器"""
        cleanup_zombie_containers()

    @shared_task
    def task_settle_orphan_records():
        """Celery 任务：结算孤立记录"""
        settle_orphan_records()

    @shared_task
    def task_check_wallet_health():
        """Celery 任务：检查钱包健康状态"""
        check_wallet_health()

    @shared_task
    def task_process_oom_refunds():
        """Celery 任务：处理 OOM 退款"""
        process_oom_refunds()

    # 配置定时任务
    celery_app.conf.beat_schedule = {
        "cleanup-zombie-containers": {
            "task": "app.tasks.billing_tasks.task_cleanup_zombie_containers",
            "schedule": 1800.0,  # 每 30 分钟
        },
        "settle-orphan-records": {
            "task": "app.tasks.billing_tasks.task_settle_orphan_records",
            "schedule": 3600.0,  # 每小时
        },
        "check-wallet-health": {
            "task": "app.tasks.billing_tasks.task_check_wallet_health",
            "schedule": 300.0,  # 每 5 分钟
        },
        "process-oom-refunds": {
            "task": "app.tasks.billing_tasks.task_process_oom_refunds",
            "schedule": 3600.0,  # 每小时
        },
    }

    log.info("✅ 计费定时任务已注册")

except ImportError:
    log.warning("Celery 未安装，跳过定时任务注册")