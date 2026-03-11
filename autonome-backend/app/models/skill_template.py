"""
SKILL Template Models - 技能模板数据模型

提供技能模板的结构定义，用于降低开发门槛，标准化技能开发流程
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum


def get_utc_now():
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


class TemplateType(str, Enum):
    """模板类型枚举"""
    BLUEPRINT = "Logical_Blueprint"    # 流程蓝图模板
    PYTHON_ENV = "Python_env"          # Python 脚本模板
    R_ENV = "R_env"                    # R 脚本模板
    NEXTFLOW = "Nextflow"              # Nextflow 流程模板


class SkillTemplateBase(SQLModel):
    """技能模板基础模型"""
    name: str = Field(max_length=255, description="模板名称")
    template_id: str = Field(max_length=100, description="模板唯一标识")
    description: Optional[str] = Field(default=None, description="模板描述")
    template_type: TemplateType = Field(default=TemplateType.PYTHON_ENV, description="模板类型")

    # 模板内容
    script_template: Optional[str] = Field(default=None, description="代码模板（含占位符）")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None, description="专家指导模板")

    # 分类信息
    category: str = Field(default="general", max_length=50, description="一级分类ID")
    category_name: str = Field(default="通用", max_length=100, description="一级分类名称")
    subcategory: Optional[str] = Field(default=None, max_length=50, description="二级分类ID")
    subcategory_name: Optional[str] = Field(default=None, max_length=100, description="二级分类名称")
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB))

    # 来源信息
    source_skill_id: Optional[str] = Field(default=None, description="来源技能ID（从哪个技能提取）")
    is_official: bool = Field(default=True, description="是否官方模板")


class SkillTemplate(SkillTemplateBase, table=True):
    """技能模板数据库表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
    usage_count: int = Field(default=0, description="使用次数")


class SkillTemplateCreate(SQLModel):
    """创建模板请求体"""
    name: str
    template_id: str
    description: Optional[str] = None
    template_type: TemplateType = TemplateType.PYTHON_ENV
    script_template: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    expert_knowledge: Optional[str] = None
    category: str = "general"
    category_name: str = "通用"
    subcategory: Optional[str] = None
    subcategory_name: Optional[str] = None
    tags: Optional[List[str]] = None
    source_skill_id: Optional[str] = None


class SkillTemplatePublic(SkillTemplateBase):
    """返回给前端的模板公共信息"""
    id: int
    created_at: datetime
    updated_at: datetime
    usage_count: int


class TemplateInstantiateRequest(SQLModel):
    """从模板实例化技能的请求"""
    skill_name: Optional[str] = Field(default=None, description="自定义技能名称")
    customizations: Optional[Dict[str, Any]] = Field(default=None, description="自定义参数覆盖")


class TemplateInstantiateResult(SQLModel):
    """实例化结果"""
    skill_id: str
    name: str
    description: str
    executor_type: str
    script_code: Optional[str] = None
    parameters_schema: Dict[str, Any]
    expert_knowledge: Optional[str] = None
    dependencies: List[str] = []