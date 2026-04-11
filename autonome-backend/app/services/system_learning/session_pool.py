"""
会话池管理器 - 管理待处理的成功会话

功能:
1. 收集成功会话（confidence > 0.8）
2. 过滤无效会话
3. 提供批量获取接口
4. 自动清理过期会话

这是系统学习层的数据收集组件，负责从 SuccessEvaluator 收集
高质量会话，为后续方法提取提供数据源。

使用方式:
    from app.services.system_learning.session_pool import get_session_pool

    pool = get_session_pool()
    pool.add_session(session_id, confidence, user_id, project_id)
    pending_ids = pool.get_pending_sessions()
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path

from app.core.logger import log


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class PendingSession:
    """
    待处理会话数据结构

    存储成功会话的关键信息，用于后续方法提取。

    属性:
        session_id: 会话唯一标识符
        confidence: 成功置信度 (0.0-1.0)
        user_id: 用户ID
        project_id: 项目ID
        message_count: 消息数量
        has_code: 是否包含代码执行
        evaluated_at: 评估时间 (ISO格式)
        added_at: 加入池的时间 (ISO格式)

    示例:
        >>> session = PendingSession(
        ...     session_id="chat_abc123",
        ...     confidence=0.92,
        ...     user_id=1,
        ...     project_id=5,
        ...     message_count=12,
        ...     has_code=True,
        ...     evaluated_at="2024-01-15T10:30:00Z"
        ... )
    """
    session_id: str
    confidence: float
    user_id: int
    project_id: int
    message_count: int = 0
    has_code: bool = False
    evaluated_at: str = ""
    added_at: str = ""

    def __post_init__(self):
        """初始化后处理：自动设置添加时间"""
        if not self.added_at:
            self.added_at = datetime.now(timezone.utc).isoformat()


# ============================================================================
# 会话池配置
# ============================================================================

class SessionPoolConfig:
    """
    会话池配置

    定义会话池的行为参数：
    - MIN_CONFIDENCE: 最低置信度阈值，低于此值的会话不加入池
    - MIN_MESSAGES: 最小消息数量，过短的会话可能不包含足够信息
    - EXPIRE_DAYS: 过期天数，超过此时间的会话将被清理
    - MAX_POOL_SIZE: 最大池容量，防止内存溢出
    """

    # 最低置信度阈值
    MIN_CONFIDENCE: float = 0.8

    # 最小消息数量
    MIN_MESSAGES: int = 3

    # 过期天数
    EXPIRE_DAYS: int = 7

    # 最大池容量
    MAX_POOL_SIZE: int = 10000


# ============================================================================
# 会话池管理器
# ============================================================================

class SessionPool:
    """
    会话池管理器

    核心职责:
    1. 收集高质量会话 (confidence > 0.8, messages >= 3)
    2. 按置信度排序，优先处理高质量会话
    3. 定期清理过期会话
    4. 提供统计信息用于监控

    存储方式:
    - JSON 文件存储，路径: system_skillbank/pending/session_pool.json
    - 文件结构:
      {
        "sessions": {
          "session_id_1": { ... PendingSession ... },
          "session_id_2": { ... PendingSession ... }
        },
        "metadata": {
          "last_updated": "2024-01-15T10:30:00Z",
          "total_count": 100,
          "processed_count": 50
        }
      }

    使用示例:
        >>> pool = SessionPool()
        >>> pool.add_session("chat_001", 0.92, user_id=1, project_id=5)
        True
        >>> pool.get_pending_sessions(limit=10)
        ["chat_001"]
        >>> pool.mark_processed("chat_001")
    """

    def __init__(self, pool_dir: Optional[str] = None):
        """
        初始化会话池

        Args:
            pool_dir: 池存储目录，默认为 system_skillbank/pending/
        """
        if pool_dir:
            self.pool_dir = Path(pool_dir)
        else:
            # 默认路径：backend/system_skillbank/pending/
            backend_dir = Path(__file__).parent.parent.parent.parent
            self.pool_dir = backend_dir / "system_skillbank" / "pending"

        self.pool_file = self.pool_dir / "session_pool.json"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """确保存储目录存在"""
        self.pool_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f"会话池目录已确认: {self.pool_dir}")

    def _load_pool(self) -> Dict[str, Any]:
        """
        加载池数据

        Returns:
            Dict: 池数据，包含 sessions 和 metadata
        """
        if not self.pool_file.exists():
            log.debug("池文件不存在，返回空数据")
            return {"sessions": {}, "metadata": {}}

        try:
            with open(self.pool_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                log.debug(f"成功加载池数据: {len(data.get('sessions', {}))} 个会话")
                return data
        except json.JSONDecodeError as e:
            log.warning(f"池文件 JSON 解析失败: {e}，返回空数据")
            return {"sessions": {}, "metadata": {}}
        except Exception as e:
            log.warning(f"加载会话池失败: {e}")
            return {"sessions": {}, "metadata": {}}

    def _save_pool(self, data: Dict[str, Any]) -> None:
        """
        保存池数据

        Args:
            data: 池数据
        """
        try:
            with open(self.pool_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug("池数据已保存")
        except Exception as e:
            log.error(f"保存会话池失败: {e}")

    def add_session(
        self,
        session_id: str,
        confidence: float,
        user_id: int,
        project_id: int,
        message_count: int = 0,
        has_code: bool = False
    ) -> bool:
        """
        添加会话到池中

        入池条件:
        - confidence >= 0.8
        - message_count >= 3

        Args:
            session_id: 会话ID
            confidence: 置信度
            user_id: 用户ID
            project_id: 项目ID
            message_count: 消息数量
            has_code: 是否包含代码

        Returns:
            bool: 是否成功添加
        """
        # -------------------------------------------------------------------------
        # 1. 验证入池条件
        # -------------------------------------------------------------------------
        if confidence < SessionPoolConfig.MIN_CONFIDENCE:
            log.debug(f"会话 {session_id} 置信度不足: {confidence} < {SessionPoolConfig.MIN_CONFIDENCE}")
            return False

        if message_count < SessionPoolConfig.MIN_MESSAGES:
            log.debug(f"会话 {session_id} 消息数不足: {message_count} < {SessionPoolConfig.MIN_MESSAGES}")
            return False

        # -------------------------------------------------------------------------
        # 2. 加载现有数据
        # -------------------------------------------------------------------------
        data = self._load_pool()

        # -------------------------------------------------------------------------
        # 3. 检查是否已存在
        # -------------------------------------------------------------------------
        if session_id in data["sessions"]:
            log.debug(f"会话 {session_id} 已在池中，跳过")
            return False

        # -------------------------------------------------------------------------
        # 4. 检查池容量
        # -------------------------------------------------------------------------
        current_count = len(data["sessions"])
        if current_count >= SessionPoolConfig.MAX_POOL_SIZE:
            log.warning(f"会话池已满 ({current_count}/{SessionPoolConfig.MAX_POOL_SIZE})，跳过添加")
            return False

        # -------------------------------------------------------------------------
        # 5. 创建并添加会话
        # -------------------------------------------------------------------------
        pending = PendingSession(
            session_id=session_id,
            confidence=confidence,
            user_id=user_id,
            project_id=project_id,
            message_count=message_count,
            has_code=has_code,
            evaluated_at=datetime.now(timezone.utc).isoformat()
        )

        data["sessions"][session_id] = asdict(pending)
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["metadata"]["total_count"] = len(data["sessions"])

        self._save_pool(data)
        log.info(f"会话 {session_id} 已添加到学习池 (置信度: {confidence:.2f}, 消息数: {message_count})")
        return True

    def get_pending_sessions(self, limit: int = 100) -> List[str]:
        """
        获取待处理会话ID列表

        按置信度降序排序，优先返回高质量会话。

        Args:
            limit: 最大返回数量

        Returns:
            List[str]: 会话ID列表
        """
        data = self._load_pool()
        sessions = data.get("sessions", {})

        if not sessions:
            return []

        # 按置信度降序排序
        sorted_sessions = sorted(
            sessions.items(),
            key=lambda x: x[1].get("confidence", 0),
            reverse=True
        )

        result = [s[0] for s in sorted_sessions[:limit]]
        log.debug(f"获取待处理会话: {len(result)} 个")
        return result

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话详情

        Args:
            session_id: 会话ID

        Returns:
            Optional[Dict]: 会话信息，不存在则返回 None
        """
        data = self._load_pool()
        info = data.get("sessions", {}).get(session_id)
        if info:
            log.debug(f"获取会话 {session_id} 详情")
        else:
            log.debug(f"会话 {session_id} 不存在")
        return info

    def mark_processed(self, session_id: str, extracted: bool = True) -> None:
        """
        标记会话已处理

        从池中移除已处理的会话，更新统计数据。

        Args:
            session_id: 会话ID
            extracted: 是否成功提取方法论
        """
        data = self._load_pool()

        if session_id in data["sessions"]:
            del data["sessions"][session_id]
            data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
            data["metadata"]["total_count"] = len(data["sessions"])
            data["metadata"]["processed_count"] = data["metadata"].get("processed_count", 0) + 1

            if extracted:
                data["metadata"]["extracted_count"] = data["metadata"].get("extracted_count", 0) + 1

            self._save_pool(data)
            log.info(f"会话 {session_id} 已标记为已处理 (提取: {extracted})")
        else:
            log.debug(f"会话 {session_id} 不在池中")

    def cleanup_expired(self, days: int = None) -> int:
        """
        清理过期未处理会话

        Args:
            days: 过期天数，默认使用配置值

        Returns:
            int: 清理数量
        """
        days = days or SessionPoolConfig.EXPIRE_DAYS
        data = self._load_pool()
        sessions = data.get("sessions", {})

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        expired = []

        for session_id, info in sessions.items():
            # 优先使用 added_at，若无则使用 evaluated_at
            added_at = info.get("added_at", info.get("evaluated_at", ""))
            try:
                added_time = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
                if added_time < cutoff:
                    expired.append(session_id)
            except (ValueError, TypeError):
                # 时间解析失败，跳过此会话
                log.warning(f"会话 {session_id} 时间格式无效: {added_at}")

        for session_id in expired:
            del data["sessions"][session_id]

        if expired:
            data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
            data["metadata"]["total_count"] = len(data["sessions"])
            data["metadata"]["expired_count"] = data["metadata"].get("expired_count", 0) + len(expired)
            self._save_pool(data)
            log.info(f"清理了 {len(expired)} 个过期会话 (>{days}天)")

        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取池统计信息

        Returns:
            Dict: 统计信息，包含:
                - total: 当前总数
                - avg_confidence: 平均置信度
                - by_user: 按用户分布
                - oldest: 最老会话时间
                - processed_count: 已处理总数
                - extracted_count: 已提取总数
        """
        data = self._load_pool()
        sessions = data.get("sessions", {})
        metadata = data.get("metadata", {})

        if not sessions:
            return {
                "total": 0,
                "avg_confidence": 0.0,
                "by_user": {},
                "by_project": {},
                "oldest": None,
                "processed_count": metadata.get("processed_count", 0),
                "extracted_count": metadata.get("extracted_count", 0),
                "expired_count": metadata.get("expired_count", 0)
            }

        # 计算统计信息
        confidences = [s.get("confidence", 0) for s in sessions.values()]
        by_user: Dict[int, int] = {}
        by_project: Dict[int, int] = {}
        oldest: Optional[str] = None

        for session_id, info in sessions.items():
            # 按用户统计
            user_id = info.get("user_id", 0)
            by_user[user_id] = by_user.get(user_id, 0) + 1

            # 按项目统计
            project_id = info.get("project_id", 0)
            by_project[project_id] = by_project.get(project_id, 0) + 1

            # 最老会话
            added = info.get("added_at", "")
            if oldest is None or (added and added < oldest):
                oldest = added

        return {
            "total": len(sessions),
            "avg_confidence": sum(confidences) / len(confidences) if confidences else 0.0,
            "max_confidence": max(confidences) if confidences else 0.0,
            "min_confidence": min(confidences) if confidences else 0.0,
            "by_user": by_user,
            "by_project": by_project,
            "oldest": oldest,
            "processed_count": metadata.get("processed_count", 0),
            "extracted_count": metadata.get("extracted_count", 0),
            "expired_count": metadata.get("expired_count", 0)
        }

    def clear_all(self) -> int:
        """
        清空所有会话

        用于测试或重置场景。

        Returns:
            int: 清除数量
        """
        data = self._load_pool()
        count = len(data.get("sessions", {}))

        data["sessions"] = {}
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["metadata"]["total_count"] = 0

        self._save_pool(data)
        log.info(f"已清空会话池: {count} 个会话")
        return count


# ============================================================================
# 全局单例管理
# ============================================================================

_pool: Optional[SessionPool] = None


def get_session_pool() -> SessionPool:
    """
    获取会话池单例

    Returns:
        SessionPool: 会话池管理器实例

    使用示例:
        >>> from app.services.system_learning.session_pool import get_session_pool
        >>> pool = get_session_pool()
        >>> pool.add_session("chat_001", 0.92, 1, 5)
    """
    global _pool
    if _pool is None:
        _pool = SessionPool()
        log.info("会话池单例已初始化")
    return _pool


def reset_session_pool() -> None:
    """
    重置会话池单例

    用于测试或需要重新初始化的场景。
    """
    global _pool
    _pool = None
    log.debug("会话池单例已重置")