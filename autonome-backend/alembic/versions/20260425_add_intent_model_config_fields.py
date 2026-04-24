"""
意图识别模型独立配置字段迁移

Revision ID: intent_001
Revises: iam_003
Create Date: 2026-04-25

变更内容：
1. user 表新增 intent_api_key、intent_base_url、intent_model_name 三个字段
2. systemconfig 表新增 intent_api_key、intent_base_url、intent_model 三个字段
3. 意图识别模型未配置时回退到主模型配置，保持向后兼容
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "intent_001"
down_revision: Union[str, None] = "iam_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加意图识别模型配置字段"""

    # ==========================================
    # user 表：新增意图识别模型配置字段
    # ==========================================
    op.add_column("user", sa.Column("intent_api_key", sa.String(length=500), nullable=True))
    op.add_column("user", sa.Column("intent_base_url", sa.String(length=500), nullable=True))
    op.add_column("user", sa.Column("intent_model_name", sa.String(length=100), nullable=True))

    # ==========================================
    # systemconfig 表：新增意图识别模型配置字段
    # ==========================================
    op.add_column("systemconfig", sa.Column("intent_api_key", sa.String(), nullable=True))
    op.add_column("systemconfig", sa.Column("intent_base_url", sa.String(), nullable=True))
    op.add_column("systemconfig", sa.Column("intent_model", sa.String(), nullable=True))

    # 设置 intent_model 默认值为 'gpt-4o-mini'
    op.execute("UPDATE systemconfig SET intent_model = 'gpt-4o-mini' WHERE intent_model IS NULL")


def downgrade() -> None:
    """移除意图识别模型配置字段"""

    # systemconfig 表
    op.drop_column("systemconfig", "intent_model")
    op.drop_column("systemconfig", "intent_base_url")
    op.drop_column("systemconfig", "intent_api_key")

    # user 表
    op.drop_column("user", "intent_model_name")
    op.drop_column("user", "intent_base_url")
    op.drop_column("user", "intent_api_key")
