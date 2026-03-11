"""
SKILL API 路由 - 提供 SKILL 目录查询、知识固化、SKILL 工厂接口
"""

import os
import json
import re
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, or_

from app.core.skill_parser import get_skill_parser, get_combined_skills, get_db_skill_parser
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User, Project, SystemConfig,
    SkillAsset, SkillAssetCreate, SkillAssetUpdate, SkillAssetPublic, SkillStatus,
    get_utc_now
)
from app.core.database import Session, get_session
from app.services.skill_bundle_writer import generate_skill_md

router = APIRouter()


# ==========================================
# 请求模型定义
# ==========================================
class TransformRequest(BaseModel):
    """Live_Coding 转 SKILL 请求"""
    session_id: int
    message_id: int
    skill_name: str
    description: str


class ConsolidateRequest(BaseModel):
    """蓝图固化请求"""
    project_id: str
    blueprint_json: str  # JSON 字符串
    skill_name: str = None  # 可选的自定义名称


class CraftRequest(BaseModel):
    """SKILL 锻造请求"""
    raw_material: str = Field(..., description="原始素材：代码/指令/文献段落")
    executor_type: str = Field(default="Python_env", description="执行器类型: Python_env/R_env/Logical_Blueprint/Python_Package")
    generate_full_bundle: bool = Field(default=False, description="是否生成完整文件系统目录")
    skill_name_hint: Optional[str] = Field(default=None, description="技能名称提示")
    category: Optional[str] = Field(default=None, description="一级分类ID")
    subcategory: Optional[str] = Field(default=None, description="二级分类ID")
    tags: List[str] = Field(default_factory=list, description="标签列表")


class SkillTestRequest(BaseModel):
    """SKILL 测试请求（增强版）"""
    script_code: str = Field(..., description="需要测试的代码")
    test_instruction: str = Field(default="", description="测试环境变量或传参模拟代码")
    parameters_schema: Optional[Dict[str, Any]] = Field(default=None, description="参数 Schema，用于自动生成测试数据")
    auto_generate_data: bool = Field(default=True, description="是否自动生成测试数据")
    max_test_rounds: int = Field(default=3, description="最大测试轮数")
    executor_type: str = Field(default="Python_env", description="执行器类型: Python_env/R_env")


# ==========================================
# 铁律校验函数
# ==========================================
def validate_iron_rules(script_code: str) -> tuple[bool, str]:
    """
    双保险强制校验 - 确保代码符合三大铁律

    Returns:
        (is_valid, error_message)
    """
    if not script_code:
        return False, "代码不能为空"

    # 1. 校验参数系统 (检查是否包含 argparse 或 optparse 或 sys.argv)
    if not re.search(r'(argparse|optparse|sys\.argv|commandArgs)', script_code):
        return False, "拦截：代码未包含参数解析系统！必须使用 argparse (Python) 或 optparse/commandArgs (R)"

    # 2. 校验输出格式 (如果是 pandas 输出，检查是否带 tab 或 tsv)
    if 'to_csv' in script_code:
        if not re.search(r"(sep=[\'\"]\\t[\'\"]|sep='\t'|sep=\"\t\"|\.tsv|sep='\t')", script_code):
            return False, "拦截：表格输出必须明确指定 tab 分割的 tsv 格式！请添加 sep='\\t' 或输出为 .tsv 文件"

    # 3. 校验注释密度 (简单判断是否包含一定数量的注释)
    comment_count = script_code.count('#')
    docstring_count = script_code.count('"""') + script_code.count("'''")
    if comment_count < 3 and docstring_count < 1:
        return False, "拦截：代码缺乏详尽的程序说明注释！请添加至少3行注释或文档字符串"

    return True, ""


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
    """
    statement = select(SkillAsset).where(
        or_(
            SkillAsset.status == SkillStatus.PUBLISHED,
            SkillAsset.owner_id == current_user.id
        )
    ).order_by(SkillAsset.created_at.desc())

    skills = session.exec(statement).all()
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
# GET /api/skills/catalog - 获取 SKILL 目录
# ==========================================
@router.get("/catalog")
async def get_skill_catalog(
    current_user: User = Depends(get_current_user)
):
    """
    获取所有可用 SKILL 的目录信息（包含文件系统和数据库）

    返回所有 SKILL 的元数据、参数 Schema 和专家知识库
    """
    try:
        # 合并文件系统和数据库的技能
        all_skills = get_combined_skills(current_user.id)

        # 精简返回信息
        catalog = []
        for skill in all_skills:
            meta = skill.get("metadata", {})
            catalog.append({
                "skill_id": meta.get("skill_id"),
                "name": meta.get("name"),
                "version": meta.get("version"),
                "author": meta.get("author"),
                "executor_type": meta.get("executor_type"),
                "timeout_seconds": meta.get("timeout_seconds"),
                "parameters_schema": skill.get("parameters_schema", {}),
                "bundle_name": skill.get("bundle_name"),
                "category": meta.get("category"),
                "category_name": meta.get("category_name"),
                "subcategory": meta.get("subcategory"),
                "subcategory_name": meta.get("subcategory_name"),
                "tags": meta.get("tags", []),
                "source": skill.get("source", "filesystem"),
                "status": meta.get("status", "PUBLISHED")
            })

        return {
            "status": "success",
            "total": len(catalog),
            "data": catalog
        }

    except Exception as e:
        log.error(f"[Skills API] 获取 SKILL 目录失败: {e}")
        return {
            "status": "error",
            "message": str(e),
            "total": 0,
            "data": []
        }


# ==========================================
# GET /api/skills/{skill_id} - 获取单个 SKILL 详情
# ==========================================
@router.get("/{skill_id}")
def get_skill_detail(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取单个 SKILL 详情（带越权检查）"""
    # 先尝试从数据库获取
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()

    if skill:
        # 权限检查：如果不是已发布的公共技能，且不是自己的，拒绝访问
        if skill.status != SkillStatus.PUBLISHED and skill.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该私有技能")

        return {
            "status": "success",
            "source": "database",
            "data": {
                "id": skill.id,
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "executor_type": skill.executor_type,
                "parameters_schema": skill.parameters_schema,
                "expert_knowledge": skill.expert_knowledge,
                "script_code": skill.script_code,
                "dependencies": skill.dependencies,
                "status": skill.status.value,
                "reject_reason": skill.reject_reason,
                "owner_id": skill.owner_id,
                "created_at": skill.created_at.isoformat(),
                "updated_at": skill.updated_at.isoformat()
            }
        }

    # 如果数据库中没有，尝试从文件系统获取
    parser = get_skill_parser()
    fs_skill = parser.get_skill_by_id(skill_id)

    if fs_skill:
        return {
            "status": "success",
            "source": "filesystem",
            "data": fs_skill
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
    """更新自己的 SKILL"""
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
    log.info(f"📝 [Skills API] 用户 {current_user.id} 更新了技能: {skill_id}")
    return skill


# ==========================================
# DELETE /api/skills/{skill_id} - 删除自己的 SKILL
# ==========================================
@router.delete("/{skill_id}")
def delete_skill(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除自己的 SKILL（只能删除自己创建的）"""
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己创建的技能")

    # 已发布的技能不能直接删除
    if skill.status == SkillStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="已发布的技能不能删除，请联系管理员下架")

    session.delete(skill)
    session.commit()
    log.info(f"🗑️ [Skills API] 用户 {current_user.id} 删除了技能: {skill_id}")
    return {"status": "success", "message": "技能已删除"}


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
# POST /api/skills/craft_from_material - AI 锻造接口
# ==========================================
@router.post("/craft_from_material")
async def craft_skill_api(
    req: CraftRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge】前端传入原始素材，后台调用大模型锻造并返回结构化的资产草稿。

    支持参数：
    - executor_type: 执行器类型 (Python_env/R_env/Logical_Blueprint/Python_Package)
    - generate_full_bundle: 是否生成完整文件系统目录
    - skill_name_hint: 技能名称提示

    (注意：此接口仅返回锻造结果供前端预览，并不直接写入数据库)
    """
    if not req.raw_material or len(req.raw_material.strip()) < 10:
        raise HTTPException(status_code=400, detail="素材内容过短，无法锻造")

    # 1. 动态获取 LLM 配置
    config = session.get(SystemConfig, 1)
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    # 2. 调用 Crafter Agent
    try:
        from app.agent.crafter import craft_skill_from_material

        log.info(f"🔨 [Skills API] 用户 {current_user.id} 开始锻造技能... 类型: {req.executor_type}")
        crafted_result = await craft_skill_from_material(
            raw_material=req.raw_material,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            executor_type=req.executor_type
        )

        # 3. 校验铁律 (仅对单脚本类型)
        if crafted_result.get("script_code") and req.executor_type in ["Python_env", "R_env"]:
            is_valid, error_msg = validate_iron_rules(crafted_result["script_code"])
            if not is_valid:
                crafted_result["validation_warning"] = error_msg
            else:
                crafted_result["validation_passed"] = True

        # 4. 如果需要生成完整文件系统目录
        bundle_path = None
        files_created = []

        if req.generate_full_bundle:
            from app.services.skill_bundle_writer import write_skill_bundle, generate_skill_id_from_name
            from app.models.skill_bundle import (
                SkillBundleContent, SkillBundleMetadata, ExecutorType, NextflowBundle
            )

            # 生成 skill_id
            skill_id = generate_skill_id_from_name(
                req.skill_name_hint or crafted_result.get("name", "custom_skill")
            )

            # 构建元数据
            metadata = SkillBundleMetadata(
                skill_id=skill_id,
                name=crafted_result.get("name", "未命名技能"),
                executor_type=ExecutorType(req.executor_type),
                category=req.category or "general",
                category_name="通用",
                subcategory=req.subcategory,
                tags=req.tags or []
            )

            # 构建内容
            content = SkillBundleContent(
                metadata=metadata,
                description=crafted_result.get("description", ""),
                parameters_schema=crafted_result.get("parameters_schema", {"type": "object", "properties": {}, "required": []}),
                expert_knowledge=crafted_result.get("expert_knowledge", ""),
                script_code=crafted_result.get("script_code"),
                dependencies=crafted_result.get("dependencies", [])
            )

            # 如果是 Nextflow 类型，添加 nextflow_bundle
            if req.executor_type == "Logical_Blueprint" and crafted_result.get("nextflow_code"):
                content.nextflow_bundle = NextflowBundle(full_code=crafted_result["nextflow_code"])

            # 写入文件系统
            result = write_skill_bundle(content, skills_dir="/app/skills")
            bundle_path = result.get("bundle_path")
            files_created = result.get("files_created", [])

            log.info(f"📁 [Skills API] 生成完整技能包: {skill_id}, 文件: {files_created}")

        # 生成 SKILL.md 内容
        # 使用已生成的 skill_id 或生成临时 ID
        md_skill_id = skill_id if req.generate_full_bundle else f"draft_{uuid.uuid4().hex[:8]}"
        skill_md = generate_skill_md(
            skill_id=md_skill_id,
            name=crafted_result.get("name", "未命名技能"),
            executor_type=req.executor_type,
            description=crafted_result.get("description", ""),
            parameters_schema=crafted_result.get("parameters_schema", {"type": "object", "properties": {}, "required": []}),
            expert_knowledge=crafted_result.get("expert_knowledge", ""),
            category=req.category or "general",
            category_name="通用",
            tags=req.tags or []
        )

        # 将 skill_md 添加到 crafted_result
        crafted_result["skill_md"] = skill_md

        return {
            "status": "success",
            "data": crafted_result,
            "bundle_path": bundle_path,
            "files_created": files_created
        }

    except Exception as e:
        log.error(f"Forge API 报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/bundle - 直接创建完整文件系统技能包
# ==========================================
@router.post("/bundle")
async def create_skill_bundle(
    req: CraftRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge Bundle】直接创建完整文件系统技能包

    该接口会：
    1. 调用 AI 锻造引擎生成技能内容
    2. 自动生成 skill_id
    3. 创建完整目录结构并写入文件

    返回：
    - skill_id: 生成的技能 ID
    - bundle_path: 生成的目录路径
    - files_created: 创建的文件列表
    """
    if not req.raw_material or len(req.raw_material.strip()) < 10:
        raise HTTPException(status_code=400, detail="素材内容过短，无法锻造")

    # 1. 动态获取 LLM 配置
    config = session.get(SystemConfig, 1)
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    try:
        from app.agent.crafter import craft_skill_from_material
        from app.services.skill_bundle_writer import write_skill_bundle, generate_skill_id_from_name
        from app.models.skill_bundle import (
            SkillBundleContent, SkillBundleMetadata, ExecutorType, NextflowBundle
        )

        # 2. 调用 AI 锻造
        log.info(f"🔨 [Skills API] 用户 {current_user.id} 创建技能包... 类型: {req.executor_type}")
        crafted_result = await craft_skill_from_material(
            raw_material=req.raw_material,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            executor_type=req.executor_type
        )

        # 3. 生成 skill_id
        skill_id = generate_skill_id_from_name(
            req.skill_name_hint or crafted_result.get("name", "custom_skill")
        )

        # 4. 构建元数据
        metadata = SkillBundleMetadata(
            skill_id=skill_id,
            name=crafted_result.get("name", "未命名技能"),
            executor_type=ExecutorType(req.executor_type),
            category=req.category or "general",
            category_name="通用",
            subcategory=req.subcategory,
            tags=req.tags or []
        )

        # 5. 构建内容
        content = SkillBundleContent(
            metadata=metadata,
            description=crafted_result.get("description", ""),
            parameters_schema=crafted_result.get("parameters_schema", {"type": "object", "properties": {}, "required": []}),
            expert_knowledge=crafted_result.get("expert_knowledge", ""),
            script_code=crafted_result.get("script_code"),
            dependencies=crafted_result.get("dependencies", [])
        )

        # 如果是 Nextflow 类型，添加 nextflow_bundle
        if req.executor_type == "Logical_Blueprint" and crafted_result.get("nextflow_code"):
            content.nextflow_bundle = NextflowBundle(full_code=crafted_result["nextflow_code"])

        # 6. 写入文件系统
        result = write_skill_bundle(content, skills_dir="/app/skills")

        log.info(f"✅ [Skills API] 技能包创建成功: {skill_id}")

        return {
            "status": "success",
            "skill_id": skill_id,
            "name": crafted_result.get("name"),
            "bundle_path": result.get("bundle_path"),
            "files_created": result.get("files_created", []),
            "executor_type": req.executor_type,
            "message": f"技能包 {skill_id} 已成功创建"
        }

    except Exception as e:
        log.error(f"创建技能包失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/test_draft - 沙箱测试接口
# ==========================================
@router.post("/test_draft")
async def test_skill_draft_api(
    req: SkillTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge】自动化沙箱测试接口（增强版）

    功能：
    1. 自动生成测试数据（基于参数 Schema）
    2. 多场景测试（不同参数组合）
    3. 测试失败自动修复

    前端传入生成的草稿代码和测试参数，后端扔进沙箱跑。
    如果失败自动触发 AI 修复，返回最终是否跑通，以及最终修复好的代码。
    """
    if not req.script_code:
        raise HTTPException(status_code=400, detail="缺少需要测试的代码")

    # 铁律校验
    is_valid, error_msg = validate_iron_rules(req.script_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 动态获取 LLM 配置
    config = session.get(SystemConfig, 1)
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    try:
        from app.agent.skill_tester import auto_test_and_heal_skill

        log.info(f"🧪 [Skills API] 用户 {current_user.id} 开始沙箱测试... 自动生成数据: {req.auto_generate_data}")

        test_result = await auto_test_and_heal_skill(
            script_code=req.script_code,
            test_instruction=req.test_instruction,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            parameters_schema=req.parameters_schema,
            auto_generate_data=req.auto_generate_data,
            max_test_rounds=req.max_test_rounds,
            executor_type=req.executor_type
        )

        return {"status": "success", "data": test_result}

    except Exception as e:
        log.error(f"自动化测试接口报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/test_draft_stream - 沙箱测试接口 (SSE 流式日志)
# ==========================================
@router.post("/test_draft_stream")
async def test_skill_draft_stream_api(
    req: SkillTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge】自动化沙箱测试接口（SSE 流式日志版本）

    功能：
    1. 实时推送测试进度日志
    2. 多场景测试进度可视化
    3. 测试失败自动修复过程可见

    返回 SSE 流，事件格式：
    - data: {"type": "log", "message": "..."}
    - data: {"type": "status", "message": "..."}
    - data: {"type": "result", "data": {...}}
    """
    if not req.script_code:
        raise HTTPException(status_code=400, detail="缺少需要测试的代码")

    # 铁律校验
    is_valid, error_msg = validate_iron_rules(req.script_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 动态获取 LLM 配置
    config = session.get(SystemConfig, 1)
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    try:
        from app.agent.skill_tester import auto_test_and_heal_skill_stream

        log.info(f"🧪 [Skills API] 用户 {current_user.id} 开始沙箱测试 (流式模式)...")

        async def event_generator():
            async for event in auto_test_and_heal_skill_stream(
                script_code=req.script_code,
                test_instruction=req.test_instruction,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                parameters_schema=req.parameters_schema,
                auto_generate_data=req.auto_generate_data,
                max_test_rounds=req.max_test_rounds,
                executor_type=req.executor_type
            ):
                yield event

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        log.error(f"自动化测试流式接口报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/transform_from_live - 知识固化接口
# ==========================================
@router.post("/transform_from_live")
async def transform_from_live(
    req: TransformRequest,
    current_user: User = Depends(get_current_user)
):
    """
    将成功的 Live_Coding 代码转化为标准 SKILL

    流程：
    1. 从数据库提取成功的 Live_Coding 代码
    2. 调用 LLM 进行逆向工程
    3. 生成 Jinja2 模板和 SKILL.md
    4. 写入物理磁盘

    注意：此功能需要管理员权限或特殊授权
    """
    # TODO: 实现完整的知识固化流程
    # 当前返回预览信息，实际转换需要更多业务逻辑

    log.info(f"[Skills API] 用户 {current_user.id} 请求转化 Live_Coding -> SKILL: {req.skill_name}")

    return {
        "status": "pending",
        "message": "知识固化功能正在开发中，敬请期待",
        "request": {
            "session_id": req.session_id,
            "message_id": req.message_id,
            "skill_name": req.skill_name,
            "description": req.description
        }
    }


# ==========================================
# GET /api/skills/bundle/{bundle_name}/scripts - 获取 Bundle 脚本列表
# ==========================================
@router.get("/bundle/{bundle_name}/scripts")
async def get_bundle_scripts(bundle_name: str):
    """
    获取指定 Bundle 的脚本文件列表

    Args:
        bundle_name: Bundle 目录名称
    """
    import os

    parser = get_skill_parser()
    skills = parser.get_all_skills()

    target_bundle = None
    for skill in skills:
        if skill.get("bundle_name") == bundle_name:
            target_bundle = skill
            break

    if not target_bundle:
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_name}")

    bundle_path = target_bundle.get("bundle_path", "")
    scripts_dir = os.path.join(bundle_path, "scripts")

    scripts = []
    if os.path.exists(scripts_dir):
        for f in os.listdir(scripts_dir):
            if f.endswith(('.py', '.r', '.sh', '.nf')):
                scripts.append({
                    "filename": f,
                    "path": f"scripts/{f}"
                })

    return {
        "status": "success",
        "bundle_name": bundle_name,
        "scripts": scripts
    }


# ==========================================
# POST /api/skills/consolidate - 蓝图固化为 SKILL
# ==========================================
@router.post("/consolidate")
async def consolidate_skill(
    req: ConsolidateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    将成功的 DAG 蓝图固化为标准 SKILL.md

    流程：
    1. 验证蓝图格式
    2. 调用 Consolidator Agent 逆向生成 SKILL.md
    3. 保存到 /app/skills 目录

    Args:
        req: 包含蓝图 JSON 和可选的自定义名称

    Returns:
        固化结果，包括 skill_id 和文件路径
    """
    from app.agent.consolidator import consolidate_and_save

    # 1. 安全校验：检查项目权限
    if req.project_id:
        project = session.get(Project, req.project_id)
        if not project or project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 验证蓝图 JSON 格式
    try:
        blueprint_data = json.loads(req.blueprint_json)
        if not blueprint_data.get("is_complex_task"):
            raise HTTPException(status_code=400, detail="蓝图格式错误：缺少 is_complex_task 标记")
        if not blueprint_data.get("tasks"):
            raise HTTPException(status_code=400, detail="蓝图格式错误：缺少任务列表")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"蓝图 JSON 解析失败: {str(e)}")

    # 3. 获取 LLM 配置
    config = session.get(SystemConfig, 1)

    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")

    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    if is_local_model:
        api_key = db_api_key if db_api_key is not None else ""
    else:
        api_key = db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key

    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    log.info(f"🔄 [Skills API] 开始固化蓝图 - user={current_user.id}, project={req.project_id}")

    # 4. 调用 Consolidator 固化
    try:
        result = await consolidate_and_save(
            blueprint_json=req.blueprint_json,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            skills_dir="/app/skills"
        )

        if result.get("success"):
            log.info(f"✅ [Skills API] SKILL 固化成功: {result.get('skill_id')}")
            return {
                "status": "success",
                "skill_id": result.get("skill_id"),
                "file_path": result.get("file_path"),
                "content_preview": result.get("content_preview")
            }
        else:
            log.error(f"❌ [Skills API] SKILL 固化失败: {result.get('error')}")
            return {
                "status": "error",
                "message": result.get("error", "SKILL 固化失败")
            }

    except Exception as e:
        log.error(f"❌ [Skills API] 固化异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"SKILL 固化失败: {str(e)}")


# ==========================================
# GET /api/skills/list - 获取 SKILL 文件列表
# ==========================================
@router.get("/list")
async def list_skills():
    """
    获取所有 SKILL 文件列表

    返回 /app/skills 目录下的所有 .md 文件
    """
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


# ==========================================
# 版本管理 API
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


# ==========================================
# 执行历史 API
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


# ==========================================
# 收藏 API
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
# 评价 API
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


@router.post("/{skill_id}/reviews")
def create_review(
    skill_id: str,
    rating: int,
    comment: str = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """提交评价"""
    from app.models.domain import SkillReview

    if rating < 1 or rating > 5:
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
        existing.rating = rating
        existing.comment = comment
        existing.updated_at = get_utc_now()
        session.add(existing)
        session.commit()
        log.info(f"📝 [Skills API] 用户 {current_user.id} 更新了评价: {skill_id}")
        return {"status": "success", "message": "评价已更新"}

    review = SkillReview(
        skill_id=skill_id,
        user_id=current_user.id,
        rating=rating,
        comment=comment
    )
    session.add(review)
    session.commit()

    log.info(f"⭐ [Skills API] 用户 {current_user.id} 提交了评价: {skill_id} - {rating}星")
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

    expires_at = None
    if expires_in_days > 0:
        from datetime import timedelta
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


log.info("📚 SKILL API 路由已加载")