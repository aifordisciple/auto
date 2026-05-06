"""
技能资产模型

包含技能资产的基础模型、表模型、创建/更新/公开模型
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.models.uuid import generate_skill_id
from app.models.enums import SkillStatus


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)




# ==========================================
# SKILL 资产库模型 (SkillAsset)
# ==========================================
class SkillAssetBase(SQLModel):
    """SKILL 资产基础模型"""
    name: str = Field(max_length=255, description="SKILL的显示名称")
    description: Optional[str] = Field(default=None, description="一句话简介")
    version: str = Field(default="1.0.0", max_length=50)
    executor_type: str = Field(default="Python_env", max_length=50)

    # 核心资产内容
    parameters_schema: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None)
    script_code: Optional[str] = Field(default=None, description="实际执行的Python/R代码")
    nextflow_code: Optional[str] = Field(default=None, description="Nextflow工作流代码（Logical_Blueprint执行器专用）")
    dependencies: Optional[List[str]] = Field(default=None, sa_column=Column(JSONB))

    # 分类信息 (新增)
    category: Optional[str] = Field(default=None, max_length=100, description="一级分类ID")
    category_name: Optional[str] = Field(default=None, max_length=100, description="一级分类名称")
    subcategory: Optional[str] = Field(default=None, max_length=100, description="二级分类ID")
    subcategory_name: Optional[str] = Field(default=None, max_length=100, description="二级分类名称")
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="标签列表")

    # ✨ 基础分析标记 (用于 Tools 按钮快速筛选)
    # 标记为 true 的技能会出现在"基础分析"快捷入口中
    # 这些通常是标准化、单步骤的分析任务（如质控、可视化等）
    is_basic_analysis: bool = Field(default=False, description="是否为基础分析技能")

    # 状态控制
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    reject_reason: Optional[str] = Field(default=None, description="如果被驳回，管理员填写的理由")

    # 发布信息 (新增)
    visibility: str = Field(default="private", max_length=20, description="可见性: private/team/public")
    license: str = Field(default="MIT", max_length=50, description="许可证")

    # 统计信息 (新增)
    usage_count: int = Field(default=0, description="使用次数")
    avg_rating: float = Field(default=0.0, ge=0.0, le=5.0, description="平均评分")
    favorite_count: int = Field(default=0, description="收藏数")

    # ==========================================
    # 执行模式控制 (管理员配置)
    # ==========================================
    # 用于控制技能是使用 Docker 容器运行还是原生系统运行
    # 仅官方技能可以使用原生执行模式
    execution_mode: str = Field(default="docker", max_length=20, description="执行模式: docker(容器执行) | native(原生执行)")
    execution_mode_updated_at: Optional[datetime] = Field(default=None, description="执行模式最后更新时间")

    # ==========================================
    # 文件系统索引字段（2026-05 技能文件系统统一化）
    # ==========================================
    bundle_path: Optional[str] = Field(default=None, max_length=500, description="技能文件夹路径")
    is_official: bool = Field(default=False, description="是否为官方预置技能")
    file_hash: Optional[str] = Field(default=None, max_length=32, description="SKILL.md SHA256 哈希(前16位)")
    indexed_at: Optional[datetime] = Field(default=None, description="最后索引时间")


class SkillAsset(SkillAssetBase, table=True):
    """SKILL 资产数据库表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(default_factory=generate_skill_id, unique=True, index=True, max_length=100, description="全局唯一的英文ID")
    owner_id: int = Field(foreign_key="user.id", index=True, description="创建者的User ID")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # ==========================================
    # 执行模式更新者（外键，仅在表类中定义）
    # ==========================================
    execution_mode_updated_by: Optional[int] = Field(
        default=None,
        foreign_key="user.id",
        description="执行模式最后更新者（管理员ID）"
    )

    # ==========================================
    # 语义向量字段已移除（pgvector 不再使用）
    # ==========================================

    # ==========================================
    # 复合索引定义（性能优化）
    # ==========================================
    # 注意：SQLModel/SQLAlchemy 的复合索引定义方式
    __table_args__ = (
        # 技能列表按所有者+状态筛选（高频查询）
        Index('ix_skill_asset_owner_status', 'owner_id', 'status'),
        # 技能列表按分类筛选（市场浏览）
        Index('ix_skill_asset_category', 'category', 'subcategory'),
        # 技能列表按可见性+状态筛选（公开技能）
        Index('ix_skill_asset_visibility_status', 'visibility', 'status'),
        # JSONB tags 字段 GIN 索引（标签搜索）
        Index('ix_skill_asset_tags_gin', 'tags', postgresql_using='gin'),
    )


class SkillAssetCreate(SkillAssetBase):
    """用于前端创建 SKILL 的请求体"""
    skill_id: Optional[str] = None  # 可选，如果不提供则自动生成


class SkillAssetUpdate(SQLModel):
    """用于更新 SKILL 的请求体"""
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    executor_type: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    expert_knowledge: Optional[str] = None
    script_code: Optional[str] = None
    nextflow_code: Optional[str] = None
    dependencies: Optional[List[str]] = None
    # 新增字段
    category: Optional[str] = None
    category_name: Optional[str] = None
    subcategory: Optional[str] = None
    subcategory_name: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = None
    license: Optional[str] = None
    is_basic_analysis: Optional[bool] = None
    # 执行模式
    execution_mode: Optional[str] = None


class SkillAssetPublic(SkillAssetBase):
    """返回给前端的 SKILL 公共信息"""
    id: int
    skill_id: str
    owner_id: int
    execution_mode: str  # 执行模式
    created_at: datetime
    updated_at: datetime