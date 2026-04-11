"""
技能 CRUD API

包含技能的基础增删改查操作

缓存策略：
- 技能列表: L1缓存 TTL=5min, L2缓存 TTL=10min
- 技能详情: L1缓存 TTL=10min, L2缓存 TTL=30min
- 写操作后自动失效相关缓存
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, or_

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, SkillAsset, SkillAssetCreate, SkillAssetUpdate, SkillAssetPublic, SkillStatus
)
from app.services.cache_service import get_cache_service, invalidate_cache

router = APIRouter()


# ==========================================
# 辅助函数：技能数据转换为可序列化字典
# ==========================================
def _skill_to_dict(skill: SkillAsset) -> dict:
    """将 SkillAsset 对象转换为可 JSON 序列化的字典"""
    return {
        "id": skill.id,
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
        "executor_type": skill.executor_type,
        "parameters_schema": skill.parameters_schema,
        "expert_knowledge": skill.expert_knowledge,
        "script_code": skill.script_code,
        "nextflow_code": skill.nextflow_code,
        "dependencies": skill.dependencies,
        "category": skill.category,
        "category_name": skill.category_name,
        "subcategory": skill.subcategory,
        "subcategory_name": skill.subcategory_name,
        "tags": skill.tags,
        "status": skill.status.value if hasattr(skill.status, 'value') else skill.status,
        "visibility": skill.visibility if skill.visibility else "private",
        "license": skill.license,
        "owner_id": skill.owner_id,
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat()
    }


# ==========================================
# GET /api/skills/ - 获取用户可用的所有 SKILL
# ==========================================
@router.get("/", response_model=List[SkillAssetPublic])
def list_available_skills(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【权限隔离】获取当前用户可用的所有 SKILL：
    包含：全平台已发布的 (PUBLISHED) + 用户自己创建的 (任何状态)

    缓存策略：L1 TTL=5min, L2 TTL=10min
    """
    # 尝试从缓存获取
    cache = get_cache_service()
    cache_key = f"skills:list:{current_user.id}"
    cached = cache.get(cache_key)

    if cached is not None:
        log.debug(f"[Skills API] 缓存命中: {cache_key}")
        return cached

    # 缓存未命中，查询数据库
    statement = select(SkillAsset).where(
        or_(
            SkillAsset.status == SkillStatus.PUBLISHED,
            SkillAsset.owner_id == current_user.id
        )
    ).order_by(SkillAsset.created_at.desc())

    skills = session.exec(statement).all()

    # 转换为可序列化格式
    result = [_skill_to_dict(s) for s in skills]

    # 存入缓存
    cache.set(cache_key, result, cache_type="skills:list")
    log.debug(f"[Skills API] 缓存已更新: {cache_key}, 共 {len(result)} 个技能")

    return result


# ==========================================
# GET /api/skills/my - 获取当前用户的技能列表
# ==========================================
@router.get("/my", response_model=List[SkillAssetPublic])
def get_my_skills(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户创建的所有技能（包含所有状态）

    Args:
        status: 可选的状态过滤 (DRAFT, PRIVATE, PENDING_REVIEW, PUBLISHED, REJECTED)
    """
    statement = select(SkillAsset).where(
        SkillAsset.owner_id == current_user.id
    )

    # 状态过滤
    if status:
        try:
            status_enum = SkillStatus(status.upper())
            statement = statement.where(SkillAsset.status == status_enum)
        except ValueError:
            pass  # 忽略无效的状态值

    statement = statement.order_by(SkillAsset.updated_at.desc())
    skills = session.exec(statement).all()

    log.info(f"[Skills API] 用户 {current_user.id} 查询我的技能，共 {len(skills)} 个")
    return skills


# ==========================================
# POST /api/skills/ - 创建新的自定义 SKILL
# ==========================================
@router.post("/", response_model=SkillAssetPublic)
def create_skill(
    skill_in: SkillAssetCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建新的自定义 SKILL (初始状态为 DRAFT)"""
    # 如果未提供 skill_id，自动生成
    if not skill_in.skill_id:
        from app.models.domain import generate_skill_id
        skill_in.skill_id = generate_skill_id()

    # 检查 skill_id 是否冲突
    existing = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_in.skill_id)).first()
    if existing:
        raise HTTPException(status_code=400, detail="该 Skill ID 已被占用，请更换")

    skill = SkillAsset.model_validate(skill_in)
    skill.owner_id = current_user.id
    skill.status = SkillStatus.DRAFT  # 强制设定为草稿

    session.add(skill)
    session.commit()
    session.refresh(skill)
    log.info(f"✅ [Skills API] 用户 {current_user.id} 创建了新技能: {skill.skill_id}")
    return skill


# ==========================================
# GET /api/skills/{skill_id} - 获取单个 SKILL 详情
# ==========================================
@router.get("/{skill_id}")
def get_skill_detail(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取单个 SKILL 详情（带越权检查）

    缓存策略：L1 TTL=10min, L2 TTL=30min
    """
    from app.core.skill_parser import get_skill_parser

    # 尝试从缓存获取
    cache = get_cache_service()
    cache_key = f"skills:detail:{skill_id}:{current_user.id}"
    cached = cache.get(cache_key)

    if cached is not None:
        log.debug(f"[Skills API] 缓存命中: {cache_key}")
        return cached

    # 先尝试从数据库获取
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()

    if skill:
        # 权限检查：如果不是已发布的公共技能，且不是自己的，拒绝访问
        if skill.status != SkillStatus.PUBLISHED and skill.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该私有技能")

        result = {
            "status": "success",
            "source": "database",
            "data": _skill_to_dict(skill)
        }

        # 存入缓存（仅缓存已发布的公共技能或用户自己的技能）
        if skill.status == SkillStatus.PUBLISHED or skill.owner_id == current_user.id:
            cache.set(cache_key, result, cache_type="skills:detail")

        return result

    # 如果数据库中没有，尝试从文件系统获取
    parser = get_skill_parser()
    fs_skill = parser.get_skill_by_id(skill_id)

    if fs_skill:
        result = {
            "status": "success",
            "source": "filesystem",
            "data": fs_skill
        }
        # 文件系统技能缓存
        cache.set(cache_key, result, cache_type="skills:detail")
        return result

    raise HTTPException(status_code=404, detail=f"SKILL not found: {skill_id}")


# ==========================================
# GET /api/skills/params/{skill_id} - 获取技能的 StrategyCard 格式参数
# ==========================================
@router.get("/params/{skill_id}")
def get_skill_params(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取技能的参数定义，用于渲染 StrategyCard。

    返回格式：
    {
        "status": "success",
        "data": {
            "tool_id": "skill_xxx",
            "title": "技能名称",
            "description": "技能描述",
            "parameters": {...}  // JSON Schema 格式
        }
    }
    """
    from app.core.skill_parser import get_skill_parser

    # 先尝试从数据库获取
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()

    if skill:
        # 权限检查
        if skill.status != SkillStatus.PUBLISHED and skill.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该私有技能")

        return {
            "status": "success",
            "source": "database",
            "data": {
                "tool_id": skill.skill_id,
                "title": skill.name,
                "description": skill.description or "",
                "parameters": skill.parameters_schema or {},
                "executor_type": skill.executor_type,
                "expert_knowledge": skill.expert_knowledge or "",
            }
        }

    # 如果数据库中没有，尝试从文件系统获取
    parser = get_skill_parser()
    fs_skill = parser.get_skill_by_id(skill_id)

    if fs_skill:
        metadata = fs_skill.get("metadata", {})
        parameters_schema = fs_skill.get("parameters_schema", {})

        return {
            "status": "success",
            "source": "filesystem",
            "data": {
                "tool_id": skill_id,
                "title": metadata.get("name", skill_id),
                "description": metadata.get("description", ""),
                "parameters": parameters_schema,
                "executor_type": metadata.get("executor_type", "Python_env"),
                "expert_knowledge": fs_skill.get("expert_knowledge", ""),
            }
        }

    raise HTTPException(status_code=404, detail=f"SKILL not found: {skill_id}")


# ==========================================
# PUT /api/skills/{skill_id} - 更新自己的 SKILL
# ==========================================
@router.put("/{skill_id}", response_model=SkillAssetPublic)
def update_skill(
    skill_id: str,
    skill_in: SkillAssetUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    更新自己的 SKILL

    更新后自动失效相关缓存
    """
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能修改自己创建的技能")

    # 如果被驳回后修改，自动退回草稿
    if skill.status == SkillStatus.REJECTED:
        skill.status = SkillStatus.DRAFT

    update_data = skill_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(skill, key, value)

    session.add(skill)
    session.commit()
    session.refresh(skill)

    # 失效相关缓存
    cache = get_cache_service()
    cache.invalidate_pattern(f"skills:list:{current_user.id}")
    cache.invalidate_pattern(f"skills:detail:{skill_id}")
    log.debug(f"[Skills API] 缓存已失效: skills:list:{current_user.id}, skills:detail:{skill_id}")

    log.info(f"📝 [Skills API] 用户 {current_user.id} 更新了技能: {skill_id}")
    return skill


# ==========================================
# DELETE /api/skills/{skill_id} - 删除或下架自己的 SKILL
# ==========================================
@router.delete("/{skill_id}")
def delete_skill(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    删除或下架自己的 SKILL

    - 草稿/私有/待审核/已驳回状态：直接删除
    - 已发布状态：改为 DEPRECATED（下架），保留记录但不在列表显示

    操作后自动失效相关缓存
    """
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己创建的技能")

    # 已发布的技能改为 DEPRECATED 状态（下架）
    if skill.status == SkillStatus.PUBLISHED:
        skill.status = SkillStatus.DEPRECATED
        session.add(skill)
        session.commit()

        # 失效相关缓存
        cache = get_cache_service()
        cache.invalidate_pattern(f"skills:list:{current_user.id}")
        cache.invalidate_pattern(f"skills:detail:{skill_id}")

        log.info(f"📦 [Skills API] 用户 {current_user.id} 下架了已发布技能: {skill_id}")
        return {"status": "success", "message": "技能已下架", "action": "deprecated"}

    # 其他状态直接删除
    session.delete(skill)
    session.commit()

    # 失效相关缓存
    cache = get_cache_service()
    cache.invalidate_pattern(f"skills:list:{current_user.id}")
    cache.invalidate_pattern(f"skills:detail:{skill_id}")

    log.info(f"🗑️ [Skills API] 用户 {current_user.id} 删除了技能: {skill_id}")
    return {"status": "success", "message": "技能已删除", "action": "deleted"}


# ==========================================
# POST /api/skills/{skill_id}/submit_review - 提交审核
# ==========================================
@router.post("/{skill_id}/submit_review")
def submit_skill_for_review(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """【状态流转】将自己的技能提交给管理员审核"""
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此技能")

    # 检查是否有代码
    if not skill.script_code:
        raise HTTPException(status_code=400, detail="请先添加执行代码")

    skill.status = SkillStatus.PENDING_REVIEW
    session.add(skill)
    session.commit()
    log.info(f"📤 [Skills API] 用户 {current_user.id} 提交了技能审核: {skill_id}")
    return {"status": "success", "message": "已提交审核，请等待管理员通过"}


# ==========================================
# GET /api/skills/list - 获取 SKILL 文件列表
# ==========================================
@router.get("/list")
async def list_skills():
    """
    获取所有 SKILL 文件列表

    返回 /app/skills 目录下的所有 .md 文件
    """
    import os

    skills_dir = "/app/skills"

    if not os.path.exists(skills_dir):
        return {
            "status": "success",
            "total": 0,
            "data": []
        }

    skills = []
    for f in os.listdir(skills_dir):
        if f.endswith('.md'):
            file_path = os.path.join(skills_dir, f)
            try:
                stat = os.stat(file_path)
                skills.append({
                    "filename": f,
                    "path": file_path,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })
            except Exception as e:
                log.warning(f"无法读取 SKILL 文件 {f}: {e}")

    return {
        "status": "success",
        "total": len(skills),
        "data": sorted(skills, key=lambda x: x["modified"], reverse=True)
    }