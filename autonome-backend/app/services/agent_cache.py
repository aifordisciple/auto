"""
Agent 缓存服务

性能优化：缓存已构建的 Agent 实例，避免每次请求都重新构建

缓存策略：
- 使用 LRU 内存缓存（Agent 对象无法序列化到 Redis）
- 基于 (user_id, project_id, model_name) 作为缓存键
- TTL 1 小时，避免内存泄漏
- 技能更新时自动失效

@created: 2026-04-08
@author: AI Assistant
"""
import threading
import time
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from dataclasses import dataclass
from loguru import logger


@dataclass
class AgentCacheEntry:
    """Agent 缓存条目"""
    agent: Any  # 编译后的 LangGraph Agent
    created_at: float
    expires_at: float
    user_id: int
    project_id: str
    model_name: str
    skill_count: int  # 构建时的技能数量，用于判断是否需要重建


class AgentCache:
    """
    Agent LRU 缓存

    特性：
    - 线程安全
    - LRU 淘汰策略
    - TTL 自动过期
    - 容量限制
    - 技能变化时自动失效
    """

    def __init__(self, capacity: int = 50, default_ttl: int = 3600):
        """
        初始化 Agent 缓存

        Args:
            capacity: 最大容量（默认 50 个 Agent）
            default_ttl: 默认 TTL（秒，默认 1 小时）
        """
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, AgentCacheEntry] = OrderedDict()
        self.lock = threading.RLock()

        # 统计
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _make_key(self, user_id: int, project_id: str, model_name: str) -> str:
        """生成缓存键"""
        return f"agent:{user_id}:{project_id}:{model_name}"

    def _is_expired(self, entry: AgentCacheEntry) -> bool:
        """检查缓存条目是否过期"""
        return time.time() > entry.expires_at

    def get(self, user_id: int, project_id: str, model_name: str) -> Optional[Any]:
        """
        获取缓存的 Agent

        Args:
            user_id: 用户 ID
            project_id: 项目 ID
            model_name: 模型名称

        Returns:
            Agent 实例，不存在或已过期返回 None
        """
        key = self._make_key(user_id, project_id, model_name)

        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None

            entry = self.cache[key]

            # 检查过期
            if self._is_expired(entry):
                del self.cache[key]
                self.evictions += 1
                self.misses += 1
                logger.debug(f"[AgentCache] 缓存已过期: {key}")
                return None

            # LRU: 移到最后（最近使用）
            self.cache.move_to_end(key)
            self.hits += 1

            logger.info(f"[AgentCache] 缓存命中: {key}, 剩余 TTL: {int(entry.expires_at - time.time())}s")
            return entry.agent

    def set(
        self,
        user_id: int,
        project_id: str,
        model_name: str,
        agent: Any,
        skill_count: int,
        ttl: Optional[int] = None
    ) -> None:
        """
        缓存 Agent 实例

        Args:
            user_id: 用户 ID
            project_id: 项目 ID
            model_name: 模型名称
            agent: Agent 实例
            skill_count: 当前技能数量
            ttl: 过期时间（秒），None 使用默认值
        """
        key = self._make_key(user_id, project_id, model_name)
        expires_at = time.time() + (ttl or self.default_ttl)

        with self.lock:
            # 如果已存在，更新并移到最后
            if key in self.cache:
                self.cache[key] = AgentCacheEntry(
                    agent=agent,
                    created_at=time.time(),
                    expires_at=expires_at,
                    user_id=user_id,
                    project_id=project_id,
                    model_name=model_name,
                    skill_count=skill_count
                )
                self.cache.move_to_end(key)
                logger.debug(f"[AgentCache] 更新缓存: {key}")
                return

            # 检查容量，淘汰最老的
            while len(self.cache) >= self.capacity:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.evictions += 1
                logger.debug(f"[AgentCache] 淘汰最老缓存: {oldest_key}")

            self.cache[key] = AgentCacheEntry(
                agent=agent,
                created_at=time.time(),
                expires_at=expires_at,
                user_id=user_id,
                project_id=project_id,
                model_name=model_name,
                skill_count=skill_count
            )

            logger.info(f"[AgentCache] 缓存 Agent: {key}, TTL={ttl or self.default_ttl}s")

    def invalidate_user(self, user_id: int) -> int:
        """
        失效指定用户的所有 Agent 缓存

        用于技能更新后自动失效

        Args:
            user_id: 用户 ID

        Returns:
            删除的条目数
        """
        with self.lock:
            keys_to_delete = [
                k for k in self.cache.keys()
                if k.startswith(f"agent:{user_id}:")
            ]

            for key in keys_to_delete:
                del self.cache[key]

            if keys_to_delete:
                logger.info(f"[AgentCache] 失效用户 {user_id} 的 {len(keys_to_delete)} 个缓存")

            return len(keys_to_delete)

    def invalidate_project(self, user_id: int, project_id: str) -> int:
        """
        失效指定项目的 Agent 缓存

        Args:
            user_id: 用户 ID
            project_id: 项目 ID

        Returns:
            是否成功删除
        """
        with self.lock:
            keys_to_delete = [
                k for k in self.cache.keys()
                if k.startswith(f"agent:{user_id}:{project_id}:")
            ]

            for key in keys_to_delete:
                del self.cache[key]

            if keys_to_delete:
                logger.info(f"[AgentCache] 失效项目 {project_id} 的 {len(keys_to_delete)} 个缓存")

            return len(keys_to_delete)

    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"[AgentCache] 清空所有缓存: {count} 个")

    def cleanup_expired(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        with self.lock:
            expired_keys = [
                k for k, v in self.cache.items()
                if self._is_expired(v)
            ]

            for key in expired_keys:
                del self.cache[key]
                self.evictions += 1

            if expired_keys:
                logger.debug(f"[AgentCache] 清理过期缓存: {len(expired_keys)} 个")

            return len(expired_keys)

    def size(self) -> int:
        """当前缓存大小"""
        return len(self.cache)

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0

        return {
            "size": self.size(),
            "capacity": self.capacity,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(hit_rate, 2),
            "evictions": self.evictions,
        }


# ==========================================
# 全局单例
# ==========================================

_agent_cache: Optional[AgentCache] = None
_cache_lock = threading.Lock()


def get_agent_cache() -> AgentCache:
    """
    获取 Agent 缓存单例

    Returns:
        AgentCache 实例
    """
    global _agent_cache

    if _agent_cache is None:
        with _cache_lock:
            if _agent_cache is None:
                _agent_cache = AgentCache()
                logger.info("[AgentCache] Agent 缓存服务已初始化")

    return _agent_cache


def invalidate_agent_cache(user_id: int, project_id: Optional[str] = None) -> int:
    """
    失效 Agent 缓存（供外部调用）

    在技能创建/更新/删除时调用，确保 Agent 使用最新的技能列表

    Args:
        user_id: 用户 ID
        project_id: 项目 ID（可选，不传则失效用户所有缓存）

    Returns:
        删除的条目数
    """
    cache = get_agent_cache()

    if project_id:
        return cache.invalidate_project(user_id, project_id)
    else:
        return cache.invalidate_user(user_id)