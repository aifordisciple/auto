"""
技能推荐系统 API - 根据用户需求智能推荐合适的技能

核心端点:
- POST /recommend: 基于用户描述推荐技能
- POST /recommend/data: 基于数据类型推荐技能
- GET /trending: 获取热门技能
- GET /personalized: 获取个性化推荐
"""

import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_, and_

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillStatus, SkillExecutionHistory, SkillReview, SkillFavorite
)

router = APIRouter()


# ==========================================
# 请求模型
# ==========================================
class RecommendRequest(BaseModel):
    """技能推荐请求"""
    user_query: str = Field(description="用户需求描述")
    data_type: Optional[str] = Field(default=None, description="数据类型: rnaseq/scrna/chipseq/atacseq")
    analysis_goal: Optional[str] = Field(default=None, description="分析目标")
    limit: int = Field(default=5, description="推荐数量")


class DataBasedRecommendRequest(BaseModel):
    """基于数据的推荐请求"""
    file_type: str = Field(description="文件类型: fastq/bam/vcf/tsv/csv/h5ad")
    data_size: Optional[str] = Field(default=None, description="数据规模")
    analysis_type: Optional[str] = Field(default=None, description="分析类型")


# ==========================================
# 响应模型
# ==========================================
class RecommendedSkill(BaseModel):
    """推荐技能"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    category: Optional[str]
    match_score: float
    match_reason: str
    avg_rating: float
    usage_count: int


class RecommendResponse(BaseModel):
    """推荐响应"""
    recommendations: List[RecommendedSkill]
    message: str


class TrendingSkill(BaseModel):
    """热门技能"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    usage_count: int
    avg_rating: float
    trend: str  # "rising" / "stable" / "hot"


# ==========================================
# 辅助函数
# ==========================================
def get_skill_category(skill: SkillAsset) -> str:
    """推断技能分类"""
    name_lower = (skill.name or "").lower()
    desc_lower = (skill.description or "").lower()

    if any(kw in name_lower or kw in desc_lower for kw in ["qc", "质量", "fastqc"]):
        return "质量控制"
    elif any(kw in name_lower or kw in desc_lower for kw in ["rna", "转录", "deseq"]):
        return "转录组分析"
    elif any(kw in name_lower or kw in desc_lower for kw in ["单细胞", "cell", "seurat", "scanpy"]):
        return "单细胞分析"
    elif any(kw in name_lower or kw in desc_lower for kw in ["图", "plot", "可视化"]):
        return "可视化"
    else:
        return "其他"


def calculate_match_score(skill: SkillAsset, query: str, data_type: str = None) -> tuple:
    """计算匹配分数"""
    score = 0.0
    reasons = []

    query_lower = query.lower()
    name_lower = (skill.name or "").lower()
    desc_lower = (skill.description or "").lower()
    combined = f"{name_lower} {desc_lower}"

    # 关键词匹配
    keywords = re.findall(r'\w+', query_lower)

    for kw in keywords:
        if len(kw) < 2:
            continue
        if kw in name_lower:
            score += 0.3
            reasons.append(f"名称包含 '{kw}'")
        elif kw in desc_lower:
            score += 0.1
            reasons.append(f"描述包含 '{kw}'")

    # 数据类型匹配
    if data_type:
        data_type_map = {
            "rnaseq": ["rna", "转录", "表达", "deseq", "fpkm", "tpm"],
            "scrna": ["单细胞", "cell", "seurat", "scanpy", "scrna"],
            "chipseq": ["chip", "peak", "tfbs"],
            "atacseq": ["atac", "peak", "染色质"],
            "fastq": ["fastq", "qc", "质量", "fastqc"],
            "vcf": ["变异", "snp", "vcf", "variant"]
        }

        type_keywords = data_type_map.get(data_type.lower(), [])
        for kw in type_keywords:
            if kw in combined:
                score += 0.2
                reasons.append(f"适用于 {data_type} 数据")
                break

    # 归一化分数
    score = min(score, 1.0)

    return score, reasons[:3]  # 返回最多3个原因


# ==========================================
# POST /recommend - 基于需求描述推荐
# ==========================================
@router.post("/recommend", response_model=RecommendResponse)
async def recommend_skills(
    request: RecommendRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    根据用户需求描述推荐技能

    使用关键词匹配 + 语义相似度推荐最合适的技能
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    # 获取所有已发布的技能
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.status == SkillStatus.PUBLISHED)
    ).all()

    if not skills:
        return RecommendResponse(
            recommendations=[],
            message="暂无可用的公开技能"
        )

    # 计算匹配分数
    scored_skills = []
    for skill in skills:
        score, reasons = calculate_match_score(
            skill,
            request.user_query,
            request.data_type
        )
        if score > 0:
            # 获取评分
            rating_result = session.exec(
                select(
                    func.avg(SkillReview.rating).label("avg"),
                    func.count(SkillReview.id).label("count")
                ).where(SkillReview.skill_id == skill.skill_id)
            ).first()
            avg_rating = float(rating_result[0] or 0)

            # 获取使用量
            usage_count = session.exec(
                select(func.count(SkillExecutionHistory.id)).where(
                    SkillExecutionHistory.skill_id == skill.skill_id
                )
            ).one() or 0

            scored_skills.append({
                "skill": skill,
                "score": score,
                "reasons": reasons,
                "avg_rating": avg_rating,
                "usage_count": usage_count
            })

    # 按分数排序
    scored_skills.sort(key=lambda x: x["score"], reverse=True)

    # 取前 N 个
    top_skills = scored_skills[:request.limit]

    recommendations = []
    for item in top_skills:
        skill = item["skill"]
        recommendations.append(RecommendedSkill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=get_skill_category(skill),
            match_score=item["score"],
            match_reason="; ".join(item["reasons"]) if item["reasons"] else "相关技能",
            avg_rating=item["avg_rating"],
            usage_count=item["usage_count"]
        ))

    log.info(f"🎯 [SkillRecommend] 推荐技能: {len(recommendations)} 个, 用户: {current_user.id}")

    return RecommendResponse(
        recommendations=recommendations,
        message=f"根据您的需求，推荐 {len(recommendations)} 个相关技能"
    )


# ==========================================
# POST /recommend/data - 基于数据类型推荐
# ==========================================
@router.post("/recommend/data", response_model=RecommendResponse)
async def recommend_by_data(
    request: DataBasedRecommendRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    根据数据类型推荐适合的分析技能
    """
    # 数据类型到关键词的映射
    file_type_keywords = {
        "fastq": ["qc", "fastqc", "质量", "比对", "mapping"],
        "bam": ["比对", "mapping", "peak", "variant"],
        "vcf": ["变异", "variant", "snp", "annotation"],
        "tsv": ["差异", "deseq", "分析", "统计"],
        "csv": ["差异", "分析", "可视化"],
        "h5ad": ["单细胞", "scanpy", "seurat", "scrna"]
    }

    keywords = file_type_keywords.get(request.file_type.lower(), [])

    # 获取已发布技能
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.status == SkillStatus.PUBLISHED)
    ).all()

    scored_skills = []
    for skill in skills:
        combined = f"{skill.name or ''} {skill.description or ''}".lower()
        score = 0
        reasons = []

        for kw in keywords:
            if kw in combined:
                score += 0.2
                reasons.append(f"适用于 {request.file_type} 文件")

        if score > 0:
            rating_result = session.exec(
                select(func.avg(SkillReview.rating)).where(
                    SkillReview.skill_id == skill.skill_id
                )
            ).first()

            usage_count = session.exec(
                select(func.count(SkillExecutionHistory.id)).where(
                    SkillExecutionHistory.skill_id == skill.skill_id
                )
            ).one() or 0

            scored_skills.append({
                "skill": skill,
                "score": min(score, 1.0),
                "reasons": reasons[:1],
                "avg_rating": float(rating_result[0] or 0),
                "usage_count": usage_count
            })

    scored_skills.sort(key=lambda x: (x["score"], x["avg_rating"]), reverse=True)

    recommendations = []
    for item in scored_skills[:5]:
        skill = item["skill"]
        recommendations.append(RecommendedSkill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            category=get_skill_category(skill),
            match_score=item["score"],
            match_reason=item["reasons"][0] if item["reasons"] else "相关技能",
            avg_rating=item["avg_rating"],
            usage_count=item["usage_count"]
        ))

    return RecommendResponse(
        recommendations=recommendations,
        message=f"基于 {request.file_type} 数据，推荐 {len(recommendations)} 个技能"
    )


# ==========================================
# GET /trending - 获取热门技能
# ==========================================
@router.get("/trending", response_model=List[TrendingSkill])
async def get_trending_skills(
    limit: int = 10,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取热门技能

    基于使用量、评分、收藏数综合排序
    """
    # 获取已发布技能
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.status == SkillStatus.PUBLISHED)
    ).all()

    trending_skills = []
    for skill in skills:
        # 使用量
        usage_count = session.exec(
            select(func.count(SkillExecutionHistory.id)).where(
                SkillExecutionHistory.skill_id == skill.skill_id
            )
        ).one() or 0

        # 评分
        rating_result = session.exec(
            select(
                func.avg(SkillReview.rating).label("avg"),
                func.count(SkillReview.id).label("count")
            ).where(SkillReview.skill_id == skill.skill_id)
        ).first()
        avg_rating = float(rating_result[0] or 0)

        # 收藏数
        favorite_count = session.exec(
            select(func.count(SkillFavorite.id)).where(
                SkillFavorite.skill_id == skill.skill_id
            )
        ).one() or 0

        # 计算热度分数
        hotness = usage_count * 0.5 + avg_rating * 10 + favorite_count * 2

        # 趋势判断
        if usage_count > 100 and avg_rating > 4:
            trend = "hot"
        elif usage_count > 50:
            trend = "rising"
        else:
            trend = "stable"

        trending_skills.append({
            "skill": skill,
            "usage_count": usage_count,
            "avg_rating": avg_rating,
            "hotness": hotness,
            "trend": trend
        })

    # 按热度排序
    trending_skills.sort(key=lambda x: x["hotness"], reverse=True)

    return [
        TrendingSkill(
            skill_id=item["skill"].skill_id,
            name=item["skill"].name,
            description=item["skill"].description,
            executor_type=item["skill"].executor_type,
            usage_count=item["usage_count"],
            avg_rating=item["avg_rating"],
            trend=item["trend"]
        )
        for item in trending_skills[:limit]
    ]


# ==========================================
# GET /personalized - 获取个性化推荐
# ==========================================
@router.get("/personalized", response_model=List[RecommendedSkill])
async def get_personalized_recommendations(
    limit: int = 5,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取个性化推荐

    基于用户历史行为推荐技能
    """
    # 获取用户使用过的技能类型
    user_skills = session.exec(
        select(SkillExecutionHistory.skill_id).where(
            SkillExecutionHistory.user_id == current_user.id
        )
    ).all()

    if not user_skills:
        # 新用户，返回热门技能
        trending = await get_trending_skills(limit, session, current_user)
        return [
            RecommendedSkill(
                skill_id=s.skill_id,
                name=s.name,
                description=s.description,
                executor_type=s.executor_type,
                category=None,
                match_score=0.5,
                match_reason="热门推荐",
                avg_rating=s.avg_rating,
                usage_count=s.usage_count
            )
            for s in trending
        ]

    # 获取用户使用过的技能详情
    used_skill_details = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id.in_(user_skills))
    ).all()

    # 提取用户偏好的关键词
    preference_keywords = set()
    for skill in used_skill_details:
        combined = f"{skill.name or ''} {skill.description or ''}".lower()
        words = re.findall(r'[a-z]+', combined)
        preference_keywords.update(words)

    # 获取已发布技能
    skills = session.exec(
        select(SkillAsset).where(
            and_(
                SkillAsset.status == SkillStatus.PUBLISHED,
                SkillAsset.skill_id.not_in(user_skills)  # 排除已使用的
            )
        )
    ).all()

    scored_skills = []
    for skill in skills:
        combined = f"{skill.name or ''} {skill.description or ''}".lower()
        score = 0

        for kw in preference_keywords:
            if len(kw) > 2 and kw in combined:
                score += 0.1

        if score > 0:
            rating_result = session.exec(
                select(func.avg(SkillReview.rating)).where(
                    SkillReview.skill_id == skill.skill_id
                )
            ).first()

            usage_count = session.exec(
                select(func.count(SkillExecutionHistory.id)).where(
                    SkillExecutionHistory.skill_id == skill.skill_id
                )
            ).one() or 0

            scored_skills.append({
                "skill": skill,
                "score": min(score, 1.0),
                "avg_rating": float(rating_result[0] or 0),
                "usage_count": usage_count
            })

    scored_skills.sort(key=lambda x: (x["score"], x["avg_rating"]), reverse=True)

    return [
        RecommendedSkill(
            skill_id=item["skill"].skill_id,
            name=item["skill"].name,
            description=item["skill"].description,
            executor_type=item["skill"].executor_type,
            category=get_skill_category(item["skill"]),
            match_score=item["score"],
            match_reason="基于您的使用偏好推荐",
            avg_rating=item["avg_rating"],
            usage_count=item["usage_count"]
        )
        for item in scored_skills[:limit]
    ]


log.info("✅ 技能推荐系统 API 已加载")