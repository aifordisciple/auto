"""
AUTONOME 缓存服务模块

三层缓存架构：
- L1: 内存缓存 (LRU, 热点数据, TTL=5-10min)
- L2: Redis缓存 (共享缓存, TTL=1-24h)
- L3: 数据库 (持久化)

缓存命中目标：
- 技能列表: 80%+
- 推荐结果: 60%+
- 向量嵌入: 95%+

@created: 2026-03-31
@author: AI Assistant
"""

import json
import time
import hashlib
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict, Callable, TypeVar, Generic
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime
import redis
from app.core.logger import log

from app.core.config import settings

T = TypeVar('T')


# ==========================================
# 缓存统计数据结构
# ==========================================

@dataclass
class CacheStats:
    """缓存统计数据"""
    hits: int = 0
    misses: int = 0
    l1_hits: int = 0
    l2_hits: int = 0
    l3_hits: int = 0  # 数据库查询
    evictions: int = 0
    total_requests: int = 0
    total_latency_ms: float = 0.0

    def hit_rate(self) -> float:
        """计算缓存命中率"""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100

    def avg_latency_ms(self) -> float:
        """计算平均延迟"""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "l1_hits": self.l1_hits,
            "l2_hits": self.l2_hits,
            "l3_hits": self.l3_hits,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate(), 2),
            "avg_latency_ms": round(self.avg_latency_ms(), 2)
        }


# ==========================================
# L1 内存缓存 (LRU)
# ==========================================

class LRUCache(Generic[T]):
    """
    LRU 内存缓存实现

    特性：
    - 线程安全
    - 支持 TTL 自动过期
    - 支持 LRU 淘汰策略
    - 容量限制
    """

    def __init__(self, capacity: int = 1000, default_ttl: int = 300):
        """
        初始化 LRU 缓存

        Args:
            capacity: 最大容量
            default_ttl: 默认 TTL（秒）
        """
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, Dict] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = CacheStats()

    def _is_expired(self, item: Dict) -> bool:
        """检查缓存项是否过期"""
        if "expires_at" not in item:
            return False
        return time.time() > item["expires_at"]

    def get(self, key: str) -> Optional[T]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在或已过期返回 None
        """
        with self.lock:
            if key not in self.cache:
                self.stats.misses += 1
                self.stats.total_requests += 1
                return None

            item = self.cache[key]

            # 检查过期
            if self._is_expired(item):
                del self.cache[key]
                self.stats.misses += 1
                self.stats.evictions += 1
                self.stats.total_requests += 1
                return None

            # LRU: 移到最后（最近使用）
            self.cache.move_to_end(key)
            self.stats.hits += 1
            self.stats.l1_hits += 1
            self.stats.total_requests += 1
            return item["value"]

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值
        """
        with self.lock:
            expires_at = time.time() + (ttl or self.default_ttl)

            # 如果已存在，更新并移到最后
            if key in self.cache:
                self.cache[key] = {"value": value, "expires_at": expires_at}
                self.cache.move_to_end(key)
                return

            # 检查容量，淘汰最老的
            while len(self.cache) >= self.capacity:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats.evictions += 1
                log.debug(f"[L1Cache] 淘汰最老缓存项: {oldest_key}")

            self.cache[key] = {"value": value, "expires_at": expires_at}

    def delete(self, key: str) -> bool:
        """
        删除缓存项

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def clear(self) -> None:
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            log.info("[L1Cache] 缓存已清空")

    def cleanup_expired(self) -> int:
        """
        清理过期缓存项

        Returns:
            清理的项数
        """
        with self.lock:
            expired_keys = [
                k for k, v in self.cache.items()
                if self._is_expired(v)
            ]
            for key in expired_keys:
                del self.cache[key]
                self.stats.evictions += 1

            if expired_keys:
                log.debug(f"[L1Cache] 清理过期缓存: {len(expired_keys)} 项")

            return len(expired_keys)

    def size(self) -> int:
        """当前缓存大小"""
        return len(self.cache)

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            **self.stats.to_dict(),
            "size": self.size(),
            "capacity": self.capacity
        }


# ==========================================
# L2 Redis 缓存
# ==========================================

class RedisCache:
    """
    Redis 缓存实现

    特性：
    - 跨进程共享
    - 支持持久化
    - 支持 TTL
    """

    def __init__(self, host: str = None, port: int = None, db: int = 2):
        """
        初始化 Redis 缓存

        Args:
            host: Redis 主机
            port: Redis 端口
            db: Redis 数据库编号（使用 db=2 区分缓存）
        """
        self.host = host or settings.REDIS_HOST
        self.port = port or settings.REDIS_PORT
        self.db = db
        self.prefix = "autonome:cache:"
        self._client: Optional[redis.Redis] = None
        self.stats = CacheStats()
        self.lock = threading.RLock()

    def _get_client(self) -> redis.Redis:
        """获取 Redis 客户端（延迟初始化 + 连接池优化）"""
        if self._client is None:
            with self.lock:
                if self._client is None:
                    # 🚀 性能优化：使用连接池，避免频繁创建连接
                    pool = redis.ConnectionPool(
                        host=self.host,
                        port=self.port,
                        db=self.db,
                        decode_responses=True,
                        max_connections=50,  # 最大连接数
                        socket_timeout=5,  # Socket 超时（秒）
                        socket_connect_timeout=5,  # 连接超时（秒）
                        retry_on_timeout=True,  # 超时重试
                        health_check_interval=30,  # 健康检查间隔（秒）
                    )
                    self._client = redis.Redis(connection_pool=pool)
                    log.info(f"[RedisCache] 连接池已初始化: host={self.host}, port={self.port}, db={self.db}")
        return self._client

    def _make_key(self, key: str) -> str:
        """生成带前缀的完整键"""
        return f"{self.prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值（已 JSON 解析）
        """
        client = self._get_client()
        full_key = self._make_key(key)

        start_time = time.time()

        try:
            value = client.get(full_key)

            latency = (time.time() - start_time) * 1000
            self.stats.total_latency_ms += latency
            self.stats.total_requests += 1

            if value is None:
                self.stats.misses += 1
                return None

            self.stats.hits += 1
            self.stats.l2_hits += 1
            return json.loads(value)

        except redis.RedisError as e:
            log.error(f"[RedisCache] 获取失败: {e}")
            self.stats.misses += 1
            self.stats.total_requests += 1
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（将被 JSON 序列化）
            ttl: 过期时间（秒）

        Returns:
            是否成功
        """
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            serialized = json.dumps(value, ensure_ascii=False)
            client.setex(full_key, ttl, serialized)
            log.debug(f"[RedisCache] 设置缓存: {full_key}, TTL={ttl}s")
            return True

        except redis.RedisError as e:
            log.error(f"[RedisCache] 设置失败: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        删除缓存项

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            result = client.delete(full_key)
            return result > 0
        except redis.RedisError as e:
            log.error(f"[RedisCache] 删除失败: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        删除匹配模式的缓存（使用 SCAN 安全迭代）

        Args:
            pattern: 键模式（不含前缀）

        Returns:
            删除的项数
        """
        client = self._get_client()
        full_pattern = self._make_key(pattern)

        try:
            # 🚨 使用 SCAN 替代 KEYS，避免阻塞 Redis
            # SCAN 是游标迭代，不会阻塞服务器
            deleted = 0
            cursor = 0
            batch_size = 100  # 每批处理的键数量

            while True:
                cursor, keys = client.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=batch_size
                )

                if keys:
                    deleted += client.delete(*keys)

                # cursor=0 表示迭代结束
                if cursor == 0:
                    break

            if deleted > 0:
                log.info(f"[RedisCache] 模式删除(SCAN): {pattern}, 删除 {deleted} 项")
            return deleted
        except redis.RedisError as e:
            log.error(f"[RedisCache] 模式删除失败: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        client = self._get_client()
        full_key = self._make_key(key)
        return client.exists(full_key) > 0

    def get_ttl(self, key: str) -> int:
        """获取键的剩余 TTL"""
        client = self._get_client()
        full_key = self._make_key(key)
        return client.ttl(full_key)

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return self.stats.to_dict()


# ==========================================
# 统一缓存服务（三层架构）
# ==========================================

class CacheService:
    """
    三层缓存服务

    查询顺序：L1 内存 → L2 Redis → L3 数据库
    写入顺序：L1 内存 → L2 Redis（可选）
    """

    # 缓存配置
    CACHE_CONFIGS = {
        # 技能列表缓存
        "skills:list": {
            "l1_capacity": 1000,
            "l1_ttl": 300,  # 5分钟
            "l2_ttl": 600,  # 10分钟
        },
        # 热门技能详情缓存
        "skills:detail": {
            "l1_capacity": 100,
            "l1_ttl": 600,  # 10分钟
            "l2_ttl": 1800,  # 30分钟
        },
        # 推荐结果缓存
        "recommend:result": {
            "l1_capacity": 500,
            "l1_ttl": 300,  # 5分钟
            "l2_ttl": 600,  # 10分钟
        },
        # 向量嵌入缓存（长期）
        "embedding:skill": {
            "l1_capacity": 500,
            "l1_ttl": 3600,  # 1小时
            "l2_ttl": 86400,  # 24小时
        },
        # 用户偏好缓存
        "user:preference": {
            "l1_capacity": 200,
            "l1_ttl": 1800,  # 30分钟
            "l2_ttl": 3600,  # 1小时
        },
    }

    def __init__(self):
        """初始化缓存服务"""
        # 创建各类型缓存实例
        self.l1_caches: Dict[str, LRUCache] = {}
        self.l2_cache = RedisCache()
        self.global_stats = CacheStats()

        # 初始化各类缓存
        for cache_type, config in self.CACHE_CONFIGS.items():
            self.l1_caches[cache_type] = LRUCache(
                capacity=config["l1_capacity"],
                default_ttl=config["l1_ttl"]
            )

        log.info("[CacheService] 缓存服务初始化完成")

    def _get_cache_type(self, key: str) -> str:
        """
        根据键名推断缓存类型

        Args:
            key: 缓存键

        Returns:
            缓存类型
        """
        if key.startswith("skills:list"):
            return "skills:list"
        elif key.startswith("skills:detail"):
            return "skills:detail"
        elif key.startswith("recommend"):
            return "recommend:result"
        elif key.startswith("embedding"):
            return "embedding:skill"
        elif key.startswith("user:pref"):
            return "user:preference"
        else:
            return "skills:list"  # 默认

    def get(self, key: str) -> Optional[Any]:
        """
        三层缓存查询

        Args:
            key: 缓存键

        Returns:
            缓存值
        """
        start_time = time.time()
        cache_type = self._get_cache_type(key)
        l1 = self.l1_caches.get(cache_type)

        # L1 查询
        if l1:
            value = l1.get(key)
            if value is not None:
                latency = (time.time() - start_time) * 1000
                self.global_stats.total_latency_ms += latency
                log.debug(f"[CacheService] L1命中: {key}, 延迟={latency:.2f}ms")
                return value

        # L2 查询
        value = self.l2_cache.get(key)
        if value is not None:
            latency = (time.time() - start_time) * 1000
            self.global_stats.total_latency_ms += latency

            # 回填 L1
            if l1:
                config = self.CACHE_CONFIGS.get(cache_type, {})
                l1.set(key, value, ttl=config.get("l1_ttl", 300))

            log.debug(f"[CacheService] L2命中: {key}, 延迟={latency:.2f}ms")
            return value

        # L3 未命中（需要调用方查询数据库）
        self.global_stats.misses += 1
        self.global_stats.total_requests += 1
        latency = (time.time() - start_time) * 1000
        self.global_stats.total_latency_ms += latency

        log.debug(f"[CacheService] 未命中: {key}, 延迟={latency:.2f}ms")
        return None

    def set(self, key: str, value: Any, cache_type: Optional[str] = None) -> None:
        """
        设置缓存（L1 + L2）

        Args:
            key: 缓存键
            value: 缓存值
            cache_type: 缓存类型（可选，自动推断）
        """
        cache_type = cache_type or self._get_cache_type(key)
        config = self.CACHE_CONFIGS.get(cache_type, {})

        # 设置 L1
        l1 = self.l1_caches.get(cache_type)
        if l1:
            l1.set(key, value, ttl=config.get("l1_ttl", 300))

        # 设置 L2
        self.l2_cache.set(key, value, ttl=config.get("l2_ttl", 3600))

        log.debug(f"[CacheService] 设置缓存: {key}")

    def delete(self, key: str) -> None:
        """
        删除缓存（L1 + L2）

        Args:
            key: 缓存键
        """
        cache_type = self._get_cache_type(key)

        # 删除 L1
        l1 = self.l1_caches.get(cache_type)
        if l1:
            l1.delete(key)

        # 删除 L2
        self.l2_cache.delete(key)

        log.debug(f"[CacheService] 删除缓存: {key}")

    def invalidate_pattern(self, pattern: str) -> int:
        """
        批量失效缓存

        Args:
            pattern: 键模式

        Returns:
            删除的项数
        """
        total_deleted = 0

        # 清理 L1
        for cache_type, l1 in self.l1_caches.items():
            # L1 不支持模式匹配，需要遍历删除
            keys_to_delete = []
            for key in list(l1.cache.keys()):
                if pattern in key or key.startswith(pattern):
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                l1.delete(key)
                total_deleted += 1

        # 清理 L2
        l2_deleted = self.l2_cache.delete_pattern(pattern)
        total_deleted += l2_deleted

        log.info(f"[CacheService] 批量失效缓存: {pattern}, 删除 {total_deleted} 项")
        return total_deleted

    def cleanup_expired(self) -> int:
        """
        清理所有过期缓存

        Returns:
            清理的项数
        """
        total = 0
        for l1 in self.l1_caches.values():
            total += l1.cleanup_expired()

        # Redis 自动过期，无需手动清理
        return total

    def get_stats(self) -> Dict:
        """
        获取全局缓存统计

        Returns:
            统计数据
        """
        l1_stats = {}
        for cache_type, l1 in self.l1_caches.items():
            l1_stats[cache_type] = l1.get_stats()

        return {
            "global": self.global_stats.to_dict(),
            "l1": l1_stats,
            "l2": self.l2_cache.get_stats(),
            "timestamp": datetime.now().isoformat()
        }

    def reset_stats(self) -> None:
        """重置统计数据"""
        self.global_stats = CacheStats()
        for l1 in self.l1_caches.values():
            l1.stats = CacheStats()
        self.l2_cache.stats = CacheStats()


# ==========================================
# 缓存装饰器
# ==========================================

def cache_result(
    key_template: str,
    ttl: Optional[int] = None,
    cache_type: Optional[str] = None,
    skip_cache_check: bool = False
):
    """
    缓存结果装饰器

    使用方式：
    @cache_result("skills:list:{user_id}")
    async def list_skills(user_id: int):
        ...

    Args:
        key_template: 缓存键模板，支持 {param} 占位符
        ttl: TTL（秒），None 使用默认值
        cache_type: 缓存类型
        skip_cache_check: 是否跳过缓存检查（仅用于写后失效）
    """

    # 获取全局缓存服务实例
    cache_service = get_cache_service()

    def decorator(func: Callable) -> Callable:

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 构建缓存键
            cache_key = _build_cache_key(key_template, func, args, kwargs)

            # 查询缓存
            if not skip_cache_check:
                cached = cache_service.get(cache_key)
                if cached is not None:
                    log.debug(f"[CacheDecorator] 缓存命中: {cache_key}")
                    return cached

            # 执行函数
            result = await func(*args, **kwargs)

            # 存入缓存
            cache_service.set(cache_key, result, cache_type)
            log.debug(f"[CacheDecorator] 结果已缓存: {cache_key}")

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 构建缓存键
            cache_key = _build_cache_key(key_template, func, args, kwargs)

            # 查询缓存
            if not skip_cache_check:
                cached = cache_service.get(cache_key)
                if cached is not None:
                    log.debug(f"[CacheDecorator] 缓存命中: {cache_key}")
                    return cached

            # 执行函数
            result = func(*args, **kwargs)

            # 存入缓存
            cache_service.set(cache_key, result, cache_type)
            log.debug(f"[CacheDecorator] 结果已缓存: {cache_key}")

            return result

        # 根据函数类型返回对应 wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def _build_cache_key(template: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """
    构建缓存键

    Args:
        template: 键模板
        func: 函数
        args: 位置参数
        kwargs: 关键字参数

    Returns:
        完整缓存键
    """
    # 获取函数参数名
    import inspect
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    # 构建参数字典
    param_dict = {}
    for i, param in enumerate(params):
        if i < len(args):
            param_dict[param] = args[i]

    param_dict.update(kwargs)

    # 替换模板中的占位符
    key = template
    for param, value in param_dict.items():
        key = key.replace(f"{{{param}}}", str(value))

    # 处理未替换的占位符（使用默认值或空）
    remaining_placeholders = [
        p for p in template.split("{")
        if "{" in p and p.split("}")[0]
    ]
    for placeholder in remaining_placeholders:
        param_name = placeholder.split("}")[0]
        if param_name not in param_dict:
            # 使用参数默认值
            param = sig.parameters.get(param_name)
            if param and param.default != inspect.Parameter.empty:
                key = key.replace(f"{{{param_name}}}", str(param.default))
            else:
                key = key.replace(f"{{{param_name}}}", "")

    return key


def invalidate_cache(key_pattern: str):
    """
    缓存失效装饰器

    用于写操作后自动失效相关缓存

    Args:
        key_pattern: 失效的键模式
    """

    cache_service = get_cache_service()

    def decorator(func: Callable) -> Callable:

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            cache_service.invalidate_pattern(key_pattern)
            log.debug(f"[CacheDecorator] 缓存已失效: {key_pattern}")
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            cache_service.invalidate_pattern(key_pattern)
            log.debug(f"[CacheDecorator] 缓存已失效: {key_pattern}")
            return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ==========================================
# 全局单例
# ==========================================

_cache_service: Optional[CacheService] = None
_cache_lock = threading.Lock()


def get_cache_service() -> CacheService:
    """
    获取缓存服务单例

    Returns:
        CacheService 实例
    """
    global _cache_service

    if _cache_service is None:
        with _cache_lock:
            if _cache_service is None:
                _cache_service = CacheService()

    return _cache_service


def init_cache_service() -> CacheService:
    """
    初始化缓存服务（应用启动时调用）

    Returns:
        CacheService 实例
    """
    return get_cache_service()


# ==========================================
# 定期清理任务
# ==========================================

def start_cache_cleanup_task(interval: int = 60):
    """
    启动定期清理任务

    Args:
        interval: 清理间隔（秒）
    """
    def cleanup_loop():
        cache = get_cache_service()
        while True:
            try:
                cleaned = cache.cleanup_expired()
                if cleaned > 0:
                    log.info(f"[CacheCleanup] 清理过期缓存: {cleaned} 项")
                time.sleep(interval)
            except Exception as e:
                log.error(f"[CacheCleanup] 清理任务异常: {e}")
                time.sleep(interval)

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    log.info(f"[CacheService] 启动定期清理任务，间隔={interval}s")