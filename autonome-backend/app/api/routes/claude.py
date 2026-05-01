"""
Claude Agent 模式 API 路由

提供 Claude 会话管理、消息发送、事件 SSE 推送、技能检索、任务管理等接口。
"""

import json
import os
import mimetypes
import asyncio
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_

from app.api.deps import get_current_user
from app.core.database import engine
from app.core.logger import log
from app.models.domain import User
from app.models.claude import ClaudeConversation, ClaudeTask
from app.models.skill.asset import SkillAsset
from app.models.experience import ExperienceAsset
from app.services.claude_session_manager import ClaudeSessionManager
from app.services.claude_redis_bridge import get_claude_bridge
from app.services.claude_container_pool import get_container_pool


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


# ==========================================
# Skill Search (供 Claude Code Agent Service 调用)
# ==========================================

@router.get("/skills/search")
async def search_skills(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """
    技能检索接口 — 供 Agent Service 中的 Claude Code 调用。

    根据关键词在技能库中搜索匹配的技能，返回技能元信息供 Claude Code 判断和调用。
    搜索范围：技能名称、描述、标签、技能ID。
    """
    with Session(engine) as db:
        # 搜索已发布的技能，按名称/描述/skill_id/标签模糊匹配
        pattern = f"%{q}%"
        skills = db.exec(
            select(SkillAsset)
            .where(
                SkillAsset.status == "published",
                or_(
                    SkillAsset.name.ilike(pattern),
                    SkillAsset.description.ilike(pattern),
                    SkillAsset.skill_id.ilike(pattern),
                ),
            )
            .order_by(SkillAsset.updated_at.desc())
            .limit(limit)
        ).all()

        # 标签匹配（JSONB 数组需要在 Python 层面过滤）
        if len(skills) < limit:
            tag_skills = db.exec(
                select(SkillAsset)
                .where(SkillAsset.status == "published")
                .order_by(SkillAsset.updated_at.desc())
                .limit(limit * 3)
            ).all()
            existing_ids = {s.id for s in skills}
            for s in tag_skills:
                if len(skills) >= limit:
                    break
                if s.id in existing_ids:
                    continue
                if s.tags and any(q.lower() in tag.lower() for tag in s.tags):
                    skills.append(s)

        return {
            "skills": [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "executor_type": s.executor_type,
                    "category": s.category,
                    "category_name": s.category_name,
                    "subcategory": s.subcategory,
                    "subcategory_name": s.subcategory_name,
                    "tags": s.tags or [],
                    "parameters_schema": s.parameters_schema or {},
                }
                for s in skills[:limit]
            ],
            "total": len(skills[:limit]),
        }


# ==========================================
# Heavy Task Management (Celery 分布式任务追踪)
# ==========================================

class SubmitTaskRequest(BaseModel):
    skill_id: Optional[str] = Field(default=None, max_length=200)
    code: Optional[str] = Field(default=None)
    parameters: Optional[dict] = Field(default=None)
    conversation_id: Optional[str] = Field(default=None)
    message_id: Optional[str] = Field(default=None)


@router.post("/tasks/submit")
async def submit_heavy_task(
    req: SubmitTaskRequest,
    user: User = Depends(get_current_user),
):
    """
    提交重型任务 — 供 Agent Service 中的 Claude Code 调用。

    将耗时较长的生信分析任务注册到数据库，后续由 Celery worker 异步执行。
    Claude Code 通过此接口将重型计算任务提交到分布式队列中。
    """
    with Session(engine) as db:
        task = ClaudeTask(
            message_id=UUID(req.message_id) if req.message_id else None,
            session_id=None,
            skill_id=req.skill_id,
            status="pending",
            code=req.code,
            parameters=req.parameters or {},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # 如果关联了消息，更新消息的 task_ids
        if req.message_id:
            msg_id = UUID(req.message_id)
            from app.models.claude import ClaudeMessage
            msg = db.get(ClaudeMessage, msg_id)
            if msg:
                current_task_ids = list(msg.task_ids or [])
                current_task_ids.append(task.id)
                msg.task_ids = current_task_ids
                db.add(msg)
                db.commit()

        return {
            "task_id": str(task.id),
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        }


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: UUID,
    user: User = Depends(get_current_user),
):
    """查询重型任务状态"""
    with Session(engine) as db:
        task = db.get(ClaudeTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {
            "task_id": str(task.id),
            "skill_id": task.skill_id,
            "status": task.status,
            "celery_task_id": task.celery_task_id,
            "output_files": task.output_files or [],
            "error_text": task.error_text,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "created_at": task.created_at.isoformat(),
        }


@router.get("/tasks")
async def list_tasks(
    session_id: Optional[UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """列出任务"""
    with Session(engine) as db:
        query = select(ClaudeTask).order_by(ClaudeTask.created_at.desc())
        if session_id:
            query = query.where(ClaudeTask.session_id == session_id)
        if status_filter:
            query = query.where(ClaudeTask.status == status_filter)
        tasks = db.exec(query.limit(limit)).all()
        return {
            "tasks": [
                {
                    "task_id": str(t.id),
                    "skill_id": t.skill_id,
                    "status": t.status,
                    "celery_task_id": t.celery_task_id,
                    "output_files": t.output_files or [],
                    "error_text": t.error_text,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tasks
            ]
        }


# ==========================================
# Workspace File Management (沙箱文件预览)
# ==========================================

WORKSPACE_ROOT = "/workspace"

# 文件大小限制: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.get("/workspace/files")
async def list_workspace_files(
    path: str = Query(default=""),
    user: User = Depends(get_current_user),
):
    """
    列出沙箱工作区文件 — 供前端预览区使用。

    返回 /workspace 下的文件列表，支持按文件类型过滤。
    """
    try:
        target = os.path.join(WORKSPACE_ROOT, path.lstrip("/"))
        # 安全检查：确保路径在 /workspace 内
        if not os.path.realpath(target).startswith(WORKSPACE_ROOT):
            raise HTTPException(status_code=403, detail="路径越界")

        if not os.path.exists(target):
            return {"files": [], "path": path}

        entries = []
        for entry in os.listdir(target):
            entry_path = os.path.join(target, entry)
            rel_path = os.path.relpath(entry_path, WORKSPACE_ROOT)
            if os.path.isfile(entry_path):
                stat = os.stat(entry_path)
                entries.append({
                    "name": entry,
                    "path": "/" + rel_path,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

        # 按修改时间倒序
        entries.sort(key=lambda e: e["modified_at"], reverse=True)
        return {"files": entries, "path": path}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"列出工作区文件失败: {e}")
        raise HTTPException(status_code=500, detail="列出文件失败")


@router.get("/workspace/files/content")
async def get_workspace_file_content(
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
):
    """
    获取沙箱工作区文件内容 — 供前端预览区使用。

    支持图片 (直接返回)、HTML、CSV/TSV、文本等类型。
    """
    try:
        file_path = os.path.join(WORKSPACE_ROOT, path.lstrip("/"))
        # 安全检查
        if not os.path.realpath(file_path).startswith(WORKSPACE_ROOT):
            raise HTTPException(status_code=403, detail="路径越界")

        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        # 大小限制
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"文件过大 ({file_size} > {MAX_FILE_SIZE})")

        # 根据文件类型返回
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("image/"):
            return FileResponse(file_path, media_type=mime_type)
        elif mime_type and mime_type == "text/html":
            return FileResponse(file_path, media_type="text/html")
        else:
            # 文本文件直接返回
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return PlainTextResponse(content)

    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="二进制文件不支持文本预览")
    except Exception as e:
        log.error(f"读取工作区文件失败: {e}")
        raise HTTPException(status_code=500, detail="读取文件失败")


# ==========================================
# Experience Integration (经验萃取)
# ==========================================

class SaveExperienceRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1)
    original_query: str = Field(default="")
    solution_code: Optional[str] = Field(default=None)
    solution_strategy: Optional[str] = Field(default=None)
    key_insights: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    category: str = Field(default="general")
    language: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)


@router.post("/experiences")
async def save_experience(
    req: SaveExperienceRequest,
    user: User = Depends(get_current_user),
):
    """
    保存 Claude Code 分析经验 — 将成功的分析模式萃取为可复用的经验。

    Claude Code 在完成分析任务后调用此接口，将有价值的分析策略、
    代码模式、参数选择等保存为结构化经验，存入 ExperienceAsset 表。
    """
    with Session(engine) as db:
        # 检查是否已存在同标题同用户经验（合并去重）
        existing = db.exec(
            select(ExperienceAsset).where(
                ExperienceAsset.title == req.title,
                ExperienceAsset.source_user_id == user.id,
            )
        ).first()

        if existing:
            # 合并更新摘要和标签
            existing.summary = existing.summary + "\n\n---\n\n" + req.summary
            existing.key_insights = list(set((existing.key_insights or []) + req.key_insights))
            existing.tags = list(set((existing.tags or []) + req.tags))
            if req.solution_code:
                existing.solution_code = req.solution_code
            if req.solution_strategy:
                existing.solution_strategy = req.solution_strategy
            existing.updated_at = datetime.utcnow()
            db.add(existing)
            db.commit()
            return {
                "experience_id": existing.experience_id,
                "title": existing.title,
                "action": "merged",
                "created_at": existing.created_at.isoformat(),
            }

        # 创建新经验
        exp = ExperienceAsset(
            title=req.title,
            summary=req.summary,
            original_query=req.original_query or req.title,
            solution_code=req.solution_code,
            solution_strategy=req.solution_strategy,
            key_insights=req.key_insights,
            category=req.category,
            tags=req.tags,
            language=req.language,
            source_user_id=user.id,
            source_session_id=req.session_id,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)

        return {
            "experience_id": exp.experience_id,
            "title": exp.title,
            "action": "created",
            "created_at": exp.created_at.isoformat(),
        }


# ==========================================
# Container Pool Stats (容器池状态)
# ==========================================

@router.get("/containers/stats")
async def get_container_pool_stats(
    user: User = Depends(get_current_user),
):
    """
    获取容器池状态 — 供管理后台使用。

    返回容器总数、空闲数、忙碌数等信息。
    """
    pool = get_container_pool()
    stats = await pool.get_stats()
    return stats.to_dict()
