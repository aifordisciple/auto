"""
系统学习管理 API

虽然是隐身系统，但提供管理接口用于:
- 查看学习统计
- 手动触发学习
- 管理系统技能

API 端点:
- GET  /system-learning/stats      - 获取学习统计
- POST /system-learning/trigger    - 手动触发学习
- GET  /system-learning/skills     - 列出系统技能
- GET  /system-learning/skills/:id - 获取技能详情
- DELETE /system-learning/skills/:id - 删除低质量技能
- GET  /system-learning/pool/stats - 获取会话池统计
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional, List

from app.core.database import get_session
from app.models.system_skill import SystemSkill, SystemSkillPublic
from app.services.system_learning.session_pool import get_session_pool
from app.services.system_learning.batch_scheduler import (
    run_learning_cycle,
    rebuild_vector_index,
    get_pool_stats
)

router = APIRouter(prefix="/system-learning", tags=["System Learning"])


# ============================================================================
# 统计接口
# ============================================================================

@router.get("/stats")
async def get_learning_stats(
    session: Session = Depends(get_session)
) -> dict:
    """
    获取学习统计

    返回:
    - total_skills: 系统技能总数
    - by_type: 各类型技能数量
    - pool_stats: 会话池统计
    """
    # 获取会话池统计
    pool = get_session_pool()
    pool_stats = pool.get_stats()

    # 从数据库查询技能统计
    statement = select(SystemSkill).where(SystemSkill.status == "active")
    total_skills = session.exec(statement).all()

    # 按类型分组统计
    by_type = {
        "analysis_strategy": 0,
        "error_fix": 0,
        "execution_opt": 0
    }

    for skill in total_skills:
        if skill.method_type in by_type:
            by_type[skill.method_type] += 1

    # 计算平均置信度
    avg_confidence = 0.0
    if total_skills:
        confidences = [s.confidence_score for s in total_skills]
        avg_confidence = sum(confidences) / len(confidences)

    return {
        "total_skills": len(total_skills),
        "by_type": by_type,
        "avg_confidence": avg_confidence,
        "pool_stats": pool_stats
    }


@router.get("/pool/stats")
async def get_pool_statistics() -> dict:
    """
    获取会话池统计

    返回:
    - total: 当前待处理会话数
    - avg_confidence: 平均置信度
    - by_user: 按用户分布
    - by_project: 按项目分布
    """
    stats = get_pool_stats()
    return stats


# ============================================================================
# 触发接口
# ============================================================================

@router.post("/trigger")
async def trigger_learning() -> dict:
    """
    手动触发学习周期

    返回:
    - processed_sessions: 处理会话数
    - extracted_skills: 提取技能数
    - updated_skills: 更新技能数
    """
    result = run_learning_cycle()
    return result


@router.post("/trigger/index-rebuild")
async def trigger_index_rebuild() -> dict:
    """
    手动触发向量索引重建

    Returns:
        dict: 重建结果
    """
    result = rebuild_vector_index()
    return result


# ============================================================================
# 技能管理接口
# ============================================================================

@router.get("/skills", response_model=List[SystemSkillPublic])
async def list_system_skills(
    method_type: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 50,
    session: Session = Depends(get_session)
) -> List[SystemSkill]:
    """
    列出系统技能（只读）

    Args:
        method_type: 按类型筛选
        min_confidence: 最低置信度
        limit: 最大返回数量

    Returns:
        List[SystemSkill]: 技能列表
    """
    statement = select(SystemSkill).where(SystemSkill.status == "active")

    if method_type:
        statement = statement.where(SystemSkill.method_type == method_type)

    if min_confidence is not None:
        statement = statement.where(SystemSkill.confidence_score >= min_confidence)

    # 按置信度降序排列
    statement = statement.order_by(SystemSkill.confidence_score.desc())
    statement = statement.limit(limit)

    skills = session.exec(statement).all()
    return skills


@router.get("/skills/{skill_id}", response_model=SystemSkillPublic)
async def get_system_skill(
    skill_id: str,
    session: Session = Depends(get_session)
) -> SystemSkill:
    """
    获取单个系统技能详情

    Args:
        skill_id: 技能ID

    Returns:
        SystemSkill: 技能详情

    Raises:
        HTTPException: 技能不存在
    """
    statement = select(SystemSkill).where(SystemSkill.skill_id == skill_id)
    skill = session.exec(statement).first()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return skill


@router.delete("/skills/{skill_id}")
async def delete_system_skill(
    skill_id: str,
    session: Session = Depends(get_session)
) -> dict:
    """
    删除低质量系统技能

    执行软删除：标记为 deprecated 而非物理删除。

    Args:
        skill_id: 技能ID

    Returns:
        dict: 删除结果

    Raises:
        HTTPException: 技能不存在
    """
    statement = select(SystemSkill).where(SystemSkill.skill_id == skill_id)
    skill = session.exec(statement).first()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # 软删除：标记为 deprecated
    skill.status = "deprecated"
    session.add(skill)
    session.commit()

    return {"status": "deleted", "skill_id": skill_id}


@router.get("/skills/{skill_id}/injection-stats")
async def get_skill_injection_stats(
    skill_id: str,
    session: Session = Depends(get_session)
) -> dict:
    """
    获取技能注入统计

    用于分析技能的使用情况和效果。

    Args:
        skill_id: 技能ID

    Returns:
        dict: 注入统计
    """
    statement = select(SystemSkill).where(SystemSkill.skill_id == skill_id)
    skill = session.exec(statement).first()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "injection_count": skill.injection_count,
        "success_rate": skill.success_rate,
        "source_sessions": skill.source_sessions,
        "confidence_score": skill.confidence_score
    }


# ============================================================================
# 健康检查
# ============================================================================

@router.get("/health")
async def health_check() -> dict:
    """
    系统学习层健康检查

    Returns:
        dict: 健康状态
    """
    try:
        # 检查会话池
        pool = get_session_pool()
        pool_stats = pool.get_stats()

        return {
            "status": "healthy",
            "pool": {
                "total_pending": pool_stats.get("total", 0),
                "status": "ok"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }