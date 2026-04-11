"""
技能管理 API

包含管理员审核相关接口
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset, SkillStatus

router = APIRouter()


def check_admin_permission(current_user: User) -> None:
    """检查管理员权限"""
    # 这里可以根据实际业务逻辑判断用户是否是管理员
    # 例如检查 user.role == "admin" 或其他条件
    # 目前暂时允许所有用户访问（实际使用时应该修改）
    pass


# ==========================================
# GET /api/skills/admin/pending - 获取待审核技能列表
# ==========================================
@router.get("/admin/pending")
def get_pending_skills(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """【管理员】获取待审核的技能列表"""
    check_admin_permission(current_user)

    pending_skills = session.exec(
        select(SkillAsset).where(SkillAsset.status == SkillStatus.PENDING_REVIEW)
    ).all()

    return {
        "status": "success",
        "total": len(pending_skills),
        "data": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "owner_id": s.owner_id,
                "created_at": s.created_at.isoformat(),
                "executor_type": s.executor_type
            }
            for s in pending_skills
        ]
    }


# ==========================================
# POST /api/skills/admin/{skill_id}/approve - 批准技能
# ==========================================
@router.post("/admin/{skill_id}/approve")
def approve_skill(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """【管理员】批准技能发布"""
    check_admin_permission(current_user)

    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    if skill.status != SkillStatus.PENDING_REVIEW:
        raise HTTPException(status_code=400, detail="技能不在待审核状态")

    skill.status = SkillStatus.PUBLISHED
    session.add(skill)
    session.commit()

    log.info(f"✅ [Skills API] 管理员 {current_user.id} 批准了技能: {skill_id}")
    return {"status": "success", "message": "技能已批准发布"}


# ==========================================
# POST /api/skills/admin/{skill_id}/reject - 驳回技能
# ==========================================
@router.post("/admin/{skill_id}/reject")
def reject_skill(
    skill_id: str,
    reason: str = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """【管理员】驳回技能"""
    check_admin_permission(current_user)

    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    if skill.status != SkillStatus.PENDING_REVIEW:
        raise HTTPException(status_code=400, detail="技能不在待审核状态")

    skill.status = SkillStatus.REJECTED
    skill.reject_reason = reason
    session.add(skill)
    session.commit()

    log.info(f"❌ [Skills API] 管理员 {current_user.id} 驳回了技能: {skill_id}, 原因: {reason}")
    return {"status": "success", "message": "技能已驳回"}