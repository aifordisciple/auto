"""
添加 Claude Agent 模式数据表

新增表:
- claude_session: Claude 会话 (对应 Project)
- claude_conversation: Claude 对话 (Session 下的对话轮次)
- claude_message: Claude 消息 (含完整事件流)
- claude_task: Claude 重型任务追踪
- claude_container: Claude 容器池管理
"""

from typing import Union, Sequence
from alembic import op
import sqlalchemy as sa


revision: str = 'claude_agent_001'
down_revision: Union[str, Sequence[str], None] = 'embedding_config_001'


def upgrade() -> None:
    # ==========================================
    # Claude 会话表
    # ==========================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_session (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id INTEGER NOT NULL REFERENCES "user"(id),
            title VARCHAR(500) NOT NULL DEFAULT '新会话',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            container_id VARCHAR(100),
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_session_user_id ON claude_session(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_session_status ON claude_session(status)
    """)

    # ==========================================
    # Claude 对话表
    # ==========================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_conversation (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES claude_session(id) ON DELETE CASCADE,
            title VARCHAR(500),
            claude_session_id VARCHAR(200),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_conversation_session ON claude_conversation(session_id)
    """)

    # ==========================================
    # Claude 消息表
    # ==========================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_message (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES claude_conversation(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT,
            events_json JSONB,
            plan_json JSONB,
            code_snapshot TEXT,
            task_ids UUID[] DEFAULT '{}',
            usage_json JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_message_conversation ON claude_message(conversation_id, created_at)
    """)

    # ==========================================
    # Claude 任务表
    # ==========================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_task (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID NOT NULL REFERENCES claude_message(id),
            session_id UUID NOT NULL REFERENCES claude_session(id),
            celery_task_id VARCHAR(200),
            skill_id VARCHAR(200),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            code TEXT,
            parameters JSONB,
            output_files JSONB DEFAULT '[]',
            error_text TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_task_session ON claude_task(session_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_task_celery ON claude_task(celery_task_id)
    """)

    # ==========================================
    # Claude 容器池表
    # ==========================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_container (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            container_id VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'idle',
            user_id INTEGER REFERENCES "user"(id),
            session_id UUID REFERENCES claude_session(id),
            last_used_at TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_container_status ON claude_container(status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claude_container CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_task CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_message CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_conversation CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_session CASCADE")
