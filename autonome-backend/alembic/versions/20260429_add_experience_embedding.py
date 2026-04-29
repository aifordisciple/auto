"""
为 ExperienceAsset 添加经验记忆字段

Revision ID: exp_embedding_001
Revises: add_tool_calls_001
Create Date: 2026-04-29

变更内容：
1. 添加 embedding_text 列 (TEXT, JSON 数组串，存 text-embedding-3-large 1536 维向量)
2. 添加 source_record_id 列 (关联 adhocanalysisrecord)
3. 添加 language 列 (python / r)
4. 创建分类 + 语言索引

设计说明：
- 不依赖 pgvector 扩展（Docker PostgreSQL:15-alpine 未安装 pgvector）
- 嵌入向量以 JSON 文本串存储（如 "[0.1, 0.2, ...]"）
- 检索时在 Python 侧计算余弦相似度（numpy），适用于百/千级经验规模
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'exp_embedding_001'
down_revision: Union[str, Sequence[str], None] = 'add_tool_calls_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加经验记忆字段"""

    # 1. 添加 embedding_text 列（JSON 文本，1536 维 float 数组）
    op.execute("""
        ALTER TABLE experienceasset
        ADD COLUMN IF NOT EXISTS embedding_text TEXT
    """)

    # 2. 添加 source_record_id 列（关联即席分析执行记录）
    op.execute("""
        ALTER TABLE experienceasset
        ADD COLUMN IF NOT EXISTS source_record_id INTEGER
    """)

    # 3. 添加 language 列
    op.execute("""
        ALTER TABLE experienceasset
        ADD COLUMN IF NOT EXISTS language VARCHAR(10)
    """)

    # 4. 创建索引
    op.create_index(
        'ix_experience_source_record',
        'experienceasset',
        ['source_record_id'],
        unique=False
    )
    op.create_index(
        'ix_experience_language',
        'experienceasset',
        ['language'],
        unique=False
    )
    op.create_index(
        'ix_experience_category',
        'experienceasset',
        ['category'],
        unique=False
    )


def downgrade() -> None:
    """回退迁移"""

    op.drop_index('ix_experience_category', table_name='experienceasset')
    op.drop_index('ix_experience_language', table_name='experienceasset')
    op.drop_index('ix_experience_source_record', table_name='experienceasset')

    op.execute("ALTER TABLE experienceasset DROP COLUMN IF EXISTS embedding_text")
    op.execute("ALTER TABLE experienceasset DROP COLUMN IF EXISTS source_record_id")
    op.execute("ALTER TABLE experienceasset DROP COLUMN IF EXISTS language")
