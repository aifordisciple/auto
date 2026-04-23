"""
Project 添加项目编号字段

Revision ID: proj_001
Revises: iam_002
Create Date: 2026-04-23

变更内容：
1. project 表新增 project_code (str, nullable, max_length=50)
   - 项目编号字段，可选，用于用户自定义项目标识
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================
# Alembic 版本标识
# ==========================================
revision: str = 'proj_001'
down_revision: Union[str, Sequence[str], None] = 'iam_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：project 表添加 project_code 字段"""

    # 检查字段是否已存在（幂等安全）
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'project' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('project')}

        if 'project_code' not in existing_columns:
            op.add_column('project',
                          sa.Column('project_code', sa.String(50), nullable=True,
                                    comment='项目编号（可选）'))


def downgrade() -> None:
    """降级：移除 project_code 字段"""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'project' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('project')}

        if 'project_code' in existing_columns:
            op.drop_column('project', 'project_code')
