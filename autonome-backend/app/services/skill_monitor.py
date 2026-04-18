"""
技能监控告警服务 - 提供执行监控和异常告警

功能：
1. 技能执行指标收集（成功率、执行时间、资源使用）
2. 异常检测（高错误率、超时、资源过载）
3. 告警触发和通知
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque

from app.core.logger import log


class AlertSeverity(str, Enum):
    """告警严重程度"""
    INFO = "info"        # 信息通知
    WARNING = "warning"  # 警告
    CRITICAL = "critical"  # 严重告警
    EMERGENCY = "emergency"  # 紧急告警


class MetricType(str, Enum):
    """指标类型"""
    EXECUTION_COUNT = "execution_count"
    SUCCESS_COUNT = "success_count"
    FAILURE_COUNT = "failure_count"
    TIMEOUT_COUNT = "timeout_count"
    AVG_EXECUTION_TIME = "avg_execution_time"
    ERROR_RATE = "error_rate"


@dataclass
class Alert:
    """告警事件"""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    skill_id: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class MetricData:
    """指标数据"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class SkillExecutionRecord:
    """技能执行记录"""
    skill_id: str
    status: str  # SUCCESS, FAILURE, TIMEOUT
    execution_time: float  # seconds
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


class SkillMonitor:
    """
    技能监控器

    收集技能执行指标，检测异常，触发告警
    """

    # 默认告警阈值
    DEFAULT_THRESHOLDS = {
        "error_rate_warning": 0.1,      # 错误率 > 10% 警告
        "error_rate_critical": 0.3,     # 错误率 > 30% 严重告警
        "execution_time_warning": 300,   # 执行时间 > 5分钟 警告
        "execution_time_critical": 600,  # 执行时间 > 10分钟 严重告警
        "timeout_rate_warning": 0.05,   # 超时率 > 5% 警告
        "timeout_rate_critical": 0.15,  # 超时率 > 15% 严重告警
        "min_sample_size": 10,          # 最小样本量（低于此值不触发告警）
    }

    # 时间窗口（秒）
    TIME_WINDOW = 3600  # 1小时

    def __init__(self):
        """初始化监控器"""
        # 存储执行记录（按技能ID分组）
        self.execution_records: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)  # 每个技能保留最近1000条记录
        )

        # 告警历史
        self.alerts: List[Alert] = []

        # 告警计数器
        self.alert_counter = 0

        # 活跃告警（未解决）
        self.active_alerts: Dict[str, Alert] = {}

        log.info("✅ 技能监控器已初始化")

    def record_execution(
        self,
        skill_id: str,
        status: str,
        execution_time: float,
        error_message: Optional[str] = None
    ):
        """
        记录技能执行

        Args:
            skill_id: 技能ID
            status: 执行状态 (SUCCESS, FAILURE, TIMEOUT)
            execution_time: 执行时间（秒）
            error_message: 错误信息（可选）
        """
        record = SkillExecutionRecord(
            skill_id=skill_id,
            status=status,
            execution_time=execution_time,
            error_message=error_message
        )

        self.execution_records[skill_id].append(record)
        log.debug(f"[Monitor] 记录执行: skill={skill_id}, status={status}, time={execution_time:.2f}s")

        # 检查是否需要触发告警
        self._check_alerts(skill_id)

    def get_metrics(self, skill_id: str) -> Dict[str, Any]:
        """
        获取技能的监控指标

        Args:
            skill_id: 技能ID

        Returns:
            指标字典
        """
        records = list(self.execution_records.get(skill_id, []))

        if not records:
            return {
                "skill_id": skill_id,
                "total_count": 0,
                "message": "暂无执行记录"
            }

        # 过滤时间窗口内的记录
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.TIME_WINDOW)
        recent_records = [
            r for r in records
            if r.timestamp >= window_start
        ]

        if not recent_records:
            return {
                "skill_id": skill_id,
                "total_count": len(records),
                "message": "时间窗口内无执行记录"
            }

        # 计算指标
        total = len(recent_records)
        success = sum(1 for r in recent_records if r.status == "SUCCESS")
        failure = sum(1 for r in recent_records if r.status == "FAILURE")
        timeout = sum(1 for r in recent_records if r.status == "TIMEOUT")

        avg_time = sum(r.execution_time for r in recent_records) / total
        error_rate = (failure + timeout) / total if total > 0 else 0
        timeout_rate = timeout / total if total > 0 else 0

        return {
            "skill_id": skill_id,
            "time_window_hours": self.TIME_WINDOW / 3600,
            "total_executions": total,
            "success_count": success,
            "failure_count": failure,
            "timeout_count": timeout,
            "success_rate": success / total if total > 0 else 0,
            "error_rate": error_rate,
            "timeout_rate": timeout_rate,
            "avg_execution_time": avg_time,
            "last_execution": recent_records[-1].timestamp.isoformat() if recent_records else None
        }

    def get_all_metrics(self) -> List[Dict[str, Any]]:
        """获取所有技能的监控指标"""
        return [
            self.get_metrics(skill_id)
            for skill_id in self.execution_records.keys()
        ]

    def _check_alerts(self, skill_id: str):
        """检查是否需要触发告警"""
        metrics = self.get_metrics(skill_id)

        # 样本量不足，不触发告警
        if metrics.get("total_executions", 0) < self.DEFAULT_THRESHOLDS["min_sample_size"]:
            return

        # 检查错误率
        self._check_error_rate(skill_id, metrics)

        # 检查超时率
        self._check_timeout_rate(skill_id, metrics)

        # 检查执行时间
        self._check_execution_time(skill_id, metrics)

    def _check_error_rate(self, skill_id: str, metrics: Dict[str, Any]):
        """检查错误率告警"""
        error_rate = metrics.get("error_rate", 0)

        # 严重告警
        if error_rate >= self.DEFAULT_THRESHOLDS["error_rate_critical"]:
            self._create_alert(
                severity=AlertSeverity.CRITICAL,
                title=f"技能 {skill_id} 错误率过高",
                message=f"错误率 {error_rate:.1%} 超过阈值 {self.DEFAULT_THRESHOLDS['error_rate_critical']:.0%}",
                skill_id=skill_id,
                metric_name="error_rate",
                metric_value=error_rate,
                threshold=self.DEFAULT_THRESHOLDS["error_rate_critical"]
            )

        # 警告
        elif error_rate >= self.DEFAULT_THRESHOLDS["error_rate_warning"]:
            self._create_alert(
                severity=AlertSeverity.WARNING,
                title=f"技能 {skill_id} 错误率偏高",
                message=f"错误率 {error_rate:.1%} 超过阈值 {self.DEFAULT_THRESHOLDS['error_rate_warning']:.0%}",
                skill_id=skill_id,
                metric_name="error_rate",
                metric_value=error_rate,
                threshold=self.DEFAULT_THRESHOLDS["error_rate_warning"]
            )

    def _check_timeout_rate(self, skill_id: str, metrics: Dict[str, Any]):
        """检查超时率告警"""
        timeout_rate = metrics.get("timeout_rate", 0)

        # 严重告警
        if timeout_rate >= self.DEFAULT_THRESHOLDS["timeout_rate_critical"]:
            self._create_alert(
                severity=AlertSeverity.CRITICAL,
                title=f"技能 {skill_id} 超时率过高",
                message=f"超时率 {timeout_rate:.1%} 超过阈值 {self.DEFAULT_THRESHOLDS['timeout_rate_critical']:.0%}",
                skill_id=skill_id,
                metric_name="timeout_rate",
                metric_value=timeout_rate,
                threshold=self.DEFAULT_THRESHOLDS["timeout_rate_critical"]
            )

        # 警告
        elif timeout_rate >= self.DEFAULT_THRESHOLDS["timeout_rate_warning"]:
            self._create_alert(
                severity=AlertSeverity.WARNING,
                title=f"技能 {skill_id} 超时率偏高",
                message=f"超时率 {timeout_rate:.1%} 超过阈值 {self.DEFAULT_THRESHOLDS['timeout_rate_warning']:.0%}",
                skill_id=skill_id,
                metric_name="timeout_rate",
                metric_value=timeout_rate,
                threshold=self.DEFAULT_THRESHOLDS["timeout_rate_warning"]
            )

    def _check_execution_time(self, skill_id: str, metrics: Dict[str, Any]):
        """检查执行时间告警"""
        avg_time = metrics.get("avg_execution_time", 0)

        # 严重告警
        if avg_time >= self.DEFAULT_THRESHOLDS["execution_time_critical"]:
            self._create_alert(
                severity=AlertSeverity.WARNING,
                title=f"技能 {skill_id} 执行时间过长",
                message=f"平均执行时间 {avg_time:.1f}s 超过阈值 {self.DEFAULT_THRESHOLDS['execution_time_critical']}s",
                skill_id=skill_id,
                metric_name="avg_execution_time",
                metric_value=avg_time,
                threshold=self.DEFAULT_THRESHOLDS["execution_time_critical"]
            )

        # 警告
        elif avg_time >= self.DEFAULT_THRESHOLDS["execution_time_warning"]:
            self._create_alert(
                severity=AlertSeverity.INFO,
                title=f"技能 {skill_id} 执行时间偏长",
                message=f"平均执行时间 {avg_time:.1f}s 超过阈值 {self.DEFAULT_THRESHOLDS['execution_time_warning']}s",
                skill_id=skill_id,
                metric_name="avg_execution_time",
                metric_value=avg_time,
                threshold=self.DEFAULT_THRESHOLDS["execution_time_warning"]
            )

    def _create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        skill_id: Optional[str] = None,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold: Optional[float] = None
    ):
        """创建告警"""
        # 检查是否已有相同类型的活跃告警
        alert_key = f"{skill_id}:{metric_name}"

        if alert_key in self.active_alerts:
            # 更新现有告警
            existing = self.active_alerts[alert_key]
            if existing.severity == severity and existing.metric_value == metric_value:
                # 相同告警，不重复创建
                return

        self.alert_counter += 1
        alert = Alert(
            id=f"alert_{self.alert_counter:06d}",
            severity=severity,
            title=title,
            message=message,
            skill_id=skill_id,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold
        )

        self.alerts.append(alert)
        self.active_alerts[alert_key] = alert

        # 记录告警日志
        if severity == AlertSeverity.CRITICAL:
            log.error(f"🚨 [Monitor Alert] {title}: {message}")
        elif severity == AlertSeverity.WARNING:
            log.warning(f"⚠️ [Monitor Alert] {title}: {message}")
        else:
            log.info(f"ℹ️ [Monitor Alert] {title}: {message}")

    def get_active_alerts(self, skill_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取活跃告警

        Args:
            skill_id: 可选，过滤特定技能的告警

        Returns:
            告警列表
        """
        alerts = [
            alert for alert in self.active_alerts.values()
            if not alert.resolved
        ]

        if skill_id:
            alerts = [a for a in alerts if a.skill_id == skill_id]

        return [
            {
                "id": alert.id,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "skill_id": alert.skill_id,
                "metric_name": alert.metric_name,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
                "created_at": alert.created_at.isoformat()
            }
            for alert in sorted(alerts, key=lambda a: a.created_at, reverse=True)
        ]

    def resolve_alert(self, alert_id: str) -> bool:
        """
        解决告警

        Args:
            alert_id: 告警ID

        Returns:
            是否成功解决
        """
        for key, alert in self.active_alerts.items():
            if alert.id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc)
                del self.active_alerts[key]
                log.info(f"✅ [Monitor] 告警已解决: {alert.title}")
                return True

        return False

    def clear_resolved_alerts(self):
        """清理已解决的告警"""
        self.alerts = [a for a in self.alerts if not a.resolved]
        log.info("[Monitor] 已清理已解决的告警")


# 全局监控器实例
_monitor_instance: Optional[SkillMonitor] = None


def get_monitor() -> SkillMonitor:
    """获取全局监控器实例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SkillMonitor()
    return _monitor_instance


def record_skill_execution(
    skill_id: str,
    status: str,
    execution_time: float,
    error_message: Optional[str] = None
):
    """
    记录技能执行（便捷函数）

    Args:
        skill_id: 技能ID
        status: 执行状态
        execution_time: 执行时间
        error_message: 错误信息
    """
    monitor = get_monitor()
    monitor.record_execution(skill_id, status, execution_time, error_message)


log.info("✅ 技能监控告警服务已加载")