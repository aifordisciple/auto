"""
Claude Agent 模式 API 路由

提供 Claude 会话管理、消息发送、事件 SSE 推送等接口。
"""

import json
import asyncio
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from app.api.deps import get_current_user
from app.core.database import engine
from app.core.logger import log
from app.models.domain import User
from app.models.claude import ClaudeConversation
from app.services.claude_session_manager import ClaudeSessionManager
from app.services.claude_redis_bridge import get_claude_bridge


router = APIRouter(prefix="/api/claude", tags=["claude"])


# ==========================================
# Pydantic Schemas
# ==========================================

class CreateSessionRequest(BaseModel):
    title: str = Field(default="新会话", max_length=500)

class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None

class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)

class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)


# ==========================================
# Session CRUD
# ==========================================

@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.create_session(req.title)
    return {
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    sessions = await mgr.list_sessions(status)
    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "container_id": session.container_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: UUID,
    req: UpdateSessionRequest,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    kwargs = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    session = await mgr.update_session(session_id, **kwargs)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"id": str(session.id), "status": "updated"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    await mgr.close_session(session_id)
    return {"status": "closed"}


# ==========================================
# Conversation & Message
# ==========================================

@router.post("/sessions/{session_id}/conversations")
async def create_conversation(
    session_id: UUID,
    req: CreateConversationRequest,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    with Session(engine) as db:
        count = db.exec(
            select(func.count()).select_from(ClaudeConversation).where(
                ClaudeConversation.session_id == session_id
            )
        ).one()
        conv = ClaudeConversation(
            session_id=session_id,
            title=req.title or f"对话 {count + 1}",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return {"id": str(conv.id), "title": conv.title}


@router.post("/sessions/{session_id}/conversations/{conversation_id}/messages")
async def send_message(
    session_id: UUID,
    conversation_id: UUID,
    req: SendMessageRequest,
    user: User = Depends(get_current_user),
):
    """发送消息并返回 SSE 事件流"""
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        result = await mgr.send_user_message(session_id, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def event_stream():
        bridge = await get_claude_bridge()

        # 发送 session_info
        yield f"event: session_info\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

        try:
            async for event in bridge.subscribe_events(str(session_id)):
                event_type = event.get("type", "unknown")
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 持久化 assistant 事件
                await mgr.persist_assistant_event(conversation_id, event)

                # status=idle 或 status=waiting_user 表示本轮对话结束
                if event_type == "status" and event.get("status") in ("idle", "waiting_user"):
                    yield f"event: end\ndata: {json.dumps({'status': 'complete'})}\n\n"
                    break

        except asyncio.CancelledError:
            await bridge.send_cancel(str(session_id))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}/conversations/{conversation_id}/messages")
async def get_messages(
    session_id: UUID,
    conversation_id: UUID,
    user: User = Depends(get_current_user),
):
    """获取对话历史消息"""
    mgr = ClaudeSessionManager(user.id)
    messages = await mgr.get_conversation_messages(conversation_id)
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "events_json": m.events_json,
                "plan_json": m.plan_json,
                "code_snapshot": m.code_snapshot,
                "usage_json": m.usage_json,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }
