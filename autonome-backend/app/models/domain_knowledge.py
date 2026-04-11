"""
领域知识模型

定义从用户行为和技能执行中提炼的生信领域知识：
1. KnowledgeType - 知识类型枚举
2. KnowledgeSource - 知识来源枚举
3. DomainKnowledgeEntry - 领域知识条目
4. KnowledgeRelation - 知识关系
5. DomainKnowledgeRecord - 数据库持久化模型

设计原则：
- 知识类型：概念、同义词、参数规则、数据特征、错误模式、工作流
- 知识来源：技能专家知识、用户反馈、执行记录、手动输入、系统推导
- 置信度：基于使用次数和验证状态动态计算
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 知识类型枚举
# ==========================================

class KnowledgeType(str, Enum):
    """
    知识类型枚举

    定义系统可以提取和存储的知识类型：
    - CONCEPT: 生信领域核心概念（如"差异表达"、"质控"）
    - SYNONYM: 同义词映射（用户实际使用的表达方式）
    - PARAMETER_RULE: 参数配置规则（最佳实践）
    - DATA_FEATURE: 数据特征（常见数据类型和处理方法）
    - ERROR_PATTERN: 错误模式（常见错误和解决方案）
    - WORKFLOW: 分析工作流（常见分析流程）
    """
    CONCEPT = "concept"                # 概念
    SYNONYM = "synonym"                # 同义词
    PARAMETER_RULE = "parameter_rule"  # 参数规则
    DATA_FEATURE = "data_feature"      # 数据特征
    ERROR_PATTERN = "error_pattern"    # 错误模式
    WORKFLOW = "workflow"              # 工作流


# ==========================================
# 知识来源枚举
# ==========================================

class KnowledgeSource(str, Enum):
    """
    知识来源枚举

    标识知识的来源，用于：
    1. 评估知识可靠性
    2. 追溯知识出处
    3. 区分自动提取和人工验证
    """
    SKILL_EXPERT = "skill_expert"          # 技能专家知识（SKILL.md）
    USER_FEEDBACK = "user_feedback"        # 用户反馈
    EXECUTION_SUCCESS = "execution_success"  # 成功执行记录
    MANUAL_INPUT = "manual_input"          # 手动输入
    SYSTEM_DERIVED = "system_derived"      # 系统推导


# ==========================================
# 领域知识条目模型
# ==========================================

class DomainKnowledgeEntry(BaseModel):
    """
    领域知识条目模型

    存储从用户行为和技能执行中提炼的生信领域知识。
    支持多种知识类型和来源，用于：
    1. 改进技能推荐
    2. 智能参数推断
    3. 同义词扩展
    4. 错误诊断
    """
    knowledge_id: str = Field(description="知识 ID")
    knowledge_type: KnowledgeType = Field(description="知识类型")

    # 核心内容
    concept: str = Field(description="概念/关键词")
    description: str = Field(description="详细描述")

    # 同义词和变体
    synonyms: List[str] = Field(
        default_factory=list,
        description="同义词列表"
    )
    variants: List[str] = Field(
        default_factory=list,
        description="变体表达（如英文缩写）"
    )

    # 关联技能
    related_skills: List[str] = Field(
        default_factory=list,
        description="关联技能 ID 列表"
    )
    related_categories: List[str] = Field(
        default_factory=list,
        description="关联分类列表"
    )

    # 使用上下文
    usage_context: List[str] = Field(
        default_factory=list,
        description="使用上下文（如应用场景）"
    )
    example_queries: List[str] = Field(
        default_factory=list,
        description="示例查询（用户可能的表达方式）"
    )

    # 规则和解决方案（针对参数规则和错误模式）
    rules: Optional[Dict[str, Any]] = Field(
        default=None,
        description="规则详情（针对参数规则类型）"
    )
    solution: Optional[str] = Field(
        default=None,
        description="解决方案（针对错误模式类型）"
    )

    # 元数据
    source: KnowledgeSource = Field(description="知识来源")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="置信度（0-1）"
    )
    usage_count: int = Field(
        default=0,
        ge=0,
        description="使用次数"
    )
    success_count: int = Field(
        default=0,
        ge=0,
        description="成功应用次数"
    )

    # 时间戳
    created_at: datetime = Field(
        default_factory=get_utc_now,
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=get_utc_now,
        description="更新时间"
    )

    # 验证状态
    is_verified: bool = Field(default=False, description="是否已验证")
    verified_by: Optional[str] = Field(default=None, description="验证者")
    verified_at: Optional[datetime] = Field(default=None, description="验证时间")

    @property
    def effective_confidence(self) -> float:
        """计算有效置信度（结合使用次数和验证状态）"""
        base = self.confidence
        if self.is_verified:
            base = min(1.0, base + 0.2)
        if self.usage_count > 0:
            # 使用越多，置信度越高
            usage_boost = min(0.2, self.usage_count / 100)
            base = min(1.0, base + usage_boost)
        return base

    def matches_query(self, query: str) -> bool:
        """检查是否匹配查询"""
        query_lower = query.lower()

        # 直接匹配概念
        if self.concept.lower() in query_lower:
            return True

        # 匹配同义词
        for synonym in self.synonyms:
            if synonym.lower() in query_lower:
                return True

        # 匹配变体
        for variant in self.variants:
            if variant.lower() in query_lower:
                return True

        return False


# ==========================================
# 知识关系模型
# ==========================================

class KnowledgeRelation(BaseModel):
    """
    知识关系模型

    定义知识条目之间的关系，用于构建知识图谱。
    """
    from_knowledge_id: str = Field(description="源知识 ID")
    to_knowledge_id: str = Field(description="目标知识 ID")
    relation_type: str = Field(
        description="关系类型: is_a, part_of, related_to, precedes, follows, solves"
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="关系权重"
    )
    evidence: Optional[str] = Field(
        default=None,
        description="关系证据来源"
    )


# ==========================================
# 知识查询结果
# ==========================================

class KnowledgeQueryResult(BaseModel):
    """知识查询结果"""
    knowledge: DomainKnowledgeEntry
    score: float = Field(description="匹配得分")
    match_type: str = Field(description="匹配类型: exact, synonym, semantic")


# ==========================================
# 数据库持久化模型
# ==========================================

class DomainKnowledgeRecord(SQLModel, table=True):
    """
    领域知识记录表

    持久化存储领域知识条目
    """
    __tablename__ = "domainknowledgerecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    knowledge_id: str = SQLField(unique=True, index=True, description="知识 ID")
    knowledge_type: str = SQLField(index=True, description="知识类型")

    # 核心内容
    concept: str = SQLField(index=True, description="概念")
    description: str = SQLField(description="描述")

    # JSON 字段
    synonyms_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="同义词列表"
    )
    variants_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="变体列表"
    )
    related_skills_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="关联技能"
    )
    related_categories_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="关联分类"
    )
    usage_context_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="使用上下文"
    )
    example_queries_json: Optional[List[str]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="示例查询"
    )
    rules_json: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="规则详情"
    )
    solution: Optional[str] = SQLField(default=None, description="解决方案")

    # 元数据
    source: str = SQLField(description="知识来源")
    confidence: float = SQLField(default=0.5, description="置信度")
    usage_count: int = SQLField(default=0, description="使用次数")
    success_count: int = SQLField(default=0, description="成功次数")

    # 验证状态
    is_verified: bool = SQLField(default=False, description="是否验证")
    verified_by: Optional[str] = SQLField(default=None, description="验证者")

    # 时间戳
    created_at: datetime = SQLField(default_factory=get_utc_now, description="创建时间")
    updated_at: datetime = SQLField(default_factory=get_utc_now, description="更新时间")

    def to_entry(self) -> DomainKnowledgeEntry:
        """转换为 DomainKnowledgeEntry"""
        return DomainKnowledgeEntry(
            knowledge_id=self.knowledge_id,
            knowledge_type=KnowledgeType(self.knowledge_type),
            concept=self.concept,
            description=self.description,
            synonyms=self.synonyms_json or [],
            variants=self.variants_json or [],
            related_skills=self.related_skills_json or [],
            related_categories=self.related_categories_json or [],
            usage_context=self.usage_context_json or [],
            example_queries=self.example_queries_json or [],
            rules=self.rules_json,
            solution=self.solution,
            source=KnowledgeSource(self.source),
            confidence=self.confidence,
            usage_count=self.usage_count,
            success_count=self.success_count,
            is_verified=self.is_verified,
            verified_by=self.verified_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_entry(cls, entry: DomainKnowledgeEntry) -> "DomainKnowledgeRecord":
        """从 DomainKnowledgeEntry 创建记录"""
        return cls(
            knowledge_id=entry.knowledge_id,
            knowledge_type=entry.knowledge_type.value,
            concept=entry.concept,
            description=entry.description,
            synonyms_json=entry.synonyms,
            variants_json=entry.variants,
            related_skills_json=entry.related_skills,
            related_categories_json=entry.related_categories,
            usage_context_json=entry.usage_context,
            example_queries_json=entry.example_queries,
            rules_json=entry.rules,
            solution=entry.solution,
            source=entry.source.value,
            confidence=entry.confidence,
            usage_count=entry.usage_count,
            success_count=entry.success_count,
            is_verified=entry.is_verified,
            verified_by=entry.verified_by,
            updated_at=get_utc_now(),
        )


# ==========================================
# 导出
# ==========================================

__all__ = [
    "KnowledgeType",
    "KnowledgeSource",
    "DomainKnowledgeEntry",
    "KnowledgeRelation",
    "KnowledgeQueryResult",
    "DomainKnowledgeRecord",
]