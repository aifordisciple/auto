"""
OAuthAccount 添加第三方用户信息字段

Revision ID: iam_002
Revises: iam_001
Create Date: 2026-04-22

变更内容：
1. oauth_accounts 表新增 provider_name (str, nullable)
2. oauth_accounts 表新增 provider_avatar_url (str, nullable)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================
# Alembic 版本标识
# ==========================================
revision: str = 'iam_002'
down_revision: Union[str, Sequence[str], None] = 'iam_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：oauth_accounts 添加第三方用户信息字段"""

    # 检查字段是否已存在（幂等安全）
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'oauth_accounts' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('oauth_accounts')}

        if 'provider_name' not in existing_columns:
            op.add_column('oauth_accounts',
                          sa.Column('provider_name', sa.String(255), nullable=True))

        if 'provider_avatar_url' not in existing_columns:
            op.add_column('oauth_accounts',
                          sa.Column('provider_avatar_url', sa.String(512), nullable=True))


def downgrade() -> None:
    """降级：移除第三方用户信息字段"""

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'oauth_accounts' in inspector.get_table_names():
        existing_columns = {col['name'] for col in inspector.get_columns('oauth_accounts')}

        if 'provider_avatar_url' in existing_columns:
            op.drop_column('oauth_accounts', 'provider_avatar_url')

        if 'provider_name' in existing_columns:
            op.drop_column('oauth_accounts', 'provider_name')
