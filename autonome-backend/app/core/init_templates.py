"""
技能模板初始化脚本 - 将预置模板写入数据库

运行方式：
    python -m app.core.init_templates
"""

from sqlmodel import Session, select
from app.core.database import engine
from app.models.skill_template import SkillTemplate, TemplateType
from app.services.skill_templates import BUILTIN_TEMPLATES
from app.core.logger import log


def init_templates():
    """初始化技能模板到数据库"""
    with Session(engine) as session:
        created_count = 0
        skipped_count = 0

        for template_data in BUILTIN_TEMPLATES:
            # 检查是否已存在
            existing = session.exec(
                select(SkillTemplate).where(
                    SkillTemplate.template_id == template_data["template_id"]
                )
            ).first()

            if existing:
                skipped_count += 1
                continue

            # 创建新模板
            template = SkillTemplate(
                name=template_data["name"],
                template_id=template_data["template_id"],
                description=template_data.get("description"),
                template_type=template_data.get("template_type", TemplateType.PYTHON_ENV),
                script_template=template_data.get("script_template"),
                parameters_schema=template_data.get("parameters_schema", {}),
                expert_knowledge=template_data.get("expert_knowledge"),
                category=template_data.get("category", "general"),
                category_name=template_data.get("category_name", "通用"),
                subcategory=template_data.get("subcategory"),
                subcategory_name=template_data.get("subcategory_name"),
                tags=template_data.get("tags", []),
                source_skill_id=template_data.get("source_skill_id"),
                is_official=template_data.get("is_official", True),
                usage_count=0
            )

            session.add(template)
            created_count += 1
            log.info(f"✅ 创建模板: {template.name}")

        session.commit()

        log.info(f"📦 模板初始化完成: 新建 {created_count} 个, 跳过 {skipped_count} 个已存在")
        return created_count


if __name__ == "__main__":
    log.info("🚀 开始初始化技能模板...")
    init_templates()