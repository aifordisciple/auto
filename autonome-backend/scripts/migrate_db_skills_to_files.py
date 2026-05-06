"""
一次性迁移脚本：将 SkillAsset 表中已有的用户技能导出为文件系统结构

执行时机：docker-compose 启动时，在 API 启动前执行
执行方式：python scripts/migrate_db_skills_to_files.py

流程：
1. 查询 SkillAsset 表中所有有 script_code 或 nextflow_code 的记录
2. 将 DB JSONB 还原为 draft 字典
3. 调用 SkillFileWriter 写入文件系统
4. 更新 SkillAsset 的 bundle_path, is_official, file_hash, indexed_at
5. 若文件已存在（幂等），跳过写入

环境变量：
- SKILL_MIGRATION_DONE: 标记迁移是否已完成（避免重复执行）
- SKILLS_DIR: 技能目录路径（默认 /app/app/skills）
"""

import os
import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select
from app.core.database import engine
from app.core.logger import log
from app.models.domain import SkillAsset, SkillStatus
from app.services.skill_bundle_writer import write_skill_from_forge_draft


SKILLS_DIR = os.environ.get("SKILLS_DIR", "/app/app/skills")


def _compute_file_hash(filepath: str) -> str:
    """计算文件 SHA256 哈希"""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return hashlib.sha256(f.read().encode("utf-8")).hexdigest()[:16]


def migrate_db_skills_to_files() -> int:
    """
    将 SkillAsset 表中的技能导出为文件系统结构

    Returns:
        迁移的技能数量
    """
    migrated_count = 0

    with Session(engine) as session:
        # 查询所有有内容的技能记录
        skills = session.exec(
            select(SkillAsset).where(
                SkillAsset.script_code.isnot(None) | SkillAsset.nextflow_code.isnot(None)
            )
        ).all()

        log.info(f"[Migration] 发现 {len(skills)} 个有内容的技能待迁移")

        for skill in skills:
            skill_id = skill.skill_id

            try:
                # 1. 检查是否已有 bundle_path（已迁移过）
                if skill.bundle_path and os.path.exists(skill.bundle_path):
                    log.info(f"[Migration] 跳过已迁移的技能: {skill_id}")
                    continue

                # 2. 从 DB 还原 draft
                draft = {
                    "name": skill.name or "未命名技能",
                    "description": skill.description or "",
                    "executor_type": skill.executor_type or "Python_env",
                    "script_code": skill.script_code or "",
                    "nextflow_code": skill.nextflow_code or "",
                    "parameters_schema": skill.parameters_schema or {"type": "object", "properties": {}, "required": []},
                    "expert_knowledge": skill.expert_knowledge or "",
                    "dependencies": skill.dependencies or [],
                    "category": skill.category or "custom",
                    "category_name": skill.category_name or "自定义",
                    "subcategory": skill.subcategory,
                    "subcategory_name": skill.subcategory_name,
                    "tags": skill.tags or [],
                }

                # 3. 写入文件系统
                result = write_skill_from_forge_draft(draft, skill_id, skills_dir=SKILLS_DIR)
                bundle_path = result.get("bundle_path", "")
                files_created = result.get("files_created", [])
                log.info(f"[Migration] 写入技能 {skill_id}: {files_created}")

                # 4. 更新 SkillAsset 索引字段
                skill.bundle_path = bundle_path
                skill.is_official = False
                skill.file_hash = _compute_file_hash(os.path.join(bundle_path, "SKILL.md"))
                skill.indexed_at = datetime.now(timezone.utc)

                # 5. 可选：清除冗余字段（兼容期内保留）
                # skill.script_code = None
                # skill.nextflow_code = None
                # skill.parameters_schema = None
                # skill.expert_knowledge = None

                session.add(skill)
                migrated_count += 1

            except Exception as e:
                log.error(f"[Migration] 迁移失败 {skill_id}: {e}", exc_info=True)
                continue

        # 批量提交
        session.commit()
        log.info(f"[Migration] 迁移完成: 共迁移 {migrated_count}/{len(skills)} 个技能")

    return migrated_count


def is_migration_done() -> bool:
    """检查迁移是否已完成"""
    return os.environ.get("SKILL_MIGRATION_DONE", "").lower() in ("true", "1", "yes")


def mark_migration_done() -> None:
    """标记迁移已完成"""
    print("SKILL_MIGRATION_DONE=true")


if __name__ == "__main__":
    if is_migration_done():
        log.info("[Migration] 迁移已标记完成，跳过")
        sys.exit(0)

    log.info("[Migration] 开始 DB→文件系统技能迁移...")
    count = migrate_db_skills_to_files()
    mark_migration_done()
    log.info(f"[Migration] ✅ 迁移完成，处理了 {count} 个技能")
