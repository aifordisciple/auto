"""
经验资产 API 路由 - 提供经验资产的 CRUD、搜索、提取等接口
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, Project, ExperienceAsset, ExperienceAssetCreate,
    ExperienceAssetUpdate, ExperienceAssetPublic, ExperienceType
)
from app.services.success_evaluator import SuccessEvaluator
from app.services.knowledge_extractor import KnowledgeExtractor
from app.services.experience_recommender import ExperienceRecommender, FeedbackProcessor


router = APIRouter()


# ==========================================
# 请求模型定义
# ==========================================
class ExtractRequest(BaseModel):
    """提取经验请求"""
    session_id: str = Field(..., description="会话 ID")
    project_id: Optional[str] = Field(None, description="项目 ID")


class FeedbackRequest(BaseModel):
    """反馈请求"""
    experience_id: str = Field(..., description="经验 ID")
    was_helpful: bool = Field(..., description="是否有帮助")
    comment: Optional[str] = Field(None, description="反馈评论")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")


# ==========================================
# API 端点
# ==========================================

@router.get("/", response_model=List[ExperienceAssetPublic])
async def list_experiences(
    category: Optional[str] = Query(None, description="按分类筛选"),
    is_public: Optional[bool] = Query(None, description="是否公开"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    获取用户的经验资产列表

    支持按分类、公开状态筛选，支持分页
    """
    try:
        query = select(ExperienceAsset).where(
            ExperienceAsset.source_user_id == current_user.id
        )

        # 分类筛选
        if category:
            query = query.where(ExperienceAsset.category == category)

        # 公开状态筛选
        if is_public is not None:
            query = query.where(ExperienceAsset.is_public == is_public)

        # 排序和分页
        query = query.order_by(ExperienceAsset.created_at.desc())
        query = query.offset(offset).limit(limit)

        experiences = db.exec(query).all()
        return experiences

    except Exception as e:
        log.error(f"获取经验列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public", response_model=List[ExperienceAssetPublic])
async def list_public_experiences(
    category: Optional[str] = Query(None, description="按分类筛选"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    获取公开的经验资产列表

    返回所有公开的经验资产，按有用性评分排序
    """
    try:
        query = select(ExperienceAsset).where(
            ExperienceAsset.is_public == True,
            ExperienceAsset.usefulness_score >= 0.3
        )

        if category:
            query = query.where(ExperienceAsset.category == category)

        # 按有用性排序
        query = query.order_by(
            ExperienceAsset.usefulness_score.desc(),
            ExperienceAsset.reuse_count.desc()
        )
        query = query.offset(offset).limit(limit)

        experiences = db.exec(query).all()
        return experiences

    except Exception as e:
        log.error(f"获取公开经验列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{experience_id}", response_model=ExperienceAssetPublic)
async def get_experience(
    experience_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    获取单个经验资产详情
    """
    experience = db.exec(
        select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
    ).first()

    if not experience:
        raise HTTPException(status_code=404, detail="经验资产不存在")

    # 权限检查：只能查看自己的或公开的经验
    if experience.source_user_id != current_user.id and not experience.is_public:
        raise HTTPException(status_code=403, detail="无权访问此经验资产")

    return experience


@router.post("/search")
async def search_experiences(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    语义搜索经验资产

    使用向量相似度搜索相关的经验资产
    """
    try:
        recommender = ExperienceRecommender(db)
        results = await recommender.recommend(
            user_query=request.query,
            user_id=current_user.id,
            top_k=request.top_k
        )

        return {
            "success": True,
            "results": results,
            "total": len(results)
        }

    except Exception as e:
        log.error(f"搜索经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract")
async def extract_experience(
    request: ExtractRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    从会话提取经验资产

    评估会话成功度，如果成功则提取知识资产
    """
    try:
        # 1. 评估会话成功度
        evaluator = SuccessEvaluator(db)
        evaluation = evaluator.evaluate_session(request.session_id)

        result = {
            "session_id": request.session_id,
            "evaluation": evaluation,
            "experience": None
        }

        # 2. 如果成功且置信度足够高，提取经验
        if evaluation["is_successful"] and evaluation["confidence"] >= 0.7:
            extractor = KnowledgeExtractor(db)
            experience = await extractor.extract_from_session(
                session_id=request.session_id,
                user_id=current_user.id,
                project_id=request.project_id
            )

            if experience:
                result["experience"] = {
                    "experience_id": experience.experience_id,
                    "title": experience.title,
                    "summary": experience.summary,
                    "category": experience.category
                }

        return result

    except Exception as e:
        log.error(f"提取经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/{session_id}")
async def evaluate_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    评估会话成功度

    返回会话成功度评估结果，不执行提取
    """
    try:
        evaluator = SuccessEvaluator(db)
        evaluation = evaluator.evaluate_session(session_id)

        return {
            "session_id": session_id,
            "evaluation": evaluation
        }

    except Exception as e:
        log.error(f"评估会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    提交经验资产反馈

    用户反馈是否有帮助，用于调整有用性评分
    """
    try:
        processor = FeedbackProcessor(db)
        result = processor.process_feedback(
            experience_id=request.experience_id,
            was_helpful=request.was_helpful,
            user_id=current_user.id,
            comment=request.comment
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"提交反馈失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{experience_id}/publish")
async def publish_experience(
    experience_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    发布经验资产

    将私有经验资产设为公开
    """
    try:
        experience = db.exec(
            select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
        ).first()

        if not experience:
            raise HTTPException(status_code=404, detail="经验资产不存在")

        # 权限检查
        if experience.source_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="只能发布自己的经验资产")

        experience.is_public = True
        db.commit()

        return {
            "success": True,
            "message": "经验资产已发布",
            "experience_id": experience_id
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"发布经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{experience_id}/unpublish")
async def unpublish_experience(
    experience_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    取消发布经验资产

    将公开经验资产设为私有
    """
    try:
        experience = db.exec(
            select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
        ).first()

        if not experience:
            raise HTTPException(status_code=404, detail="经验资产不存在")

        if experience.source_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="只能操作自己的经验资产")

        experience.is_public = False
        db.commit()

        return {
            "success": True,
            "message": "经验资产已设为私有",
            "experience_id": experience_id
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"取消发布经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{experience_id}")
async def delete_experience(
    experience_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    删除经验资产
    """
    try:
        experience = db.exec(
            select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
        ).first()

        if not experience:
            raise HTTPException(status_code=404, detail="经验资产不存在")

        if experience.source_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="只能删除自己的经验资产")

        db.delete(experience)
        db.commit()

        return {
            "success": True,
            "message": "经验资产已删除",
            "experience_id": experience_id
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"删除经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{experience_id}", response_model=ExperienceAssetPublic)
async def update_experience(
    experience_id: str,
    update_data: ExperienceAssetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    更新经验资产
    """
    try:
        experience = db.exec(
            select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
        ).first()

        if not experience:
            raise HTTPException(status_code=404, detail="经验资产不存在")

        if experience.source_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="只能更新自己的经验资产")

        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(experience, key, value)

        db.commit()
        db.refresh(experience)

        return experience

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"更新经验失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_stats_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    获取经验资产统计摘要
    """
    try:
        # 用户自己的经验数量
        total_experiences = db.exec(
            select(ExperienceAsset).where(ExperienceAsset.source_user_id == current_user.id)
        ).all()

        # 按分类统计
        category_counts = {}
        for exp in total_experiences:
            cat = exp.category or "general"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # 公开数量
        public_count = sum(1 for exp in total_experiences if exp.is_public)

        return {
            "total": len(total_experiences),
            "public": public_count,
            "by_category": category_counts
        }

    except Exception as e:
        log.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))