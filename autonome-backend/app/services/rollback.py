"""
自动回滚服务

提供模型性能监控和自动回滚：
1. 回滚条件配置
2. 性能监控触发
3. 回滚执行
4. 回滚历史记录

设计原则：
- 多种触发条件支持
- 安全的版本回退
- 完整的历史追踪
- 与版本管理服务集成
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 回滚触发条件枚举
# ==========================================

class RollbackTrigger(str, Enum):
    """回滚触发条件"""
    PERFORMANCE_DROP = "performance_drop"
    ERROR_RATE_SPIKE = "error_rate_spike"
    USER_FEEDBACK_NEGATIVE = "user_feedback_negative"
    MANUAL = "manual"


# ==========================================
# 回滚状态枚举
# ==========================================

class RollbackStatus(str, Enum):
    """回滚状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ==========================================
# 回滚配置数据类
# ==========================================

@dataclass
class RollbackConfig:
    """回滚配置"""
    model_type: str
    trigger: RollbackTrigger
    threshold: float
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_type": self.model_type,
            "trigger": self.trigger.value,
            "threshold": self.threshold,
            "enabled": self.enabled,
        }


# ==========================================
# 回滚记录数据类
# ==========================================

@dataclass
class RollbackRecord:
    """回滚记录"""
    model_type: str
    from_version: str
    to_version: str
    reason: str
    status: RollbackStatus = RollbackStatus.COMPLETED
    trigger: RollbackTrigger = RollbackTrigger.MANUAL
    timestamp: datetime = field(default_factory=get_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_type": self.model_type,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "reason": self.reason,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "timestamp": self.timestamp.isoformat(),
        }


# ==========================================
# 自动回滚服务
# ==========================================

class RollbackService:
    """
    自动回滚服务

    提供完整的回滚管理：
    - 配置回滚条件
    - 检查是否需要回滚
    - 执行回滚操作
    - 记录回滚历史
    """

    def __init__(self):
        """初始化服务"""
        self._configs: Dict[str, RollbackConfig] = {}
        self._history: Dict[str, List[RollbackRecord]] = {}
        self._versioning_service = None

    def set_versioning_service(self, versioning_service):
        """
        设置版本管理服务

        Args:
            versioning_service: 版本管理服务实例
        """
        self._versioning_service = versioning_service

    def configure_rollback(
        self,
        model_type: str,
        trigger: RollbackTrigger,
        threshold: float,
    ):
        """
        配置回滚条件

        Args:
            model_type: 模型类型
            trigger: 触发条件
            threshold: 阈值
        """
        config = RollbackConfig(
            model_type=model_type,
            trigger=trigger,
            threshold=threshold,
        )

        self._configs[f"{model_type}:{trigger.value}"] = config

        log.info(f"[RollbackService] 配置回滚: {model_type}, trigger={trigger.value}, threshold={threshold}")

    def check_rollback_needed(
        self,
        model_type: str,
        current_performance: Optional[float] = None,
        baseline_performance: Optional[float] = None,
        error_rate: Optional[float] = None,
    ) -> bool:
        """
        检查是否需要回滚

        Args:
            model_type: 模型类型
            current_performance: 当前性能
            baseline_performance: 基准性能
            error_rate: 错误率

        Returns:
            是否需要回滚
        """
        # 检查性能下降触发
        perf_config_key = f"{model_type}:{RollbackTrigger.PERFORMANCE_DROP.value}"
        if perf_config_key in self._configs:
            config = self._configs[perf_config_key]
            if config.enabled and current_performance is not None and baseline_performance is not None:
                drop_rate = (baseline_performance - current_performance) / baseline_performance
                if drop_rate >= config.threshold:
                    log.info(f"[RollbackService] 性能下降触发回滚: {model_type}, drop={drop_rate:.2%}")
                    return True

        # 检查错误率飙升触发
        error_config_key = f"{model_type}:{RollbackTrigger.ERROR_RATE_SPIKE.value}"
        if error_config_key in self._configs:
            config = self._configs[error_config_key]
            if config.enabled and error_rate is not None:
                if error_rate >= config.threshold:
                    log.info(f"[RollbackService] 错误率飙升触发回滚: {model_type}, rate={error_rate:.2%}")
                    return True

        return False

    def execute_rollback(
        self,
        model_type: str,
        from_version: str,
        to_version: str,
        reason: str,
        trigger: RollbackTrigger = RollbackTrigger.MANUAL,
    ) -> RollbackRecord:
        """
        执行回滚

        Args:
            model_type: 模型类型
            from_version: 源版本
            to_version: 目标版本
            reason: 回滚原因
            trigger: 触发类型

        Returns:
            回滚记录
        """
        # 验证版本存在
        if self._versioning_service:
            try:
                # 检查目标版本是否存在
                history = self._versioning_service.get_version_history(model_type)
                version_exists = any(v.version == to_version for v in history)
                if not version_exists:
                    raise ValueError(f"Target version '{to_version}' not found for {model_type}")
            except Exception as e:
                raise ValueError(f"Version validation failed: {e}")

        # 创建回滚记录
        record = RollbackRecord(
            model_type=model_type,
            from_version=from_version,
            to_version=to_version,
            reason=reason,
            status=RollbackStatus.IN_PROGRESS,
            trigger=trigger,
        )

        try:
            # 更新活跃版本
            if self._versioning_service:
                self._versioning_service.set_active_version(model_type, to_version)

            # 标记完成
            record.status = RollbackStatus.COMPLETED

            # 记录历史
            if model_type not in self._history:
                self._history[model_type] = []
            self._history[model_type].append(record)

            log.info(f"[RollbackService] 回滚完成: {model_type} {from_version} -> {to_version}")

        except Exception as e:
            record.status = RollbackStatus.FAILED
            log.error(f"[RollbackService] 回滚失败: {e}")
            raise

        return record

    def get_rollback_history(
        self,
        model_type: str,
    ) -> List[RollbackRecord]:
        """
        获取回滚历史

        Args:
            model_type: 模型类型

        Returns:
            回滚记录列表
        """
        return self._history.get(model_type, [])

    def auto_rollback_if_needed(
        self,
        model_type: str,
        current_performance: Optional[float] = None,
        baseline_performance: Optional[float] = None,
        error_rate: Optional[float] = None,
    ) -> Optional[RollbackRecord]:
        """
        检查并执行自动回滚

        Args:
            model_type: 模型类型
            current_performance: 当前性能
            baseline_performance: 基准性能
            error_rate: 错误率

        Returns:
            回滚记录（如果执行了回滚）
        """
        if not self.check_rollback_needed(
            model_type,
            current_performance,
            baseline_performance,
            error_rate,
        ):
            return None

        # 获取当前版本和历史版本
        if not self._versioning_service:
            log.warning("[RollbackService] 无法执行自动回滚：版本服务未设置")
            return None

        current_version = self._versioning_service.get_active_version(model_type)
        if not current_version:
            log.warning(f"[RollbackService] 无法执行自动回滚：未找到活跃版本 {model_type}")
            return None

        history = self._versioning_service.get_version_history(model_type)
        if len(history) < 2:
            log.warning(f"[RollbackService] 无法执行自动回滚：版本历史不足 {model_type}")
            return None

        # 找到上一个版本
        previous_version = None
        for i, v in enumerate(history):
            if v.version == current_version.version and i > 0:
                previous_version = history[i - 1]
                break

        if not previous_version:
            log.warning(f"[RollbackService] 无法执行自动回滚：未找到回退版本 {model_type}")
            return None

        # 执行回滚
        return self.execute_rollback(
            model_type=model_type,
            from_version=current_version.version,
            to_version=previous_version.version,
            reason="Automatic rollback due to performance degradation",
            trigger=RollbackTrigger.PERFORMANCE_DROP,
        )


# ==========================================
# 导出
# ==========================================

__all__ = [
    "RollbackTrigger",
    "RollbackStatus",
    "RollbackConfig",
    "RollbackRecord",
    "RollbackService",
]