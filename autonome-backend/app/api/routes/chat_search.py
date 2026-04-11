"""
对话搜索 API

使用 PostgreSQL 全文搜索功能搜索对话内容
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.models.domain import ChatSession, ChatMessage, Project, User
from app.api.deps import get_current_user


router = APIRouter()


class SearchRequest(BaseModel):
    """对话搜索请求"""
    query: str
    project_id: Optional[str] = None
    limit: int = 20


class SearchResultMessage(BaseModel):
    """搜索结果消息"""
    message_id: str
    content: str
    role: str
    created_at: datetime
    highlight: str


class SearchResult(BaseModel):
    """搜索结果"""
    session_id: str
    session_title: str
    matched_messages: list[SearchResultMessage]


@router.post("/search")
def search_messages(
    request: SearchRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    搜索对话内容 - 使用 PostgreSQL 全文搜索
    """
    if not request.query or len(request.query.strip()) < 2:
        return {"status": "success", "results": []}

    query_text = request.query.strip().lower()

    # 构建基础查询 - 获取用户的所有项目
    projects = session.exec(
        select(Project).where(Project.owner_id == current_user.id)
    ).all()
    project_ids = [p.id for p in projects]

    if not project_ids:
        return {"status": "success", "results": []}

    # 搜索消息内容
    base_query = (
        select(ChatMessage, ChatSession)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.project_id.in_(project_ids))
        .where(ChatMessage.content.ilike(f"%{query_text}%"))
        .order_by(ChatMessage.created_at.desc())
        .limit(request.limit)
    )

    if request.project_id:
        base_query = (
            select(ChatMessage, ChatSession)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.project_id == request.project_id)
            .where(ChatMessage.content.ilike(f"%{query_text}%"))
            .order_by(ChatMessage.created_at.desc())
            .limit(request.limit)
        )

    results = session.exec(base_query).all()

    # 按会话分组
    grouped: dict[str, SearchResult] = {}
    for msg, chat_session in results:
        if chat_session.id not in grouped:
            # 高亮关键词
            content_lower = msg.content.lower()
            highlight_start = content_lower.find(query_text)
            if highlight_start != -1:
                start = max(0, highlight_start - 50)
                end = min(len(msg.content), highlight_start + len(query_text) + 100)
                highlight = msg.content[start:end]
                if start > 0:
                    highlight = "..." + highlight
                if end < len(msg.content):
                    highlight = highlight + "..."
            else:
                highlight = msg.content[:150] + "..." if len(msg.content) > 150 else msg.content

            grouped[chat_session.id] = SearchResult(
                session_id=chat_session.id,
                session_title=chat_session.title,
                matched_messages=[SearchResultMessage(
                    message_id=msg.id,
                    content=msg.content,
                    role=msg.role.value,
                    created_at=msg.created_at,
                    highlight=highlight
                )]
            )
        else:
            # 添加到现有会话的匹配消息
            content_lower = msg.content.lower()
            highlight_start = content_lower.find(query_text)
            if highlight_start != -1:
                start = max(0, highlight_start - 50)
                end = min(len(msg.content), highlight_start + len(query_text) + 100)
                highlight = msg.content[start:end]
                if start > 0:
                    highlight = "..." + highlight
                if end < len(msg.content):
                    highlight = highlight + "..."
            else:
                highlight = msg.content[:150] + "..." if len(msg.content) > 150 else msg.content

            grouped[chat_session.id].matched_messages.append(SearchResultMessage(
                message_id=msg.id,
                content=msg.content,
                role=msg.role.value,
                created_at=msg.created_at,
                highlight=highlight
            ))

    return {"status": "success", "results": list(grouped.values())}