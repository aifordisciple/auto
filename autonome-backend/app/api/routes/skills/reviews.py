"""
技能评价 API

包含评价功能相关接口
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset, get_utc_now
from app.schemas.skill import ReviewCreateRequest

router = APIRouter()


# ==========================================
# GET /api/skills/{skill_id}/reviews - 获取评价列表
# ==========================================
@router.get("/{skill_id}/reviews")
def get_skill_reviews(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能的评价列表"""
    from app.models.domain import SkillReview

    reviews = session.exec(
        select(SkillReview).where(SkillReview.skill_id == skill_id).order_by(SkillReview.created_at.desc())
    ).all()

    # 计算平均分
    avg_rating = sum(r.rating for r in reviews) / len(reviews) if reviews else 0

    return {
        "status": "success",
        "total": len(reviews),
        "average_rating": round(avg_rating, 1),
        "data": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat()
            }
            for r in reviews
        ]
    }


# ==========================================
# POST /api/skills/{skill_id}/reviews - 提交评价
# ==========================================
@router.post("/{skill_id}/reviews")
def create_review(
    skill_id: str,
    req: ReviewCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """提交评价"""
    from app.models.domain import SkillReview

    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="评分必须在 1-5 之间")

    # 检查是否已评价
    existing = session.exec(
        select(SkillReview).where(
            SkillReview.skill_id == skill_id,
            SkillReview.user_id == current_user.id
        )
    ).first()

    if existing:
        # 更新评价
        existing.rating = req.rating
        existing.comment = req.comment
        existing.updated_at = get_utc_now()
        session.add(existing)
        session.commit()
        log.info(f"📝 [Skills API] 用户 {current_user.id} 更新了评价: {skill_id}")
        return {"status": "success", "message": "评价已更新"}

    review = SkillReview(
        skill_id=skill_id,
        user_id=current_user.id,
        rating=req.rating,
        comment=req.comment
    )
    session.add(review)
    session.commit()

    log.info(f"⭐ [Skills API] 用户 {current_user.id} 提交了评价: {skill_id} - {req.rating}星")
    return {"status": "success", "message": "评价已提交"}


# ==========================================
# 结果分享 API
# ==========================================

@router.post("/{skill_id}/share")
def create_share_link(
    skill_id: str,
    task_id: str,
    expires_in_days: int = 7,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建结果分享链接"""
    from app.models.domain import ResultShare
    from datetime import timedelta

    expires_at = None
    if expires_in_days > 0:
        expires_at = get_utc_now() + timedelta(days=expires_in_days)

    share = ResultShare(
        task_id=task_id,
        created_by=current_user.id,
        expires_at=expires_at
    )
    session.add(share)
    session.commit()
    session.refresh(share)

    log.info(f"🔗 [Skills API] 用户 {current_user.id} 创建了分享链接: {share.share_token}")
    return {
        "status": "success",
        "share_token": share.share_token,
        "share_url": f"/shared/{share.share_token}",
        "expires_at": expires_at.isoformat() if expires_at else None
    }