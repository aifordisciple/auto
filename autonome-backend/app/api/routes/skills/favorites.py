"""
技能收藏 API

包含收藏功能相关接口
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset

router = APIRouter()


# ==========================================
# GET /api/skills/favorites - 获取收藏列表
# ==========================================
@router.get("/favorites")
def get_favorites(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的收藏列表"""
    from app.models.domain import SkillFavorite

    favorites = session.exec(
        select(SkillFavorite).where(SkillFavorite.user_id == current_user.id)
    ).all()

    # 获取收藏的技能详情
    skill_ids = [f.skill_id for f in favorites]
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id.in_(skill_ids))
    ).all()

    return {
        "status": "success",
        "total": len(skills),
        "data": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "executor_type": s.executor_type,
                "status": s.status.value
            }
            for s in skills
        ]
    }


# ==========================================
# POST /api/skills/{skill_id}/favorite - 添加收藏
# ==========================================
@router.post("/{skill_id}/favorite")
def add_favorite(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """添加收藏"""
    from app.models.domain import SkillFavorite

    # 检查是否已收藏
    existing = session.exec(
        select(SkillFavorite).where(
            SkillFavorite.skill_id == skill_id,
            SkillFavorite.user_id == current_user.id
        )
    ).first()

    if existing:
        return {"status": "success", "message": "已经收藏过了"}

    favorite = SkillFavorite(skill_id=skill_id, user_id=current_user.id)
    session.add(favorite)
    session.commit()

    log.info(f"⭐ [Skills API] 用户 {current_user.id} 收藏了技能: {skill_id}")
    return {"status": "success", "message": "收藏成功"}


# ==========================================
# DELETE /api/skills/{skill_id}/favorite - 取消收藏
# ==========================================
@router.delete("/{skill_id}/favorite")
def remove_favorite(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """取消收藏"""
    from app.models.domain import SkillFavorite

    favorite = session.exec(
        select(SkillFavorite).where(
            SkillFavorite.skill_id == skill_id,
            SkillFavorite.user_id == current_user.id
        )
    ).first()

    if not favorite:
        return {"status": "success", "message": "未收藏"}

    session.delete(favorite)
    session.commit()

    log.info(f"💔 [Skills API] 用户 {current_user.id} 取消收藏: {skill_id}")
    return {"status": "success", "message": "已取消收藏"}


# ==========================================
# GET /api/skills/my/favorites - 获取我的收藏（用于 MySkillsPanel）
# ==========================================
@router.get("/my/favorites")
def get_my_favorite_skills(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户收藏的所有技能（用于 MySkillsPanel）"""
    from app.models.domain import SkillFavorite

    # 获取收藏
    favorites = session.exec(
        select(SkillFavorite).where(SkillFavorite.user_id == current_user.id)
    ).all()

    skill_ids = [f.skill_id for f in favorites]
    if not skill_ids:
        return {"favorites": []}

    # 获取技能详情
    skills = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id.in_(skill_ids))
    ).all()

    return {
        "favorites": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "executor_type": s.executor_type,
                "owner_id": s.owner_id,
                "status": s.status.value if s.status else "DRAFT"
            }
            for s in skills
        ]
    }