"""
添加系统级学习技能表 (systemskill)

Revision ID: sys_skill_001
Revises: None
Create Date: 2026-04-07

系统学习层核心表结构：
- 用于存储从用户成功对话中自动提取的方法论和策略
- 隐身运行，用户不可见
- 支持语义向量检索（pgvector）

表结构：
- 基本信息：method_type, name, description
- 可执行内容：instructions (Markdown)
- 检索字段：triggers, tags, examples (JSONB)
- 版本管理：version
- 演进追踪：source_sessions, confidence_score, last_updated
- 统计信息：injection_count, success_rate
- 状态：status (active/deprecated)
- 向量嵌入：combined_embedding (pgvector Vector(1536))
- 元数据：extra_metadata (JSONB)

索引策略：
- skill_id: 主查询键（唯一索引）
- method_type: 分类查询
- status: 状态筛选
- combined_embedding: 向量索引（IVFFlat, cosine ops）

隐私设计：
- 无 owner_id 字段（系统级资产）
- source_sessions 仅存储会话 ID
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# ==========================================
# pgvector 扩展导入
# ==========================================
# 注意：pgvector 需要先在数据库中安装扩展
# 执行: CREATE EXTENSION IF NOT EXISTS vector;
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # 如果 pgvector 未安装，提供一个 dummy Vector 类型用于迁移脚本生成
    class Vector:
        """Dummy Vector 类型，用于迁移脚本"""
        def __init__(self, dimension=None):
            self.dimension = dimension

        def __repr__(self):
            if self.dimension:
                return f"Vector({self.dimension})"
            return "Vector()"


# ==========================================
# Alembic 版本标识
# ==========================================
revision: str = 'sys_skill_001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================
# 升级操作：添加索引和向量索引
# ==========================================
def upgrade() -> None:
    """
    升级数据库架构

    注意：SQLModel 已自动创建 systemskill 表（单数形式）
    此迁移主要添加额外索引和向量索引以优化查询性能

    操作步骤：
    1. 确保 pgvector 扩展已安装
    2. 创建分类和状态索引
    3. 创建向量索引（IVFFlat, cosine ops）
    """

    # ==========================================
    # 步骤 1: 确保 pgvector 扩展已安装
    # ==========================================
    # pgvector 是 PostgreSQL 的向量扩展，用于存储和检索向量嵌入
    # 如果扩展未安装，需要先安装（通常由 DBA 或初始化脚本执行）
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # ==========================================
    # 步骤 2: 创建分类和状态索引
    # ==========================================
    # method_type 索引：用于按方法类型分类查询
    op.create_index(
        'ix_systemskill_method_type',
        'systemskill',
        ['method_type'],
        unique=False
    )

    # status 索引：用于状态筛选（active/deprecated）
    op.create_index(
        'ix_systemskill_status',
        'systemskill',
        ['status'],
        unique=False
    )

    # name 索引：用于名称搜索
    op.create_index(
        'ix_systemskill_name',
        'systemskill',
        ['name'],
        unique=False
    )

    # confidence_score 索引：用于高置信度方法筛选
    op.create_index(
        'ix_systemskill_confidence_score',
        'systemskill',
        ['confidence_score'],
        unique=False
    )

    # ==========================================
    # 步骤 3: 创建向量索引
    # ==========================================
    # pgvector 向量索引支持两种类型：
    # 1. IVFFlat: 适合中等规模数据（<100万向量），构建快，查询快
    # 2. HNSW: 适合大规模数据，查询更快，构建慢
    #
    # 对于系统级技能（预计 <1000 条），使用 IVFFlat 即可
    #
    # 参数说明：
    # - lists: 聚类中心数量，通常设置为 rows/1000
    #   对于预期 <1000 行，设置为 10 即可
    # - cosine: 余弦相似度，适合语义向量检索
    #
    # 注意：向量索引需要在有一定数量数据后才能高效创建
    # 建议在首次插入数据后执行：REINDEX INDEX ix_systemskill_embedding

    # 创建向量索引（使用 cosine ops，适合语义相似度）
    # 注意：IVFFlat 索引需要表中有足够数据才能高效工作
    # 这里先创建索引结构，后续可使用 REINDEX 优化
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_systemskill_embedding
        ON systemskill
        USING ivfflat (combined_embedding vector_cosine_ops)
        WITH (lists = 10)
    """)


# ==========================================
# 降级操作：删除索引
# ==========================================
def downgrade() -> None:
    """
    降级数据库架构

    注意：此迁移仅删除索引，不删除表本身
    表由 SQLModel 自动管理，不建议通过迁移删除

    操作步骤：
    1. 删除向量索引
    2. 删除基础索引
    """

    # ==========================================
    # 步骤 1: 删除向量索引
    # ==========================================
    op.execute("DROP INDEX IF EXISTS ix_systemskill_embedding")

    # ==========================================
    # 步骤 2: 删除基础索引
    # ==========================================
    op.drop_index('ix_systemskill_confidence_score', table_name='systemskill')
    op.drop_index('ix_systemskill_name', table_name='systemskill')
    op.drop_index('ix_systemskill_status', table_name='systemskill')
    op.drop_index('ix_systemskill_method_type', table_name='systemskill')