"""
跨轮回合文件上下文持久化服务。

通过 Redis 存储每个用户在每个项目中的最近文件上下文（active_file + context_files），
解决前端未传 context_files 时（如切换对话、页面刷新后追问）文件上下文丢失的问题。

设计原则：
- Redis 仅作缓存层，数据源头仍是前端请求
- TTL 1 小时后自动过期，避免脏数据
- Redis 不可用时静默降级，不阻断正常流程

@created: 2026-04-26
"""

import json
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime

import redis

from app.core.logger import log
from app.core.config import settings


# Redis db 编号（与缓存服务 db=2 隔离）
FILE_CONTEXT_REDIS_DB = 3
# 文件上下文过期时间（秒）
FILE_CONTEXT_TTL = 3600


class FileContextService:
    """
    文件上下文持久化服务。

    程序说明：
    使用 Redis 存储用户-项目维度的最近文件上下文。
    Key 格式: autonome:file_context:{user_id}:{project_id}
    Value: JSON 序列化的 active_file + context_files + updated_at
    TTL: 1 小时自动过期

    集成点：
    - chat.py 收到请求后调用 save() 持久化当前上下文
    - L2 探查时调用 restore() 尝试恢复上次的文件上下文
    """

    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._lock = threading.RLock()
        self._available = True  # Redis 可用标志，失败一次后不再重试

    def _get_client(self) -> Optional[redis.Redis]:
        """获取 Redis 客户端（延迟初始化 + 连接池）。"""
        if not self._available:
            return None
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        pool = redis.ConnectionPool(
                            host=settings.REDIS_HOST,
                            port=settings.REDIS_PORT,
                            db=FILE_CONTEXT_REDIS_DB,
                            decode_responses=True,
                            max_connections=10,
                            socket_timeout=3,
                            socket_connect_timeout=3,
                        )
                        self._client = redis.Redis(connection_pool=pool)
                        self._client.ping()
                        log.info(
                            f"[FileContext] Redis 连接成功: "
                            f"host={settings.REDIS_HOST}, db={FILE_CONTEXT_REDIS_DB}"
                        )
                    except Exception as e:
                        log.warning(f"[FileContext] Redis 不可用，文件上下文持久化已禁用: {e}")
                        self._available = False
                        return None
        return self._client

    @staticmethod
    def _make_key(user_id: str, project_id: str) -> str:
        """生成 Redis key。"""
        return f"autonome:file_context:{user_id}:{project_id}"

    def save(
        self,
        user_id: str,
        project_id: str,
        active_file: str,
        context_files: List[Dict[str, Any]],
    ) -> None:
        """
        持久化当前请求的文件上下文。

        程序说明：
        每次前端请求携带 context_files 时调用，将文件上下文写入 Redis。
        无文件上下文时不保存（避免用空数据覆盖上次有效数据）。

        Args:
            user_id: 当前用户 ID
            project_id: 当前项目 ID
            active_file: 当前活跃文件路径
            context_files: 工作区文件列表
        """
        if not user_id or not project_id:
            return
        # 无文件上下文时不保存，避免覆盖有效数据
        if not active_file and not context_files:
            return

        client = self._get_client()
        if client is None:
            return

        payload = {
            "active_file": active_file or "",
            "context_files": [
                {"id": f.get("id", ""), "name": f.get("name", "")}
                if isinstance(f, dict)
                else str(f)
                for f in (context_files or [])
            ],
            "updated_at": datetime.utcnow().isoformat(),
        }

        try:
            key = self._make_key(user_id, project_id)
            client.setex(key, FILE_CONTEXT_TTL, json.dumps(payload, ensure_ascii=False))
            log.debug(
                f"[FileContext] 已保存: user={user_id}, project={project_id}, "
                f"active_file={active_file}, context_files={len(context_files or [])}"
            )
        except Exception as e:
            log.warning(f"[FileContext] 保存失败: {e}")

    def restore(
        self,
        user_id: str,
        project_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        恢复上次的文件上下文。

        程序说明：
        当前端请求未携带 context_files 时调用，从 Redis 恢复最近的文件上下文。
        返回 None 表示无缓存数据或 Redis 不可用，调用方应使用 fallback 逻辑。

        Args:
            user_id: 当前用户 ID
            project_id: 当前项目 ID

        Returns:
            {"active_file": str, "context_files": list} 或 None
        """
        if not user_id or not project_id:
            return None

        client = self._get_client()
        if client is None:
            return None

        try:
            key = self._make_key(user_id, project_id)
            raw = client.get(key)
            if raw is None:
                log.debug(f"[FileContext] 无缓存: user={user_id}, project={project_id}")
                return None

            data = json.loads(raw)
            log.info(
                f"[FileContext] 已恢复: user={user_id}, project={project_id}, "
                f"active_file={data.get('active_file')}, "
                f"context_files={len(data.get('context_files', []))}"
            )
            return data
        except Exception as e:
            log.warning(f"[FileContext] 恢复失败: {e}")
            return None

    def delete(self, user_id: str, project_id: str) -> None:
        """
        删除文件上下文缓存。

        程序说明：
        用户手动清除上下文或项目被删除时调用。

        Args:
            user_id: 当前用户 ID
            project_id: 当前项目 ID
        """
        client = self._get_client()
        if client is None:
            return

        try:
            key = self._make_key(user_id, project_id)
            client.delete(key)
            log.debug(f"[FileContext] 已删除: user={user_id}, project={project_id}")
        except Exception as e:
            log.warning(f"[FileContext] 删除失败: {e}")


# 全局单例
_file_context_service: Optional[FileContextService] = None


def get_file_context_service() -> FileContextService:
    """获取 FileContextService 全局单例。"""
    global _file_context_service
    if _file_context_service is None:
        _file_context_service = FileContextService()
    return _file_context_service
