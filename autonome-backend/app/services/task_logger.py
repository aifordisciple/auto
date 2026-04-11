"""
任务日志工具

统一的日志函数：同时写入 Redis 和文件，支持前端流式读取
"""

import json
import time
import redis

from app.core.config import settings
from app.core.logger import log


# 初始化 Redis 客户端 (用于日志流)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=2,
    decode_responses=True
)


def create_task_logger(task_id: str):
    """
    创建任务日志记录器

    返回两个函数：
    1. log_to_redis_and_file: 写入日志到 Redis 和文件
    2. send_code_update: 发送代码更新事件到前端

    Args:
        task_id: 任务 ID

    Returns:
        (log_func, send_code_update_func)
    """
    def log_to_redis_and_file(message: str, level: str = "INFO"):
        """写入日志到 Redis 和文件"""
        # 1. 写入 Redis 供前端流式读取
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] [{level}] {message}"
        log_key = f"task_logs:{task_id}"
        redis_client.rpush(log_key, formatted_msg)
        redis_client.expire(log_key, 86400)

        # 2. 写入物理服务器日志
        if level == "ERROR":
            log.error(f"[Task {task_id}] {message}")
        elif level == "WARNING":
            log.warning(f"[Task {task_id}] {message}")
        else:
            log.info(f"[Task {task_id}] {message}")

    def send_code_update(code: str, language: str = "python", attempt: int = 1):
        """发送代码更新事件到前端"""
        log_key = f"task_logs:{task_id}"
        # 使用特殊的 JSON 格式，前端可以识别
        code_event = json.dumps({
            "type": "code_update",
            "code": code,
            "language": language,
            "attempt": attempt,
            "timestamp": time.strftime('%H:%M:%S')
        })
        redis_client.rpush(log_key, f"__CODE_UPDATE__:{code_event}")
        redis_client.expire(log_key, 86400)
        log.info(f"[Task {task_id}] 代码更新事件已发送 (attempt {attempt})")

    return log_to_redis_and_file, send_code_update


def safe_add_chat_message(session_id: str, role: str, content: str) -> bool:
    """
    安全地插入聊天消息

    检查 session 是否存在，如果不存在则跳过插入，避免外键约束错误。

    Args:
        session_id: 会话 ID
        role: 角色 (user/assistant)
        content: 消息内容

    Returns:
        True 如果成功插入，False 如果跳过
    """
    from sqlmodel import Session
    from app.core.database import engine
    from app.models.domain import ChatSession, ChatMessage, RoleEnum

    try:
        with Session(engine) as db:
            # 检查会话是否存在
            chat_session = db.get(ChatSession, session_id)
            if not chat_session:
                log.warning(f"[ChatMessage] 会话 {session_id} 不存在，跳过消息插入")
                return False

            # 插入消息
            message = ChatMessage(
                session_id=session_id,
                role=role,
                content=content
            )
            db.add(message)
            db.commit()
            return True
    except Exception as e:
        log.error(f"[ChatMessage] 插入消息失败: {e}")
        return False