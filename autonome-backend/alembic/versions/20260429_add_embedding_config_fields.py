"""
添加独立的 Embedding 模型配置字段

在 systemconfig 表新增:
- embedding_api_base: 嵌入模型 API 端点
- embedding_model: 嵌入模型名称
- embedding_api_key: 嵌入模型 API Key
- embedding_dimension: 向量维度

在 user 表新增:
- embedding_api_key: 用户自定义嵌入 API Key
- embedding_base_url: 用户自定义嵌入 Base URL
- embedding_model_name: 用户自定义嵌入模型名称

设计意图：原有嵌入生成逻辑回退到 thinking_api_key 或环境变量 OPENAI_API_KEY，
但这样无法为嵌入模型单独配置（如使用不同的 API 端点或本地 Embedding 服务）。
新增独立字段后，三级回退链为：
  用户 embedding_* → 系统 embedding_* → 环境变量 OPENAI_API_KEY
"""

from typing import Union, Sequence
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'embedding_config_001'
down_revision: Union[str, Sequence[str], None] = 'exp_embedding_001'


def upgrade() -> None:
    # ==========================================
    # systemconfig 表：新增 Embedding 模型配置字段
    # ==========================================
    op.execute("""
        ALTER TABLE systemconfig
        ADD COLUMN IF NOT EXISTS embedding_api_base TEXT
    """)
    op.execute("""
        ALTER TABLE systemconfig
        ADD COLUMN IF NOT EXISTS embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-large'
    """)
    op.execute("""
        ALTER TABLE systemconfig
        ADD COLUMN IF NOT EXISTS embedding_api_key TEXT
    """)
    op.execute("""
        ALTER TABLE systemconfig
        ADD COLUMN IF NOT EXISTS embedding_dimension INTEGER NOT NULL DEFAULT 3072
    """)

    # ==========================================
    # user 表：新增 per-user Embedding 模型配置字段
    # （允许用户覆盖系统全局 Embedding 配置）
    # ==========================================
    op.execute("""
        ALTER TABLE "user"
        ADD COLUMN IF NOT EXISTS embedding_api_key VARCHAR(500)
    """)
    op.execute("""
        ALTER TABLE "user"
        ADD COLUMN IF NOT EXISTS embedding_base_url VARCHAR(500)
    """)
    op.execute("""
        ALTER TABLE "user"
        ADD COLUMN IF NOT EXISTS embedding_model_name VARCHAR(100)
    """)


def downgrade() -> None:
    # systemconfig 表回滚
    op.execute("ALTER TABLE systemconfig DROP COLUMN IF EXISTS embedding_dimension")
    op.execute("ALTER TABLE systemconfig DROP COLUMN IF EXISTS embedding_api_key")
    op.execute("ALTER TABLE systemconfig DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE systemconfig DROP COLUMN IF EXISTS embedding_api_base")

    # user 表回滚
    op.execute("ALTER TABLE \"user\" DROP COLUMN IF EXISTS embedding_model_name")
    op.execute("ALTER TABLE \"user\" DROP COLUMN IF EXISTS embedding_base_url")
    op.execute("ALTER TABLE \"user\" DROP COLUMN IF EXISTS embedding_api_key")
