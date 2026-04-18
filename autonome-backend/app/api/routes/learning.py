"""
学习中心 API 路由

提供文献上传、检索、锻造上下文生成等接口

路由前缀: /api/learning
"""

import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.learning import (
    Literature, LiteratureCreate, LiteratureUpdate, LiteraturePublic,
    LiteratureChunk, LiteratureChunkUpdate, LiteratureChunkPublic,
    LiteratureNote, LiteratureNoteCreate, LiteratureNoteUpdate, LiteratureNotePublic,
    LiteratureTag, LiteratureTagCreate, LiteratureTagUpdate, LiteratureTagPublic,
)
from app.models.enums import LiteratureStatus
from app.services import learning_service
from app.services.learning_ingestion_service import compute_file_hash

router = APIRouter()


# ==========================================
# 文献 CRUD
# ==========================================

@router.get("/literatures", response_model=List[LiteraturePublic])
def list_literatures(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """列出用户的文献（分页、搜索、标签筛选）"""
    literatures, total = learning_service.list_literatures(
        session, current_user.id, page, page_size, search, tag, status
    )
    return literatures


@router.post("/literatures", response_model=LiteraturePublic)
async def upload_pdf(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    上传 PDF 文件（支持批量）

    流程：
    1. 保存文件到 uploads 目录
    2. 计算 file_hash 去重
    3. 创建 Literature 记录
    4. 触发 Celery 异步解析任务
    """
    if len(files) > 10:
        raise HTTPException(400, "最多同时上传 10 个文件")

    results = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"仅支持 PDF 文件: {file.filename}")

        # 保存文件
        upload_dir = os.path.join(settings.UPLOAD_DIR, "literatures")
        os.makedirs(upload_dir, exist_ok=True)
        file_id = str(uuid.uuid4())[:8]
        file_path = os.path.join(upload_dir, f"{file_id}_{file.filename}")

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # 计算文件哈希
        file_hash = compute_file_hash(file_path)

        # 去重检查
        existing = learning_service.check_duplicate(session, current_user.id, file_hash)
        if existing:
            log.info(f"📚 [Learning] 文件已存在，跳过: {file.filename}")
            results.append(existing)
            continue

        # 创建文献记录
        literature = Literature(
            title=os.path.splitext(file.filename)[0],
            file_path=file_path,
            file_hash=file_hash,
            owner_id=current_user.id,
            status=LiteratureStatus.UPLOADING,
        )
        session.add(literature)
        session.commit()
        session.refresh(literature)

        # 触发异步解析任务
        try:
            from app.tasks.learning_tasks import task_process_literature
            task_process_literature.delay(literature.id)
            log.info(f"📚 [Learning] 已触发解析任务: {literature.literature_id}")
        except Exception as e:
            log.warning(f"📚 [Learning] 触发解析任务失败: {e}")
            learning_service.update_literature_status(
                session, literature.id, LiteratureStatus.ERROR, str(e)
            )

        results.append(literature)

    # 返回第一个结果（单文件上传场景）
    return results[0] if len(results) == 1 else results


@router.get("/literatures/{literature_id}", response_model=LiteraturePublic)
def get_literature(
    literature_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取文献详情"""
    literature = learning_service.get_literature(session, literature_id, current_user.id)
    if not literature:
        raise HTTPException(404, "文献不存在")
    return literature


@router.delete("/literatures/{literature_id}")
def delete_literature(
    literature_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """删除文献"""
    literature = learning_service.get_literature(session, literature_id, current_user.id)
    if not literature:
        raise HTTPException(404, "文献不存在")
    learning_service.delete_literature(session, literature)
    return {"status": "success"}


@router.get("/literatures/{literature_id}/status")
def get_literature_status(
    literature_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """轮询文献解析状态"""
    literature = learning_service.get_literature(session, literature_id, current_user.id)
    if not literature:
        raise HTTPException(404, "文献不存在")
    return {
        "status": literature.status.value,
        "parse_error": literature.parse_error,
    }


@router.get("/literatures/{literature_id}/chunks", response_model=List[LiteratureChunkPublic])
def get_literature_chunks(
    literature_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取文献的所有知识块"""
    literature = learning_service.get_literature(session, literature_id, current_user.id)
    if not literature:
        raise HTTPException(404, "文献不存在")
    return learning_service.list_chunks(session, literature_id)


@router.put("/literatures/chunks/{chunk_id}", response_model=LiteratureChunkPublic)
def update_chunk(
    chunk_id: int,
    chunk_in: LiteratureChunkUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """更新知识块（专家修正）"""
    chunk = learning_service.get_chunk(session, chunk_id)
    if not chunk:
        raise HTTPException(404, "知识块不存在")
    updated = learning_service.update_chunk(session, chunk, chunk_in)

    # 如果内容被修改，重新生成 embedding
    if chunk_in.content:
        try:
            from app.services.learning_ingestion_service import generate_embedding
            embedding = generate_embedding(updated.content)
            if embedding:
                # 更新 embedding（需要原生 SQL，因为 SQLModel 不直接支持 vector 字段）
                from sqlalchemy import text as sql_text
                import json
                session.exec(sql_text(
                    "UPDATE literature_chunk SET embedding = :embedding WHERE id = :id"
                ), params={"embedding": json.dumps(embedding), "id": updated.id})
                session.commit()
                log.info(f"📚 [Learning] 知识块 embedding 已重新生成: {updated.chunk_id}")
        except Exception as e:
            log.warning(f"📚 [Learning] embedding 重新生成失败: {e}")

    return updated


# ==========================================
# 笔记 CRUD
# ==========================================

@router.get("/literatures/{literature_id}/notes", response_model=List[LiteratureNotePublic])
def get_literature_notes(
    literature_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取文献的用户笔记"""
    return learning_service.list_notes(session, literature_id, current_user.id)


@router.post("/literatures/{literature_id}/notes", response_model=LiteratureNotePublic)
def create_note(
    literature_id: int,
    note_in: LiteratureNoteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """创建笔记"""
    note_in.literature_id = literature_id
    return learning_service.create_note(session, current_user.id, note_in)


@router.put("/notes/{note_id}", response_model=LiteratureNotePublic)
def update_note(
    note_id: int,
    note_in: LiteratureNoteUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """更新笔记"""
    note = session.get(LiteratureNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "笔记不存在")
    return learning_service.update_note(session, note, note_in)


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """删除笔记"""
    note = session.get(LiteratureNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "笔记不存在")
    learning_service.delete_note(session, note)
    return {"status": "success"}


# ==========================================
# 标签管理
# ==========================================

@router.get("/tags", response_model=List[LiteratureTagPublic])
def list_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取用户的所有标签"""
    return learning_service.list_tags(session, current_user.id)


@router.post("/tags", response_model=LiteratureTagPublic)
def create_tag(
    tag_in: LiteratureTagCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """创建标签"""
    return learning_service.create_tag(session, current_user.id, tag_in)


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """删除标签"""
    tag = session.get(LiteratureTag, tag_id)
    if not tag or tag.user_id != current_user.id:
        raise HTTPException(404, "标签不存在")
    learning_service.delete_tag(session, tag)
    return {"status": "success"}


# ==========================================
# 混合检索
# ==========================================

@router.post("/search")
def search_knowledge(
    query: str,
    top_k: int = Query(default=10, ge=1, le=50),
    use_semantic: bool = True,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """混合检索（关键词 + pgvector 语义）"""
    results = learning_service.search_knowledge(
        session, current_user.id, query, top_k, use_semantic
    )
    return {"results": results, "total": len(results)}


# ==========================================
# DOI 导入
# ==========================================

@router.post("/ingest/doi")
def ingest_doi(
    doi: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    通过 DOI 导入文献

    流程：
    1. 调用 CrossRef API 获取元数据
    2. 尝试 Unpaywall 获取开放获取 PDF
    3. 如获取到 PDF，触发异步解析任务
    """
    # 先创建文献记录（仅元数据）
    literature = Literature(
        title=f"DOI: {doi}",
        doi=doi,
        owner_id=current_user.id,
        status=LiteratureStatus.PARSING,
    )
    session.add(literature)
    session.commit()
    session.refresh(literature)

    # 触发异步 DOI 解析任务
    try:
        from app.tasks.learning_tasks import task_process_doi
        task_process_doi.delay(literature.id, doi)
        log.info(f"📚 [Learning] 已触发 DOI 解析任务: {doi}")
    except Exception as e:
        log.warning(f"📚 [Learning] 触发 DOI 解析任务失败: {e}")
        learning_service.update_literature_status(
            session, literature.id, LiteratureStatus.ERROR, str(e)
        )

    return {"status": "processing", "literature_id": literature.literature_id}


# ==========================================
# 锻造上下文生成
# ==========================================

@router.post("/forge-context")
def generate_forge_context(
    literature_id: int,
    chunk_ids: Optional[List[str]] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    生成锻造上下文 Prompt

    将文献的结构化知识组装为 Prompt，供 Chat 中的 Agent 使用
    """
    prompt = learning_service.generate_forge_context(
        session, literature_id, current_user.id, chunk_ids
    )
    if not prompt:
        raise HTTPException(404, "文献不存在")
    return {"prompt": prompt}
