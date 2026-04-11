"""
Agent Schema 定义 - 所有输出的 Pydantic 模型

提供结构化输出，确保 JSON 格式正确性。
"""

from typing import Annotated, Literal, Optional, Any
from pydantic import BaseModel, Field


class RouteQuery(BaseModel):
    """快速意图路由结果"""
    intent: Literal["casual_chat", "bio_analysis", "complex_blueprint", "skill_execute"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""


class MatchedSkill(BaseModel):
    """匹配到的技能"""
    skill_id: str
    skill_type: Literal["knowledge", "executable"]
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    match_reason: str = ""


class IntentResult(BaseModel):
    """意图识别结果（供内部使用）"""
    intent_type: Literal["casual_chat", "knowledge_skill", "executable_skill", "live_coding"]
    matched_skills: list[MatchedSkill] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_action: Literal["direct_execute", "confirm_with_user", "show_options"] = "direct_execute"
    parameters_suggestion: dict[str, Any] = Field(default_factory=dict)


class StrategyCard(BaseModel):
    """策略卡片 - 单步任务/Live Coding 输出"""
    title: str
    description: str
    task_summary: str = ""
    tool_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    estimated_time: str = "约 1 分钟"
    task_mode: Optional[str] = None
    visualization_config: Optional[dict[str, Any]] = None


class BlueprintNode(BaseModel):
    """蓝图任务节点"""
    task_id: str
    name: str
    tool: str
    depends_on: list[str] = Field(default_factory=list)
    expected_input: Optional[str] = None
    expected_output: Optional[str] = None
    instruction: str = ""


class BlueprintResult(BaseModel):
    """复杂任务蓝图输出"""
    project_goal: str
    is_complex_task: bool = True
    tasks: list[BlueprintNode] = Field(default_factory=list)


class InteractivePlotConfig(BaseModel):
    """交互式图表配置"""
    plot_type: Literal["scatter", "heatmap", "bar", "line", "volcano", "pca", "boxplot", "violin", "pie", "treemap"]
    title: str
    description: str = ""
    data_source: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    export_formats: list[str] = Field(default_factory=lambda: ["pdf", "png_300dpi", "tsv"])
    aspect_ratio: float = 1.5


class ChatResponse(BaseModel):
    """闲聊响应（直接流式输出）"""
    content: str
    is_streaming: bool = True
