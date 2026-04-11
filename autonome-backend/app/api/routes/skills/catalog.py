"""
技能目录 API

包含技能目录、分类、标签相关接口
"""

from typing import Dict
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.core.database import get_session
from app.core.logger import log
from app.core.skill_parser import get_combined_skills
from app.api.deps import get_current_user
from app.models.domain import User, SkillAsset, SkillStatus

router = APIRouter()


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
# GET /api/skills/categories - 获取技能分类
# ==========================================
@router.get("/categories")
def get_skill_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取所有技能分类"""
    # 系统预置分类
    categories = [
        {"id": "quality_control", "name": "质量控制", "icon": "🔬", "description": "数据质量评估与控制"},
        {"id": "alignment", "name": "序列比对", "icon": "🧬", "description": "序列比对与映射"},
        {"id": "quantification", "name": "定量分析", "icon": "📊", "description": "表达定量与计数"},
        {"id": "differential_analysis", "name": "差异分析", "icon": "📉", "description": "差异表达与统计分析"},
        {"id": "visualization", "name": "可视化", "icon": "📈", "description": "数据可视化与图表生成"},
        {"id": "pipeline", "name": "流程编排", "icon": "⚙️", "description": "多步骤分析流程"},
        {"id": "single_cell", "name": "单细胞分析", "icon": "🧫", "description": "单细胞数据分析"},
        {"id": "other", "name": "其他", "icon": "📦", "description": "其他类型技能"}
    ]

    # ✨ SQL 聚合查询替代 N+1 Python 循环
    # 一次性查询所有分类的技能数量
    category_counts = session.exec(
        select(SkillAsset.category, func.count(SkillAsset.id))
        .where(SkillAsset.status == SkillStatus.PUBLISHED)
        .group_by(SkillAsset.category)
    ).all()

    # 构建分类计数字典
    count_dict = {row[0]: row[1] for row in category_counts}

    # 更新每个分类的计数
    for cat in categories:
        cat["skill_count"] = count_dict.get(cat["id"], 0)

    return {"categories": categories}


# ==========================================
# GET /api/skills/tags - 获取技能标签
# ==========================================
@router.get("/tags")
def get_skill_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取所有技能标签"""
    # ✨ 使用 PostgreSQL 的 unnest 函数在 SQL 层面展开标签数组并统计
    # 这避免了加载所有技能到内存再用 Python 循环统计
    from sqlalchemy import text

    # 检查是否为 PostgreSQL
    if "postgresql" in session.bind.url.database:
        # 使用原生 SQL 利用 unnest + GROUP BY
        result = session.exec(text("""
            SELECT unnest.tags as tag, COUNT(*) as count
            FROM skill_assets,
                 LATERAL unnest(CASE WHEN tags IS NOT NULL THEN tags ELSE ARRAY[]::text[] END) AS unnest(tags)
            WHERE status = 'PUBLISHED'
            GROUP BY unnest.tags
            ORDER BY count DESC
        """)).all()

        tags = [
            {
                "id": row.tag.lower().replace(" ", "_"),
                "name": row.tag,
                "usage_count": row.count,
                "color": "#3B82F6"
            }
            for row in result
        ]
    else:
        # SQLite 或其他数据库，回退到 Python 循环（但仍优化为单次查询）
        skills = session.exec(
            select(SkillAsset.tags).where(SkillAsset.status == SkillStatus.PUBLISHED)
        ).all()

        tag_counts: Dict[str, int] = {}
        for tags in skills:
            if tags:
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        tags = [
            {
                "id": tag.lower().replace(" ", "_"),
                "name": tag,
                "usage_count": count,
                "color": "#3B82F6"
            }
            for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
        ]

    return {"tags": tags}