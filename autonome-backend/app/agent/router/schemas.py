"""
意图识别引擎 V2.0 数据结构定义。

包含 13 种原子意图类型枚举、意图-节点映射、提取结果模型、
DAG 调度数据模型、Active Probing 请求模型和 LangGraph 状态定义。

升级要点：
- 意图从 6 种扩展为 12 种 MECE 原子意图（4 组）
- 新增 TaskNode / TaskDAG 支持多任务有向无环图调度
- 新增 ProbingRequest 支持主动反问与前端 Generative UI 表单
- 新增 RouteResult 作为路由引擎的完整输出
- AgentState 扩展 DAG 调度状态字段
- V2.1 新增即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS)
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Annotated

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class IntentType(str, Enum):
    """
    意图类型枚举 - 13 种原子意图分类 (V2.0 MECE)。

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
    # 组1 新增：计算与编排
    ADHOC_INTERACTIVE_ANALYSIS = "INTENT_ADHOC_INTERACTIVE_ANALYSIS"  # 即席交互式分析
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
    IntentType.ADHOC_INTERACTIVE_ANALYSIS: "adhoc_analysis_node",
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
    # 新增：用于即席分析的元数据（策略、生成的Schema、临时代码等）
    # 仅 ADHOC_INTERACTIVE_ANALYSIS 意图时有值
    adhoc_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析元数据：策略描述、生成的代码、参数 Schema、输入映射"
    )


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
    # 新增：区分参数反问卡片和即席分析卡片的渲染类型
    render_type: str = Field(
        default="parameter_probing",
        description="渲染类型：parameter_probing(参数反问) | adhoc_card(即席分析卡片)"
    )
    # 新增：即席分析卡片数据（仅 render_type=adhoc_card 时有值）
    adhoc_card_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析卡片数据（仅 render_type=adhoc_card 时有值）"
    )


class ExecutionStatus(str, Enum):
    """DAG 执行状态枚举"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 全部完成
    FAILED = "failed"          # 执行失败
    PROBING = "probing"        # 等待用户参数补全


class TaskNodeStatus(str, Enum):
    """DAG 中单个 TaskNode 的执行状态"""
    PENDING = "pending"      # 等待前置节点完成
    READY = "ready"          # 可执行（前置节点已完成）
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    SKIPPED = "skipped"      # 因依赖失败而跳过


class ProbingResponse(BaseModel):
    """用户提交的 Active Probing 参数"""
    message_id: str = Field(..., description="对应的 ProbingRequest message_id")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="用户填写的参数")


class TaskResult(BaseModel):
    """单个 TaskNode 的执行结果"""
    task_id: str = Field(..., description="子任务 ID")
    skill_id: str = Field(default="", description="执行的技能 ID")
    status: str = Field(default="pending", description="执行状态: success/failed/timeout")
    output: Optional[Any] = Field(None, description="执行输出")
    error: Optional[str] = Field(None, description="错误信息")
    execution_time_seconds: float = Field(0.0, description="执行耗时（秒）")


class RouteResult(BaseModel):
    """路由引擎的完整输出结果"""
    dag: TaskDAG = Field(..., description="L1 解析出的任务图谱")
    probing: Optional[ProbingRequest] = Field(default=None, description="L2 探查结果（仅当参数缺失时有值）")


class WorkspaceContext(BaseModel):
    """
    结构化工作区上下文 - 供 L1 解构器消费。

    将前端注入的原始 context 字典转换为类型化的结构化模型，
    确保 L1 提示词中的上下文信息格式一致、可解析。
    支持指代消解：active_file 对应"这个文件"，last_execution_result 对应"上面的结果"。
    """
    active_file: Optional[str] = Field(
        None, description="当前打开的文件路径或 ID"
    )
    active_file_type: Optional[str] = Field(
        None, description="文件类型 (h5ad, csv, fastq, bam, etc.)"
    )
    recent_files: List[Dict[str, str]] = Field(
        default_factory=list, description="最近使用的文件 [{id, name, type}]"
    )
    active_skills: List[Dict[str, str]] = Field(
        default_factory=list, description="工作区中可用的技能 [{id, name, category}]"
    )
    last_execution_status: Optional[str] = Field(
        None, description="上次执行状态 (success/failed)"
    )
    last_execution_result: Optional[str] = Field(
        None, description="上次执行结果摘要"
    )
    workspace_summary: Optional[str] = Field(
        None, description="工作区自然语言摘要"
    )


class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态 (V2.0)。

    支持多任务 DAG 调度、Active Probing 挂起/恢复、L3 执行结果收集。
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
    # --- V2.0+ 新增字段 ---
    execution_status: str              # ExecutionStatus 值，默认 "pending"
    probing_response: Optional[Dict]   # ProbingResponse 序列化结果（用户提交的参数）
