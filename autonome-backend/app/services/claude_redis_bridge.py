"""
Claude Redis 桥接服务

后端侧的 Redis pub/sub 管理:
- 发布消息到 claude:session:{sid} 通道
- 订阅 claude:session:{sid}:events 通道接收 Agent 事件
- 心跳监控 (检测 Agent Service 存活)
"""

import os
import json
import time
from typing import AsyncIterator, Optional, Dict, Any
import redis.asyncio as aioredis

from app.core.logger import log


CLAUDE_REDIS_URL = os.environ.get("CLAUDE_REDIS_URL", "redis://claude-redis:6380/0")


class ClaudeRedisBridge:
    """后端侧 Claude Redis 桥接"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """建立 Redis 连接"""
        self._redis = aioredis.from_url(
            CLAUDE_REDIS_URL,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        await self._redis.ping()

    async def send_message(
        self,
        session_id: str,
        message_type: str,
        content: str = "",
        conversation_id: str = "",
        claude_session_id: str = "",
        **extra,
    ) -> None:
        """发送消息到 Agent Service"""
        msg = {
            "type": message_type,
            "content": content,
            "conversation_id": conversation_id,
            "claude_session_id": claude_session_id,
            **extra,
        }
        await self._redis.publish(
            f"claude:session:{session_id}",
            json.dumps(msg, ensure_ascii=False),
        )

    async def send_cancel(self, session_id: str) -> None:
        """发送取消指令"""
        await self.send_message(session_id, "cancel")

    async def subscribe_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """订阅 Agent 事件通道, 返回异步迭代器"""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"claude:session:{session_id}:events")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError:
                        continue
        finally:
            await pubsub.unsubscribe(f"claude:session:{session_id}:events")

    async def publish_allocation(self, container_id: str, session_id: str) -> None:
        """
        发布容器分配消息到 broadcast 通道

        预热容器中的 agent_service 订阅 claude:pool:broadcast 等待分配。
        分配时调用此方法 publish {action: "assign", container_id, session_id}，
        使对应容器切换到指定 session 的消息通道。
        """
        await self._redis.publish(
            "claude:pool:broadcast",
            json.dumps({
                "action": "assign",
                "container_id": container_id,
                "session_id": session_id,
            }),
        )

    async def check_heartbeat(self, session_id: str) -> bool:
        """检查 Agent Service 心跳"""
        data = await self._redis.get(f"claude:heartbeat:{session_id}")
        if data:
            try:
                heartbeat = json.loads(data)
                elapsed = time.time() - heartbeat.get("timestamp", 0)
                return elapsed < 30
            except json.JSONDecodeError:
                pass
        return False

    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.close()


# 全局单例
_claude_bridge: Optional[ClaudeRedisBridge] = None


async def get_claude_bridge() -> ClaudeRedisBridge:
    """获取 Claude Redis Bridge 单例"""
    global _claude_bridge
    if _claude_bridge is None:
        _claude_bridge = ClaudeRedisBridge()
        await _claude_bridge.connect()
    return _claude_bridge
