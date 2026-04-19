"""
意图识别引擎 2.0 数据结构定义。

包含意图类型枚举、提取结果模型、槽位提取模型和 LangGraph 状态定义。
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Annotated

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class IntentType(str, Enum):
    """
    意图类型枚举 - 6 种核心意图分类。

    每种意图对应一个下游 Agent 节点，通过 INTENT_NODE_MAP 映射。
    """
    CHAT = "chat"                      # 通用闲聊、概念解释
    SKILL_FORGE = "skill_forge"        # 生成/执行分析代码
    EXPLICIT_SKILL = "explicit_skill"  # 用户直接指定技能 ID
    DIAGNOSTIC = "diagnostic"          # 报错/环境问题诊断
    LITERATURE = "literature"          # 文献/DOI/论文复现
    DATA_PROBE = "data_probe"          # 数据预览/探查


# 意图 → LangGraph 节点映射（引擎计算，不由 LLM 输出）
INTENT_NODE_MAP: Dict[IntentType, str] = {
    IntentType.CHAT: "chat_node",
    IntentType.SKILL_FORGE: "skill_forge_node",
    IntentType.EXPLICIT_SKILL: "explicit_skill_node",
    IntentType.DIAGNOSTIC: "diagnostic_node",
    IntentType.LITERATURE: "literature_node",
    IntentType.DATA_PROBE: "data_probe_node",
}


class IntentExtraction(BaseModel):
    """
    意图提取结果 - L1 LLM 结构化输出的目标格式。

    下游 LangGraph 节点根据此结果进行确定性路由。
    """
    intent: IntentType = Field(
        description="识别出的核心意图分类"
    )
    confidence: float = Field(
        description="意图识别的置信度 (0.0 到 1.0 之间)",
        ge=0.0,
        le=1.0
    )
    entities: Dict[str, str] = Field(
        default_factory=dict,
        description="从用户输入中提取的生信实体或关键参数"
    )
    skill_id: Optional[str] = Field(
        default=None,
        description="仅 explicit_skill 意图时有值，表示用户指定的技能 ID"
    )
    requires_followup: bool = Field(
        default=False,
        description="是否需要向用户追问缺失的必要参数"
    )
    followup_question: Optional[str] = Field(
        default=None,
        description="如果 requires_followup 为 true，提供追问话术"
    )
    routing_target: Optional[str] = Field(
        default=None,
        description="目标 Agent 节点名，由引擎根据 intent 计算"
    )


class SlotExtraction(BaseModel):
    """
    L2 槽位提取结果。

    slots: LLM 提取的参数键值对
    missing_slots: 必需但未填充的参数名列表
    context_enrichments: 从工作区上下文自动填充的参数
    """
    slots: Dict[str, str] = Field(
        default_factory=dict,
        description="LLM 提取的槽位键值对"
    )
    missing_slots: List[str] = Field(
        default_factory=list,
        description="必需但未填充的参数名"
    )
    context_enrichments: Dict[str, str] = Field(
        default_factory=dict,
        description="从工作区上下文自动填充的参数"
    )


class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态。

    在意图路由节点和各 Agent 节点之间传递。
    """
    messages: Annotated[Sequence[BaseMessage], "消息历史"]
    context: Dict[str, Any]            # 前端注入的工作区上下文
    intent_data: Optional[Dict]        # IntentExtraction 序列化结果
    skill_id: Optional[str]            # 匹配到的技能 ID
    execution_result: Optional[Dict]   # 执行结果
