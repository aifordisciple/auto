"""
AI 模型配置字段重命名：thinking/fast 语义化

Revision ID: rename_thinking_fast
Revises: intent_001
Create Date: 2026-04-25

变更内容：
1. user 表字段重命名：
   - llm_api_key    → thinking_api_key
   - llm_base_url   → thinking_base_url
   - llm_model_name → thinking_model_name
   - intent_api_key   → fast_api_key
   - intent_base_url  → fast_base_url
   - intent_model_name → fast_model_name

2. systemconfig 表字段重命名：
   - openai_api_key  → thinking_api_key
   - openai_base_url → thinking_base_url
   - default_model   → thinking_model
   - intent_api_key  → fast_api_key
   - intent_base_url → fast_base_url
   - intent_model    → fast_model

设计说明：
- "thinking" 对应主/深度推理模型（原 llm/openai 前缀）
- "fast" 对应轻量/快速模型（原 intent 前缀）
- 纯列重命名，不改变数据类型和约束，数据零丢失
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rename_thinking_fast"
down_revision: Union[str, None] = "intent_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """将 AI 模型配置字段重命名为 thinking/fast 语义"""

    # ==========================================
    # user 表：重命名字段
    # ==========================================
    # 主模型（原 llm 前缀）→ thinking
    op.alter_column("user", "llm_api_key", new_column_name="thinking_api_key")
    op.alter_column("user", "llm_base_url", new_column_name="thinking_base_url")
    op.alter_column("user", "llm_model_name", new_column_name="thinking_model_name")
    # 意图识别模型（原 intent 前缀）→ fast
    op.alter_column("user", "intent_api_key", new_column_name="fast_api_key")
    op.alter_column("user", "intent_base_url", new_column_name="fast_base_url")
    op.alter_column("user", "intent_model_name", new_column_name="fast_model_name")

    # ==========================================
    # systemconfig 表：重命名字段
    # ==========================================
    # 主模型（原 openai 前缀 / default_model）→ thinking
    op.alter_column("systemconfig", "openai_api_key", new_column_name="thinking_api_key")
    op.alter_column("systemconfig", "openai_base_url", new_column_name="thinking_base_url")
    op.alter_column("systemconfig", "default_model", new_column_name="thinking_model")
    # 意图识别模型（原 intent 前缀）→ fast
    op.alter_column("systemconfig", "intent_api_key", new_column_name="fast_api_key")
    op.alter_column("systemconfig", "intent_base_url", new_column_name="fast_base_url")
    op.alter_column("systemconfig", "intent_model", new_column_name="fast_model")


def downgrade() -> None:
    """回退：将 thinking/fast 字段名恢复为原始名称"""

    # ==========================================
    # systemconfig 表：恢复原始字段名
    # ==========================================
    # fast → intent
    op.alter_column("systemconfig", "fast_model", new_column_name="intent_model")
    op.alter_column("systemconfig", "fast_base_url", new_column_name="intent_base_url")
    op.alter_column("systemconfig", "fast_api_key", new_column_name="intent_api_key")
    # thinking → openai / default_model
    op.alter_column("systemconfig", "thinking_model", new_column_name="default_model")
    op.alter_column("systemconfig", "thinking_base_url", new_column_name="openai_base_url")
    op.alter_column("systemconfig", "thinking_api_key", new_column_name="openai_api_key")

    # ==========================================
    # user 表：恢复原始字段名
    # ==========================================
    # fast → intent
    op.alter_column("user", "fast_model_name", new_column_name="intent_model_name")
    op.alter_column("user", "fast_base_url", new_column_name="intent_base_url")
    op.alter_column("user", "fast_api_key", new_column_name="intent_api_key")
    # thinking → llm
    op.alter_column("user", "thinking_model_name", new_column_name="llm_model_name")
    op.alter_column("user", "thinking_base_url", new_column_name="llm_base_url")
    op.alter_column("user", "thinking_api_key", new_column_name="llm_api_key")
