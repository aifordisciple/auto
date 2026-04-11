"""
模型版本管理服务

提供模型版本的生命周期管理：
1. 版本创建和存储
2. 版本历史追踪
3. 版本切换和状态管理
4. 版本配置比较
5. 性能指标记录

设计原则：
- 语义化版本号管理
- 版本状态流转验证
- 配置差异比较
- 性能指标追踪
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 模型类型枚举
# ==========================================

class ModelType(str, Enum):
    """模型类型"""
    RECOMMENDATION = "recommendation"
    PARAMETER_INFERENCE = "parameter_inference"
    WEIGHT_OPTIMIZATION = "weight_optimization"


# ==========================================
# 版本状态枚举
# ==========================================

class VersionStatus(str, Enum):
    """版本状态"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


# ==========================================
# 模型版本数据类
# ==========================================

@dataclass
class ModelVersion:
    """模型版本"""
    model_type: ModelType
    version: str
    config: Dict[str, Any]
    description: str = ""
    status: VersionStatus = VersionStatus.ACTIVE
    created_at: datetime = field(default_factory=get_utc_now)
    performance_metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_type": self.model_type.value,
            "version": self.version,
            "config": self.config,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "performance_metrics": self.performance_metrics,
        }


# ==========================================
# 模型版本管理服务
# ==========================================

class ModelVersioningService:
    """
    模型版本管理服务

    提供完整的版本生命周期管理：
    - 创建版本
    - 查询历史
    - 切换活跃版本
    - 比较配置差异
    """

    def __init__(self):
        """初始化服务"""
        # 存储结构: {model_type: {version: ModelVersion}}
        self._versions: Dict[ModelType, Dict[str, ModelVersion]] = {}
        # 活跃版本: {model_type: version}
        self._active_versions: Dict[ModelType, str] = {}

    def create_version(
        self,
        model_type: ModelType,
        version: str,
        config: Dict[str, Any],
        description: str = "",
    ) -> ModelVersion:
        """
        创建模型版本

        Args:
            model_type: 模型类型
            version: 版本号（语义化）
            config: 配置字典
            description: 版本描述

        Returns:
            创建的版本对象
        """
        # 初始化模型类型的版本存储
        if model_type not in self._versions:
            self._versions[model_type] = {}

        # 检查版本是否已存在
        if version in self._versions[model_type]:
            raise ValueError(f"Version '{version}' already exists for {model_type.value}")

        # 创建版本
        model_version = ModelVersion(
            model_type=model_type,
            version=version,
            config=config,
            description=description,
            status=VersionStatus.ACTIVE,
        )

        self._versions[model_type][version] = model_version

        log.info(f"[ModelVersioning] 创建版本: {model_type.value}@{version}")
        return model_version

    def get_version(
        self,
        model_type: ModelType,
        version: str,
    ) -> ModelVersion:
        """
        获取指定版本

        Args:
            model_type: 模型类型
            version: 版本号

        Returns:
            版本对象
        """
        if model_type not in self._versions:
            raise ValueError(f"No versions found for {model_type.value}")

        if version not in self._versions[model_type]:
            raise ValueError(f"Version '{version}' not found for {model_type.value}")

        return self._versions[model_type][version]

    def get_version_history(
        self,
        model_type: ModelType,
    ) -> List[ModelVersion]:
        """
        获取版本历史

        Args:
            model_type: 模型类型

        Returns:
            版本列表（按版本号排序）
        """
        if model_type not in self._versions:
            return []

        # 按版本号排序
        versions = list(self._versions[model_type].values())
        versions.sort(key=lambda v: self._parse_version(v.version))

        return versions

    def _parse_version(self, version: str) -> tuple:
        """解析版本号为元组用于排序"""
        try:
            parts = version.split(".")
            return tuple(int(p) for p in parts)
        except ValueError:
            return (0, 0, 0)

    def get_active_version(
        self,
        model_type: ModelType,
    ) -> Optional[ModelVersion]:
        """
        获取当前活跃版本

        Args:
            model_type: 模型类型

        Returns:
            活跃版本对象
        """
        if model_type not in self._active_versions:
            # 如果没有设置活跃版本，返回最新创建的版本
            history = self.get_version_history(model_type)
            if history:
                return history[-1]
            return None

        version = self._active_versions[model_type]
        return self._versions[model_type].get(version)

    def set_active_version(
        self,
        model_type: ModelType,
        version: str,
    ):
        """
        设置活跃版本

        Args:
            model_type: 模型类型
            version: 版本号
        """
        # 验证版本存在
        if model_type not in self._versions:
            raise ValueError(f"No versions found for {model_type.value}")

        if version not in self._versions[model_type]:
            raise ValueError(f"Version '{version}' not found for {model_type.value}")

        # 获取当前活跃版本并标记为 deprecated
        current_active = self._active_versions.get(model_type)
        if current_active and current_active in self._versions[model_type]:
            self._versions[model_type][current_active].status = VersionStatus.DEPRECATED

        # 设置新的活跃版本
        self._active_versions[model_type] = version
        self._versions[model_type][version].status = VersionStatus.ACTIVE

        log.info(f"[ModelVersioning] 切换活跃版本: {model_type.value}@{version}")

    def compare_versions(
        self,
        model_type: ModelType,
        version1: str,
        version2: str,
    ) -> Dict[str, Any]:
        """
        比较两个版本的配置差异

        Args:
            model_type: 模型类型
            version1: 版本1
            version2: 版本2

        Returns:
            差异字典
        """
        v1 = self.get_version(model_type, version1)
        v2 = self.get_version(model_type, version2)

        config1 = v1.config
        config2 = v2.config

        # 找出所有键
        all_keys = set(config1.keys()) | set(config2.keys())

        added = []
        removed = []
        changed = []

        for key in all_keys:
            if key not in config1:
                added.append(key)
            elif key not in config2:
                removed.append(key)
            elif config1[key] != config2[key]:
                changed.append(key)

        return {
            "version1": version1,
            "version2": version2,
            "added": added,
            "removed": removed,
            "changed": changed,
            "config1": config1,
            "config2": config2,
        }

    def record_performance(
        self,
        model_type: ModelType,
        version: str,
        metrics: Dict[str, float],
    ):
        """
        记录版本性能指标

        Args:
            model_type: 模型类型
            version: 版本号
            metrics: 性能指标字典
        """
        model_version = self.get_version(model_type, version)
        model_version.performance_metrics.update(metrics)

        log.info(f"[ModelVersioning] 记录性能: {model_type.value}@{version}, metrics={metrics}")

    def get_performance_metrics(
        self,
        model_type: ModelType,
        version: str,
    ) -> Dict[str, float]:
        """
        获取版本性能指标

        Args:
            model_type: 模型类型
            version: 版本号

        Returns:
            性能指标字典
        """
        model_version = self.get_version(model_type, version)
        return model_version.performance_metrics

    def archive_version(
        self,
        model_type: ModelType,
        version: str,
    ):
        """
        归档版本

        Args:
            model_type: 模型类型
            version: 版本号
        """
        model_version = self.get_version(model_type, version)
        model_version.status = VersionStatus.ARCHIVED

        log.info(f"[ModelVersioning] 归档版本: {model_type.value}@{version}")


# ==========================================
# 导出
# ==========================================

__all__ = [
    "ModelType",
    "VersionStatus",
    "ModelVersion",
    "ModelVersioningService",
]