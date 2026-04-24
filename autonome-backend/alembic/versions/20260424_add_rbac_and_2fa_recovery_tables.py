"""
RBAC 角色权限 + 2FA 恢复码表迁移

Revision ID: iam_003
Revises: proj_001
Create Date: 2026-04-24

阶段2：RBAC 迁移缺失修复 + 2FA 恢复码数据库存储

变更内容：
1. 新建 roles 表 — 角色定义（admin / researcher / viewer 等）
2. 新建 permissions 表 — 细粒度权限码（如 project:read, skill:execute）
3. 新建 role_permissions 表 — 角色-权限多对多关联
4. 新建 user_roles 表 — 用户-角色多对多关联
5. 新建 audit_logs 表 — 审计日志，记录敏感操作
6. 新建 two_factor_recovery_codes 表 — 2FA 恢复码数据库存储
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================
# Alembic 版本标识
# ==========================================
revision: str = 'iam_003'
down_revision: Union[str, Sequence[str], None] = 'proj_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建 RBAC 及 2FA 恢复码表"""

    # 获取当前数据库连接，用于检查表是否已存在（幂等安全）
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # ==========================================
    # 步骤 1: 新建 roles 表（如已存在则跳过）
    # ==========================================
    if 'roles' not in existing_tables:
        op.create_table(
            'roles',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(50), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('is_default', sa.Boolean(), server_default='false', nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )
        op.create_index('ix_roles_name', 'roles', ['name'])

    # ==========================================
    # 步骤 2: 新建 permissions 表（如已存在则跳过）
    # ==========================================
    if 'permissions' not in existing_tables:
        op.create_table(
            'permissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(100), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('module', sa.String(50), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code'),
        )
        op.create_index('ix_permissions_code', 'permissions', ['code'])
        op.create_index('ix_permissions_module', 'permissions', ['module'])

    # ==========================================
    # 步骤 3: 新建 role_permissions 关联表（如已存在则跳过）
    # 角色-权限多对多关联，CASCADE 删除保证数据一致性
    # ==========================================
    if 'role_permissions' not in existing_tables:
        op.create_table(
            'role_permissions',
            sa.Column('role_id', sa.Integer(), nullable=False),
            sa.Column('permission_id', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('role_id', 'permission_id'),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        )

    # ==========================================
    # 步骤 4: 新建 user_roles 关联表（如已存在则跳过）
    # 用户-角色多对多关联（主角色通过 User.role_id，此表存储额外角色）
    # ==========================================
    if 'user_roles' not in existing_tables:
        op.create_table(
            'user_roles',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('role_id', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('user_id', 'role_id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        )

    # ==========================================
    # 步骤 5: 新建 audit_logs 表（如已存在则跳过）
    # 审计日志，记录所有敏感操作，支持按用户+操作、按时间查询
    # ==========================================
    if 'audit_logs' not in existing_tables:
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('action', sa.String(100), nullable=False),
            sa.Column('resource_type', sa.String(50), nullable=True),
            sa.Column('resource_id', sa.String(100), nullable=True),
            sa.Column('detail', sa.Text(), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        )
        op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
        # 复合索引：按用户+操作快速查询
        op.create_index('ix_audit_logs_user_action', 'audit_logs', ['user_id', 'action'])
        # 时间索引：按创建时间排序和筛选
        op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # ==========================================
    # 步骤 6: 新建 two_factor_recovery_codes 表（如已存在则跳过）
    # 2FA 恢复码数据库存储，替代文件存储方案
    # ==========================================
    if 'two_factor_recovery_codes' not in existing_tables:
        op.create_table(
            'two_factor_recovery_codes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('code_hash', sa.String(255), nullable=False),
            sa.Column('is_used', sa.Boolean(), server_default='false', nullable=True),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_two_factor_recovery_codes_user_id', 'two_factor_recovery_codes', ['user_id'])


def downgrade() -> None:
    """降级：按反向依赖顺序删除 RBAC 及 2FA 恢复码表"""

    # 先删除依赖 roles 和 user 的关联表，再删除主表
    # 删除顺序：被依赖的表后删，依赖别人的表先删

    # 1. 删除 two_factor_recovery_codes 表（依赖 user）
    op.drop_index('ix_two_factor_recovery_codes_user_id', table_name='two_factor_recovery_codes')
    op.drop_table('two_factor_recovery_codes')

    # 2. 删除 audit_logs 表（依赖 user）
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')

    # 3. 删除 user_roles 关联表（依赖 user + roles）
    op.drop_table('user_roles')

    # 4. 删除 role_permissions 关联表（依赖 roles + permissions）
    op.drop_table('role_permissions')

    # 5. 删除 permissions 表
    op.drop_index('ix_permissions_module', table_name='permissions')
    op.drop_index('ix_permissions_code', table_name='permissions')
    op.drop_table('permissions')

    # 6. 删除 roles 表
    op.drop_index('ix_roles_name', table_name='roles')
    op.drop_table('roles')
