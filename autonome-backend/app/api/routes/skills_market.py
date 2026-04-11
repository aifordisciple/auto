"""
技能市场 API 路由 - 提供技能浏览、搜索、评分、收藏等功能

核心端点:
- GET /skills: 获取公开技能列表（分页、筛选、排序）
- GET /skills/{skill_id}: 获取技能详情
- POST /skills/{skill_id}/rate: 为技能评分
- POST /skills/{skill_id}/favorite: 收藏/取消收藏技能
- GET /my/favorites: 获取我收藏的技能
- GET /my/created: 获取我创建的技能
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func, or_, and_
from pydantic import BaseModel, Field

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillStatus, SkillReview, SkillFavorite,
    SkillExecutionHistory, get_utc_now
)

router = APIRouter()


# ==========================================
# 请求/响应模型定义
# ==========================================

class SkillSummary(BaseModel):
    """技能摘要信息"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    category: Optional[str] = None
    tags: List[str] = []
    avg_rating: float = 0.0
    rating_count: int = 0
    usage_count: int = 0
    owner_name: Optional[str] = None
    is_favorited: bool = False
    status: str = "DRAFT"  # 技能状态：DRAFT, PRIVATE, PUBLISHED, PENDING_REVIEW
    created_at: str
    updated_at: Optional[str] = None  # 最后更新时间


class SkillDetail(BaseModel):
    """技能详细信息"""
    skill_id: str
    name: str
    description: Optional[str]
    version: str
    executor_type: str
    parameters_schema: dict
    expert_knowledge: Optional[str]
    dependencies: List[str]
    avg_rating: float = 0.0
    rating_count: int = 0
    usage_count: int = 0
    owner_id: int
    owner_name: Optional[str] = None
    is_favorited: bool = False
    user_rating: Optional[int] = None
    created_at: str
    updated_at: str


class PaginatedSkillsResponse(BaseModel):
    """分页技能列表响应"""
    skills: List[SkillSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class RateSkillRequest(BaseModel):
    """评分请求"""
    rating: int = Field(ge=1, le=5, description="评分 1-5 星")
    comment: Optional[str] = Field(default=None, max_length=500, description="评价内容")


class RateSkillResponse(BaseModel):
    """评分响应"""
    skill_id: str
    rating: int
    avg_rating: float
    rating_count: int


class FavoriteResponse(BaseModel):
    """收藏响应"""
    skill_id: str
    is_favorited: bool
    favorite_count: int


class ReviewItem(BaseModel):
    """评价项"""
    id: int
    user_name: Optional[str]
    rating: int
    comment: Optional[str]
    created_at: str


class ExecutionHistoryItem(BaseModel):
    """执行历史项"""
    id: int
    project_id: str
    status: str
    parameters: dict
    execution_time: Optional[float]
    created_at: str


class SkillDetailFull(BaseModel):
    """技能完整详情（包含评论和执行历史）"""
    skill_id: str
    name: str
    description: Optional[str]
    version: str
    executor_type: str
    parameters_schema: dict
    expert_knowledge: Optional[str]
    dependencies: List[str]
    avg_rating: float = 0.0
    rating_count: int = 0
    usage_count: int = 0
    favorite_count: int = 0
    owner_id: int
    owner_name: Optional[str] = None
    is_favorited: bool = False
    user_rating: Optional[int] = None
    reviews: List[ReviewItem] = []
    recent_executions: List[ExecutionHistoryItem] = []
    created_at: str
    updated_at: str


# ==========================================
# 辅助函数
# ==========================================

def get_skill_category(skill: SkillAsset) -> str:
    """从技能信息推断分类"""
    # 简单分类逻辑，可以根据实际情况扩展
    name_lower = (skill.name or "").lower()
    desc_lower = (skill.description or "").lower()

    if any(kw in name_lower or kw in desc_lower for kw in ["qc", "质量", "fastqc", "quality"]):
        return "质量控制"
    elif any(kw in name_lower or kw in desc_lower for kw in ["rna", "转录", "表达", "deseq", "rnaseq"]):
        return "转录组分析"
    elif any(kw in name_lower or kw in desc_lower for kw in ["单细胞", "cell", "seurat", "scanpy", "scrna"]):
        return "单细胞分析"
    elif any(kw in name_lower or kw in desc_lower for kw in ["chip", "peak", "atac", "染色质"]):
        return "表观遗传分析"
    elif any(kw in name_lower or kw in desc_lower for kw in ["变异", "snp", "vcf", "外显子", "exome"]):
        return "变异检测"
    elif any(kw in name_lower or kw in desc_lower for kw in ["图", "plot", "可视化", "vis"]):
        return "可视化"
    elif any(kw in name_lower or kw in desc_lower for kw in ["nextflow", "pipeline", "流程", "工作流"]):
        return "工作流"
    else:
        return "其他"


# ==========================================
# GET /skills - 获取公开技能列表
# ==========================================
@router.get("/skills", response_model=PaginatedSkillsResponse)
async def list_public_skills(
    category: Optional[str] = Query(default=None, description="分类筛选"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
    sort_by: str = Query(default="popularity", regex="^(popularity|rating|recent)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取公开技能列表（分页、筛选、排序）

    - category: 分类筛选
    - search: 搜索关键词（名称、描述）
    - sort_by: 排序方式 (popularity | rating | recent)
    """
    # 基础查询：只获取已发布的技能
    base_query = select(SkillAsset).where(SkillAsset.status == SkillStatus.PUBLISHED)

    # 分类筛选
    if category:
        # 由于没有 category 字段，使用名称/描述匹配
        category_keywords = {
            "质量控制": ["qc", "质量", "fastqc", "quality"],
            "转录组分析": ["rna", "转录", "表达", "deseq", "rnaseq"],
            "单细胞分析": ["单细胞", "cell", "seurat", "scanpy", "scrna"],
            "表观遗传分析": ["chip", "peak", "atac", "染色质"],
            "变异检测": ["变异", "snp", "vcf", "外显子", "exome"],
            "可视化": ["图", "plot", "可视化", "vis"],
            "工作流": ["nextflow", "pipeline", "流程", "工作流"],
        }
        keywords = category_keywords.get(category, [])
        if keywords:
            conditions = [or_(
                SkillAsset.name.ilike(f"%{kw}%"),
                SkillAsset.description.ilike(f"%{kw}%")
            ) for kw in keywords]
            base_query = base_query.where(or_(*conditions))

    # 搜索筛选
    if search:
        base_query = base_query.where(or_(
            SkillAsset.name.ilike(f"%{search}%"),
            SkillAsset.description.ilike(f"%{search}%")
        ))

    # 获取总数
    count_query = select(func.count()).select_from(base_query.subquery())
    total = session.exec(count_query).one()

    # 排序
    if sort_by == "recent":
        base_query = base_query.order_by(SkillAsset.created_at.desc())
    elif sort_by == "rating":
        # 按评分排序（需要子查询）
        base_query = base_query.order_by(SkillAsset.updated_at.desc())
    else:  # popularity
        # 按使用量排序（需要子查询）
        base_query = base_query.order_by(SkillAsset.updated_at.desc())

    # 分页
    offset = (page - 1) * page_size
    skills = session.exec(base_query.offset(offset).limit(page_size)).all()

    # 获取附加信息（评分、使用量、收藏状态）
    skill_summaries = []
    for skill in skills:
        # 平均评分
        rating_query = select(
            func.avg(SkillReview.rating).label("avg"),
            func.count(SkillReview.id).label("count")
        ).where(SkillReview.skill_id == skill.skill_id)
        rating_result = session.exec(rating_query).first()
        avg_rating = float(rating_result[0] or 0)
        rating_count = rating_result[1] or 0

        # 使用量
        usage_query = select(func.count(SkillExecutionHistory.id)).where(
            SkillExecutionHistory.skill_id == skill.skill_id
        )
        usage_count = session.exec(usage_query).one() or 0

        # 收藏状态
        is_favorited = session.exec(
            select(SkillFavorite).where(
                and_(
                    SkillFavorite.skill_id == skill.skill_id,
                    SkillFavorite.user_id == current_user.id
                )
            )
        ).first() is not None

        # 所有者名称
        owner = session.get(User, skill.owner_id)
        owner_name = owner.full_name or owner.email if owner else None

        skill_summaries.append(SkillSummary(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=get_skill_category(skill),
            tags=[],
            avg_rating=round(avg_rating, 1),
            rating_count=rating_count,
            usage_count=usage_count,
            owner_name=owner_name,
            is_favorited=is_favorited,
            created_at=skill.created_at.isoformat()
        ))

    total_pages = (total + page_size - 1) // page_size

    log.info(f"📊 [SkillMarket] 获取技能列表: {len(skills)} 条, 用户: {current_user.id}")

    return PaginatedSkillsResponse(
        skills=skill_summaries,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


# ==========================================
# GET /skills/{skill_id} - 获取技能详情
# ==========================================
@router.get("/skills/{skill_id}", response_model=SkillDetail)
async def get_skill_detail(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能详细信息"""
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 检查权限：非公开技能只有所有者可查看
    if skill.status != SkillStatus.PUBLISHED and skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此技能")

    # 平均评分
    rating_query = select(
        func.avg(SkillReview.rating).label("avg"),
        func.count(SkillReview.id).label("count")
    ).where(SkillReview.skill_id == skill_id)
    rating_result = session.exec(rating_query).first()
    avg_rating = float(rating_result[0] or 0)
    rating_count = rating_result[1] or 0

    # 使用量
    usage_query = select(func.count(SkillExecutionHistory.id)).where(
        SkillExecutionHistory.skill_id == skill_id
    )
    usage_count = session.exec(usage_query).one() or 0

    # 收藏状态
    is_favorited = session.exec(
        select(SkillFavorite).where(
            and_(
                SkillFavorite.skill_id == skill_id,
                SkillFavorite.user_id == current_user.id
            )
        )
    ).first() is not None

    # 用户评分
    user_review = session.exec(
        select(SkillReview).where(
            and_(
                SkillReview.skill_id == skill_id,
                SkillReview.user_id == current_user.id
            )
        )
    ).first()
    user_rating = user_review.rating if user_review else None

    # 所有者名称
    owner = session.get(User, skill.owner_id)
    owner_name = owner.full_name or owner.email if owner else None

    log.info(f"📊 [SkillMarket] 获取技能详情: {skill_id}, 用户: {current_user.id}")

    return SkillDetail(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        version=skill.version,
        executor_type=skill.executor_type,
        parameters_schema=skill.parameters_schema,
        expert_knowledge=skill.expert_knowledge,
        dependencies=skill.dependencies,
        avg_rating=round(avg_rating, 1),
        rating_count=rating_count,
        usage_count=usage_count,
        owner_id=skill.owner_id,
        owner_name=owner_name,
        is_favorited=is_favorited,
        user_rating=user_rating,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat()
    )


# ==========================================
# GET /skills/{skill_id}/full - 获取技能完整详情（含评论和执行历史）
# ==========================================
@router.get("/skills/{skill_id}/full", response_model=SkillDetailFull)
async def get_skill_detail_full(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取技能完整详情，包括：
    - 基本信息
    - 参数说明
    - 专家知识
    - 用户评价
    - 执行历史
    """
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 检查权限：非公开技能只有所有者可查看
    if skill.status != SkillStatus.PUBLISHED and skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此技能")

    # 平均评分
    rating_query = select(
        func.avg(SkillReview.rating).label("avg"),
        func.count(SkillReview.id).label("count")
    ).where(SkillReview.skill_id == skill_id)
    rating_result = session.exec(rating_query).first()
    avg_rating = float(rating_result[0] or 0)
    rating_count = rating_result[1] or 0

    # 使用量
    usage_query = select(func.count(SkillExecutionHistory.id)).where(
        SkillExecutionHistory.skill_id == skill_id
    )
    usage_count = session.exec(usage_query).one() or 0

    # 收藏总数
    favorite_count = session.exec(
        select(func.count(SkillFavorite.id)).where(SkillFavorite.skill_id == skill_id)
    ).one() or 0

    # 收藏状态
    is_favorited = session.exec(
        select(SkillFavorite).where(
            and_(
                SkillFavorite.skill_id == skill_id,
                SkillFavorite.user_id == current_user.id
            )
        )
    ).first() is not None

    # 用户评分
    user_review = session.exec(
        select(SkillReview).where(
            and_(
                SkillReview.skill_id == skill_id,
                SkillReview.user_id == current_user.id
            )
        )
    ).first()
    user_rating = user_review.rating if user_review else None

    # 所有者名称
    owner = session.get(User, skill.owner_id)
    owner_name = owner.full_name or owner.email if owner else None

    # 获取评价列表（最近10条）
    reviews_query = select(SkillReview).where(
        SkillReview.skill_id == skill_id
    ).order_by(SkillReview.created_at.desc()).limit(10)
    reviews = session.exec(reviews_query).all()

    review_items = []
    for review in reviews:
        reviewer = session.get(User, review.user_id)
        review_items.append(ReviewItem(
            id=review.id,
            user_name=reviewer.full_name or reviewer.email if reviewer else "匿名用户",
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at.isoformat()
        ))

    # 获取执行历史（最近10条，仅当前用户）
    executions_query = select(SkillExecutionHistory).where(
        and_(
            SkillExecutionHistory.skill_id == skill_id,
            SkillExecutionHistory.user_id == current_user.id
        )
    ).order_by(SkillExecutionHistory.created_at.desc()).limit(10)
    executions = session.exec(executions_query).all()

    execution_items = []
    for execution in executions:
        execution_items.append(ExecutionHistoryItem(
            id=execution.id,
            project_id=execution.project_id or "",
            status=execution.status or "unknown",
            parameters=execution.parameters or {},
            execution_time=execution.execution_time,
            created_at=execution.created_at.isoformat()
        ))

    log.info(f"📊 [SkillMarket] 获取技能完整详情: {skill_id}, 用户: {current_user.id}, 评价: {len(review_items)}, 执行: {len(execution_items)}")

    return SkillDetailFull(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        version=skill.version,
        executor_type=skill.executor_type,
        parameters_schema=skill.parameters_schema,
        expert_knowledge=skill.expert_knowledge,
        dependencies=skill.dependencies,
        avg_rating=round(avg_rating, 1),
        rating_count=rating_count,
        usage_count=usage_count,
        favorite_count=favorite_count,
        owner_id=skill.owner_id,
        owner_name=owner_name,
        is_favorited=is_favorited,
        user_rating=user_rating,
        reviews=review_items,
        recent_executions=execution_items,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat()
    )


# ==========================================
# POST /skills/{skill_id}/rate - 为技能评分
# ==========================================
@router.post("/skills/{skill_id}/rate", response_model=RateSkillResponse)
async def rate_skill(
    skill_id: str,
    request: RateSkillRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """为技能评分（更新或创建）"""
    # 检查技能是否存在
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 检查是否已评分
    existing_review = session.exec(
        select(SkillReview).where(
            and_(
                SkillReview.skill_id == skill_id,
                SkillReview.user_id == current_user.id
            )
        )
    ).first()

    if existing_review:
        # 更新评分
        existing_review.rating = request.rating
        existing_review.comment = request.comment
        existing_review.updated_at = get_utc_now()
        session.add(existing_review)
        log.info(f"⭐ [SkillMarket] 更新评分: {skill_id} -> {request.rating}, 用户: {current_user.id}")
    else:
        # 创建新评分
        review = SkillReview(
            skill_id=skill_id,
            user_id=current_user.id,
            rating=request.rating,
            comment=request.comment
        )
        session.add(review)
        log.info(f"⭐ [SkillMarket] 新增评分: {skill_id} -> {request.rating}, 用户: {current_user.id}")

    session.commit()

    # 重新计算平均评分
    rating_query = select(
        func.avg(SkillReview.rating).label("avg"),
        func.count(SkillReview.id).label("count")
    ).where(SkillReview.skill_id == skill_id)
    rating_result = session.exec(rating_query).first()
    avg_rating = float(rating_result[0] or 0)
    rating_count = rating_result[1] or 0

    return RateSkillResponse(
        skill_id=skill_id,
        rating=request.rating,
        avg_rating=round(avg_rating, 1),
        rating_count=rating_count
    )


# ==========================================
# POST /skills/{skill_id}/favorite - 收藏/取消收藏
# ==========================================
@router.post("/skills/{skill_id}/favorite", response_model=FavoriteResponse)
async def toggle_favorite(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """收藏或取消收藏技能"""
    # 检查技能是否存在
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 检查是否已收藏
    existing_favorite = session.exec(
        select(SkillFavorite).where(
            and_(
                SkillFavorite.skill_id == skill_id,
                SkillFavorite.user_id == current_user.id
            )
        )
    ).first()

    if existing_favorite:
        # 取消收藏
        session.delete(existing_favorite)
        is_favorited = False
        log.info(f"💔 [SkillMarket] 取消收藏: {skill_id}, 用户: {current_user.id}")
    else:
        # 添加收藏
        favorite = SkillFavorite(
            skill_id=skill_id,
            user_id=current_user.id
        )
        session.add(favorite)
        is_favorited = True
        log.info(f"❤️ [SkillMarket] 添加收藏: {skill_id}, 用户: {current_user.id}")

    session.commit()

    # 获取收藏总数
    favorite_count = session.exec(
        select(func.count(SkillFavorite.id)).where(SkillFavorite.skill_id == skill_id)
    ).one() or 0

    return FavoriteResponse(
        skill_id=skill_id,
        is_favorited=is_favorited,
        favorite_count=favorite_count
    )


# ==========================================
# GET /my/favorites - 获取我收藏的技能
# ==========================================
@router.get("/my/favorites", response_model=List[SkillSummary])
async def get_my_favorites(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取我收藏的技能列表"""
    # 获取收藏记录
    favorites = session.exec(
        select(SkillFavorite).where(SkillFavorite.user_id == current_user.id)
    ).all()

    skill_ids = [f.skill_id for f in favorites]
    if not skill_ids:
        return []

    # 获取技能详情
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id.in_(skill_ids))
    ).all()

    skill_summaries = []
    for skill in skills:
        # 平均评分
        rating_query = select(
            func.avg(SkillReview.rating).label("avg"),
            func.count(SkillReview.id).label("count")
        ).where(SkillReview.skill_id == skill.skill_id)
        rating_result = session.exec(rating_query).first()
        avg_rating = float(rating_result[0] or 0)
        rating_count = rating_result[1] or 0

        # 使用量
        usage_query = select(func.count(SkillExecutionHistory.id)).where(
            SkillExecutionHistory.skill_id == skill.skill_id
        )
        usage_count = session.exec(usage_query).one() or 0

        # 所有者名称
        owner = session.get(User, skill.owner_id)
        owner_name = owner.full_name or owner.email if owner else None

        skill_summaries.append(SkillSummary(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=get_skill_category(skill),
            tags=[],
            avg_rating=round(avg_rating, 1),
            rating_count=rating_count,
            usage_count=usage_count,
            owner_name=owner_name,
            is_favorited=True,
            created_at=skill.created_at.isoformat()
        ))

    log.info(f"📚 [SkillMarket] 获取收藏列表: {len(skill_summaries)} 条, 用户: {current_user.id}")

    return skill_summaries


# ==========================================
# GET /my/created - 获取我创建的技能
# ==========================================
@router.get("/my/created", response_model=List[SkillSummary])
async def get_my_created_skills(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取我创建的技能列表"""
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.owner_id == current_user.id)
    ).all()

    skill_summaries = []
    for skill in skills:
        # 平均评分
        rating_query = select(
            func.avg(SkillReview.rating).label("avg"),
            func.count(SkillReview.id).label("count")
        ).where(SkillReview.skill_id == skill.skill_id)
        rating_result = session.exec(rating_query).first()
        avg_rating = float(rating_result[0] or 0)
        rating_count = rating_result[1] or 0

        # 使用量
        usage_query = select(func.count(SkillExecutionHistory.id)).where(
            SkillExecutionHistory.skill_id == skill.skill_id
        )
        usage_count = session.exec(usage_query).one() or 0

        skill_summaries.append(SkillSummary(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=get_skill_category(skill),
            tags=[],
            avg_rating=round(avg_rating, 1),
            rating_count=rating_count,
            usage_count=usage_count,
            owner_name="我",
            is_favorited=False,
            status=skill.status,  # 技能状态
            created_at=skill.created_at.isoformat(),
            updated_at=skill.updated_at.isoformat() if skill.updated_at else None  # 最后更新时间
        ))

    log.info(f"🔧 [SkillMarket] 获取创建列表: {len(skill_summaries)} 条, 用户: {current_user.id}")

    return skill_summaries


# ==========================================
# GET /categories - 获取分类列表
# ==========================================
@router.get("/categories")
async def get_categories():
    """获取技能分类列表"""
    return {
        "categories": [
            {"id": "qc", "name": "质量控制", "icon": "🛡️"},
            {"id": "transcriptome", "name": "转录组分析", "icon": "🧬"},
            {"id": "singlecell", "name": "单细胞分析", "icon": "🔬"},
            {"id": "epigenome", "name": "表观遗传分析", "icon": "🎨"},
            {"id": "variant", "name": "变异检测", "icon": "🔍"},
            {"id": "visualization", "name": "可视化", "icon": "📊"},
            {"id": "pipeline", "name": "工作流", "icon": "⚙️"},
            {"id": "other", "name": "其他", "icon": "📦"},
        ]
    }


log.info("✅ 技能市场 API 已加载")


# ==========================================
# 推荐相关端点
# ==========================================

class TrendingSkillResponse(BaseModel):
    """热门技能响应"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    usage_count: int
    avg_rating: float
    trend: str  # "rising" | "stable" | "hot"


class RecentSkillResponse(BaseModel):
    """最新技能响应"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    avg_rating: float
    created_at: str
    is_new: bool


class PersonalizedSkillResponse(BaseModel):
    """个性化推荐响应"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    category: Optional[str]
    match_score: float
    match_reason: str
    avg_rating: float
    usage_count: int


class HistoryItemResponse(BaseModel):
    """执行历史响应"""
    id: int
    skill_id: str
    skill_name: str
    status: str
    parameters: dict  # ✨ 新增：执行参数，用于重新执行
    execution_time: Optional[float]
    created_at: str
    output_dir: Optional[str]


# GET /trending - 热门技能
@router.get("/trending", response_model=List[TrendingSkillResponse])
async def get_trending_skills(
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session)
):
    """获取热门技能（按使用量排序）"""
    # 获取已发布技能
    skills = session.exec(
        select(SkillAsset)
        .where(SkillAsset.status == SkillStatus.PUBLISHED)
        .order_by(SkillAsset.updated_at.desc())
        .limit(limit * 3)  # 多取一些用于计算使用量
    ).all()

    results = []
    for skill in skills:
        # 使用量
        usage_count = session.exec(
            select(func.count(SkillExecutionHistory.id))
            .where(SkillExecutionHistory.skill_id == skill.skill_id)
        ).one() or 0

        # 评分
        avg_rating = session.exec(
            select(func.avg(SkillReview.rating))
            .where(SkillReview.skill_id == skill.skill_id)
        ).first() or 0

        # 趋势判断
        if usage_count > 50:
            trend = "hot"
        elif usage_count > 10:
            trend = "rising"
        else:
            trend = "stable"

        results.append(TrendingSkillResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            usage_count=usage_count,
            avg_rating=round(float(avg_rating), 1),
            trend=trend
        ))

    # 按使用量排序，返回指定数量
    results.sort(key=lambda x: x.usage_count, reverse=True)
    return results[:limit]


# GET /recent - 最新上线
@router.get("/recent", response_model=List[RecentSkillResponse])
async def get_recent_skills(
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session)
):
    """获取最新上线的技能"""
    from datetime import datetime, timedelta

    skills = session.exec(
        select(SkillAsset)
        .where(SkillAsset.status == SkillStatus.PUBLISHED)
        .order_by(SkillAsset.created_at.desc())
        .limit(limit)
    ).all()

    results = []
    for skill in skills:
        # 评分
        avg_rating = session.exec(
            select(func.avg(SkillReview.rating))
            .where(SkillReview.skill_id == skill.skill_id)
        ).first() or 0

        # 判断是否是新技能（7天内创建）
        days_old = (datetime.utcnow() - skill.created_at.replace(tzinfo=None)).days if skill.created_at else 999
        is_new = days_old < 7

        results.append(RecentSkillResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            avg_rating=round(float(avg_rating), 1),
            created_at=skill.created_at.isoformat() if skill.created_at else "",
            is_new=is_new
        ))

    return results


# GET /personalized - 个性化推荐
@router.get("/personalized", response_model=List[PersonalizedSkillResponse])
async def get_personalized_skills(
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取个性化推荐技能（基于用户历史）"""
    # 获取用户最近执行的技能分类
    recent_executions = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.user_id == current_user.id)
        .order_by(SkillExecutionHistory.created_at.desc())
        .limit(10)
    ).all()

    # 获取用户执行过的技能ID
    executed_skill_ids = list(set(e.skill_id for e in recent_executions if e.skill_id))

    # 获取这些技能的分类信息
    user_categories = set()
    for skill_id_str in executed_skill_ids:
        # 使用 skill_id 字符串查询，不是主键
        skill = session.exec(
            select(SkillAsset).where(SkillAsset.skill_id == skill_id_str)
        ).first()
        if skill:
            cat = get_skill_category(skill)
            user_categories.add(cat)

    # 获取推荐技能（排除已执行过的）
    all_skills = session.exec(
        select(SkillAsset)
        .where(SkillAsset.status == SkillStatus.PUBLISHED)
        .order_by(SkillAsset.updated_at.desc())
        .limit(50)
    ).all()

    results = []
    for skill in all_skills:
        if skill.skill_id in executed_skill_ids:
            continue

        # 评分
        avg_rating = session.exec(
            select(func.avg(SkillReview.rating))
            .where(SkillReview.skill_id == skill.skill_id)
        ).first() or 0

        # 使用量
        usage_count = session.exec(
            select(func.count(SkillExecutionHistory.id))
            .where(SkillExecutionHistory.skill_id == skill.skill_id)
        ).one() or 0

        # 匹配分数计算
        skill_category = get_skill_category(skill)
        if skill_category in user_categories:
            match_score = 0.9
            match_reason = "基于您的使用偏好"
        else:
            match_score = 0.5
            match_reason = "热门推荐"

        results.append(PersonalizedSkillResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=skill_category,
            match_score=match_score,
            match_reason=match_reason,
            avg_rating=round(float(avg_rating), 1),
            usage_count=usage_count
        ))

    # 按匹配分数排序
    results.sort(key=lambda x: x.match_score, reverse=True)
    return results[:limit]


# GET /my/history - 执行历史
@router.get("/my/history", response_model=List[HistoryItemResponse])
async def get_my_execution_history(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的技能执行历史

    包含完整的执行参数，支持前端"重新执行"功能
    """
    executions = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.user_id == current_user.id)
        .order_by(SkillExecutionHistory.created_at.desc())
        .limit(limit)
    ).all()

    results = []
    for execution in executions:
        # 获取技能名称（使用 skill_id 字符串查询，不是主键）
        skill = session.exec(
            select(SkillAsset).where(SkillAsset.skill_id == execution.skill_id)
        ).first()
        skill_name = skill.name if skill else execution.skill_id

        results.append(HistoryItemResponse(
            id=execution.id,
            skill_id=execution.skill_id,
            skill_name=skill_name,
            status=execution.status or "unknown",
            parameters=execution.parameters or {},  # ✨ 返回执行参数
            execution_time=execution.execution_time,
            created_at=execution.created_at.isoformat() if execution.created_at else "",
            output_dir=execution.output_dir
        ))

    return results