"""
技能草稿模型

用于存储自动生成的技能草稿，支持"零确认转化"功能。
用户可在技能工厂中查看、编辑、一键发布这些草稿。
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import String, Text, JSON


class DraftStatus(str, Enum):
    """草稿状态枚举"""
    PENDING = "PENDING"           # 待处理：已生成，等待用户确认
    REVIEWED = "REVIEWED"         # 已查看：用户已查看但未发布
    PUBLISHED = "PUBLISHED"       # 已发布：已转化为正式技能
    DISMISSED = "DISMISSED"       # 已忽略：用户选择不发布
    FAILED = "FAILED"             # 生成失败


class TriggerSource(str, Enum):
    """触发来源枚举"""
    CODE_COMPLEXITY = "code_complexity"       # 代码复杂度触发
    EXECUTION_TIME = "execution_time"         # 执行时长触发
    OUTPUT_FILE = "output_file"               # 输出文件触发
    USER_ACTION = "user_action"               # 用户主动操作
    SUCCESS_SIGNAL = "success_signal"         # 成功信号触发


# ==========================================
# 技能草稿模型
# ==========================================

class PendingSkillDraftBase(SQLModel):
    """技能草稿基类"""
    # 会话信息
    session_id: str = Field(..., description="来源会话ID")
    project_id: Optional[str] = Field(default=None, description="项目ID")

    # 触发信息
    trigger_source: str = Field(default=TriggerSource.CODE_COMPLEXITY, description="触发来源")
    trigger_score: float = Field(default=0.0, description="触发评分(0-1)")
    trigger_reason: str = Field(default="", description="触发原因描述")

    # 原始素材
    raw_material: str = Field(default="", sa_column=Column(Text), description="原始素材(代码+需求)")
    code_blocks: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON), description="提取的代码块")
    strategies: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON), description="提取的策略卡片")

    # 生成的草稿数据
    draft_name: str = Field(default="", description="草稿名称")
    draft_description: str = Field(default="", sa_column=Column(Text), description="草稿描述")
    executor_type: str = Field(default="Python_env", description="执行器类型")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON), description="参数Schema")
    expert_knowledge: str = Field(default="", sa_column=Column(Text), description="专家知识")
    script_code: str = Field(default="", sa_column=Column(Text), description="生成的代码")
    dependencies: List[str] = Field(default_factory=list, sa_column=Column(JSON), description="依赖包列表")

    # 状态
    status: str = Field(default=DraftStatus.PENDING, description="草稿状态")


class PendingSkillDraft(PendingSkillDraftBase, table=True):
    """技能草稿数据表"""
    __tablename__ = "pending_skill_drafts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(..., foreign_key="user.id", index=True, description="用户ID")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}, description="更新时间")

    # 发布后的技能ID（如果已发布）
    published_skill_id: Optional[str] = Field(default=None, description="发布后的技能ID")


class PendingSkillDraftCreate(SQLModel):
    """创建技能草稿的请求体"""
    session_id: str
    project_id: Optional[str] = None
    trigger_source: str = TriggerSource.CODE_COMPLEXITY
    trigger_score: float = 0.0
    trigger_reason: str = ""
    raw_material: str = ""
    code_blocks: List[Dict[str, Any]] = []
    strategies: List[Dict[str, Any]] = []
    draft_name: str = ""
    draft_description: str = ""
    executor_type: str = "Python_env"
    parameters_schema: Dict[str, Any] = {}
    expert_knowledge: str = ""
    script_code: str = ""
    dependencies: List[str] = []


class PendingSkillDraftPublic(PendingSkillDraftBase):
    """技能草稿公开模型"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    published_skill_id: Optional[str] = None

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """兼容历史数据：strategies 中可能存储了字符串而非字典"""
        if hasattr(obj, "strategies") and obj.strategies:
            obj.strategies = [
                {"strategy": s} if isinstance(s, str) else s
                for s in obj.strategies
            ]
        return super().model_validate(obj, **kwargs)


class PendingSkillDraftUpdate(SQLModel):
    """更新技能草稿的请求体"""
    draft_name: Optional[str] = None
    draft_description: Optional[str] = None
    executor_type: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    expert_knowledge: Optional[str] = None
    script_code: Optional[str] = None
    dependencies: Optional[List[str]] = None
    status: Optional[str] = None