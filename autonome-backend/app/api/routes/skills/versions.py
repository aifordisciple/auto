"""
技能版本管理 API

包含技能版本创建、查询、回滚等接口
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset, get_utc_now

router = APIRouter()


# ==========================================
# GET /api/skills/{skill_id}/versions - 获取版本历史
# ==========================================
@router.get("/{skill_id}/versions")
def get_skill_versions(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能的所有版本历史"""
    from app.models.domain import SkillVersion

    versions = session.exec(
        select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(SkillVersion.created_at.desc())
    ).all()

    return {
        "status": "success",
        "total": len(versions),
        "data": [
            {
                "id": v.id,
                "version": v.version,
                "change_log": v.change_log,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by
            }
            for v in versions
        ]
    }


# ==========================================
# POST /api/skills/{skill_id}/versions - 创建新版本
# ==========================================
@router.post("/{skill_id}/versions")
def create_skill_version(
    skill_id: str,
    version: str,
    change_log: str = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建新版本"""
    from app.models.domain import SkillVersion

    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能为自己创建版本")

    new_version = SkillVersion(
        skill_id=skill_id,
        version=version,
        script_code=skill.script_code,
        parameters_schema=skill.parameters_schema,
        expert_knowledge=skill.expert_knowledge,
        created_by=current_user.id,
        change_log=change_log
    )

    session.add(new_version)
    session.commit()
    session.refresh(new_version)

    log.info(f"📜 [Skills API] 用户 {current_user.id} 创建了版本: {skill_id}@{version}")
    return {"status": "success", "version_id": new_version.id}


# ==========================================
# GET /api/skills/{skill_id}/versions/{version_id} - 获取版本详情
# ==========================================
@router.get("/{skill_id}/versions/{version_id}")
def get_version_detail(
    skill_id: str,
    version_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取单个版本的详细信息"""
    from app.models.domain import SkillVersion

    version = session.exec(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.id == version_id
        )
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    return {
        "status": "success",
        "data": {
            "id": version.id,
            "skill_id": version.skill_id,
            "version": version.version,
            "script_code": version.script_code,
            "parameters_schema": version.parameters_schema,
            "expert_knowledge": version.expert_knowledge,
            "change_log": version.change_log,
            "created_at": version.created_at.isoformat(),
            "created_by": version.created_by
        }
    }


# ==========================================
# POST /api/skills/{skill_id}/rollback/{version_id} - 回滚版本
# ==========================================
@router.post("/{skill_id}/rollback/{version_id}")
def rollback_skill_version(
    skill_id: str,
    version_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """回滚到指定版本"""
    from app.models.domain import SkillVersion

    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能回滚自己的技能")

    version = session.exec(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.id == version_id
        )
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    # 回滚
    skill.script_code = version.script_code
    skill.parameters_schema = version.parameters_schema
    skill.expert_knowledge = version.expert_knowledge
    skill.updated_at = get_utc_now()

    session.add(skill)
    session.commit()

    log.info(f"🔄 [Skills API] 用户 {current_user.id} 回滚到版本: {skill_id}@{version.version}")
    return {"status": "success", "message": f"已回滚到版本 {version.version}"}