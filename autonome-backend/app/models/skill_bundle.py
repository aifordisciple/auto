"""
SKILL Bundle 数据模型 - 用于文件系统技能包的完整数据结构

支持 4 种执行器类型：
- Python_env: 单 Python 脚本
- R_env: 单 R 脚本
- Logical_Blueprint: Nextflow 工作流
- Python_Package: 完整 Python 包
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class ExecutorType(str, Enum):
    """技能执行器类型"""
    PYTHON_ENV = "Python_env"           # 单 Python 脚本
    R_ENV = "R_env"                     # 单 R 脚本
    LOGICAL_BLUEPRINT = "Logical_Blueprint"  # Nextflow 工作流
    PYTHON_PACKAGE = "Python_Package"   # 完整 Python 包


class SkillBundleMetadata(BaseModel):
    """
    SKILL.md YAML Frontmatter 数据结构

    对应 SKILL.md 文件开头的 YAML 元数据块
    """
    skill_id: str = Field(..., description="全局唯一的英文ID")
    name: str = Field(..., description="SKILL的显示名称")
    version: str = Field(default="1.0.0", description="版本号")
    author: str = Field(default="Anonymous", description="作者")
    executor_type: ExecutorType = Field(default=ExecutorType.PYTHON_ENV, description="执行器类型")
    entry_point: str = Field(default="none", description="入口点，通常为 none 或脚本路径")
    timeout_seconds: int = Field(default=3600, description="超时时间（秒）")

    # 分类信息
    category: str = Field(default="general", description="一级分类ID")
    category_name: str = Field(default="通用", description="一级分类显示名")
    subcategory: Optional[str] = Field(default=None, description="二级分类ID")
    subcategory_name: Optional[str] = Field(default=None, description="二级分类显示名")
    tags: List[str] = Field(default_factory=list, description="标签列表")


class NextflowProcess(BaseModel):
    """Nextflow Process 定义"""
    name: str = Field(..., description="Process 名称")
    code: str = Field(..., description="Process 完整代码")


class NextflowWorkflow(BaseModel):
    """Nextflow Workflow 定义"""
    name: str = Field(..., description="Workflow 名称")
    code: str = Field(..., description="Workflow 完整代码")


class NextflowBundle(BaseModel):
    """Nextflow 工作流包"""
    processes: List[NextflowProcess] = Field(default_factory=list, description="Process 列表")
    workflow: Optional[NextflowWorkflow] = Field(default=None, description="主 Workflow")
    full_code: str = Field(default="", description="完整的 process.nf 代码")


class ScriptFile(BaseModel):
    """脚本文件定义"""
    filename: str = Field(..., description="文件名，如 main.py")
    content: str = Field(..., description="文件内容")
    language: str = Field(default="python", description="编程语言")


class SkillBundleContent(BaseModel):
    """
    完整技能包内容结构

    包含技能的所有文件内容
    """
    metadata: SkillBundleMetadata = Field(..., description="元数据")
    description: str = Field(default="", description="技能意图与功能边界描述")

    # 参数 Schema (JSON Schema 格式)
    parameters_schema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    # 专家知识库
    expert_knowledge: str = Field(default="", description="操作指令与专家级知识库")

    # 单脚本类型 (Python_env / R_env)
    script_code: Optional[str] = Field(default=None, description="主脚本代码")
    dependencies: List[str] = Field(default_factory=list, description="依赖包列表")

    # Nextflow 工作流 (Logical_Blueprint)
    nextflow_bundle: Optional[NextflowBundle] = Field(default=None, description="Nextflow 工作流包")

    # 多脚本 (Python_Package 或额外脚本)
    additional_scripts: List[ScriptFile] = Field(default_factory=list, description="额外脚本文件")


class ForgeRequest(BaseModel):
    """
    增强版锻造请求模型

    支持选择执行器类型和是否生成完整文件系统目录
    """
    raw_material: str = Field(..., description="原始素材：代码/指令/文献段落")
    executor_type: ExecutorType = Field(default=ExecutorType.PYTHON_ENV, description="执行器类型")
    generate_full_bundle: bool = Field(default=False, description="是否生成完整文件系统目录")
    skill_name_hint: Optional[str] = Field(default=None, description="技能名称提示")

    # 分类信息（可选）
    category: Optional[str] = Field(default=None, description="一级分类ID")
    subcategory: Optional[str] = Field(default=None, description="二级分类ID")
    tags: List[str] = Field(default_factory=list, description="标签列表")


class ForgeResponse(BaseModel):
    """
    锻造响应模型

    返回锻造结果和生成的文件信息
    """
    status: str = Field(default="success", description="状态")
    skill_id: Optional[str] = Field(default=None, description="生成的 skill_id")
    skill_name: str = Field(..., description="技能名称")

    # 锻造内容
    content: SkillBundleContent = Field(..., description="完整内容")

    # 文件系统信息（如果生成了文件）
    bundle_path: Optional[str] = Field(default=None, description="生成的 Bundle 目录路径")
    files_created: List[str] = Field(default_factory=list, description="创建的文件列表")

    # 校验信息
    validation_passed: bool = Field(default=False, description="是否通过校验")
    validation_warning: Optional[str] = Field(default=None, description="校验警告")


class CraftedSkillResult(BaseModel):
    """
    AI 锻造结果模型

    用于解析 LLM 返回的锻造结果
    """
    name: str = Field(..., description="技能名称")
    description: str = Field(default="", description="一句话简介")
    executor_type: str = Field(default="Python_env", description="执行器类型")

    parameters_schema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []},
        description="参数 Schema"
    )

    expert_knowledge: str = Field(default="", description="专家指导")

    script_code: Optional[str] = Field(default=None, description="主脚本代码")
    dependencies: List[str] = Field(default_factory=list, description="依赖包列表")

    # Nextflow 相关字段
    nextflow_code: Optional[str] = Field(default=None, description="Nextflow process.nf 代码")
    processes: List[Dict[str, str]] = Field(default_factory=list, description="Process 定义列表")


# ==========================================
# 辅助函数
# ==========================================

def get_script_extension(executor_type: ExecutorType) -> str:
    """根据执行器类型获取脚本扩展名"""
    extension_map = {
        ExecutorType.PYTHON_ENV: ".py",
        ExecutorType.R_ENV: ".R",
        ExecutorType.LOGICAL_BLUEPRINT: ".nf",
        ExecutorType.PYTHON_PACKAGE: ".py"
    }
    return extension_map.get(executor_type, ".py")


def get_script_filename(executor_type: ExecutorType) -> str:
    """根据执行器类型获取主脚本文件名"""
    filename_map = {
        ExecutorType.PYTHON_ENV: "main.py",
        ExecutorType.R_ENV: "main.R",
        ExecutorType.LOGICAL_BLUEPRINT: "process.nf",
        ExecutorType.PYTHON_PACKAGE: "__init__.py"
    }
    return filename_map.get(executor_type, "main.py")


def is_script_type(executor_type: ExecutorType) -> bool:
    """判断是否为单脚本类型"""
    return executor_type in [ExecutorType.PYTHON_ENV, ExecutorType.R_ENV]


def is_nextflow_type(executor_type: ExecutorType) -> bool:
    """判断是否为 Nextflow 工作流类型"""
    return executor_type == ExecutorType.LOGICAL_BLUEPRINT