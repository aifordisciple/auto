"""
意图识别引擎 V2.0 数据结构定义。

包含 12 种原子意图类型枚举、意图-节点映射、提取结果模型、
DAG 调度数据模型、Active Probing 请求模型和 LangGraph 状态定义。

升级要点：
- 意图从 6 种扩展为 12 种 MECE 原子意图（4 组）
- 新增 TaskNode / TaskDAG 支持多任务有向无环图调度
- 新增 ProbingRequest 支持主动反问与前端 Generative UI 表单
- 新增 RouteResult 作为路由引擎的完整输出
- AgentState 扩展 DAG 调度状态字段
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Annotated

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class IntentType(str, Enum):
    """
    意图类型枚举 - 12 种原子意图分类 (V2.0 MECE)。

    每种意图对应一个下游 Agent 节点，通过 INTENT_NODE_MAP 映射。
    """
    # 组1: 计算与编排 (Compute & Engineering)
    WORKFLOW_ORCHESTRATE = "INTENT_WORKFLOW_ORCHESTRATE"        # 工作流编排与多步骤调度
    SKILL_FORGE = "INTENT_SKILL_FORGE"                          # 生成/锻造分析技能
    EXPLICIT_EXEC = "INTENT_EXPLICIT_EXEC"                      # 用户直接指定技能 ID 执行
    VERSION_CONTROL = "INTENT_VERSION_CONTROL"                  # 版本控制与代码管理
    # 组2: 视觉与探究 (Perception & Discovery)
    VISUAL_PERCEPTION_AND_TWEAK = "INTENT_VISUAL_PERCEPTION_AND_TWEAK"  # 可视化感知与交互微调
    DATA_PROBE = "INTENT_DATA_PROBE"                            # 数据预览/探查
    LITERATURE_MINING = "INTENT_LITERATURE_MINING"              # 文献/DOI/论文挖掘与复现
    # 组3: 运维与协作 (Operations & Collaboration)
    SYSTEM_ASSET_OPS = "INTENT_SYSTEM_ASSET_OPS"                # 系统资产运维（环境/依赖/配置）
    COLLABORATION = "INTENT_COLLABORATION"                      # 团队协作与共享
    DIAGNOSTIC_RECOVERY = "INTENT_DIAGNOSTIC_RECOVERY"          # 报错/环境问题诊断与恢复
    # 组4: 通用兜底 (General Support)
    GENERAL_CHAT = "INTENT_GENERAL_CHAT"                        # 通用闲聊、概念解释
    SYSTEM_MACRO = "INTENT_SYSTEM_MACRO"                        # 系统级宏指令（设置/偏好/帮助）


# 意图 → LangGraph 节点映射（引擎计算，不由 LLM 输出）
INTENT_NODE_MAP: Dict[IntentType, str] = {
    IntentType.WORKFLOW_ORCHESTRATE: "orchestrator_node",
    IntentType.SKILL_FORGE: "skill_forge_node",
    IntentType.EXPLICIT_EXEC: "explicit_exec_node",
    IntentType.VERSION_CONTROL: "version_control_node",
    IntentType.VISUAL_PERCEPTION_AND_TWEAK: "ui_state_node",
    IntentType.DATA_PROBE: "data_probe_node",
    IntentType.LITERATURE_MINING: "literature_node",
    IntentType.SYSTEM_ASSET_OPS: "system_asset_node",
    IntentType.COLLABORATION: "collaboration_node",
    IntentType.DIAGNOSTIC_RECOVERY: "diagnostic_node",
    IntentType.GENERAL_CHAT: "chat_node",
    IntentType.SYSTEM_MACRO: "system_macro_node",
}


class IntentExtraction(BaseModel):
    """
    意图提取结果 - L0 规则引擎的结构化输出格式。

    下游 LangGraph 节点根据此结果进行确定性路由。
    L0 规则仍返回此格式，路由引擎将其包装为单节点 DAG。

    v2: 合并 L1+L2 为单次调用，slots 字段替代独立的 L2 提取。
    仅当意图为 skill_forge/explicit_exec/data_probe 时 slots 有值。
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
        description="仅 explicit_exec 意图时有值，表示用户指定的技能 ID"
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
    # v2: 合并 L2 的槽位提取结果，避免串行二次 LLM 调用
    slots: Dict[str, str] = Field(
        default_factory=dict,
        description="仅 skill_forge/explicit_exec/data_probe 意图时提取的参数槽位"
    )
    missing_slots: List[str] = Field(
        default_factory=list,
        description="必需但未填充的参数名"
    )


class SlotExtraction(BaseModel):
    """
    L2 槽位提取结果（向后兼容保留）。

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


class TaskNode(BaseModel):
    """DAG 中的单一执行节点"""
    task_id: str = Field(..., description="子任务的唯一标识符，如 'task_1'")
    intent: IntentType = Field(..., description="解析出的原子意图类型")
    raw_instruction: str = Field(..., description="该子任务对应的具体自然语言指令")
    dependencies: List[str] = Field(default_factory=list, description="依赖的前置 task_id 列表")
    resolved_assets: List[str] = Field(default_factory=list, description="指代消解后的具体 FileID 或 DB_Hash")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="初步提取的关键参数（若有）")


class TaskDAG(BaseModel):
    """由多个 TaskNode 组成的有向无环图"""
    nodes: List[TaskNode] = Field(..., description="构成本次执行图谱的子任务节点列表")
    is_conditional: bool = Field(default=False, description="图中是否包含 If/Else 条件分支探针逻辑")


class ProbingRequest(BaseModel):
    """主动反问请求对象，用于触发前端 Generative UI 表单"""
    is_missing: bool = Field(..., description="是否存在缺失的必要参数")
    missing_params: List[str] = Field(default_factory=list, description="缺失的参数名列表")
    ui_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema 供前端渲染动态表单")
    message_to_user: str = Field(default="", description="向用户展示的追问提示语")


class RouteResult(BaseModel):
    """路由引擎的完整输出结果"""
    dag: TaskDAG = Field(..., description="L1 解析出的任务图谱")
    probing: Optional[ProbingRequest] = Field(default=None, description="L2 探查结果（仅当参数缺失时有值）")


class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态 (V2.0)。

    支持多任务 DAG 调度、Active Probing 挂起/恢复。
    """
    messages: Annotated[Sequence[BaseMessage], "消息历史"]
    context: Dict[str, Any]            # 前端注入的工作区上下文
    intent_data: Optional[Dict]        # IntentExtraction 序列化结果
    skill_id: Optional[str]            # 匹配到的技能 ID
    execution_result: Optional[Dict]   # 执行结果
    # --- V2.0 DAG 调度状态 ---
    dag: Optional[Dict]                # TaskDAG 序列化结果
    current_task_idx: int              # 当前执行到 DAG 中的哪一个任务
    active_probing: Optional[Dict]     # ProbingRequest 序列化结果
    task_results: Dict[str, Any]       # 各子任务执行完毕后的结果上下文
