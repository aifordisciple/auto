#!/usr/bin/env python3
"""
Agent Service 主入口

在 Claude 沙箱容器中运行，作为守护进程:
1. 连接 Redis
2. 订阅 claude:session:{sid} 通道
3. 收到消息 → spawn Claude Code → 推送事件流
"""

import os
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.sandbox.agent_service.redis_client import AgentRedisClient
from app.sandbox.agent_service.claude_manager import ClaudeManager
from app.sandbox.agent_service.event_types import StatusEvent, ErrorEvent, AgentStatus


SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://claude-redis:6380/0")

redis_client: AgentRedisClient = None
claude_manager: ClaudeManager = None
running = True


def handle_message(data: dict) -> None:
    """处理收到的 Redis 消息"""
    msg_type = data.get("type", "")
    content = data.get("content", "")
    claude_session_id = data.get("claude_session_id", "")

    if msg_type == "user_message":
        redis_client.publish_event(
            SESSION_ID,
            StatusEvent(status=AgentStatus.THINKING.value, message="正在处理..."),
        )

        claude_manager.run_with_prompt(
            prompt=content,
            session_id=claude_session_id,
            on_event=lambda ev: redis_client.publish_event(SESSION_ID, ev),
        )

        redis_client.publish_event(
            SESSION_ID,
            StatusEvent(status=AgentStatus.WAITING_USER.value, message="等待用户输入"),
        )

    elif msg_type == "cancel":
        if claude_manager and claude_manager.is_running:
            claude_manager.kill()
            redis_client.publish_event(
                SESSION_ID,
                StatusEvent(status=AgentStatus.IDLE.value, message="已取消"),
            )


def handle_signal(signum, frame) -> None:
    """处理退出信号"""
    global running
    running = False
    if claude_manager:
        claude_manager.kill()
    if redis_client:
        redis_client.stop()


def main() -> None:
    global redis_client, claude_manager, running

    if not SESSION_ID:
        print("ERROR: CLAUDE_SESSION_ID not set")
        sys.exit(1)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    redis_client = AgentRedisClient(REDIS_URL)
    if not redis_client.connect():
        print("ERROR: Cannot connect to Redis, exiting")
        sys.exit(1)

    claude_manager = ClaudeManager(
        api_key=API_KEY,
        api_base_url=API_BASE_URL or None,
    )

    redis_client.start_heartbeat(SESSION_ID)

    redis_client.publish_event(
        SESSION_ID,
        StatusEvent(status=AgentStatus.IDLE.value, message="Agent Service 已就绪"),
    )

    print(f"[AgentService] 已就绪, session={SESSION_ID}")

    redis_client.subscribe(SESSION_ID, handle_message)

    print("[AgentService] 已退出")


if __name__ == "__main__":
    main()
