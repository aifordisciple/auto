"""
分析数据库模型

包含分析数据库模型及其创建/更新/公开模型
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.enums import DatabaseType


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 分析数据库模型 (AnalysisDatabase)
# ==========================================
# 设计理念：
# - 管理 GO/KEGG、蛋白质、信号通路等分析数据库
# - 支持多种数据库类型分类
# - 统计使用频率，支持热度排序
# - 权限控制：公开/团队/私有
# ==========================================

class AnalysisDatabase(SQLModel, table=True):
    """
    分析数据库表 - 管理 GO/KEGG、蛋白质等数据库

    核心设计理念：
    - 统一管理生信分析所需的各类数据库资源
    - 支持多种数据库类型分类，便于检索和管理
    - 记录使用频率，支持热度排序和推荐
    - 多租户权限控制，支持公开/团队/私有级别

    数据流：
    1. 管理员创建公开数据库（所有用户可见）
    2. 普通用户创建私有数据库（仅自己可见）
    3. SKILL 执行时通过 db_id 引用数据库
    """
    __tablename__ = "analysisdatabase"

    # ==========================================
    # 基础标识
    # ==========================================
    id: Optional[int] = Field(default=None, primary_key=True)
    db_id: str = Field(unique=True, index=True, max_length=100, description="数据库唯一标识，如 go_basic, kegg_hsa")
    name: str = Field(max_length=255, description="数据库显示名称")
    description: Optional[str] = Field(default=None, description="数据库描述（支持 Markdown 格式）")

    # ==========================================
    # 分类信息
    # ==========================================
    db_type: str = Field(max_length=50, index=True, description="数据库类型: annotation/pathway/protein/variant/regulation/metabolism/custom")
    species: Optional[str] = Field(default=None, max_length=100, description="适用物种，如 human, mouse, all")
    version: Optional[str] = Field(default=None, max_length=50, description="数据库版本号")

    # ==========================================
    # 存储信息
    # ==========================================
    path: str = Field(max_length=500, description="数据库文件或目录路径")
    file_format: Optional[str] = Field(default=None, max_length=50, description="文件格式，如 tsv, json, rds")
    size_bytes: Optional[int] = Field(default=None, description="数据库大小（字节）")

    # ==========================================
    # 状态与统计
    # ==========================================
    is_active: bool = Field(default=True, description="是否启用")
    is_public: bool = Field(default=True, description="是否公开（兼容旧字段）")
    usage_count: int = Field(default=0, description="使用次数")
    last_used_at: Optional[datetime] = Field(default=None, description="最后使用时间")

    # ==========================================
    # 元数据
    # ==========================================
    source_url: Optional[str] = Field(default=None, max_length=500, description="数据来源 URL")
    license: Optional[str] = Field(default=None, max_length=100, description="许可证类型")
    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="标签列表，便于检索"
    )

    # ==========================================
    # 自定义字段支持
    # ==========================================
    custom_fields: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="自定义扩展字段"
    )

    # ==========================================
    # 权限与共享
    # ==========================================
    owner_id: int = Field(foreign_key="user.id", index=True, description="所有者用户 ID")
    visibility: str = Field(default="public", max_length=20, description="可见性: public/team/private")
    shared_with: List[int] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="共享给的用户 ID 列表"
    )

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class AnalysisDatabaseCreate(SQLModel):
    """创建分析数据库的请求体"""
    db_id: str = Field(max_length=100, description="数据库唯一标识")
    name: str = Field(max_length=255, description="数据库显示名称")
    description: Optional[str] = None
    db_type: str = Field(max_length=50, description="数据库类型")
    species: Optional[str] = None
    version: Optional[str] = None
    path: str = Field(max_length=500, description="数据库文件或目录路径")
    file_format: Optional[str] = None
    size_bytes: Optional[int] = None
    is_active: bool = True
    source_url: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    visibility: str = "private"


class AnalysisDatabaseUpdate(SQLModel):
    """更新分析数据库的请求体"""
    name: Optional[str] = None
    description: Optional[str] = None
    db_type: Optional[str] = None
    species: Optional[str] = None
    version: Optional[str] = None
    path: Optional[str] = None
    file_format: Optional[str] = None
    size_bytes: Optional[int] = None
    is_active: Optional[bool] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    visibility: Optional[str] = None
    shared_with: Optional[List[int]] = None


class AnalysisDatabasePublic(SQLModel):
    """返回给前端的分析数据库公共信息"""
    id: int
    db_id: str
    name: str
    description: Optional[str]
    db_type: str
    species: Optional[str]
    version: Optional[str]
    path: str
    file_format: Optional[str]
    size_bytes: Optional[int]
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    source_url: Optional[str]
    license: Optional[str]
    tags: List[str]
    custom_fields: Dict[str, Any]
    owner_id: int
    visibility: str
    shared_with: List[int]
    created_at: datetime
    updated_at: datetime