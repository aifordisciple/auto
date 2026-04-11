"""
SKILL Templates API Routes - 技能模板 API 路由

提供模板的查询、实例化、创建、删除等接口
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.skill_template import (
    SkillTemplate, SkillTemplateCreate, SkillTemplatePublic,
    TemplateInstantiateRequest, TemplateInstantiateResult
)
from app.services.skill_templates import SkillTemplateService
from app.core.logger import log

router = APIRouter()


# ==========================================
# GET /api/templates/ - 获取所有模板
# ==========================================
@router.get("/", response_model=List[SkillTemplatePublic])
def list_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取所有可用的技能模板

    返回数据库模板 + 内置官方模板
    """
    try:
        service = SkillTemplateService(session)
        templates = service.get_all_templates()
        log.info(f"[Templates API] 用户 {current_user.id} 查询模板列表，共 {len(templates)} 个")
        return templates
    except Exception as e:
        log.error(f"[Templates API] 获取模板列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# GET /api/templates/{template_id} - 获取模板详情
# ==========================================
@router.get("/{template_id}")
def get_template_detail(
    template_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取单个模板的详细信息

    Args:
        template_id: 模板唯一标识
    """
    try:
        service = SkillTemplateService(session)
        template = service.get_template_by_id(template_id)

        if not template:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

        log.info(f"[Templates API] 用户 {current_user.id} 查看模板: {template_id}")
        return {
            "status": "success",
            "data": {
                "id": template.id,
                "template_id": template.template_id,
                "name": template.name,
                "description": template.description,
                "template_type": template.template_type.value,
                "script_template": template.script_template,
                "parameters_schema": template.parameters_schema,
                "expert_knowledge": template.expert_knowledge,
                "category": template.category,
                "category_name": template.category_name,
                "subcategory": template.subcategory,
                "subcategory_name": template.subcategory_name,
                "tags": template.tags,
                "source_skill_id": template.source_skill_id,
                "is_official": template.is_official,
                "usage_count": template.usage_count,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "updated_at": template.updated_at.isoformat() if template.updated_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Templates API] 获取模板详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/templates/{template_id}/instantiate - 从模板实例化技能
# ==========================================
@router.post("/{template_id}/instantiate", response_model=TemplateInstantiateResult)
def instantiate_template(
    template_id: str,
    request: TemplateInstantiateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    从模板实例化一个新技能

    该接口返回实例化后的技能数据，前端可以：
    1. 直接保存为草稿
    2. 进一步编辑后保存
    3. 直接执行测试

    Args:
        template_id: 模板 ID
        request: 实例化请求参数
    """
    try:
        service = SkillTemplateService(session)
        result = service.instantiate_template(template_id, request)

        log.info(f"[Templates API] 用户 {current_user.id} 从模板 {template_id} 实例化技能: {result.skill_id}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"[Templates API] 模板实例化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/templates/ - 创建新模板
# ==========================================
@router.post("/", response_model=SkillTemplatePublic)
def create_template(
    template_in: SkillTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    创建新的技能模板

    仅管理员或高级用户可创建模板
    """
    try:
        service = SkillTemplateService(session)
        template = service.create_template(template_in)

        log.info(f"[Templates API] 用户 {current_user.id} 创建模板: {template.template_id}")
        return SkillTemplatePublic.model_validate(template)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"[Templates API] 创建模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/templates/extract - 从现有技能提取模板
# ==========================================
@router.post("/extract")
def extract_template_from_skill(
    skill_id: str,
    template_name: str,
    template_id: str = None,
    save_to_db: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    从现有技能提取模板

    Args:
        skill_id: 源技能 ID
        template_name: 模板名称
        template_id: 自定义模板 ID（可选）
        save_to_db: 是否保存到数据库（默认只返回预览）
    """
    try:
        service = SkillTemplateService(session)
        template_data = service.extract_template_from_skill(
            skill_id=skill_id,
            template_name=template_name,
            template_id=template_id
        )

        if save_to_db:
            template = service.create_template(template_data)
            log.info(f"[Templates API] 用户 {current_user.id} 从技能 {skill_id} 提取并保存模板: {template.template_id}")
            return {
                "status": "success",
                "message": "模板已保存到数据库",
                "data": SkillTemplatePublic.model_validate(template).model_dump()
            }
        else:
            log.info(f"[Templates API] 用户 {current_user.id} 从技能 {skill_id} 提取模板预览")
            return {
                "status": "success",
                "message": "模板预览（未保存）",
                "data": template_data.model_dump()
            }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"[Templates API] 提取模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# DELETE /api/templates/{template_id} - 删除模板
# ==========================================
@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    删除模板

    注意：只能删除数据库中的自定义模板，不能删除内置官方模板
    """
    try:
        service = SkillTemplateService(session)
        success = service.delete_template(template_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="模板不存在或为内置模板，无法删除"
            )

        log.info(f"[Templates API] 用户 {current_user.id} 删除模板: {template_id}")
        return {"status": "success", "message": "模板已删除"}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Templates API] 删除模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# GET /api/templates/categories/list - 获取模板分类
# ==========================================
@router.get("/categories/list")
def get_template_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取模板分类列表

    返回所有模板的分类统计信息
    """
    try:
        service = SkillTemplateService(session)
        templates = service.get_all_templates()

        # 统计各分类的模板数量
        categories = {}
        for t in templates:
            cat_id = t.category
            if cat_id not in categories:
                categories[cat_id] = {
                    "id": cat_id,
                    "name": t.category_name,
                    "count": 0,
                    "subcategories": {}
                }
            categories[cat_id]["count"] += 1

            # 统计子分类
            if t.subcategory:
                sub_id = t.subcategory
                if sub_id not in categories[cat_id]["subcategories"]:
                    categories[cat_id]["subcategories"][sub_id] = {
                        "id": sub_id,
                        "name": t.subcategory_name,
                        "count": 0
                    }
                categories[cat_id]["subcategories"][sub_id]["count"] += 1

        return {
            "status": "success",
            "data": list(categories.values())
        }

    except Exception as e:
        log.error(f"[Templates API] 获取分类列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


log.info("📚 SKILL Templates API 路由已加载")