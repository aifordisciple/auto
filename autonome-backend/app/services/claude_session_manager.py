"""
Claude 会话管理器

管理 Claude Session 的完整生命周期:
- 创建/关闭会话
- 分配/回收沙箱容器
- 消息持久化
- 通过 Redis Bridge 与 Agent Service 通信
"""

import json
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.claude import (
    ClaudeSession,
    ClaudeConversation,
    ClaudeMessage,
    ClaudeContainer,
)
from app.services.claude_redis_bridge import get_claude_bridge


class ClaudeSessionManager:

    def __init__(self, user_id: int):
        self.user_id = user_id

    async def create_session(self, title: str = "新会话") -> ClaudeSession:
        """创建新 Claude 会话"""
        with Session(engine) as db:
            session = ClaudeSession(
                user_id=self.user_id,
                title=title,
                status="active",
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            # 创建默认对话
            conv = ClaudeConversation(
                session_id=session.id,
                title="对话 1",
            )
            db.add(conv)
            db.commit()

            return session

    async def get_session(self, session_id: UUID) -> Optional[ClaudeSession]:
        """获取会话详情"""
        with Session(engine) as db:
            session = db.exec(
                select(ClaudeSession).where(
                    ClaudeSession.id == session_id,
                    ClaudeSession.user_id == self.user_id,
                )
            ).first()
            return session

    async def list_sessions(self, status: str = None) -> List[ClaudeSession]:
        """列出用户的所有会话"""
        with Session(engine) as db:
            query = select(ClaudeSession).where(
                ClaudeSession.user_id == self.user_id
            ).order_by(ClaudeSession.updated_at.desc())
            if status:
                query = query.where(ClaudeSession.status == status)
            return list(db.exec(query).all())

    async def update_session(self, session_id: UUID, **kwargs) -> Optional[ClaudeSession]:
        """更新会话字段"""
        with Session(engine) as db:
            session = db.exec(
                select(ClaudeSession).where(
                    ClaudeSession.id == session_id,
                    ClaudeSession.user_id == self.user_id,
                )
            ).first()
            if not session:
                return None
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.updated_at = datetime.now(timezone.utc)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    async def close_session(self, session_id: UUID) -> None:
        """关闭会话"""
        bridge = await get_claude_bridge()
        await bridge.send_cancel(str(session_id))
        await self.update_session(session_id, status="closed")

    async def get_or_create_conversation(self, session_id: UUID) -> ClaudeConversation:
        """获取或创建对话 (取最新活跃对话)"""
        with Session(engine) as db:
            conv = db.exec(
                select(ClaudeConversation)
                .where(
                    ClaudeConversation.session_id == session_id,
                    ClaudeConversation.status == "active",
                )
                .order_by(ClaudeConversation.created_at.desc())
            ).first()
            if not conv:
                conv = ClaudeConversation(
                    session_id=session_id,
                    title="对话 1",
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)
            return conv

    async def send_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> Dict[str, Any]:
        """
        发送用户消息到 Claude Code, 返回消息信息
        """
        bridge = await get_claude_bridge()
        session = await self.get_session(session_id)
        if not session:
            raise ValueError("会话不存在")

        conv = await self.get_or_create_conversation(session_id)

        # 持久化用户消息
        with Session(engine) as db:
            msg = ClaudeMessage(
                conversation_id=conv.id,
                role="user",
                content=content,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)

        # 通过 Redis 发送到 Agent Service
        await bridge.send_message(
            session_id=str(session_id),
            message_type="user_message",
            content=content,
            conversation_id=str(conv.id),
            claude_session_id=conv.claude_session_id or "",
        )

        await self.update_session(session_id)

        return {
            "message_id": str(msg.id),
            "conversation_id": str(conv.id),
            "session_id": str(session_id),
        }

    async def persist_assistant_event(
        self,
        conversation_id: UUID,
        event: Dict[str, Any],
    ) -> None:
        """持久化 Assistant 事件到消息"""
        with Session(engine) as db:
            # 查找最近的 assistant 消息，不存在则创建
            msg = db.exec(
                select(ClaudeMessage)
                .where(
                    ClaudeMessage.conversation_id == conversation_id,
                    ClaudeMessage.role == "assistant",
                )
                .order_by(ClaudeMessage.created_at.desc())
            ).first()

            if msg and msg.events_json:
                events = list(msg.events_json)
                events.append(event)
                msg.events_json = events
            elif msg:
                msg.events_json = [event]
            else:
                msg = ClaudeMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    events_json=[event],
                )
            db.add(msg)
            db.commit()

    async def get_conversation_messages(self, conversation_id: UUID) -> List[ClaudeMessage]:
        """获取对话的所有消息"""
        with Session(engine) as db:
            return list(db.exec(
                select(ClaudeMessage)
                .where(ClaudeMessage.conversation_id == conversation_id)
                .order_by(ClaudeMessage.created_at)
            ).all())

    async def allocate_container(self, session_id: UUID) -> Optional[str]:
        """从容器池分配容器"""
        with Session(engine) as db:
            container = db.exec(
                select(ClaudeContainer)
                .where(ClaudeContainer.status == "idle")
                .limit(1)
            ).first()
            if container:
                container.status = "busy"
                container.user_id = self.user_id
                container.session_id = session_id
                container.last_used_at = datetime.now(timezone.utc)
                db.add(container)
                db.commit()
                await self.update_session(session_id, container_id=container.container_id)
                return container.container_id
        return None
