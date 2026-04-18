"""
技能锻造 API

包含从素材、压缩包锻造技能的接口
"""

import os
import json
import uuid
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.config import settings
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.utils.llm_config import get_llm_config
from app.services.skill_validator import validate_iron_rules
from app.services.skill_bundle_writer import generate_skill_md
from app.schemas.skill import CraftRequest

router = APIRouter()


# ==========================================
# POST /api/skills/craft_from_bundle - 从压缩包锻造技能
# ==========================================
@router.post("/craft_from_bundle")
async def craft_from_bundle(
    file: UploadFile = File(...),
    executor_type: str = Form("Logical_Blueprint"),
    skill_name_hint: Optional[str] = Form(None),
    generate_full_bundle: bool = Form(True),
    category: Optional[str] = Form(None),
    tags: str = Form("[]"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge Bundle】从压缩包创建技能

    接收 multipart/form-data 格式的压缩包，自动解析并锻造技能。

    支持格式：
    - .zip
    - .tar.gz
    - .tgz

    推荐使用 Logical_Blueprint (Nextflow 工作流) 作为执行器类型，
    因为压缩包通常包含多个脚本文件，适合工作流编排。

    Returns:
        - data: 锻造结果
        - files: 解析出的文件列表
        - bundle_path: 生成的技能包路径
        - files_created: 创建的文件列表
    """
    # 1. 验证文件类型
    filename = file.filename.lower()
    if not (filename.endswith('.zip') or filename.endswith('.tar.gz') or filename.endswith('.tgz') or filename.endswith('.tar')):
        raise HTTPException(status_code=400, detail="只支持 .zip, .tar.gz, .tgz 格式的压缩包")

    # 2. 保存上传文件到临时目录
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
    try:
        content = await file.read()
        temp_file.write(content)
        temp_file.close()

        log.info(f"📦 [Skills API] 用户 {current_user.id} 上传压缩包: {file.filename}, 大小: {len(content)} bytes")

        # 3. 解析压缩包
        from app.services.bundle_parser import parse_upload_bundle, get_bundle_preview

        parse_result = parse_upload_bundle(temp_file.name)

        if not parse_result.success:
            raise HTTPException(status_code=400, detail=parse_result.error or "解析压缩包失败")

        if not parse_result.raw_material or len(parse_result.raw_material.strip()) < 10:
            raise HTTPException(status_code=400, detail="压缩包内容不足以锻造技能")

        # 4. 获取 LLM 配置（共享工具：per-user override → system global → env fallback）
        llm_cfg = get_llm_config(session, user_id=current_user.id)
        api_key, base_url, model_name = llm_cfg.api_key, llm_cfg.base_url, llm_cfg.model_name

        # 5. 调用 AI 锻造
        try:
            from app.agent.crafter import craft_skill_from_material

            log.info(f"🔨 [Skills API] 从压缩包锻造技能... 类型: {executor_type}, 文件数: {len(parse_result.files)}")

            # 解析 tags
            try:
                tags_list = json.loads(tags)
            except:
                tags_list = []

            crafted_result = await craft_skill_from_material(
                raw_material=parse_result.raw_material,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                executor_type=executor_type
            )

            # 6. 校验铁律 (仅对单脚本类型)
            if crafted_result.get("script_code") and executor_type in ["Python_env", "R_env"]:
                is_valid, error_msg = validate_iron_rules(crafted_result["script_code"])
                if not is_valid:
                    crafted_result["validation_warning"] = error_msg
                else:
                    crafted_result["validation_passed"] = True

            # 7. 如果需要生成完整文件系统目录
            bundle_path = None
            files_created = []

            if generate_full_bundle:
                from app.services.skill_bundle_writer import write_skill_bundle, generate_skill_id_from_name
                from app.models.skill_bundle import (
                    SkillBundleContent, SkillBundleMetadata, ExecutorType, NextflowBundle
                )

                # 生成 skill_id
                skill_id = generate_skill_id_from_name(
                    skill_name_hint or crafted_result.get("name", "custom_skill")
                )

                # 构建元数据
                metadata = SkillBundleMetadata(
                    skill_id=skill_id,
                    name=crafted_result.get("name", "未命名技能"),
                    executor_type=ExecutorType(executor_type),
                    category=category or "general",
                    category_name="通用",
                    subcategory=None,
                    tags=tags_list
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
                if executor_type == "Logical_Blueprint" and crafted_result.get("nextflow_code"):
                    content.nextflow_bundle = NextflowBundle(full_code=crafted_result["nextflow_code"])

                # 写入文件系统
                result = write_skill_bundle(content, skills_dir="/app/skills")
                bundle_path = result.get("bundle_path")
                files_created = result.get("files_created", [])

                log.info(f"📁 [Skills API] 生成完整技能包: {skill_id}, 文件: {files_created}")

            # 8. 生成 SKILL.md 内容
            md_skill_id = skill_id if generate_full_bundle else f"draft_{uuid.uuid4().hex[:8]}"
            skill_md = generate_skill_md(
                skill_id=md_skill_id,
                name=crafted_result.get("name", "未命名技能"),
                executor_type=executor_type,
                description=crafted_result.get("description", ""),
                parameters_schema=crafted_result.get("parameters_schema", {"type": "object", "properties": {}, "required": []}),
                expert_knowledge=crafted_result.get("expert_knowledge", ""),
                category=category or "general",
                category_name="通用",
                tags=tags_list
            )

            crafted_result["skill_md"] = skill_md

            # 9. 生成文件预览
            file_preview = get_bundle_preview(parse_result.files)

            return {
                "status": "success",
                "data": crafted_result,
                "bundle_path": bundle_path,
                "files_created": files_created,
                "parsed_files": file_preview,
                "file_stats": parse_result.stats,
                "raw_material_length": len(parse_result.raw_material)
            }

        except Exception as e:
            log.error(f"从压缩包锻造失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 清理临时文件
        try:
            os.unlink(temp_file.name)
        except:
            pass


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

    # 1. 获取 LLM 配置（共享工具：per-user override → system global → env fallback）
    llm_cfg = get_llm_config(session, user_id=current_user.id)
    api_key, base_url, model_name = llm_cfg.api_key, llm_cfg.base_url, llm_cfg.model_name

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

        crafted_result["skill_md"] = skill_md

        return {
            "status": "success",
            "data": crafted_result,
            "bundle_path": bundle_path,
            "files_created": files_created
        }

    except Exception as e:
        log.error(f"锻造技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/bundle - 创建 SKILL Bundle
# ==========================================
@router.post("/bundle")
async def create_skill_bundle(
    skill_id: str,
    name: str,
    executor_type: str,
    description: str = "",
    script_code: str = None,
    parameters_schema: dict = None,
    expert_knowledge: str = "",
    category: str = "general",
    tags: list = None,
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Bundle】直接创建 SKILL Bundle（高级接口）

    直接传入完整的技能元数据和代码，创建技能包。
    """
    try:
        from app.services.skill_bundle_writer import write_skill_bundle
        from app.models.skill_bundle import (
            SkillBundleContent, SkillBundleMetadata, ExecutorType, NextflowBundle
        )

        # 构建元数据
        metadata = SkillBundleMetadata(
            skill_id=skill_id,
            name=name,
            executor_type=ExecutorType(executor_type),
            category=category,
            category_name="通用",
            tags=tags or []
        )

        # 构建内容
        content = SkillBundleContent(
            metadata=metadata,
            description=description,
            parameters_schema=parameters_schema or {"type": "object", "properties": {}, "required": []},
            expert_knowledge=expert_knowledge,
            script_code=script_code
        )

        # 写入文件系统
        result = write_skill_bundle(content, skills_dir="/app/skills")

        log.info(f"📁 [Skills API] 用户 {current_user.id} 创建了技能包: {skill_id}")

        return {
            "status": "success",
            "bundle_path": result.get("bundle_path"),
            "files_created": result.get("files_created", [])
        }

    except Exception as e:
        log.error(f"创建技能包失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))