"""
经验资产模型

包含经验资产模型及其创建/更新/公开模型。

pgvector 嵌入列 (embedding Vector(1536)) 通过 Alembic 迁移添加，
不在 SQLModel 定义中声明（遵循 LiteratureChunk 模式）。
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.uuid import generate_experience_id
from app.models.enums import ExperienceType


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)




# ==========================================
# 经验资产模型 (ExperienceAsset)
# ==========================================
class ExperienceAsset(SQLModel, table=True):
    """经验资产表 - 用户成功经验的沉淀"""
    __tablename__ = "experienceasset"

    id: Optional[int] = Field(default=None, primary_key=True)
    experience_id: str = Field(
        default_factory=generate_experience_id,
        unique=True, index=True, max_length=50,
        description="经验资产唯一标识"
    )

    # 来源追溯
    source_session_id: Optional[str] = Field(default=None, foreign_key="chatsession.id", index=True)
    source_user_id: int = Field(foreign_key="user.id", index=True)
    source_project_id: Optional[str] = Field(default=None, foreign_key="project.id")
    source_record_id: Optional[int] = Field(default=None, foreign_key="adhocanalysisrecord.id", description="关联的即席分析执行记录")

    # 经验内容
    experience_type: ExperienceType = Field(default=ExperienceType.SUCCESSFUL_SESSION)
    title: str = Field(max_length=255, description="经验标题")
    summary: str = Field(description="经验摘要（用户需求+解决方案）")
    key_insights: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="关键洞察列表")

    # 核心内容
    original_query: str = Field(description="用户原始问题")
    solution_code: Optional[str] = Field(default=None, description="核心解决方案代码")
    solution_strategy: Optional[str] = Field(default=None, description="解决策略描述")
    debug_iterations: int = Field(default=0, description="调试迭代次数")

    # 代码语言（用于检索时按语言过滤）
    language: Optional[str] = Field(default=None, max_length=10, description="代码语言: python / r")

    # 向量嵌入（TEXT 列，JSON 数组串，如 "[0.1, 0.2, ...]"）
    # text-embedding-3-large 1536 维向量，用于语义检索
    embedding_text: Optional[str] = Field(default=None, description="JSON 数组格式的嵌入向量文本")

    # 元数据
    category: str = Field(default="general", max_length=50, description="经验分类: qc/analysis/visualization/pipeline/general")
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="标签列表")

    # 质量评分
    usefulness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="有用性评分")
    reuse_count: int = Field(default=0, description="被复用次数")

    # 状态
    is_public: bool = Field(default=False, description="是否公开")
    is_verified: bool = Field(default=False, description="是否已验证")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class ExperienceAssetCreate(SQLModel):
    """创建经验资产的请求体"""
    title: str
    summary: str
    key_insights: List[str] = []
    original_query: str
    solution_code: Optional[str] = None
    solution_strategy: Optional[str] = None
    category: str = "general"
    tags: List[str] = []
    language: Optional[str] = None
    debug_iterations: int = 0
    source_session_id: Optional[str] = None
    source_project_id: Optional[str] = None
    source_record_id: Optional[int] = None
    is_public: bool = False


class ExperienceAssetUpdate(SQLModel):
    """更新经验资产的请求体"""
    title: Optional[str] = None
    summary: Optional[str] = None
    key_insights: Optional[List[str]] = None
    solution_code: Optional[str] = None
    solution_strategy: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class ExperienceAssetPublic(SQLModel):
    """返回给前端的经验资产公共信息"""
    id: int
    experience_id: str
    title: str
    summary: str
    key_insights: List[str]
    original_query: str
    solution_code: Optional[str]
    solution_strategy: Optional[str]
    category: str
    tags: List[str]
    language: Optional[str] = None
    debug_iterations: int = 0
    usefulness_score: float
    reuse_count: int
    is_public: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime