"""
新增 SkillAsset 文件系统索引字段

在 skill_asset 表新增:
- bundle_path: 技能文件夹路径
- is_official: 是否为官方预置技能
- file_hash: SKILL.md SHA256 哈希(前16位)，用于变更检测
- indexed_at: 最后索引时间

设计意图：技能统一化升级，DB 降级为索引，文件系统作为唯一真相源。
SkillIndexer 负责从文件系统同步元数据到 DB，通过 file_hash 对比实现增量更新。
"""

from typing import Union, Sequence
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'skill_file_index_001'
down_revision: Union[str, Sequence[str], None] = 'claude_task_nullable'


def upgrade() -> None:
    # ==========================================
    # skill_asset 表：新增文件系统索引字段
    # ==========================================
    op.execute("""
        ALTER TABLE skill_asset
        ADD COLUMN IF NOT EXISTS bundle_path VARCHAR(500)
    """)
    op.execute("""
        ALTER TABLE skill_asset
        ADD COLUMN IF NOT EXISTS is_official BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE skill_asset
        ADD COLUMN IF NOT EXISTS file_hash VARCHAR(32)
    """)
    op.execute("""
        ALTER TABLE skill_asset
        ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMP WITH TIME ZONE
    """)

    # ==========================================
    # 为已有的官方技能记录设置 is_official = true
    # ==========================================
    op.execute("""
        UPDATE skill_asset
        SET is_official = true
        WHERE bundle_path LIKE '%/skills/%'
           OR skill_id LIKE 'meta_%'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE skill_asset DROP COLUMN IF EXISTS indexed_at")
    op.execute("ALTER TABLE skill_asset DROP COLUMN IF EXISTS file_hash")
    op.execute("ALTER TABLE skill_asset DROP COLUMN IF EXISTS is_official")
    op.execute("ALTER TABLE skill_asset DROP COLUMN IF EXISTS bundle_path")
