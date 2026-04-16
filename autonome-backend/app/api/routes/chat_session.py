"""
会话管理 API

处理会话的 CRUD 操作，包括：
- 获取项目下的会话列表
- 获取会话消息
- 更新消息内容
- 重命名会话
- 删除会话
- 自动命名会话
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.models.domain import (
    ChatSession, ChatMessage, Project, User, RoleEnum,
    MessageBookmark, SkillRecommendationLog, SessionSummaryCache,
    SessionTagRelation, SkillExecutionHistory, ExperienceAsset
)
from app.api.deps import get_current_user
from app.core.logger import log


router = APIRouter()


class SessionUpdate(BaseModel):
    """会话更新请求"""
    title: str


@router.get("/projects/{project_id}/sessions")
def get_project_sessions(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取项目下的所有历史对话列表"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    sessions = session.exec(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return {"status": "success", "data": sessions}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取指定对话的所有聊天记录"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return {"status": "success", "data": messages}


@router.patch("/messages/{message_id}")
def update_message_content(
    message_id: str,
    content: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """更新消息内容（用于持久化任务ID等元数据）"""
    message = session.get(ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    # 验证权限
    chat_session = session.get(ChatSession, message.session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    message.content = content
    session.add(message)
    session.commit()
    return {"status": "success"}


@router.put("/sessions/{session_id}")
def rename_session(
    session_id: str,
    req: SessionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """手动重命名对话"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    chat_session.title = req.title[:100]
    session.add(chat_session)
    session.commit()
    return {"status": "success", "title": chat_session.title}


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    删除对话（级联删除所有关联数据）

    级联删除的关联表：
    - ChatMessage (消息记录)
    - SkillRecommendationLog (技能推荐日志)
    - SessionSummaryCache (会话摘要缓存)
    - SessionTagRelation (会话标签关系)
    - SkillExecutionHistory (技能执行历史)
    """
    # 获取会话
    chat_session = db_session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 权限校验
    project = db_session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    # ==========================================
    # 级联删除所有关联数据（必须先于会话删除）
    # ==========================================

    # 1. 删除消息收藏 (MessageBookmark) - 通过 ChatMessage 间接关联
    messages = db_session.exec(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    ).all()
    for msg in messages:
        db_session.exec(
            select(MessageBookmark).where(MessageBookmark.message_id == msg.id)
        ).all()
        # 删除收藏记录
        bookmarks = db_session.exec(
            select(MessageBookmark).where(MessageBookmark.message_id == msg.id)
        ).all()
        for bookmark in bookmarks:
            db_session.delete(bookmark)

    # 2. 删除消息记录 (ChatMessage)
    for msg in messages:
        db_session.delete(msg)

    # 3. 删除技能推荐日志 (SkillRecommendationLog)
    skill_logs = db_session.exec(
        select(SkillRecommendationLog).where(SkillRecommendationLog.session_id == session_id)
    ).all()
    for log_entry in skill_logs:
        db_session.delete(log_entry)

    # 4. 删除会话摘要缓存 (SessionSummaryCache)
    summary_cache = db_session.exec(
        select(SessionSummaryCache).where(SessionSummaryCache.session_id == session_id)
    ).first()
    if summary_cache:
        db_session.delete(summary_cache)

    # 5. 删除会话标签关系 (SessionTagRelation)
    tag_relations = db_session.exec(
        select(SessionTagRelation).where(SessionTagRelation.session_id == session_id)
    ).all()
    for relation in tag_relations:
        db_session.delete(relation)

    # 6. 删除技能执行历史 (SkillExecutionHistory)
    skill_executions = db_session.exec(
        select(SkillExecutionHistory).where(SkillExecutionHistory.session_id == session_id)
    ).all()
    for execution in skill_executions:
        db_session.delete(execution)

    # 7. 清理经验资产的会话引用 (ExperienceAsset)
    # 注意：经验资产是用户的宝贵数据，不应该删除，只是断开与会话的关联
    experience_assets = db_session.exec(
        select(ExperienceAsset).where(ExperienceAsset.source_session_id == session_id)
    ).all()
    for asset in experience_assets:
        asset.source_session_id = None
        db_session.add(asset)

    # 最后删除会话本身
    db_session.delete(chat_session)
    db_session.commit()
    return {"status": "success"}


@router.post("/sessions/{session_id}/auto-name")
def auto_name_session(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    根据第一条消息自动生成标题（基于截断，无 LLM 依赖）

    取第一条消息的前 30 个字符作为标题，省略部分用 ... 补充
    """
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    first_msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).first()

    if not first_msg:
        return {"title": chat_session.title}

    # 基于截断生成标题，无需 LLM
    content = (first_msg.content or "").strip()
    # 移除换行，取前 30 个字符
    content_oneline = content.replace("\n", " ").replace("\r", " ")
    max_len = 30
    if len(content_oneline) > max_len:
        new_title = content_oneline[:max_len] + "..."
    else:
        new_title = content_oneline or "新对话"

    chat_session.title = new_title
    session.add(chat_session)
    session.commit()
    return {"status": "success", "title": new_title}