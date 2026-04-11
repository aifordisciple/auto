"""
系统级学习技能模型 (SystemSkill)

系统学习层核心数据模型 - 隐身方法论提取系统
从所有用户对话中自动提取方法论和策略，持续优化 Agent 能力。

设计理念：
- 隐身运行：用户不可见，系统自动触发
- 自动提取：从成功对话中提取方法论
- 智能注入：根据触发条件自动注入到 Agent prompt
- 演进追踪：记录来源会话、置信度、成功率

数据生命周期：
1. 提取阶段：MethodExtractor 从成功会话中提取候选方法
2. 验证阶段：SuccessEvaluator 评估置信度
3. 激活阶段：高置信度方法转为 active 状态
4. 注入阶段：根据触发条件注入到 Agent prompt
5. 淘汰阶段：低成功率方法转为 deprecated 状态
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum

from app.models.uuid import get_utc_now, generate_system_skill_id


# ==========================================
# pgvector Vector 类型导入
# ==========================================
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # 如果 pgvector 未安装，提供一个 dummy Vector 类型
    class Vector:
        def __init__(self, dimension=None):
            self.dimension = dimension


# ==========================================
# 系统技能状态枚举
# ==========================================
class SystemSkillStatus(str, Enum):
    """系统级技能状态（简化版，用于方法提取）"""
    ACTIVE = "active"          # 活跃：正在使用，高置信度
    DEPRECATED = "deprecated"  # 弃用：低成功率，已淘汰


# ==========================================
# 方法类型枚举
# ==========================================
class MethodType(str, Enum):
    """方法论类型分类"""
    # 分析策略类
    ANALYSIS_STRATEGY = "analysis_strategy"      # 分析策略：如何分解问题
    DATA_INSIGHT = "data_insight"                # 数据洞察：数据处理技巧

    # 执行模式类
    EXECUTION_PATTERN = "execution_pattern"      # 执行模式：代码/流程执行方式
    ERROR_HANDLING = "error_handling"            # 错误处理：异常恢复策略

    # 知识应用类
    DOMAIN_KNOWLEDGE = "domain_knowledge"        # 领域知识：生信专业知识应用
    TOOL_SELECTION = "tool_selection"            # 工具选择：何时用什么工具

    # 用户交互类
    COMMUNICATION = "communication"              # 沟通技巧：如何清晰解释结果
    REQUIREMENT_CLARIFICATION = "requirement_clarification"  # 需求澄清


# ==========================================
# 系统级学习技能模型 (SystemSkill)
# ==========================================
class SystemSkillBase(SQLModel):
    """
    系统级技能基础模型

    核心字段说明：
    - method_type: 方法类型分类（策略/模式/知识）
    - name: 方法名称（简短描述）
    - description: 详细描述
    - instructions: 可执行指令（Markdown 格式，注入到 Agent prompt）

    检索字段：
    - triggers: 触发关键词列表（JSONB，用于匹配用户查询）
    - tags: 标签列表（JSONB，用于分类和检索）
    - examples: 示例场景列表（JSONB，展示何时应用）

    版本与演进：
    - version: 版本号（支持迭代优化）
    - source_sessions: 来源会话 ID 列表（JSONB，追溯方法论来源）
    - confidence_score: 置信度评分（0-1，衡量方法可靠性）

    统计信息：
    - injection_count: 注入次数（累计被注入到 prompt 的次数）
    - success_rate: 成功率（注入后成功完成任务的比例）
    """

    # ==========================================
    # 基本信息
    # ==========================================
    method_type: str = Field(
        max_length=50,
        default=MethodType.ANALYSIS_STRATEGY,
        description="方法类型：analysis_strategy/data_insight/execution_pattern/error_handling/domain_knowledge/tool_selection/communication/requirement_clarification"
    )
    name: str = Field(
        max_length=255,
        description="方法名称，简短描述性标题"
    )
    description: Optional[str] = Field(
        default=None,
        description="详细描述，说明方法的核心原理和适用场景"
    )

    # ==========================================
    # 可执行内容（核心资产）
    # ==========================================
    instructions: Optional[str] = Field(
        default=None,
        description="可执行指令，Markdown 格式，会被注入到 Agent prompt 中指导其行为"
    )

    # ==========================================
    # 检索字段（JSONB）
    # ==========================================
    triggers: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="触发关键词列表，用于匹配用户查询场景。例如：['质控', 'QC', '质量控制', '数据清洗']"
    )
    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="标签列表，用于分类和检索。例如：['生信分析', '数据处理', '常见问题']"
    )
    examples: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="示例场景列表，展示方法何时被应用。每个示例包含 {query, context, result} 结构"
    )

    # ==========================================
    # 版本管理
    # ==========================================
    version: str = Field(
        default="1.0.0",
        max_length=50,
        description="版本号，支持迭代优化。格式：major.minor.patch"
    )

    # ==========================================
    # 演进追踪（追溯方法论来源和可靠性）
    # ==========================================
    source_sessions: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="来源会话 ID 列表，追溯方法论是从哪些成功对话中提取的"
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="置信度评分（0-1），衡量方法的可靠性。基于提取时的会话质量、验证结果计算"
    )
    last_updated: datetime = Field(
        default_factory=get_utc_now,
        description="最后更新时间"
    )

    # ==========================================
    # 统计信息（衡量方法效用）
    # ==========================================
    injection_count: int = Field(
        default=0,
        ge=0,
        description="注入次数，累计被注入到 Agent prompt 的次数"
    )
    success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="成功率（0-1），注入后成功完成任务的比例。低于阈值会被降级"
    )

    # ==========================================
    # 状态控制
    # ==========================================
    status: str = Field(
        default=SystemSkillStatus.ACTIVE,
        max_length=20,
        description="状态：active(活跃使用) | deprecated(已弃用)"
    )

    # ==========================================
    # 元数据（扩展字段）
    # ==========================================
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="扩展元数据，存储方法提取时的上下文、验证细节等"
    )


# ==========================================
# 数据库表模型
# ==========================================
class SystemSkill(SystemSkillBase, table=True):
    """
    系统级技能数据库表

    表名：systemskill

    索引策略：
    - skill_id: 主查询键
    - method_type: 分类查询
    - status: 状态筛选
    - combined_embedding: 向量索引（pgvector IVFFlat，cosine ops）

    隐私设计：
    - 无 owner_id 字段（系统级资产，不归属特定用户）
    - source_sessions 仅存储会话 ID，不存储对话内容
    - 用户无法直接查看或操作此表
    """

    # ==========================================
    # 主键和唯一标识
    # ==========================================
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="自增主键"
    )
    skill_id: str = Field(
        default_factory=generate_system_skill_id,
        unique=True,
        index=True,
        max_length=100,
        description="全局唯一 ID，格式：sys_skill_xxxxxxxx"
    )

    # ==========================================
    # 时间戳
    # ==========================================
    created_at: datetime = Field(
        default_factory=get_utc_now,
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=get_utc_now,
        description="更新时间，每次方法迭代或统计更新时刷新"
    )

    # ==========================================
    # 语义向量字段（用于智能检索）
    # ==========================================
    # 使用 pgvector 存储方法的语义向量嵌入
    # 向量维度: 1536 (OpenAI text-embedding-3-small 维度)
    # 用途: 基于语义相似度匹配用户查询场景
    combined_embedding: Optional[List[float]] = Field(
        default=None,
        sa_column=Column(Vector(1536)),
        description="混合语义向量嵌入，结合方法名称、描述、指令、触发关键词"
    )
    embedding_updated_at: Optional[datetime] = Field(
        default=None,
        description="向量嵌入最后更新时间"
    )


# ==========================================
# 创建模型（用于 Service 层创建）
# ==========================================
class SystemSkillCreate(SystemSkillBase):
    """
    用于创建系统级技能的请求体

    使用场景：
    - MethodExtractor 提取新方法后创建
    - 系统管理员手动添加核心方法论

    注意：
    - skill_id 可选，不提供则自动生成
    - confidence_score 初始值由 MethodExtractor 计算
    - status 默认为 active（需要验证）
    """
    skill_id: Optional[str] = None  # 可选，如果不提供则自动生成


# ==========================================
# 更新模型
# ==========================================
class SystemSkillUpdate(SQLModel):
    """
    用于更新系统级技能的请求体

    使用场景：
    - 方法迭代优化时更新 instructions
    - 统计信息更新（injection_count, success_rate）
    - 状态变更（active -> deprecated）
    - 版本升级

    注意：
    - 所有字段可选，仅更新传入的字段
    - 更新后自动刷新 updated_at
    """
    method_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    triggers: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    version: Optional[str] = None
    source_sessions: Optional[List[str]] = None
    confidence_score: Optional[float] = None
    injection_count: Optional[int] = None
    success_rate: Optional[float] = None
    status: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


# ==========================================
# 公开模型（用于内部 Service 返回）
# ==========================================
class SystemSkillPublic(SystemSkillBase):
    """
    系统级技能公开信息

    注意：
    - 此模型主要用于 Service 层内部返回
    - 用户无法直接访问系统级技能
    - 仅在管理员后台或内部调试时使用
    """
    id: int
    skill_id: str
    created_at: datetime
    updated_at: datetime
    combined_embedding: Optional[List[float]] = None
    embedding_updated_at: Optional[datetime] = None