"""
SKILL API 路由 - 提供 SKILL 目录查询和知识固化接口
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.skill_parser import get_skill_parser
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User

router = APIRouter()


class TransformRequest(BaseModel):
    """Live_Coding 转 SKILL 请求"""
    session_id: int
    message_id: int
    skill_name: str
    description: str


# ==========================================
# GET /api/skills/catalog - 获取 SKILL 目录
# ==========================================
@router.get("/catalog")
async def get_skill_catalog():
    """
    获取所有可用 SKILL 的目录信息

    返回所有 SKILL 的元数据、参数 Schema 和专家知识库
    """
    try:
        parser = get_skill_parser()
        skills = parser.get_all_skills()

        # 精简返回信息
        catalog = []
        for skill in skills:
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
                "tags": meta.get("tags", [])
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
async def get_skill_detail(skill_id: str):
    """
    获取单个 SKILL 的详细信息

    Args:
        skill_id: SKILL 的唯一标识符
    """
    parser = get_skill_parser()
    skill = parser.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"SKILL not found: {skill_id}")

    return {
        "status": "success",
        "data": skill
    }


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