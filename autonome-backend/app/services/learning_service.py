"""
学习中心核心业务服务

提供文献 CRUD、标签管理、笔记管理、混合检索等核心业务逻辑

设计要点：
- 文献去重（file_hash 检查）
- 混合检索：关键词（tsvector）+ 语义（pgvector cosine distance）
- 分页查询支持
"""

from typing import Optional, List, Dict, Any
from sqlmodel import Session, select, col
from sqlalchemy import func, text

from app.core.logger import log
from app.models.learning import (
    Literature, LiteratureCreate, LiteratureUpdate, LiteraturePublic,
    LiteratureChunk, LiteratureChunkCreate, LiteratureChunkUpdate, LiteratureChunkPublic,
    LiteratureNote, LiteratureNoteCreate, LiteratureNoteUpdate, LiteratureNotePublic,
    LiteratureTag, LiteratureTagCreate, LiteratureTagUpdate, LiteratureTagPublic,
)
from app.models.enums import LiteratureStatus


# ==========================================
# 文献 CRUD
# ==========================================

def list_literatures(
    session: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = None,
) -> tuple[List[Literature], int]:
    """
    列出用户的文献（分页、搜索、标签筛选）

    Args:
        session: 数据库会话
        user_id: 用户 ID
        page: 页码（从 1 开始）
        page_size: 每页数量
        search: 搜索关键词（匹配标题、作者、DOI）
        tag: 标签筛选
        status: 状态筛选

    Returns:
        (文献列表, 总数)
    """
    query = select(Literature).where(Literature.owner_id == user_id)

    # 搜索条件：匹配标题、作者、DOI
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            col(Literature.title).ilike(search_pattern)
            | col(Literature.authors).ilike(search_pattern)
            | col(Literature.doi).ilike(search_pattern)
        )

    # 状态筛选
    if status:
        query = query.where(Literature.status == status)

    # 标签筛选（JSONB 包含查询）
    if tag:
        query = query.where(col(Literature.tags).contains([tag]))

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # 分页
    offset = (page - 1) * page_size
    query = query.order_by(col(Literature.updated_at).desc()).offset(offset).limit(page_size)
    literatures = session.exec(query).all()

    return literatures, total


def get_literature(session: Session, literature_id: int, user_id: int) -> Optional[Literature]:
    """获取文献详情（含权限检查）"""
    literature = session.get(Literature, literature_id)
    if literature and literature.owner_id == user_id:
        return literature
    return None


def create_literature(session: Session, user_id: int, lit_in: LiteratureCreate) -> Literature:
    """创建文献记录"""
    literature = Literature(
        **lit_in.model_dump(),
        owner_id=user_id,
    )
    session.add(literature)
    session.commit()
    session.refresh(literature)
    log.info(f"📚 [Learning] 创建文献: {literature.literature_id} - {literature.title}")
    return literature


def update_literature(session: Session, literature: Literature, lit_in: LiteratureUpdate) -> Literature:
    """更新文献"""
    update_data = lit_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(literature, key, value)
    session.add(literature)
    session.commit()
    session.refresh(literature)
    return literature


def delete_literature(session: Session, literature: Literature) -> None:
    """删除文献及其关联的知识块和笔记"""
    # 先删除关联的知识块
    chunks = session.exec(
        select(LiteratureChunk).where(LiteratureChunk.literature_id == literature.id)
    ).all()
    for chunk in chunks:
        session.delete(chunk)

    # 删除关联的笔记
    notes = session.exec(
        select(LiteratureNote).where(LiteratureNote.literature_id == literature.id)
    ).all()
    for note in notes:
        session.delete(note)

    # 删除文献本身
    session.delete(literature)
    session.commit()
    log.info(f"📚 [Learning] 删除文献: {literature.literature_id}")


def check_duplicate(session: Session, user_id: int, file_hash: str) -> Optional[Literature]:
    """检查文件是否已上传（基于 file_hash 去重）"""
    return session.exec(
        select(Literature).where(
            Literature.owner_id == user_id,
            Literature.file_hash == file_hash,
        )
    ).first()


def update_literature_status(
    session: Session,
    literature_id: int,
    status: LiteratureStatus,
    error: Optional[str] = None,
) -> None:
    """更新文献解析状态"""
    literature = session.get(Literature, literature_id)
    if literature:
        literature.status = status
        if error:
            literature.parse_error = error
        session.add(literature)
        session.commit()


# ==========================================
# 知识块 CRUD
# ==========================================

def list_chunks(session: Session, literature_id: int) -> List[LiteratureChunk]:
    """获取文献的所有知识块"""
    return session.exec(
        select(LiteratureChunk)
        .where(LiteratureChunk.literature_id == literature_id)
        .order_by(col(LiteratureChunk.chunk_index))
    ).all()


def create_chunk(session: Session, chunk_in: LiteratureChunkCreate) -> LiteratureChunk:
    """创建知识块"""
    chunk = LiteratureChunk(**chunk_in.model_dump())
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


def update_chunk(session: Session, chunk: LiteratureChunk, chunk_in: LiteratureChunkUpdate) -> LiteratureChunk:
    """更新知识块（支持专家修正）"""
    update_data = chunk_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(chunk, key, value)
    session.add(chunk)
    session.commit()
    session.refresh(chunk)
    return chunk


def get_chunk(session: Session, chunk_id: int) -> Optional[LiteratureChunk]:
    """获取知识块"""
    return session.get(LiteratureChunk, chunk_id)


# ==========================================
# 笔记 CRUD
# ==========================================

def list_notes(session: Session, literature_id: int, user_id: int) -> List[LiteratureNote]:
    """获取文献的用户笔记"""
    return session.exec(
        select(LiteratureNote).where(
            LiteratureNote.literature_id == literature_id,
            LiteratureNote.user_id == user_id,
        ).order_by(col(LiteratureNote.created_at).desc())
    ).all()


def create_note(session: Session, user_id: int, note_in: LiteratureNoteCreate) -> LiteratureNote:
    """创建笔记"""
    note = LiteratureNote(**note_in.model_dump(), user_id=user_id)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def update_note(session: Session, note: LiteratureNote, note_in: LiteratureNoteUpdate) -> LiteratureNote:
    """更新笔记"""
    update_data = note_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(note, key, value)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def delete_note(session: Session, note: LiteratureNote) -> None:
    """删除笔记"""
    session.delete(note)
    session.commit()


# ==========================================
# 标签管理
# ==========================================

def list_tags(session: Session, user_id: int) -> List[LiteratureTag]:
    """获取用户的所有标签"""
    return session.exec(
        select(LiteratureTag).where(LiteratureTag.user_id == user_id)
        .order_by(col(LiteratureTag.name))
    ).all()


def create_tag(session: Session, user_id: int, tag_in: LiteratureTagCreate) -> LiteratureTag:
    """创建标签"""
    tag = LiteratureTag(**tag_in.model_dump(), user_id=user_id)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


def delete_tag(session: Session, tag: LiteratureTag) -> None:
    """删除标签"""
    session.delete(tag)
    session.commit()


# ==========================================
# 混合检索
# ==========================================

def search_knowledge(
    session: Session,
    user_id: int,
    query: str,
    top_k: int = 10,
    use_semantic: bool = True,
) -> List[Dict[str, Any]]:
    """
    混合检索：关键词 + 语义检索

    Args:
        session: 数据库会话
        user_id: 用户 ID
        query: 搜索查询
        top_k: 返回结果数量
        use_semantic: 是否使用语义检索（需要 pgvector）

    Returns:
        检索结果列表，每项包含知识块内容和来源文献信息
    """
    results: List[Dict[str, Any]] = []

    # 1. 关键词检索（PostgreSQL ILIKE）
    keyword_pattern = f"%{query}%"
    keyword_chunks = session.exec(
        select(LiteratureChunk)
        .join(Literature, LiteratureChunk.literature_id == Literature.id)
        .where(
            Literature.owner_id == user_id,
            Literature.status == LiteratureStatus.READY,
            col(LiteratureChunk.content).ilike(keyword_pattern)
            | col(LiteratureChunk.figure_caption).ilike(keyword_pattern)
            | col(LiteratureChunk.section_title).ilike(keyword_pattern),
        )
        .limit(top_k)
    ).all()

    for chunk in keyword_chunks:
        lit = session.get(Literature, chunk.literature_id)
        results.append({
            "chunk_id": chunk.chunk_id,
            "content": chunk.content,
            "chunk_type": chunk.chunk_type.value,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "figure_caption": chunk.figure_caption,
            "source_title": lit.title if lit else None,
            "source_doi": lit.doi if lit else None,
            "source_literature_id": lit.literature_id if lit else None,
            "match_type": "keyword",
        })

    # 2. 语义检索（pgvector cosine distance）
    if use_semantic and len(results) < top_k:
        try:
            semantic_results = _semantic_search(session, user_id, query, top_k - len(results))
            results.extend(semantic_results)
        except Exception as e:
            log.warning(f"📚 [Learning] 语义检索失败，降级为纯关键词检索: {e}")

    return results[:top_k]


def _semantic_search(
    session: Session,
    user_id: int,
    query: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    语义检索（pgvector cosine distance）

    需要：
    1. 生成 query embedding
    2. 使用 pgvector 的 <=> 运算符进行近似最近邻搜索

    注意：此函数需要 embedding 服务可用，否则抛出异常
    """
    # 尝试生成 query embedding
    try:
        from app.services.skill_embedding_service import get_embedding
        query_vector = get_embedding(query)
    except ImportError:
        # 备选：使用 mcp/semantic_search 中的 embedding
        try:
            from app.mcp.semantic_search import get_query_embedding
            query_vector = get_query_embedding(query)
        except ImportError:
            log.warning("📚 [Learning] Embedding 服务不可用，跳过语义检索")
            return []

    if not query_vector:
        return []

    # 使用原生 SQL 进行 pgvector 检索
    # cosine distance: <=> 运算符（值越小越相似）
    sql = text("""
        SELECT lc.chunk_id, lc.content, lc.chunk_type, lc.page_number,
               lc.section_title, lc.figure_caption,
               l.title AS source_title, l.doi AS source_doi, l.literature_id AS source_literature_id
        FROM literature_chunk lc
        JOIN literature l ON lc.literature_id = l.id
        WHERE l.owner_id = :user_id
          AND l.status = 'ready'
          AND lc.embedding IS NOT NULL
        ORDER BY lc.embedding <=> :query_vector::vector
        LIMIT :top_k
    """)

    import json
    rows = session.exec(sql, params={
        "user_id": user_id,
        "query_vector": json.dumps(query_vector),
        "top_k": top_k,
    }).all()

    return [
        {
            "chunk_id": row.chunk_id,
            "content": row.content,
            "chunk_type": row.chunk_type,
            "page_number": row.page_number,
            "section_title": row.section_title,
            "figure_caption": row.figure_caption,
            "source_title": row.source_title,
            "source_doi": row.source_doi,
            "source_literature_id": row.source_literature_id,
            "match_type": "semantic",
        }
        for row in rows
    ]


# ==========================================
# 锻造上下文生成
# ==========================================

def generate_forge_context(
    session: Session,
    literature_id: int,
    user_id: int,
    chunk_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """
    生成锻造上下文 Prompt

    将文献的结构化知识组装为 Prompt，供 Chat 中的 Agent 使用

    Args:
        session: 数据库会话
        literature_id: 文献 ID
        user_id: 用户 ID
        chunk_ids: 指定知识块 ID（可选，不指定则使用所有 figure/table 块）

    Returns:
        结构化 Prompt 文本，或 None（文献不存在）
    """
    literature = get_literature(session, literature_id, user_id)
    if not literature:
        return None

    # 获取知识块
    if chunk_ids:
        chunks = session.exec(
            select(LiteratureChunk).where(
                LiteratureChunk.literature_id == literature_id,
                col(LiteratureChunk.chunk_id).in_(chunk_ids),
            )
        ).all()
    else:
        # 默认只取 figure 和 table 类型的块
        from app.models.enums import ChunkType
        chunks = session.exec(
            select(LiteratureChunk).where(
                LiteratureChunk.literature_id == literature_id,
                col(LiteratureChunk.chunk_type).in_([ChunkType.FIGURE, ChunkType.TABLE]),
            )
        ).all()
        # 如果没有图表块，则取所有块
        if not chunks:
            chunks = list_chunks(session, literature_id)

    # 组装 Prompt
    prompt_parts = [
        "基于以下文献知识，请生成可执行的分析代码：\n",
        f"文献：{literature.title} ({literature.journal or '未知期刊'}, {literature.year or '未知年份'})",
    ]
    if literature.doi:
        prompt_parts.append(f"DOI: {literature.doi}")
    prompt_parts.append("")

    for chunk in chunks:
        if chunk.chunk_type.value in ("figure", "table"):
            prompt_parts.append(f"### {chunk.chunk_type.value.upper()}: {chunk.figure_caption or '未命名'}")
        else:
            prompt_parts.append(f"### Section: {chunk.section_title or '未命名章节'}")

        prompt_parts.append(chunk.content)

        # 如果有提取的方法论元数据，附加到 Prompt
        if chunk.metadata_:
            if "methodology" in chunk.metadata_:
                prompt_parts.append(f"\n分析方法: {chunk.metadata_['methodology']}")
            if "tool_stack" in chunk.metadata_:
                prompt_parts.append(f"工具链: {chunk.metadata_['tool_stack']}")
            if "parameters" in chunk.metadata_:
                prompt_parts.append(f"关键参数: {chunk.metadata_['parameters']}")

        prompt_parts.append("")

    prompt_parts.append("请遵循 Autonome 代码规范生成完整的 Python/R 脚本。")
    prompt_parts.append("规范要求：1) 必须包含 argparse 参数系统；2) 表格数据输出 TSV；3) 绘图输出 PDF+PNG；4) 详细中文注释。")

    return "\n".join(prompt_parts)
