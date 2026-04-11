"""
我的技能 API

包含用户个人技能相关的接口（用于前端 MySkillsPanel）
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset

router = APIRouter()


# ==========================================
# GET /api/skills/my/created - 获取我创建的技能
# ==========================================
@router.get("/my/created")
def get_my_created_skills(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户创建的所有技能（用于 MySkillsPanel）
    """
    skills = session.exec(
        select(SkillAsset)
        .where(SkillAsset.owner_id == current_user.id)
        .order_by(SkillAsset.updated_at.desc())
    ).all()

    return {
        "skills": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "executor_type": s.executor_type,
                "status": s.status.value if s.status else "DRAFT",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "category": s.category,
                "category_name": s.category_name,
                "usage_count": s.usage_count or 0,
                "avg_rating": s.avg_rating or 0.0
            }
            for s in skills
        ]
    }


# ==========================================
# GET /api/skills/my/history - 获取我的执行历史
# ==========================================
@router.get("/my/history")
def get_my_execution_history(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的执行历史（用于 MySkillsPanel）
    """
    from app.models.domain import SkillExecutionHistory

    history = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.user_id == current_user.id)
        .order_by(SkillExecutionHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "history": [
            {
                "id": h.id,
                "skill_id": h.skill_id,
                "skill_name": h.skill_name,
                "project_id": h.project_id,
                "status": h.status,
                "execution_time": h.execution_time,
                "result_summary": h.result_summary,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in history
        ]
    }