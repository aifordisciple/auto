"""
消息收藏 API

处理消息收藏的 CRUD 操作，包括：
- 创建收藏
- 删除收藏
- 更新收藏笔记
- 获取收藏列表
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.models.domain import ChatSession, ChatMessage, Project, User, MessageBookmark
from app.api.deps import get_current_user


router = APIRouter()


class BookmarkCreate(BaseModel):
    """创建收藏请求"""
    note: Optional[str] = None


class BookmarkUpdate(BaseModel):
    """更新收藏请求"""
    note: Optional[str] = None


@router.post("/messages/{message_id}/bookmark")
def create_bookmark(
    message_id: str,
    request: BookmarkCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """收藏消息"""
    # 验证消息存在且用户有权访问
    msg = session.get(ChatMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")

    chat_session = session.get(ChatSession, msg.session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    # 检查是否已收藏
    existing = session.exec(
        select(MessageBookmark)
        .where(MessageBookmark.message_id == message_id)
        .where(MessageBookmark.user_id == current_user.id)
    ).first()

    if existing:
        return {"status": "success", "bookmark_id": existing.id, "message": "已收藏"}

    # 创建收藏
    bookmark = MessageBookmark(
        message_id=message_id,
        user_id=current_user.id,
        note=request.note
    )
    session.add(bookmark)
    session.commit()
    session.refresh(bookmark)

    return {"status": "success", "bookmark_id": bookmark.id}


@router.delete("/messages/{message_id}/bookmark")
def delete_bookmark(
    message_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """取消收藏消息"""
    bookmark = session.exec(
        select(MessageBookmark)
        .where(MessageBookmark.message_id == message_id)
        .where(MessageBookmark.user_id == current_user.id)
    ).first()

    if not bookmark:
        raise HTTPException(status_code=404, detail="收藏不存在")

    session.delete(bookmark)
    session.commit()

    return {"status": "success"}


@router.put("/bookmarks/{bookmark_id}")
def update_bookmark(
    bookmark_id: int,
    request: BookmarkUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """更新收藏笔记"""
    bookmark = session.get(MessageBookmark, bookmark_id)
    if not bookmark or bookmark.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="收藏不存在")

    bookmark.note = request.note
    session.add(bookmark)
    session.commit()

    return {"status": "success"}


@router.get("/bookmarks")
def get_bookmarks(
    project_id: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取收藏列表"""
    # 获取用户的所有收藏
    bookmarks = session.exec(
        select(MessageBookmark)
        .where(MessageBookmark.user_id == current_user.id)
        .order_by(MessageBookmark.created_at.desc())
    ).all()

    results = []
    for bookmark in bookmarks:
        msg = session.get(ChatMessage, bookmark.message_id)
        if not msg:
            continue

        chat_session = session.get(ChatSession, msg.session_id)
        if not chat_session:
            continue

        # 如果指定了项目ID，过滤
        if project_id and chat_session.project_id != project_id:
            continue

        results.append({
            "bookmark_id": bookmark.id,
            "message_id": bookmark.message_id,
            "session_id": chat_session.id,
            "session_title": chat_session.title,
            "project_id": chat_session.project_id,
            "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
            "note": bookmark.note,
            "created_at": bookmark.created_at
        })

    return {"status": "success", "data": results}