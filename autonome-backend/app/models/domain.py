from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
import uuid

# 导入其他模型以确保数据库表被创建
from app.models.skill_template import SkillTemplate  # noqa: F401
from app.models.forge_session import ForgeSession, ForgeMessage  # noqa: F401

# ✨ 引入 pgvector 的 Vector 类型
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # 如果 pgvector 未安装，提供一个 dummy Vector 类型
    class Vector:
        def __init__(self, dimension=None):
            self.dimension = dimension


# ==========================================
# ✨ UUID 生成函数 (商业级 ID)
# ==========================================
def generate_project_id():
    return f"proj_{uuid.uuid4().hex[:12]}"

def generate_session_id():
    return f"chat_{uuid.uuid4().hex[:12]}"

def generate_msg_id():
    return f"msg_{uuid.uuid4().hex[:16]}"


# ==========================================
# 0. 定义枚举 (规范字段)
# ==========================================
class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class SkillStatus(str, Enum):
    """SKILL 技能的状态机"""
    DRAFT = "DRAFT"                 # 草稿：AI 刚生成，还未进行沙箱测试
    PRIVATE = "PRIVATE"             # 私有：沙箱测试通过，仅自己可用
    PENDING_REVIEW = "PENDING_REVIEW"  # 待审核：用户已提交，等待管理员审核
    PUBLISHED = "PUBLISHED"         # 已发布：管理员审核通过，全平台可用
    REJECTED = "REJECTED"           # 已驳回：审核不通过


def get_utc_now():
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    return datetime.now(timezone.utc)


# ==========================================
# -1. 用户表 (User - Multi-tenant)
# ==========================================
class User(SQLModel, table=True):
    """User - Multi-tenant SaaS 用户表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=255)
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=get_utc_now)
    
    # 关系：一个用户可以有多个项目
    projects: List["Project"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    # 关系：一个用户只有一个计费账户
    billing: Optional["BillingAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# -2. 计费账户表 (BillingAccount)
# ==========================================
class BillingAccount(SQLModel, table=True):
    """BillingAccount - 用户计费与算力余额"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    credits_balance: float = Field(default=100.0)  # 初始送 100 点算力
    total_consumed: float = Field(default=0.0)    # 历史累计消耗
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
    
    user: Optional[User] = Relationship(back_populates="billing")


# ==========================================
# 1. 项目表 (Project/Workspace)
# ==========================================
class Project(SQLModel, table=True):
    # ✨ 修改为主键字符串，使用默认工厂函数自动生成
    id: str = Field(default_factory=generate_project_id, primary_key=True, index=True)
    name: str = Field(index=True, max_length=100)
    description: Optional[str] = None
    # ✨ 新增字段
    icon: str = Field(default="📁")
    status: str = Field(default="active", index=True)  # "active" 或 "archived"
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # ✨ 多租户：增加项目所有者
    owner_id: int = Field(foreign_key="user.id", index=True)
    
    # ✨ 分享与公开状态字段 (Growth Hacker 病毒传播)
    is_public: bool = Field(default=False)
    share_token: Optional[str] = Field(default=None, index=True)
    
    owner: Optional[User] = Relationship(back_populates="projects")
    
    # ✨ 增加级联删除
    sessions: List["ChatSession"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    files: List["DataFile"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 2. 会话表 (Chat Session)
# ==========================================
class ChatSession(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_session_id, primary_key=True, index=True)
    title: str = Field(default="默认分析会话", max_length=200)
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)
    
    project: Optional[Project] = Relationship(back_populates="sessions")
    messages: List["ChatMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 3. 聊天记录表 (ChatMessage)
# ==========================================
class ChatMessage(SQLModel, table=True):
    # ✨ 修改为主键字符串
    id: str = Field(default_factory=generate_msg_id, primary_key=True, index=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)  # ✨ 外键改为 str
    role: RoleEnum
    content: str
    created_at: datetime = Field(default_factory=get_utc_now)
    
    session: Optional["ChatSession"] = Relationship(back_populates="messages")


# ==========================================
# 4. 文件表 (Data File Meta)
# ==========================================
class DataFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  # 文件ID保持int
    filename: str
    file_path: str
    file_size: int
    file_type: Optional[str] = None
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    uploaded_at: datetime = Field(default_factory=get_utc_now)
    
    project: Optional[Project] = Relationship(back_populates="files")


# ==========================================
# 5. 任务记录表 (Task Record)
# ==========================================
class TaskRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    tool_id: str
    parameters: str
    status: str = Field(index=True)
    result: Optional[str] = None
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)
    completed_at: Optional[datetime] = None


# ==========================================
# 6. 系统全局配置表 (System Settings)
# ==========================================
class SystemConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    openai_api_key: Optional[str] = None
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    default_model: str = Field(default="gpt-3.5-turbo")
    theme: str = Field(default="dark")
    updated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 7.1 项目更新 Schema
# ==========================================
class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    status: Optional[str] = None


# ==========================================
# 7. 公共数据集 (PublicDataset)
# ==========================================
class PublicDataset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    accession: str = Field(index=True)
    title: str
    summary: str
    organism: Optional[str] = None
    source_url: str
    owner_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 8. SKILL 资产库模型 (SkillAsset)
# ==========================================
def generate_skill_id():
    """生成 SKILL 唯一 ID"""
    return f"skill_{uuid.uuid4().hex[:8]}"


class SkillAssetBase(SQLModel):
    """SKILL 资产基础模型"""
    name: str = Field(max_length=255, description="SKILL的显示名称")
    description: Optional[str] = Field(default=None, description="一句话简介")
    version: str = Field(default="1.0.0", max_length=50)
    executor_type: str = Field(default="Python_env", max_length=50)

    # 核心资产内容
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None)
    script_code: Optional[str] = Field(default=None, description="实际执行的Python/R代码")
    dependencies: List[str] = Field(default_factory=list, sa_column=Column(JSONB))

    # 状态控制
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    reject_reason: Optional[str] = Field(default=None, description="如果被驳回，管理员填写的理由")


class SkillAsset(SkillAssetBase, table=True):
    """SKILL 资产数据库表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(default_factory=generate_skill_id, unique=True, index=True, max_length=100, description="全局唯一的英文ID")
    owner_id: int = Field(foreign_key="user.id", index=True, description="创建者的User ID")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class SkillAssetCreate(SkillAssetBase):
    """用于前端创建 SKILL 的请求体"""
    skill_id: Optional[str] = None  # 可选，如果不提供则自动生成


class SkillAssetUpdate(SQLModel):
    """用于更新 SKILL 的请求体"""
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    executor_type: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    expert_knowledge: Optional[str] = None
    script_code: Optional[str] = None
    dependencies: Optional[List[str]] = None


class SkillAssetPublic(SkillAssetBase):
    """返回给前端的 SKILL 公共信息"""
    id: int
    skill_id: str
    owner_id: int
    created_at: datetime
    updated_at: datetime


# ==========================================
# 9. SKILL 版本管理模型 (SkillVersion)
# ==========================================
class SkillVersion(SQLModel, table=True):
    """SKILL 版本历史表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="关联的技能 ID")
    version: str = Field(max_length=50, description="版本号")
    script_code: Optional[str] = Field(default=None, description="该版本的代码")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=get_utc_now)
    created_by: int = Field(foreign_key="user.id", index=True)
    change_log: Optional[str] = Field(default=None, description="版本变更说明")


# ==========================================
# 10. SKILL 执行历史模型 (SkillExecutionHistory)
# ==========================================
class SkillExecutionHistory(SQLModel, table=True):
    """SKILL 执行历史记录表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="执行的技能 ID")
    skill_name: Optional[str] = Field(default=None, description="技能名称快照")
    user_id: int = Field(index=True, foreign_key="user.id")
    project_id: str = Field(index=True, foreign_key="project.id")
    session_id: Optional[str] = Field(default=None, description="聊天会话 ID")
    parameters: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = Field(default="PENDING", index=True, description="执行状态: PENDING/SUCCESS/FAILURE")
    result_summary: Optional[str] = Field(default=None, description="结果摘要")
    execution_time: Optional[float] = Field(default=None, description="执行耗时（秒）")
    output_dir: Optional[str] = Field(default=None, description="输出目录路径")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 11. SKILL 收藏模型 (SkillFavorite)
# ==========================================
class SkillFavorite(SQLModel, table=True):
    """SKILL 收藏表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="收藏的技能 ID")
    user_id: int = Field(index=True, foreign_key="user.id")
    created_at: datetime = Field(default_factory=get_utc_now)

    class Config:
        # 联合唯一约束：同一用户不能重复收藏同一技能
        # 注：实际约束需要在数据库层面通过 migration 实现
        pass


# ==========================================
# 12. SKILL 评价模型 (SkillReview)
# ==========================================
class SkillReview(SQLModel, table=True):
    """SKILL 评价表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="评价的技能 ID")
    user_id: int = Field(index=True, foreign_key="user.id")
    rating: int = Field(ge=1, le=5, description="评分 1-5 星")
    comment: Optional[str] = Field(default=None, description="评价内容")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 13. 结果分享模型 (ResultShare)
# ==========================================
def generate_share_token():
    """生成分享令牌"""
    return f"share_{uuid.uuid4().hex[:12]}"


class ResultShare(SQLModel, table=True):
    """结果分享表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True, description="关联的任务 ID")
    share_token: str = Field(default_factory=generate_share_token, unique=True, index=True)
    created_by: int = Field(foreign_key="user.id", index=True)
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    access_count: int = Field(default=0, description="访问次数")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 14. 消息收藏模型 (MessageBookmark)
# ==========================================
class MessageBookmark(SQLModel, table=True):
    """消息收藏表 - 用于收藏重要消息并添加笔记"""
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(foreign_key="chatmessage.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    note: Optional[str] = Field(default=None, description="收藏笔记")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 15. 会话摘要缓存模型 (SessionSummaryCache)
# ==========================================
class SessionSummaryCache(SQLModel, table=True):
    """会话摘要缓存表 - 存储 AI 生成的会话摘要"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", unique=True, index=True)
    summary: str = Field(description="会话摘要内容")
    key_points: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="关键要点列表")
    generated_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 16. 会话标签模型 (ChatSessionTag)
# ==========================================
class ChatSessionTag(SQLModel, table=True):
    """会话标签表 - 用户自定义标签"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=50, index=True, description="标签名称")
    color: str = Field(default="#3B82F6", description="标签颜色")
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 17. 会话标签关联模型 (SessionTagRelation)
# ==========================================
class SessionTagRelation(SQLModel, table=True):
    """会话标签关联表 - 多对多关系"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    tag_id: int = Field(foreign_key="chatsessiontag.id", index=True)
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 18. 经验资产类型枚举 (ExperienceType)
# ==========================================
class ExperienceType(str, Enum):
    """经验资产类型"""
    SUCCESSFUL_SESSION = "successful_session"    # 成功会话
    DEBUG_PATTERN = "debug_pattern"              # 调试模式
    CODE_SNIPPET = "code_snippet"                # 代码片段


# ==========================================
# 19. 经验资产模型 (ExperienceAsset)
# ==========================================
def generate_experience_id():
    """生成经验资产唯一 ID"""
    return f"exp_{uuid.uuid4().hex[:8]}"


class ExperienceAsset(SQLModel, table=True):
    """经验资产表 - 用户成功经验的沉淀"""
    __tablename__ = "experienceasset"

    id: Optional[int] = Field(default=None, primary_key=True)
    experience_id: str = Field(
        default_factory=generate_experience_id,
        unique=True, index=True, max_length=50,
        description="经验资产唯一标识"
    )

    # 来源追溯
    source_session_id: Optional[str] = Field(default=None, foreign_key="chatsession.id", index=True)
    source_user_id: int = Field(foreign_key="user.id", index=True)
    source_project_id: Optional[str] = Field(default=None, foreign_key="project.id")

    # 经验内容
    experience_type: ExperienceType = Field(default=ExperienceType.SUCCESSFUL_SESSION)
    title: str = Field(max_length=255, description="经验标题")
    summary: str = Field(description="经验摘要（用户需求+解决方案）")
    key_insights: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="关键洞察列表")

    # 核心内容
    original_query: str = Field(description="用户原始问题")
    solution_code: Optional[str] = Field(default=None, description="核心解决方案代码")
    solution_strategy: Optional[str] = Field(default=None, description="解决策略描述")
    debug_iterations: int = Field(default=0, description="调试迭代次数")

    # 向量化（使用 pgvector）
    summary_embedding: Optional[List[float]] = Field(
        default=None, sa_column=Column(Vector(1536)), description="摘要向量嵌入"
    )

    # 元数据
    category: str = Field(default="general", max_length=50, description="经验分类: qc/analysis/visualization/pipeline/general")
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB), description="标签列表")

    # 质量评分
    usefulness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="有用性评分")
    reuse_count: int = Field(default=0, description="被复用次数")

    # 状态
    is_public: bool = Field(default=False, description="是否公开")
    is_verified: bool = Field(default=False, description="是否已验证")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class ExperienceAssetCreate(SQLModel):
    """创建经验资产的请求体"""
    title: str
    summary: str
    key_insights: List[str] = []
    original_query: str
    solution_code: Optional[str] = None
    solution_strategy: Optional[str] = None
    category: str = "general"
    tags: List[str] = []
    source_session_id: Optional[str] = None
    source_project_id: Optional[str] = None
    is_public: bool = False


class ExperienceAssetUpdate(SQLModel):
    """更新经验资产的请求体"""
    title: Optional[str] = None
    summary: Optional[str] = None
    key_insights: Optional[List[str]] = None
    solution_code: Optional[str] = None
    solution_strategy: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class ExperienceAssetPublic(SQLModel):
    """返回给前端的经验资产公共信息"""
    id: int
    experience_id: str
    title: str
    summary: str
    key_insights: List[str]
    original_query: str
    solution_code: Optional[str]
    solution_strategy: Optional[str]
    category: str
    tags: List[str]
    usefulness_score: float
    reuse_count: int
    is_public: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


# ==========================================
# 20. 用户组模型 (UserGroup)
# ==========================================
class UserGroup(SQLModel, table=True):
    """用户组表 - 用于团队协作"""
    __tablename__ = "usergroup"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, description="组名称")
    description: Optional[str] = Field(default=None, description="组描述")
    owner_id: int = Field(foreign_key="user.id", index=True, description="组创建者")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class UserGroupMember(SQLModel, table=True):
    """用户组成员关联表"""
    __tablename__ = "usergroupmember"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="usergroup.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    role: str = Field(default="member", description="角色: owner/admin/member")
    joined_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 21. 技能分享模型 (SkillShare)
# ==========================================
class PermissionLevel(str, Enum):
    """权限级别枚举"""
    READ = "READ"        # 只读：查看详情、执行技能
    WRITE = "WRITE"      # 读写：编辑技能
    ADMIN = "ADMIN"      # 管理：编辑、分享、删除


class SkillShare(SQLModel, table=True):
    """技能分享表 - 分享给特定用户"""
    __tablename__ = "skillshare"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="技能 ID")
    shared_with_user_id: int = Field(foreign_key="user.id", index=True, description="被分享用户")
    permission_level: str = Field(default="READ", description="权限级别: READ/WRITE/ADMIN")
    shared_by: int = Field(foreign_key="user.id", description="分享者")
    created_at: datetime = Field(default_factory=get_utc_now)


class SkillShareGroup(SQLModel, table=True):
    """技能分享给用户组表"""
    __tablename__ = "skillsharegroup"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: str = Field(index=True, description="技能 ID")
    group_id: int = Field(foreign_key="usergroup.id", index=True, description="用户组")
    permission_level: str = Field(default="READ", description="权限级别")
    shared_by: int = Field(foreign_key="user.id", description="分享者")
    created_at: datetime = Field(default_factory=get_utc_now)


# ==========================================
# 请求/响应模型
# ==========================================
class SkillShareCreate(SQLModel):
    """创建技能分享请求"""
    skill_id: str
    user_ids: List[int] = Field(default_factory=list, description="分享给用户列表")
    group_ids: List[int] = Field(default_factory=list, description="分享给用户组列表")
    permission_level: str = Field(default="READ", description="权限级别")


class SkillShareUpdate(SQLModel):
    """更新权限请求"""
    permission_level: str


class SkillSharePublic(SQLModel):
    """技能分享公开信息"""
    id: int
    skill_id: str
    shared_with_user_id: Optional[int] = None
    group_id: Optional[int] = None
    permission_level: str
    shared_by: int
    created_at: datetime
