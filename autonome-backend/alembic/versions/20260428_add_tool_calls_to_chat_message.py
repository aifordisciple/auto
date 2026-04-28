"""
添加 tool_calls JSONB 字段到 ChatMessage 模型

Revision ID: add_tool_calls_001
Revises: rename_thinking_fast
Create Date: 2026-04-28

变更内容：
1. chatmessage 表新增 tool_calls 列（JSONB），存储工具调用信息
   格式: [{"id": "call_xxx", "name": "render_adhoc_card", "args": {...}}]
   用于页面刷新后重建 Active Probing 工具调用（如即席分析策略卡片）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_tool_calls_001'
down_revision: Union[str, Sequence[str], None] = 'rename_thinking_fast'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chatmessage', sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('chatmessage', 'tool_calls')
