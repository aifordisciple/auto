"""
会话标签 API

处理标签的 CRUD 操作，包括：
- 获取用户标签列表
- 创建标签
- 删除标签
- 获取会话标签
- 添加/移除会话标签
- 按标签筛选会话
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.models.domain import (
    ChatSession, ChatSessionTag, SessionTagRelation, Project, User
)
from app.api.deps import get_current_user


router = APIRouter()


class TagCreate(BaseModel):
    """创建标签请求"""
    name: str
    color: Optional[str] = "#3B82F6"


@router.get("/tags")
def get_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取用户的所有标签"""
    tags = session.exec(
        select(ChatSessionTag)
        .where(ChatSessionTag.user_id == current_user.id)
        .order_by(ChatSessionTag.created_at.desc())
    ).all()

    return {"status": "success", "data": tags}


@router.post("/tags")
def create_tag(
    request: TagCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建新标签"""
    # 检查是否已存在同名标签
    existing = session.exec(
        select(ChatSessionTag)
        .where(ChatSessionTag.user_id == current_user.id)
        .where(ChatSessionTag.name == request.name)
    ).first()

    if existing:
        return {"status": "success", "tag": existing}

    tag = ChatSessionTag(
        name=request.name,
        color=request.color or "#3B82F6",
        user_id=current_user.id
    )
    session.add(tag)
    session.commit()
    session.refresh(tag)

    return {"status": "success", "tag": tag}


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除标签"""
    tag = session.get(ChatSessionTag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="标签不存在")

    # 删除所有关联
    relations = session.exec(
        select(SessionTagRelation)
        .where(SessionTagRelation.tag_id == tag_id)
    ).all()
    for rel in relations:
        session.delete(rel)

    session.delete(tag)
    session.commit()

    return {"status": "success"}


@router.get("/sessions/{session_id}/tags")
def get_session_tags(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取会话的所有标签"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    # 获取会话的所有标签
    relations = session.exec(
        select(SessionTagRelation)
        .where(SessionTagRelation.session_id == session_id)
    ).all()

    tags = []
    for rel in relations:
        tag = session.get(ChatSessionTag, rel.tag_id)
        if tag:
            tags.append({
                "id": tag.id,
                "name": tag.name,
                "color": tag.color
            })

    return {"status": "success", "tags": tags}


@router.post("/sessions/{session_id}/tags/{tag_id}")
def add_tag_to_session(
    session_id: str,
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """为会话添加标签"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    tag = session.get(ChatSessionTag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="标签不存在")

    # 检查是否已关联
    existing = session.exec(
        select(SessionTagRelation)
        .where(SessionTagRelation.session_id == session_id)
        .where(SessionTagRelation.tag_id == tag_id)
    ).first()

    if existing:
        return {"status": "success", "message": "已关联"}

    relation = SessionTagRelation(session_id=session_id, tag_id=tag_id)
    session.add(relation)
    session.commit()

    return {"status": "success"}


@router.delete("/sessions/{session_id}/tags/{tag_id}")
def remove_tag_from_session(
    session_id: str,
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """移除会话的标签"""
    relation = session.exec(
        select(SessionTagRelation)
        .where(SessionTagRelation.session_id == session_id)
        .where(SessionTagRelation.tag_id == tag_id)
    ).first()

    if not relation:
        raise HTTPException(status_code=404, detail="关联不存在")

    session.delete(relation)
    session.commit()

    return {"status": "success"}


@router.get("/projects/{project_id}/sessions/tagged/{tag_id}")
def get_sessions_by_tag(
    project_id: str,
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取项目中带有特定标签的会话"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    # 获取带有该标签的会话
    relations = session.exec(
        select(SessionTagRelation)
        .where(SessionTagRelation.tag_id == tag_id)
    ).all()

    session_ids = [rel.session_id for rel in relations]

    if not session_ids:
        return {"status": "success", "data": []}

    tagged_sessions = session.exec(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .where(ChatSession.id.in_(session_ids))
        .order_by(ChatSession.created_at.desc())
    ).all()

    return {"status": "success", "data": tagged_sessions}