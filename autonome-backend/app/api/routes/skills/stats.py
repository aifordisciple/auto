"""
技能统计与历史 API

包含技能使用统计、执行历史等接口
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset

router = APIRouter()


# ==========================================
# GET /api/skills/{skill_id}/stats - 获取技能统计
# ==========================================
@router.get("/{skill_id}/stats")
def get_skill_stats(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能使用统计"""
    from app.models.domain import SkillExecutionHistory, SkillReview

    # 验证技能存在
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    # 权限检查：只有所有者可以查看统计
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有技能所有者可以查看统计")

    # ✨ SQL 聚合查询替代 Python 循环（性能优化）
    # 执行统计 - 使用 COUNT
    total_result = session.exec(
        select(func.count(SkillExecutionHistory.id))
        .where(SkillExecutionHistory.skill_id == skill_id)
    ).one()
    total_executions = total_result or 0

    success_result = session.exec(
        select(func.count(SkillExecutionHistory.id))
        .where(SkillExecutionHistory.skill_id == skill_id, SkillExecutionHistory.status == 'SUCCESS')
    ).one()
    success_count = success_result or 0

    failure_result = session.exec(
        select(func.count(SkillExecutionHistory.id))
        .where(SkillExecutionHistory.skill_id == skill_id, SkillExecutionHistory.status == 'FAILURE')
    ).one()
    failure_count = failure_result or 0

    success_rate = (success_count / total_executions * 100) if total_executions > 0 else 0

    # 平均执行时间 - 使用 AVG
    avg_time_result = session.exec(
        select(func.avg(SkillExecutionHistory.execution_time))
        .where(SkillExecutionHistory.skill_id == skill_id, SkillExecutionHistory.execution_time.isnot(None))
    ).one()
    avg_execution_time = avg_time_result[0] if avg_time_result and avg_time_result[0] else 0

    # 评分统计 - 使用 AVG/COUNT
    rating_result = session.exec(
        select(func.avg(SkillReview.rating), func.count(SkillReview.rating))
        .where(SkillReview.skill_id == skill_id)
    ).one()
    avg_rating = rating_result[0] if rating_result and rating_result[0] else 0
    rating_count = rating_result[1] if rating_result and rating_result[1] else 0

    # 最近30天趋势 - 使用 SQL GROUP BY
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # 获取按日期分组的执行数量
    trend_query = session.exec(
        select(
            func.date(SkillExecutionHistory.created_at).label('date'),
            func.count(SkillExecutionHistory.id).label('count')
        )
        .where(
            SkillExecutionHistory.skill_id == skill_id,
            SkillExecutionHistory.created_at >= thirty_days_ago
        )
        .group_by(func.date(SkillExecutionHistory.created_at))
        .order_by(func.date(SkillExecutionHistory.created_at))
    ).all()

    trend = [{"date": str(row.date), "count": row.count} for row in trend_query]

    return {
        "status": "success",
        "data": {
            "total_executions": total_executions,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 1),
            "avg_execution_time": round(avg_execution_time, 1),
            "rating": {
                "average": round(avg_rating, 1),
                "count": rating_count
            },
            "trend": trend[-30:]  # 最近30天
        }
    }


# ==========================================
# GET /api/skills/{skill_id}/history - 获取技能执行历史
# ==========================================
@router.get("/{skill_id}/history")
def get_skill_execution_history(
    skill_id: str,
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取指定技能的执行历史"""
    from app.models.domain import SkillExecutionHistory

    # 验证技能存在
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    history = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.skill_id == skill_id)
        .order_by(SkillExecutionHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "status": "success",
        "total": len(history),
        "data": [
            {
                "id": h.id,
                "user_id": h.user_id,
                "project_id": h.project_id,
                "status": h.status,
                "execution_time": h.execution_time,
                "result_summary": h.result_summary,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in history
        ]
    }


# ==========================================
# GET /api/skills/history - 获取用户的执行历史
# ==========================================
@router.get("/history")
def get_execution_history(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的执行历史"""
    from app.models.domain import SkillExecutionHistory

    history = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.user_id == current_user.id)
        .order_by(SkillExecutionHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    total = session.exec(
        select(SkillExecutionHistory)
        .where(SkillExecutionHistory.user_id == current_user.id)
    ).all().__len__()

    return {
        "status": "success",
        "total": total,
        "data": [
            {
                "id": h.id,
                "skill_id": h.skill_id,
                "skill_name": h.skill_name,
                "project_id": h.project_id,
                "status": h.status,
                "execution_time": h.execution_time,
                "created_at": h.created_at.isoformat()
            }
            for h in history
        ]
    }