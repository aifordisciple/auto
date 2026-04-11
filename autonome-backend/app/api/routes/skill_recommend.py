"""
技能推荐系统 API - 根据用户需求智能推荐合适的技能

核心端点:
- POST /recommend: 基于用户描述推荐技能
- POST /recommend/data: 基于数据类型推荐技能
- POST /intent: 意图识别 + 技能推荐（增强版）
- POST /match: 统一匹配接口（新增，整合三阶段匹配）
- POST /feedback: 提交匹配反馈（新增）
- GET /trending: 获取热门技能
- GET /personalized: 获取个性化推荐
"""

import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_, and_

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillStatus, SkillExecutionHistory, SkillReview, SkillFavorite,
    SkillMatchingFeedback
)
from app.services.intent_recognition import IntentRecognitionService, IntentType
from app.services.skill_matcher import match_skills

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
# GET /recent - 获取最新上线技能
# ==========================================
class RecentSkill(BaseModel):
    """最新技能"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    avg_rating: float
    created_at: str
    is_new: bool  # 7天内上线


@router.get("/recent", response_model=List[RecentSkill])
async def get_recent_skills(
    limit: int = 5,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取最新上线的技能

    按创建时间倒序排列
    """
    from datetime import datetime, timedelta

    # 获取已发布技能，按创建时间倒序
    skills = session.exec(
        select(SkillAsset)
        .where(SkillAsset.status == SkillStatus.PUBLISHED)
        .order_by(SkillAsset.created_at.desc())
        .limit(limit * 2)  # 多取一些用于筛选
    ).all()

    recent_skills = []
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    for skill in skills[:limit]:
        # 评分
        rating_result = session.exec(
            select(func.avg(SkillReview.rating)).where(
                SkillReview.skill_id == skill.skill_id
            )
        ).first()
        avg_rating = float(rating_result[0] or 0)

        # 判断是否为新技能（7天内上线）
        is_new = skill.created_at > seven_days_ago if skill.created_at else False

        recent_skills.append(RecentSkill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            executor_type=skill.executor_type,
            avg_rating=round(avg_rating, 1),
            created_at=skill.created_at.isoformat() if skill.created_at else "",
            is_new=is_new
        ))

    log.info(f"🆕 [SkillRecommend] 获取最新技能: {len(recent_skills)} 个, 用户: {current_user.id}")

    return recent_skills


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


# ==========================================
# GET /feedback/stats - 反馈统计（管理员）
# ==========================================

class FeedbackStatsResponse(BaseModel):
    """反馈统计响应"""
    aggregation_time: str
    total_skills: int
    total_recommendations: int
    total_clicks: int
    total_executions: int
    total_successes: int
    overall_click_rate: float
    overall_success_rate: float
    top_performing_skills: List[Dict[str, Any]]


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取反馈统计信息

    返回过去24小时的推荐反馈聚合数据
    """
    from app.services.recommendation_feedback_service import RecommendationFeedbackService

    service = RecommendationFeedbackService(session)
    result = service.run_periodic_aggregation()

    return FeedbackStatsResponse(**result)


# ==========================================
# POST /feedback/record - 记录行为埋点
# ==========================================

class RecordBehaviorRequest(BaseModel):
    """记录行为请求"""
    session_id: str = Field(description="聊天会话ID")
    event_type: str = Field(description="事件类型: recommend/click/execute/success/failure/dismiss")
    skill_id: str = Field(description="技能ID")
    query: Optional[str] = Field(default=None, description="用户查询（推荐时必填）")
    match_source: Optional[str] = Field(default=None, description="匹配来源")
    confidence: float = Field(default=0.0, description="置信度")
    execution_time: Optional[float] = Field(default=None, description="执行耗时")


class RecordBehaviorResponse(BaseModel):
    """记录行为响应"""
    success: bool
    message: str


@router.post("/feedback/record", response_model=RecordBehaviorResponse)
async def record_behavior(
    request: RecordBehaviorRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    记录用户行为埋点

    用于收集用户与技能推荐的交互数据，支持推荐系统优化。

    事件类型：
    - recommend: 技能被推荐
    - click: 用户点击技能
    - execute: 技能被执行
    - success: 执行成功
    - failure: 执行失败
    - dismiss: 用户忽略推荐
    """
    from app.services.recommendation_feedback_service import (
        RecommendationFeedbackService,
        BehaviorEvent,
    )

    try:
        service = RecommendationFeedbackService(session)
        event = BehaviorEvent(
            user_id=current_user.id,
            session_id=request.session_id,
            event_type=request.event_type,
            skill_id=request.skill_id,
            query=request.query,
            match_source=request.match_source,
            confidence=request.confidence,
            execution_time=request.execution_time,
        )

        success = service.record_event(event)

        if success:
            return RecordBehaviorResponse(
                success=True,
                message=f"事件 '{request.event_type}' 已记录"
            )
        else:
            return RecordBehaviorResponse(
                success=False,
                message="记录失败"
            )

    except Exception as e:
        log.error(f"[Recommend] 记录行为失败: {e}")
        return RecordBehaviorResponse(
            success=False,
            message=f"记录失败: {str(e)}"
        )


# ==========================================
# POST /match - 统一匹配接口（新增）
# ==========================================
class MatchRequest(BaseModel):
    """统一匹配请求"""
    user_query: str = Field(description="用户查询/需求描述")
    session_id: Optional[str] = Field(default=None, description="聊天会话ID")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息（项目文件、历史会话等）")
    mode: str = Field(
        default="auto",
        description="匹配模式: fast(快速,<200ms) / precise(精准,~1-2s) / auto(自动,默认)"
    )


class MatchedSkillResult(BaseModel):
    """匹配的技能结果"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    match_score: float
    match_reason: str
    match_source: str  # rule | vector | llm | hybrid


class MatchResponse(BaseModel):
    """统一匹配响应"""
    intent_type: str
    confidence: float
    matched_skills: List[MatchedSkillResult]
    parameters_suggestion: Dict[str, Any]
    matched_domains: List[str]
    match_source: str
    match_mode: str = Field(description="实际使用的匹配模式")
    reason: str


@router.post("/match", response_model=MatchResponse)
async def unified_match(
    request: MatchRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    统一匹配接口 - 整合规则/向量/LLM三阶段匹配

    这是技能推荐的主要入口，支持三种匹配模式：

    ## 匹配模式
    - **fast（快速模式）**: 仅规则+向量匹配，响应时间 <200ms
      - 适用场景：实时搜索、即时推荐
      - 牺牲精度换取速度

    - **precise（精准模式）**: 完整三阶段匹配（含LLM精排），响应时间 ~1-2s
      - 适用场景：用户明确要求精准推荐
      - 包含参数推断和复杂意图理解

    - **auto（自动模式，默认）**: 根据置信度自动决定是否使用LLM
      - 高置信度直接返回，低置信度触发LLM
      - 平衡速度和精度

    返回最优推荐结果和参数建议。
    """
    import asyncio

    log.info(f"🎯 [Match] 统一匹配请求: query='{request.user_query[:50]}...', user={current_user.id}, mode={request.mode}")

    try:
        # 调用统一匹配器，传入匹配模式
        result = await match_skills(
            user_query=request.user_query,
            user_id=current_user.id,
            context=request.context,
            mode=request.mode
        )

        # 获取技能详细信息
        matched_skills = []
        for skill_match in result.get("matched_skills", []):
            skill_id = skill_match.get("skill_id")
            skill = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == skill_id)
            ).first()

            if skill:
                matched_skills.append(MatchedSkillResult(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    description=skill.description,
                    executor_type=skill.executor_type,
                    match_score=skill_match.get("match_score", 0),
                    match_reason=skill_match.get("match_reason", "相关技能"),
                    match_source=result.get("match_source", "hybrid")
                ))

        # 异步记录反馈
        if matched_skills:
            background_tasks.add_task(
                _record_match_feedback,
                user_id=current_user.id,
                session_id=request.session_id or "unknown",
                query=request.user_query,
                match_source=result.get("match_source", "hybrid"),
                recommended_skill_ids=[s.skill_id for s in matched_skills],
                confidence=result.get("confidence", 0)
            )

        return MatchResponse(
            intent_type=result.get("intent_type", "live_coding"),
            confidence=result.get("confidence", 0),
            matched_skills=matched_skills,
            parameters_suggestion=result.get("parameters_suggestion", {}),
            matched_domains=result.get("matched_domains", []),
            match_source=result.get("match_source", "hybrid"),
            match_mode=result.get("match_mode", request.mode),
            reason=result.get("reason", "")
        )

    except Exception as e:
        log.error(f"❌ [Match] 匹配失败: {e}")
        return MatchResponse(
            intent_type="live_coding",
            confidence=0.3,
            matched_skills=[],
            parameters_suggestion={},
            matched_domains=[],
            match_source="error",
            match_mode=request.mode,
            reason=f"匹配失败: {e}"
        )


def _record_match_feedback(
    user_id: int,
    session_id: str,
    query: str,
    match_source: str,
    recommended_skill_ids: List[str],
    confidence: float
):
    """后台任务：记录匹配反馈"""
    try:
        from app.core.database import engine
        from sqlmodel import Session as SQLModelSession

        with SQLModelSession(engine) as db_session:
            feedback = SkillMatchingFeedback(
                user_id=user_id,
                session_id=session_id,
                query=query,
                match_source=match_source,
                recommended_skill_ids=recommended_skill_ids,
                confidence=confidence,
                accepted=False
            )
            db_session.add(feedback)
            db_session.commit()
            log.info(f"📝 [Match] 记录反馈: user={user_id}, skills={len(recommended_skill_ids)}")
    except Exception as e:
        log.warning(f"记录反馈失败: {e}")


# ==========================================
# POST /feedback - 提交匹配反馈（新增）
# ==========================================
class FeedbackRequest(BaseModel):
    """匹配反馈请求"""
    feedback_id: Optional[int] = Field(default=None, description="反馈记录ID")
    session_id: str = Field(description="聊天会话ID")
    query: str = Field(description="原始查询")
    accepted: bool = Field(description="是否接受推荐")
    accepted_skill_id: Optional[str] = Field(default=None, description="用户选择的技能ID")
    rejected_skills: List[str] = Field(default_factory=list, description="用户拒绝的技能ID列表")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    success: bool
    message: str


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_match_feedback(
    request: FeedbackRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    提交匹配反馈

    用于记录用户对推荐的反馈，支持持续优化推荐系统。

    使用场景:
    1. 用户选择推荐的技能 → accepted=True, accepted_skill_id=选中的技能ID
    2. 用户拒绝推荐 → accepted=False, rejected_skills=拒绝的技能列表
    3. 用户选择其他方式 → accepted=False
    """
    try:
        # 查找或创建反馈记录
        feedback = None

        if request.feedback_id:
            feedback = session.exec(
                select(SkillMatchingFeedback).where(
                    SkillMatchingFeedback.id == request.feedback_id,
                    SkillMatchingFeedback.user_id == current_user.id
                )
            ).first()

        if not feedback:
            # 创建新的反馈记录
            feedback = SkillMatchingFeedback(
                user_id=current_user.id,
                session_id=request.session_id,
                query=request.query,
                match_source="user_feedback",
                recommended_skill_ids=[],
                confidence=0,
                accepted=request.accepted,
                accepted_skill_id=request.accepted_skill_id,
                rejected_skills=request.rejected_skills
            )
            session.add(feedback)
        else:
            # 更新现有记录
            feedback.accepted = request.accepted
            feedback.accepted_skill_id = request.accepted_skill_id
            feedback.rejected_skills = request.rejected_skills

        session.commit()

        log.info(f"📝 [Feedback] 用户反馈: user={current_user.id}, accepted={request.accepted}, "
                f"skill={request.accepted_skill_id}")

        return FeedbackResponse(
            success=True,
            message="反馈已记录"
        )

    except Exception as e:
        log.error(f"❌ [Feedback] 记录失败: {e}")
        return FeedbackResponse(
            success=False,
            message=f"记录失败: {e}"
        )


# ==========================================
# POST /intent - 意图识别 + 技能推荐（增强版）
# ==========================================
class IntentDetectRequest(BaseModel):
    """意图检测请求"""
    user_query: str = Field(description="用户输入/查询")
    session_id: Optional[str] = Field(default=None, description="聊天会话ID")


class IntentSkillMatch(BaseModel):
    """意图匹配的技能"""
    skill_id: str
    name: str
    description: Optional[str]
    executor_type: str
    match_score: float
    match_reason: str


class IntentDetectResponse(BaseModel):
    """意图检测响应"""
    intent_type: str  # explicit_skill, implicit_skill, live_coding, general_question
    confidence: float
    matched_skills: List[IntentSkillMatch]
    matched_domains: List[str]
    reason: str
    should_inject: bool  # 是否应该在聊天上下文中注入推荐


@router.post("/intent", response_model=IntentDetectResponse)
async def detect_user_intent(
    request: IntentDetectRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    意图识别 + 技能推荐

    分析用户输入，判断是否有技能调用意图，并返回匹配的技能推荐
    """
    # 获取可用技能
    skills = session.exec(
        select(SkillAsset).where(
            or_(
                SkillAsset.status == SkillStatus.PUBLISHED,
                SkillAsset.owner_id == current_user.id
            )
        )
    ).all()

    # 转换为意图识别服务需要的格式
    skills_data = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "executor_type": s.executor_type
        }
        for s in skills
    ]

    # 初始化意图识别服务
    intent_service = IntentRecognitionService(session)

    # 检测意图
    intent_result = intent_service.detect_intent(request.user_query, skills_data)

    # 记录推荐日志
    if intent_result["matched_skills"]:
        intent_service.log_recommendation(
            user_id=current_user.id,
            session_id=request.session_id or "unknown",
            query=request.user_query,
            intent_result=intent_result
        )

    # 构建匹配技能列表
    matched_skills = []
    for match in intent_result.get("matched_skills", []):
        skill = next((s for s in skills if s.skill_id == match["skill_id"]), None)
        if skill:
            # 获取评分
            rating_result = session.exec(
                select(func.avg(SkillReview.rating)).where(
                    SkillReview.skill_id == skill.skill_id
                )
            ).first()
            avg_rating = float(rating_result[0] or 0) if rating_result else 0

            matched_skills.append(IntentSkillMatch(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                executor_type=skill.executor_type,
                match_score=match["match_score"],
                match_reason=match["match_reason"]
            ))

    # 判断是否应该注入推荐到聊天上下文
    should_inject = (
        intent_result["intent_type"] in [IntentType.EXPLICIT_SKILL, IntentType.IMPLICIT_SKILL]
        and intent_result["confidence"] > 0.5
        and len(matched_skills) > 0
    )

    log.info(f"🎯 [IntentDetect] 意图: {intent_result['intent_type']}, "
             f"置信度: {intent_result['confidence']:.2f}, "
             f"匹配技能: {len(matched_skills)}, "
             f"注入推荐: {should_inject}")

    return IntentDetectResponse(
        intent_type=intent_result["intent_type"],
        confidence=intent_result["confidence"],
        matched_skills=matched_skills,
        matched_domains=intent_result.get("matched_domains", []),
        reason=intent_result.get("reason", ""),
        should_inject=should_inject
    )