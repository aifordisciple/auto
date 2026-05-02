"""
claude_task 表 message_id 和 session_id 改为 nullable

ClaudeTask 模型中这两个字段已是 Optional，但 claude_agent_001 迁移中错误设为 NOT NULL。
Agent Service 调用 POST /tasks/submit 时不传 message_id，导致 DB 约束错误。
"""

from typing import Union, Sequence
from alembic import op

revision: str = 'claude_task_nullable'
down_revision: Union[str, Sequence[str], None] = 'claude_agent_001'


def upgrade() -> None:
    op.execute("ALTER TABLE claude_task ALTER COLUMN message_id DROP NOT NULL")
    op.execute("ALTER TABLE claude_task ALTER COLUMN session_id DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE claude_task ALTER COLUMN message_id SET NOT NULL")
    op.execute("ALTER TABLE claude_task ALTER COLUMN session_id SET NOT NULL")
