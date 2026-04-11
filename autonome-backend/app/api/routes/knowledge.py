"""
知识检索 API 路由

提供领域知识相关接口：
1. GET /knowledge/search - 搜索知识
2. GET /knowledge/{knowledge_id} - 获取知识详情
3. POST /knowledge/extract - 触发知识提取
4. GET /knowledge/graph - 获取知识图谱
5. GET /knowledge/graph/related - 获取相关概念
6. POST /knowledge/graph/prerequisites - 推断前置步骤

设计原则：
- RESTful API 设计
- 分页和过滤支持
- 错误处理友好
- 统计信息暴露
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.logger import log
from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.domain_knowledge import (
    KnowledgeType,
    KnowledgeSource,
    DomainKnowledgeEntry,
    KnowledgeQueryResult,
    DomainKnowledgeRecord,
)
from app.services.knowledge_engine import KnowledgeEngine
from app.services.knowledge_graph import KnowledgeGraphService, RelationType


# ==========================================
# 请求/响应模型
# ==========================================

class KnowledgeSearchRequest(BaseModel):
    """知识搜索请求"""
    query: str = Field(description="搜索查询")
    knowledge_types: Optional[List[str]] = Field(default=None, description="知识类型过滤")
    limit: int = Field(default=10, ge=1, le=100, description="返回数量限制")


class KnowledgeSearchResult(BaseModel):
    """知识搜索结果项"""
    knowledge_id: str
    knowledge_type: str
    concept: str
    description: str
    synonyms: List[str] = Field(default_factory=list)
    confidence: float
    score: float
    match_type: str  # exact, synonym, semantic


class KnowledgeSearchResponse(BaseModel):
    """知识搜索响应"""
    success: bool
    data: Dict[str, Any]


class KnowledgeDetailResponse(BaseModel):
    """知识详情响应"""
    success: bool
    data: Dict[str, Any]


class KnowledgeExtractRequest(BaseModel):
    """知识提取请求"""
    source: str = Field(default="all", description="来源: all, executions, feedbacks, skills")
    skill_id: Optional[str] = Field(default=None, description="指定技能")
    days: int = Field(default=30, ge=1, le=365, description="分析最近 N 天数据")


class KnowledgeExtractResponse(BaseModel):
    """知识提取响应"""
    success: bool
    message: str
    stats: Dict[str, int]


class GraphNodeResponse(BaseModel):
    """图谱节点响应"""
    id: str
    label: str
    type: str
    confidence: float


class GraphEdgeResponse(BaseModel):
    """图谱边响应"""
    source: str
    target: str
    type: str
    weight: float


class KnowledgeGraphResponse(BaseModel):
    """知识图谱响应"""
    success: bool
    data: Dict[str, Any]


class PrerequisitesResponse(BaseModel):
    """前置步骤推断响应"""
    concept: str
    prerequisites: List[Dict[str, Any]]


class SolutionsResponse(BaseModel):
    """解决方案推荐响应"""
    error_keyword: str
    solutions: List[Dict[str, Any]]


# ==========================================
# 路由定义
# ==========================================

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str = Query(..., description="搜索查询"),
    knowledge_types: Optional[str] = Query(None, description="知识类型过滤，逗号分隔"),
    limit: int = Query(10, ge=1, le=100, description="返回数量限制"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    搜索知识

    根据查询搜索匹配的知识条目，支持类型过滤。

    Args:
        query: 搜索查询（概念、同义词等）
        knowledge_types: 知识类型过滤（可选）
        limit: 返回数量限制

    Returns:
        匹配的知识条目列表
    """
    log.info(f"[KnowledgeAPI] 搜索知识: query={query}, types={knowledge_types}")

    engine = KnowledgeEngine(session)

    # 解析知识类型
    types_filter = None
    if knowledge_types:
        try:
            types_filter = [
                KnowledgeType(t.strip())
                for t in knowledge_types.split(",")
                if t.strip() in [kt.value for kt in KnowledgeType]
            ]
        except ValueError:
            pass

    # 执行搜索
    results = engine.query_knowledge(
        query=query,
        knowledge_types=types_filter,
        limit=limit,
    )

    # 构建响应
    search_results = [
        KnowledgeSearchResult(
            knowledge_id=r.knowledge.knowledge_id,
            knowledge_type=r.knowledge.knowledge_type.value,
            concept=r.knowledge.concept,
            description=r.knowledge.description,
            synonyms=r.knowledge.synonyms,
            confidence=r.knowledge.effective_confidence,
            score=r.score,
            match_type=r.match_type,
        )
        for r in results
    ]

    return KnowledgeSearchResponse(
        success=True,
        data={
            "results": [r.model_dump() for r in search_results],
            "total": len(search_results),
            "query": query,
            "filters": {
                "knowledge_types": [t.value for t in types_filter] if types_filter else None,
            },
        },
    )


@router.get("/{knowledge_id}", response_model=KnowledgeDetailResponse)
async def get_knowledge_detail(
    knowledge_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取知识详情

    根据知识 ID 获取详细信息。

    Args:
        knowledge_id: 知识 ID

    Returns:
        知识详情
    """
    log.info(f"[KnowledgeAPI] 获取知识详情: {knowledge_id}")

    # 查询数据库
    record = session.exec(
        select(DomainKnowledgeRecord).where(
            DomainKnowledgeRecord.knowledge_id == knowledge_id
        )
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Knowledge not found: {knowledge_id}")

    # 转换为条目
    entry = record.to_entry()

    return KnowledgeDetailResponse(
        success=True,
        data={
            "knowledge_id": entry.knowledge_id,
            "knowledge_type": entry.knowledge_type.value,
            "concept": entry.concept,
            "description": entry.description,
            "synonyms": entry.synonyms,
            "variants": entry.variants,
            "related_skills": entry.related_skills,
            "related_categories": entry.related_categories,
            "usage_context": entry.usage_context,
            "example_queries": entry.example_queries,
            "rules": entry.rules,
            "solution": entry.solution,
            "source": entry.source.value,
            "confidence": entry.confidence,
            "effective_confidence": entry.effective_confidence,
            "usage_count": entry.usage_count,
            "success_count": entry.success_count,
            "is_verified": entry.is_verified,
            "verified_by": entry.verified_by,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        },
    )


@router.post("/extract", response_model=KnowledgeExtractResponse)
async def extract_knowledge(
    request: KnowledgeExtractRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    触发知识提取

    从指定来源提取知识并存储。

    Args:
        request: 提取请求参数

    Returns:
        提取统计信息
    """
    log.info(f"[KnowledgeAPI] 触发知识提取: source={request.source}")

    engine = KnowledgeEngine(session)

    # 根据来源执行提取
    all_knowledge: List[DomainKnowledgeEntry] = []

    if request.source in ["all", "executions"]:
        exec_knowledge = engine.extract_from_executions(
            skill_id=request.skill_id,
            days=request.days,
        )
        all_knowledge.extend(exec_knowledge)

    if request.source in ["all", "feedbacks"]:
        fb_knowledge = engine.extract_from_feedbacks(
            days=request.days,
        )
        all_knowledge.extend(fb_knowledge)

    if request.source in ["all", "skills"]:
        skill_knowledge = engine.extract_from_skills()
        all_knowledge.extend(skill_knowledge)

    # 批量保存
    engine.batch_save_knowledge(all_knowledge)

    # 获取统计
    stats = engine.get_stats()

    return KnowledgeExtractResponse(
        success=True,
        message=f"知识提取完成，共提取 {len(all_knowledge)} 条知识",
        stats=stats,
    )


@router.get("/graph/stats", response_model=KnowledgeGraphResponse)
async def get_graph_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取知识图谱统计信息

    Returns:
        图谱统计数据
    """
    log.info("[KnowledgeAPI] 获取图谱统计")

    graph = KnowledgeGraphService(session)

    if not graph.is_built():
        graph.build_from_knowledge_base()

    stats = graph.get_stats()

    return KnowledgeGraphResponse(
        success=True,
        data={"stats": stats},
    )


@router.get("/graph/related", response_model=KnowledgeGraphResponse)
async def get_related_concepts(
    concept: str = Query(..., description="概念关键词"),
    max_depth: int = Query(2, ge=1, le=5, description="最大搜索深度"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取相关概念

    在知识图谱中查找与给定概念相关的其他概念。

    Args:
        concept: 概念关键词
        max_depth: 最大搜索深度

    Returns:
        相关概念列表
    """
    log.info(f"[KnowledgeAPI] 查找相关概念: concept={concept}")

    graph = KnowledgeGraphService(session)

    if not graph.is_built():
        graph.build_from_knowledge_base()

    # 查找相关概念
    related = graph.find_related_concepts(concept, max_depth=max_depth)

    # 构建响应
    results = [
        {
            "knowledge_id": node.knowledge_id,
            "concept": node.concept,
            "knowledge_type": node.knowledge_type,
            "confidence": node.confidence,
            "relevance_score": score,
            "related_skills": node.related_skills,
        }
        for node, score in related
    ]

    return KnowledgeGraphResponse(
        success=True,
        data={
            "query_concept": concept,
            "related_concepts": results,
            "total": len(results),
        },
    )


@router.get("/graph/path", response_model=KnowledgeGraphResponse)
async def find_concept_path(
    from_concept: str = Query(..., description="起始概念"),
    to_concept: str = Query(..., description="目标概念"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    查找概念间路径

    在知识图谱中查找两个概念之间的路径。

    Args:
        from_concept: 起始概念
        to_concept: 目标概念

    Returns:
        路径信息
    """
    log.info(f"[KnowledgeAPI] 查找路径: {from_concept} -> {to_concept}")

    graph = KnowledgeGraphService(session)

    if not graph.is_built():
        graph.build_from_knowledge_base()

    # 查找路径
    path = graph.find_path(from_concept, to_concept)

    if not path:
        return KnowledgeGraphResponse(
            success=False,
            data={
                "message": f"未找到从 '{from_concept}' 到 '{to_concept}' 的路径",
                "path": None,
            },
        )

    # 构建响应
    path_data = {
        "nodes": [
            {
                "id": node.knowledge_id,
                "concept": node.concept,
                "type": node.knowledge_type,
            }
            for node in path.nodes
        ],
        "edges": [
            {
                "type": edge.relation_type,
                "weight": edge.weight,
                "evidence": edge.evidence,
            }
            for edge in path.edges
        ],
        "length": path.length,
        "confidence": path.confidence,
    }

    return KnowledgeGraphResponse(
        success=True,
        data={
            "from_concept": from_concept,
            "to_concept": to_concept,
            "path": path_data,
        },
    )


@router.post("/graph/prerequisites", response_model=PrerequisitesResponse)
async def infer_prerequisites(
    concept: str = Query(..., description="目标概念"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    推断前置步骤

    基于知识图谱推断执行某分析前需要的步骤。

    Args:
        concept: 目标概念

    Returns:
        前置步骤列表
    """
    log.info(f"[KnowledgeAPI] 推断前置步骤: concept={concept}")

    graph = KnowledgeGraphService(session)

    if not graph.is_built():
        graph.build_from_knowledge_base()

    # 推断前置步骤
    prereqs = graph.infer_prerequisites(concept)

    return PrerequisitesResponse(
        concept=concept,
        prerequisites=[
            {
                "knowledge_id": node.knowledge_id,
                "concept": node.concept,
                "knowledge_type": node.knowledge_type,
                "description": node.description,
            }
            for node in prereqs
        ],
    )


@router.post("/graph/solutions", response_model=SolutionsResponse)
async def infer_solutions(
    error_keyword: str = Query(..., description="错误关键词"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    推断错误解决方案

    基于知识图谱推荐可能的解决方案。

    Args:
        error_keyword: 错误关键词

    Returns:
        解决方案列表
    """
    log.info(f"[KnowledgeAPI] 推断解决方案: error={error_keyword}")

    graph = KnowledgeGraphService(session)

    if not graph.is_built():
        graph.build_from_knowledge_base()

    # 推断解决方案
    solutions = graph.infer_solutions(error_keyword)

    return SolutionsResponse(
        error_keyword=error_keyword,
        solutions=[
            {
                "knowledge_id": node.knowledge_id,
                "concept": node.concept,
                "description": node.description,
                "confidence": node.confidence,
            }
            for node in solutions
        ],
    )


@router.get("/types", response_model=Dict[str, Any])
async def get_knowledge_types():
    """
    获取知识类型列表

    Returns:
        所有可用的知识类型
    """
    return {
        "knowledge_types": [
            {"value": kt.value, "name": kt.name}
            for kt in KnowledgeType
        ],
        "sources": [
            {"value": ks.value, "name": ks.name}
            for ks in KnowledgeSource
        ],
        "relation_types": RelationType.all(),
    }


log.info("✅ 知识检索 API 路由已加载")