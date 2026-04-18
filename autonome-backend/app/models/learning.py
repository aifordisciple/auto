"""
学习中心模型

包含文献、知识块、笔记、标签的基础模型、表模型、创建/更新/公开模型

设计要点：
- Literature: 文献元数据与解析状态
- LiteratureChunk: 段落级知识块，支持 pgvector 语义检索
- LiteratureNote: 用户笔记与标注
- LiteratureTag: 文献标签（M:N 关联）
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column, Index, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.uuid import generate_literature_id, generate_chunk_id, generate_note_id, generate_ltag_id
from app.models.enums import LiteratureStatus, ChunkType


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# LITERATURE 文献模型
# ==========================================
class LiteratureBase(SQLModel):
    """文献基础模型"""
    title: str = Field(max_length=512, description="文献标题")
    authors: Optional[str] = Field(default=None, max_length=2048, description="作者列表（逗号分隔）")
    year: Optional[int] = Field(default=None, description="发表年份")
    journal: Optional[str] = Field(default=None, max_length=255, description="期刊/会议名")
    doi: Optional[str] = Field(default=None, max_length=100, description="DOI 标识符")
    abstract: Optional[str] = Field(default=None, description="摘要")
    keywords: Optional[str] = Field(default=None, max_length=1024, description="关键词（逗号分隔）")
    file_path: Optional[str] = Field(default=None, max_length=512, description="原始 PDF 存储路径")
    file_hash: Optional[str] = Field(default=None, max_length=64, description="文件 SHA256，防重复上传")
    thumbnail_url: Optional[str] = Field(default=None, max_length=512, description="封面缩略图 URL")
    page_count: int = Field(default=0, description="页数")
    status: LiteratureStatus = Field(default=LiteratureStatus.UPLOADING, description="解析状态")
    parse_error: Optional[str] = Field(default=None, max_length=1024, description="解析失败原因")


class Literature(LiteratureBase, table=True):
    """文献数据库表"""
    __tablename__ = "literature"

    id: Optional[int] = Field(default=None, primary_key=True)
    literature_id: str = Field(default_factory=generate_literature_id, unique=True, index=True, max_length=100, description="全局唯一的文献ID")
    owner_id: int = Field(foreign_key="user.id", index=True, description="所属用户 ID")

    # M:N 标签关联（通过关联表实现，此处不定义字段）
    tags: List["LiteratureTag"] = Field(default_factory=list, sa_column=Column(JSONB))

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    __table_args__ = (
        # 按所有者+状态筛选（高频查询）
        Index('ix_literature_owner_status', 'owner_id', 'status'),
        # DOI 唯一索引（同一用户不可重复导入）
        Index('ix_literature_doi', 'doi'),
        # 文件哈希索引（去重检查）
        Index('ix_literature_file_hash', 'file_hash'),
    )


class LiteratureCreate(SQLModel):
    """创建文献的请求体"""
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None


class LiteratureUpdate(SQLModel):
    """更新文献的请求体"""
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    tags: Optional[List[str]] = None


class LiteraturePublic(LiteratureBase):
    """返回给前端的文献公共信息"""
    id: int
    literature_id: str
    owner_id: int
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ==========================================
# LITERATURE CHUNK 知识块模型
# ==========================================
class LiteratureChunkBase(SQLModel):
    """知识块基础模型"""
    chunk_index: int = Field(description="块序号")
    chunk_type: ChunkType = Field(default=ChunkType.TEXT, description="块类型")
    content: str = Field(sa_column=Column(Text), description="块文本内容")
    page_number: int = Field(default=0, description="所在页码")
    section_title: Optional[str] = Field(default=None, max_length=255, description="所属章节标题")
    figure_caption: Optional[str] = Field(default=None, sa_column=Column(Text), description="图表标题（仅 figure/table 类型）")
    metadata_: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB), description="扩展元数据")


class LiteratureChunk(LiteratureChunkBase, table=True):
    """知识块数据库表"""
    __tablename__ = "literature_chunk"

    id: Optional[int] = Field(default=None, primary_key=True)
    chunk_id: str = Field(default_factory=generate_chunk_id, unique=True, index=True, max_length=100, description="全局唯一的知识块ID")
    literature_id: int = Field(foreign_key="literature.id", index=True, description="所属文献 ID")

    # pgvector 向量字段（1536 维，与 text-embedding-3-large 对齐）
    # 注意：实际向量字段通过 Alembic 迁移添加，此处仅做声明
    # embedding 字段在 PostgreSQL 中通过 pgvector 扩展实现

    created_at: datetime = Field(default_factory=get_utc_now)

    __table_args__ = (
        # 按文献+类型筛选
        Index('ix_chunk_literature_type', 'literature_id', 'chunk_type'),
        # 按文献+序号排序
        Index('ix_chunk_literature_index', 'literature_id', 'chunk_index'),
    )


class LiteratureChunkCreate(LiteratureChunkBase):
    """创建知识块的请求体"""
    literature_id: int


class LiteratureChunkUpdate(SQLModel):
    """更新知识块的请求体（支持专家修正）"""
    content: Optional[str] = None
    figure_caption: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None


class LiteratureChunkPublic(LiteratureChunkBase):
    """返回给前端的知识块公共信息"""
    id: int
    chunk_id: str
    literature_id: int
    created_at: datetime


# ==========================================
# LITERATURE NOTE 笔记模型
# ==========================================
class LiteratureNoteBase(SQLModel):
    """笔记基础模型"""
    content: str = Field(sa_column=Column(Text), description="笔记内容")
    color: Optional[str] = Field(default=None, max_length=20, description="高亮颜色")


class LiteratureNote(LiteratureNoteBase, table=True):
    """笔记数据库表"""
    __tablename__ = "literature_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    note_id: str = Field(default_factory=generate_note_id, unique=True, index=True, max_length=100, description="全局唯一的笔记ID")
    literature_id: int = Field(foreign_key="literature.id", index=True, description="所属文献 ID")
    user_id: int = Field(foreign_key="user.id", index=True, description="所属用户 ID")
    chunk_id: Optional[int] = Field(default=None, foreign_key="literature_chunk.id", description="关联知识块 ID（可选）")

    created_at: datetime = Field(default_factory=get_utc_now)

    __table_args__ = (
        # 按文献+用户筛选
        Index('ix_note_literature_user', 'literature_id', 'user_id'),
    )


class LiteratureNoteCreate(LiteratureNoteBase):
    """创建笔记的请求体"""
    literature_id: int
    chunk_id: Optional[int] = None


class LiteratureNoteUpdate(SQLModel):
    """更新笔记的请求体"""
    content: Optional[str] = None
    color: Optional[str] = None


class LiteratureNotePublic(LiteratureNoteBase):
    """返回给前端的笔记公共信息"""
    id: int
    note_id: str
    literature_id: int
    user_id: int
    chunk_id: Optional[int] = None
    created_at: datetime


# ==========================================
# LITERATURE TAG 标签模型
# ==========================================
class LiteratureTagBase(SQLModel):
    """标签基础模型"""
    name: str = Field(max_length=100, description="标签名称")
    color: Optional[str] = Field(default=None, max_length=20, description="标签颜色")


class LiteratureTag(LiteratureTagBase, table=True):
    """标签数据库表"""
    __tablename__ = "literature_tag"

    id: Optional[int] = Field(default=None, primary_key=True)
    ltag_id: str = Field(default_factory=generate_ltag_id, unique=True, index=True, max_length=100, description="全局唯一的标签ID")
    user_id: int = Field(foreign_key="user.id", index=True, description="所属用户 ID")

    created_at: datetime = Field(default_factory=get_utc_now)

    __table_args__ = (
        # 同一用户下标签名唯一
        Index('ix_ltag_user_name', 'user_id', 'name'),
    )


class LiteratureTagCreate(LiteratureTagBase):
    """创建标签的请求体"""
    pass


class LiteratureTagUpdate(SQLModel):
    """更新标签的请求体"""
    name: Optional[str] = None
    color: Optional[str] = None


class LiteratureTagPublic(LiteratureTagBase):
    """返回给前端的标签公共信息"""
    id: int
    ltag_id: str
    user_id: int
    created_at: datetime
