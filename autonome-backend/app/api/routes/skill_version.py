"""
技能版本管理 API 路由 - 提供版本历史、回滚功能

核心端点:
- POST /skills/{skill_id}/versions: 创建新版本
- GET /skills/{skill_id}/versions: 获取版本列表
- GET /skills/{skill_id}/versions/{version}: 获取特定版本
- POST /skills/{skill_id}/rollback: 回滚到指定版本
"""

import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel, Field

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillVersion, get_utc_now
)

router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================
class CreateVersionRequest(BaseModel):
    """创建版本请求"""
    change_log: Optional[str] = Field(default=None, description="版本变更说明")


class VersionSummary(BaseModel):
    """版本摘要"""
    id: int
    version: str
    change_log: Optional[str]
    created_at: str
    created_by: int
    created_by_name: Optional[str] = None
    is_current: bool


class VersionDetail(BaseModel):
    """版本详情"""
    id: int
    skill_id: str
    version: str
    script_code: Optional[str]
    parameters_schema: dict
    expert_knowledge: Optional[str]
    change_log: Optional[str]
    created_at: str
    created_by: int
    created_by_name: Optional[str] = None
    is_current: bool


class VersionListResponse(BaseModel):
    """版本列表响应"""
    skill_id: str
    skill_name: str
    current_version: str
    versions: List[VersionSummary]


# ==========================================
# 辅助函数
# ==========================================
def generate_next_version(current_version: str) -> str:
    """生成下一个版本号"""
    # 匹配 semver 格式
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', current_version)
    if match:
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        # 默认升级 patch 版本
        return f"{major}.{minor}.{patch + 1}"
    return "1.0.1"


def check_skill_ownership(session: Session, skill_id: str, user_id: int) -> SkillAsset:
    """检查技能所有权"""
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    if skill.owner_id != user_id:
        raise HTTPException(status_code=403, detail="只有技能所有者可以管理版本")

    return skill


# ==========================================
# POST /skills/{skill_id}/versions - 创建新版本
# ==========================================
@router.post("/skills/{skill_id}/versions", response_model=VersionDetail)
async def create_version(
    skill_id: str,
    request: CreateVersionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    创建技能新版本

    保存当前技能状态为新版本
    """
    skill = check_skill_ownership(session, skill_id, current_user.id)

    # 将当前版本标记为非当前
    current_versions = session.exec(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id
        )
    ).all()

    for v in current_versions:
        v.is_current = False
        session.add(v)

    # 创建新版本
    new_version_num = generate_next_version(skill.version)

    version = SkillVersion(
        skill_id=skill_id,
        version=new_version_num,
        script_code=skill.script_code,
        parameters_schema=skill.parameters_schema,
        expert_knowledge=skill.expert_knowledge,
        change_log=request.change_log,
        created_by=current_user.id,
        is_current=True
    )
    session.add(version)

    # 更新技能版本号
    skill.version = new_version_num
    skill.updated_at = get_utc_now()
    session.add(skill)

    session.commit()
    session.refresh(version)

    log.info(f"📜 [SkillVersion] 创建新版本: {skill_id} -> {new_version_num}")

    return VersionDetail(
        id=version.id,
        skill_id=version.skill_id,
        version=version.version,
        script_code=version.script_code,
        parameters_schema=version.parameters_schema,
        expert_knowledge=version.expert_knowledge,
        change_log=version.change_log,
        created_at=version.created_at.isoformat(),
        created_by=version.created_by,
        created_by_name=current_user.full_name or current_user.email,
        is_current=True
    )


# ==========================================
# GET /skills/{skill_id}/versions - 获取版本列表
# ==========================================
@router.get("/skills/{skill_id}/versions", response_model=VersionListResponse)
async def list_versions(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取技能版本列表"""
    skill = check_skill_ownership(session, skill_id, current_user.id)

    versions = session.exec(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id
        ).order_by(SkillVersion.created_at.desc())
    ).all()

    version_summaries = []
    for v in versions:
        creator = session.get(User, v.created_by)
        version_summaries.append(VersionSummary(
            id=v.id,
            version=v.version,
            change_log=v.change_log,
            created_at=v.created_at.isoformat(),
            created_by=v.created_by,
            created_by_name=creator.full_name or creator.email if creator else None,
            is_current=v.is_current
        ))

    return VersionListResponse(
        skill_id=skill_id,
        skill_name=skill.name,
        current_version=skill.version,
        versions=version_summaries
    )


# ==========================================
# GET /skills/{skill_id}/versions/{version_id} - 获取版本详情
# ==========================================
@router.get("/skills/{skill_id}/versions/{version_id}", response_model=VersionDetail)
async def get_version_detail(
    skill_id: str,
    version_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取特定版本详情"""
    check_skill_ownership(session, skill_id, current_user.id)

    version = session.get(SkillVersion, version_id)
    if not version or version.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="版本不存在")

    creator = session.get(User, version.created_by)

    return VersionDetail(
        id=version.id,
        skill_id=version.skill_id,
        version=version.version,
        script_code=version.script_code,
        parameters_schema=version.parameters_schema,
        expert_knowledge=version.expert_knowledge,
        change_log=version.change_log,
        created_at=version.created_at.isoformat(),
        created_by=version.created_by,
        created_by_name=creator.full_name or creator.email if creator else None,
        is_current=version.is_current
    )


# ==========================================
# POST /skills/{skill_id}/rollback - 回滚版本
# ==========================================
class RollbackRequest(BaseModel):
    """回滚请求"""
    version_id: int = Field(description="目标版本 ID")


class RollbackResponse(BaseModel):
    """回滚响应"""
    skill_id: str
    from_version: str
    to_version: str
    message: str


@router.post("/skills/{skill_id}/rollback", response_model=RollbackResponse)
async def rollback_version(
    skill_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    回滚到指定版本

    将技能恢复到历史版本的状态
    """
    skill = check_skill_ownership(session, skill_id, current_user.id)
    old_version = skill.version

    # 获取目标版本
    target_version = session.get(SkillVersion, request.version_id)
    if not target_version or target_version.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="目标版本不存在")

    # 创建当前状态的快照（自动保存当前版本）
    snapshot = SkillVersion(
        skill_id=skill_id,
        version=f"{skill.version}-pre-rollback",
        script_code=skill.script_code,
        parameters_schema=skill.parameters_schema,
        expert_knowledge=skill.expert_knowledge,
        change_log=f"回滚前自动保存 (目标: {target_version.version})",
        created_by=current_user.id,
        is_current=False
    )
    session.add(snapshot)

    # 将所有版本标记为非当前
    versions = session.exec(
        select(SkillVersion).where(SkillVersion.skill_id == skill_id)
    ).all()
    for v in versions:
        v.is_current = False
        session.add(v)

    # 恢复目标版本的内容
    skill.script_code = target_version.script_code
    skill.parameters_schema = target_version.parameters_schema
    skill.expert_knowledge = target_version.expert_knowledge
    skill.version = target_version.version
    skill.updated_at = get_utc_now()
    session.add(skill)

    # 标记目标版本为当前
    target_version.is_current = True
    session.add(target_version)

    session.commit()

    log.info(f"📜 [SkillVersion] 回滚版本: {skill_id} {old_version} -> {target_version.version}")

    return RollbackResponse(
        skill_id=skill_id,
        from_version=old_version,
        to_version=target_version.version,
        message=f"已回滚到版本 {target_version.version}"
    )


# ==========================================
# DELETE /skills/{skill_id}/versions/{version_id} - 删除版本
# ==========================================
@router.delete("/skills/{skill_id}/versions/{version_id}")
async def delete_version(
    skill_id: str,
    version_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除版本（不能删除当前版本）"""
    check_skill_ownership(session, skill_id, current_user.id)

    version = session.get(SkillVersion, version_id)
    if not version or version.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="版本不存在")

    if version.is_current:
        raise HTTPException(status_code=400, detail="不能删除当前版本")

    session.delete(version)
    session.commit()

    log.info(f"📜 [SkillVersion] 删除版本: {skill_id} v{version.version}")

    return {"status": "success", "message": "版本已删除"}


log.info("✅ 技能版本管理 API 已加载")