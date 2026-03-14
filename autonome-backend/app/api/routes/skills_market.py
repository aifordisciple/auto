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
    created_at: str


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
            created_at=skill.created_at.isoformat()
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