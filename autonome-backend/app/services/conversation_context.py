"""
对话上下文服务

加载历史消息，构建对话上下文
"""

from typing import Optional
from sqlmodel import Session, select

from app.models.domain import ChatMessage, RoleEnum
from app.core.logger import log


def load_conversation_history(session_id: str, db: Session, max_messages: int = 20) -> list:
    """
    加载最近 N 条历史消息，构建对话上下文

    Args:
        session_id: 会话 ID
        db: 数据库会话
        max_messages: 最大加载消息数（防止 token 超限）

    Returns:
        格式化的消息列表 [{"role": "user/assistant", "content": "..."}]
    """
    try:
        messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(max_messages)
        ).all()

        # 按时间正序排列（从旧到新）
        messages = list(reversed(messages))

        # 转换为 LangChain 消息格式
        history = []
        for msg in messages:
            if msg.role == RoleEnum.user:
                history.append({"role": "user", "content": msg.content})
            elif msg.role == RoleEnum.assistant:
                history.append({"role": "assistant", "content": msg.content})
            # 忽略 system 消息（如果有）

        log.info(f"📜 [Context] 加载了 {len(history)} 条历史消息")
        return history

    except Exception as e:
        log.error(f"❌ [Context] 加载历史消息失败: {e}")
        return []