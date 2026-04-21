"""
商业级身份验证系统 - 数据结构双向兼容升级

Revision ID: iam_001
Revises: sys_skill_001
Create Date: 2026-04-21

阶段1：底层数据结构双向兼容

变更内容：
1. user 表：
   - phone → phone_number (重命名，添加 unique + index)
   - hashed_password 改为 nullable (支持纯验证码用户)
   - 新增 is_email_verified (bool, default False)
   - 新增 is_2fa_enabled (bool, default False)
   - 新增 two_factor_secret (str, nullable)
2. 新建 oauth_accounts 表 (第三方账号绑定) - 如已存在则跳过
3. 新建 active_sessions 表 (会话管理与多设备管控) - 如已存在则跳过
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================
# Alembic 版本标识
# ==========================================
revision: str = 'iam_001'
down_revision: Union[str, Sequence[str], None] = 'sys_skill_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：添加商业级 IAM 表结构"""

    # ==========================================
    # 步骤 1: 修改 user 表
    # ==========================================

    # 1a. 重命名 phone → phone_number（保留老数据）
    op.alter_column('user', 'phone', new_column_name='phone_number')

    # 1b. 为 phone_number 添加唯一约束和索引
    op.create_index('ix_user_phone_number', 'user', ['phone_number'], unique=True)

    # 1c. hashed_password 改为 nullable（支持纯验证码用户）
    op.alter_column('user', 'hashed_password',
                    existing_type=sa.String(),
                    nullable=True)

    # 1d. 新增安全相关字段
    op.add_column('user', sa.Column('is_email_verified', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('user', sa.Column('is_2fa_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('user', sa.Column('two_factor_secret', sa.String(255), nullable=True))

    # ==========================================
    # 步骤 2: 新建 oauth_accounts 表（如已存在则跳过）
    # ==========================================
    # 检查表是否已存在（SQLModel 自动创建可能已建表）
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'oauth_accounts' not in existing_tables:
        op.create_table(
            'oauth_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(20), nullable=False),
            sa.Column('provider_account_id', sa.String(255), nullable=False),
            sa.Column('access_token', sa.String(1024), nullable=True),
            sa.Column('refresh_token', sa.String(1024), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_oauth_accounts_user_id', 'oauth_accounts', ['user_id'])
        op.create_index('ix_oauth_accounts_provider_account_id', 'oauth_accounts', ['provider_account_id'])

    # ==========================================
    # 步骤 3: 新建 active_sessions 表（如已存在则跳过）
    # ==========================================
    if 'active_sessions' not in existing_tables:
        op.create_table(
            'active_sessions',
            sa.Column('session_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('refresh_token_hash', sa.String(64), nullable=False),
            sa.Column('user_agent', sa.String(512), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('device_type', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('last_active_at', sa.DateTime(), nullable=True),
            sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=True),
            sa.PrimaryKeyConstraint('session_id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_active_sessions_user_id', 'active_sessions', ['user_id'])


def downgrade() -> None:
    """降级：移除商业级 IAM 表结构"""

    # 删除 active_sessions 表
    op.drop_index('ix_active_sessions_user_id', table_name='active_sessions')
    op.drop_table('active_sessions')

    # 删除 oauth_accounts 表
    op.drop_index('ix_oauth_accounts_provider_account_id', table_name='oauth_accounts')
    op.drop_index('ix_oauth_accounts_user_id', table_name='oauth_accounts')
    op.drop_table('oauth_accounts')

    # 移除 user 表新增字段
    op.drop_column('user', 'two_factor_secret')
    op.drop_column('user', 'is_2fa_enabled')
    op.drop_column('user', 'is_email_verified')

    # 恢复 hashed_password 为 NOT NULL
    op.alter_column('user', 'hashed_password',
                    existing_type=sa.String(),
                    nullable=False)

    # 恢复 phone_number → phone
    op.drop_index('ix_user_phone_number', table_name='user')
    op.alter_column('user', 'phone_number', new_column_name='phone')
