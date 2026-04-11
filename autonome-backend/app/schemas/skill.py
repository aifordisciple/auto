"""
技能相关 Pydantic 模型

集中定义技能 API 请求和响应模型
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TransformRequest(BaseModel):
    """Live_Coding 转 SKILL 请求"""
    session_id: int
    message_id: int
    skill_name: str
    description: str


class ConsolidateRequest(BaseModel):
    """蓝图固化请求"""
    project_id: str
    blueprint_json: str  # JSON 字符串
    skill_name: str = None  # 可选的自定义名称


class CraftRequest(BaseModel):
    """SKILL 锻造请求"""
    raw_material: str = Field(..., description="原始素材：代码/指令/文献段落")
    executor_type: str = Field(default="Python_env", description="执行器类型: Python_env/R_env/Logical_Blueprint/Python_Package")
    generate_full_bundle: bool = Field(default=False, description="是否生成完整文件系统目录")
    skill_name_hint: Optional[str] = Field(default=None, description="技能名称提示")
    category: Optional[str] = Field(default=None, description="一级分类ID")
    subcategory: Optional[str] = Field(default=None, description="二级分类ID")
    tags: List[str] = Field(default_factory=list, description="标签列表")


class SkillTestRequest(BaseModel):
    """SKILL 测试请求（增强版）"""
    script_code: str = Field(..., description="需要测试的代码")
    test_instruction: str = Field(default="", description="测试环境变量或传参模拟代码")
    parameters_schema: Optional[Dict[str, Any]] = Field(default=None, description="参数 Schema，用于自动生成测试数据")
    auto_generate_data: bool = Field(default=True, description="是否自动生成测试数据")
    max_test_rounds: int = Field(default=3, description="最大测试轮数")
    executor_type: str = Field(default="Python_env", description="执行器类型: Python_env/R_env")


class TransformFromLiveRequest(BaseModel):
    """从聊天会话转化技能请求"""
    session_id: str = Field(..., description="聊天会话ID")
    skill_name: Optional[str] = Field(default=None, description="自定义技能名称")
    auto_save: bool = Field(default=False, description="是否自动保存为草稿")


class ReviewCreateRequest(BaseModel):
    """创建评价请求"""
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: Optional[str] = Field(default=None, description="评价内容")


class VersionCreateRequest(BaseModel):
    """创建版本请求"""
    version: str = Field(..., description="版本号")
    change_log: Optional[str] = Field(default=None, description="变更日志")


class ShareCreateRequest(BaseModel):
    """创建分享链接请求"""
    task_id: str = Field(..., description="任务ID")
    expires_in_days: int = Field(default=7, ge=0, le=365, description="过期天数，0表示永不过期")


class PublishDraftRequest(BaseModel):
    """发布技能草稿请求"""
    skill_name: Optional[str] = Field(default=None, description="自定义技能名称")
    category: Optional[str] = Field(default=None, description="分类ID")
    tags: Optional[List[str]] = Field(default=None, description="标签列表")


__all__ = [
    "TransformRequest",
    "ConsolidateRequest",
    "CraftRequest",
    "SkillTestRequest",
    "TransformFromLiveRequest",
    "ReviewCreateRequest",
    "VersionCreateRequest",
    "ShareCreateRequest",
    "PublishDraftRequest",
]