"""
Agent Service Redis 客户端

管理 Redis pub/sub 连接，负责：
- SUBSCRIBE claude:session:{sid} 通道接收后端消息
- PUBLISH claude:session:{sid}:events 通道发送事件
- 心跳定时上报
- 自动重连 (指数退避)
"""

import os
import json
import time
import threading
from typing import Callable, Optional
import redis

from app.sandbox.agent_service.event_types import AgentEvent


REDIS_URL = os.environ.get("REDIS_URL", "redis://claude-redis:6380/0")
AGENT_ID = os.environ.get("AGENT_ID", "unknown")
HEARTBEAT_INTERVAL = 10
RECONNECT_MAX_ATTEMPTS = 5
RECONNECT_BASE_DELAY = 1


class AgentRedisClient:
    """Agent Service 侧 Redis 客户端"""

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._message_handler: Optional[Callable] = None

    def connect(self) -> bool:
        """连接 Redis, 返回是否成功"""
        try:
            self._client = redis.Redis.from_url(
                self._redis_url,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            self._client.ping()
            return True
        except redis.RedisError as e:
            print(f"[AgentRedis] 连接失败: {e}")
            return False

    def start_heartbeat(self, session_id: str) -> None:
        """启动心跳线程"""
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(session_id,),
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self, session_id: str) -> None:
        """心跳循环"""
        while self._running:
            try:
                self._client.setex(
                    f"claude:heartbeat:{session_id}",
                    HEARTBEAT_INTERVAL * 2,
                    json.dumps({"agent_id": AGENT_ID, "timestamp": time.time()}),
                )
            except redis.RedisError:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def subscribe(self, session_id: str, message_handler: Callable) -> None:
        """订阅 session 消息通道, 阻塞运行"""
        self._message_handler = message_handler
        self._pubsub = self._client.pubsub()
        self._pubsub.subscribe(f"claude:session:{session_id}")

        attempt = 0
        while self._running:
            try:
                for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            self._message_handler(data)
                        except json.JSONDecodeError:
                            pass
                attempt = 0
            except redis.RedisError as e:
                print(f"[AgentRedis] 订阅断开: {e}")
                attempt += 1
                if attempt > RECONNECT_MAX_ATTEMPTS:
                    print("[AgentRedis] 重连次数耗尽, 退出")
                    break
                delay = RECONNECT_BASE_DELAY * (2 ** (attempt - 1))
                time.sleep(delay)
                if self.connect():
                    self._pubsub = self._client.pubsub()
                    self._pubsub.subscribe(f"claude:session:{session_id}")

    def publish_event(self, session_id: str, event: AgentEvent) -> None:
        """发布事件到 session 事件通道"""
        if self._client:
            try:
                self._client.publish(
                    f"claude:session:{session_id}:events",
                    event.to_json(),
                )
            except redis.RedisError:
                pass

    def publish_raw(self, channel: str, data: str) -> None:
        """发布原始数据到指定通道"""
        if self._client:
            try:
                self._client.publish(channel, data)
            except redis.RedisError:
                pass

    def stop(self) -> None:
        """停止心跳和订阅"""
        self._running = False
        if self._pubsub:
            self._pubsub.close()
        if self._client:
            self._client.close()
