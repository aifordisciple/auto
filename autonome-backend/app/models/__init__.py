"""
Models package - 数据模型导出

本文件是领域模型的统一入口，实际实现已拆分到多个子模块：

模块结构：
- enums.py: 所有枚举定义
- uuid.py: UUID 生成函数
- user.py: 用户和计费账户模型
- project.py: 项目、数据文件模型
- chat.py: 会话、消息、标签等模型
- task.py: 任务记录模型
- config.py: 系统配置模型
- skill/: 技能相关模型目录
- experience.py: 经验资产模型
- sharing.py: 用户组和分享模型
- package.py: 用户包管理模型
- genome.py: 参考基因组模型
- database.py: 分析数据库模型
- claude_executor.py: Claude 执行器模型
- domain.py: 保留原有入口（向后兼容）
- system_skill.py: 系统级学习技能模型
"""

# ==========================================
# 从模块化入口导入所有模型
# ==========================================
from app.models.domain import (
    # 枚举
    RoleEnum, SkillStatus, SkillVisibility, ExecutionMode,
    ExperienceType, PermissionLevel, PackageLanguage, PackageStatus,
    DatabaseType, ClaudeCodeSessionStatus,
    # UUID 生成函数
    generate_project_id, generate_session_id, generate_msg_id,
    generate_skill_id, generate_share_token, generate_experience_id,
    generate_package_id,
    # 工具函数
    get_utc_now,
    # 用户模型
    User, BillingAccount,
    # 项目模型
    Project, DataFile, ProjectUpdate, PublicDataset,
    # 聊天模型
    ChatSession, ChatMessage, MessageBookmark, SessionSummaryCache,
    ChatSessionTag, SessionTagRelation,
    # 任务模型
    TaskRecord,
    # 系统配置
    SystemConfig,
    # 技能模型
    SkillAssetBase, SkillAsset, SkillAssetCreate, SkillAssetUpdate, SkillAssetPublic,
    SkillVersion, SkillExecutionHistory, SkillFavorite, SkillReview,
    SkillRecommendationLog, SkillMatchingFeedback, ResultShare,
    # 经验资产
    ExperienceAsset, ExperienceAssetCreate, ExperienceAssetUpdate, ExperienceAssetPublic,
    # 用户组和分享
    UserGroup, UserGroupMember, SkillShare, SkillShareGroup,
    SkillShareCreate, SkillShareUpdate, SkillSharePublic,
    # 用户包管理
    UserPackage, UserPackageCreate, UserPackagePublic, UserPackageQuota,
    # 参考基因组
    GenomeAsset, GenomeAssetCreate, GenomeAssetUpdate, GenomeAssetPublic,
    # 分析数据库
    AnalysisDatabase, AnalysisDatabaseCreate, AnalysisDatabaseUpdate, AnalysisDatabasePublic,
    # Claude 执行器
    ClaudeExecutorPermission, ClaudeExecutorPermissionCreate,
    ClaudeExecutorPermissionUpdate, ClaudeExecutorPermissionPublic,
    ClaudeCodeSession, ClaudeCodeSessionCreate, ClaudeCodeSessionUpdate, ClaudeCodeSessionPublic,
)

# 技能模板
from app.models.skill_template import SkillTemplate

# 技能锻造会话
from app.models.forge_session import (
    ForgeSession, ForgeSessionCreate, ForgeSessionUpdate, ForgeSessionPublic,
    ForgeMessage, ForgeMessageCreate, ForgeMessagePublic,
    ForgeStatus, ForgeChatRequest, SkillDraftUpdate, SkillDraftSchema
)

# 系统级学习技能
from app.models.system_skill import (
    SystemSkillStatus,
    MethodType,
    SystemSkill,
    SystemSkillCreate,
    SystemSkillUpdate,
    SystemSkillPublic,
    generate_system_skill_id,
)

__all__ = [
    # 枚举
    "RoleEnum", "SkillStatus", "SkillVisibility", "ExecutionMode",
    "ExperienceType", "PermissionLevel", "PackageLanguage", "PackageStatus",
    "DatabaseType", "ClaudeCodeSessionStatus",

    # UUID 生成函数
    "generate_project_id", "generate_session_id", "generate_msg_id",
    "generate_skill_id", "generate_share_token", "generate_experience_id",
    "generate_package_id",

    # 工具函数
    "get_utc_now",

    # User & Project
    "User", "BillingAccount", "Project", "ProjectUpdate",
    "ChatSession", "ChatMessage", "DataFile", "TaskRecord",
    "SystemConfig", "PublicDataset",

    # Skill
    "SkillAssetBase", "SkillAsset", "SkillAssetCreate", "SkillAssetUpdate", "SkillAssetPublic",
    "SkillVersion", "SkillExecutionHistory", "SkillFavorite", "SkillReview",
    "SkillRecommendationLog", "SkillMatchingFeedback",
    "SkillTemplate",

    # Result & Bookmark
    "ResultShare", "MessageBookmark", "SessionSummaryCache",
    "ChatSessionTag", "SessionTagRelation",

    # Experience
    "ExperienceAsset", "ExperienceAssetCreate", "ExperienceAssetUpdate", "ExperienceAssetPublic",

    # Sharing
    "UserGroup", "UserGroupMember", "SkillShare", "SkillShareGroup",
    "SkillShareCreate", "SkillShareUpdate", "SkillSharePublic",

    # Package
    "UserPackage", "UserPackageCreate", "UserPackagePublic", "UserPackageQuota",

    # Genome
    "GenomeAsset", "GenomeAssetCreate", "GenomeAssetUpdate", "GenomeAssetPublic",

    # Database
    "AnalysisDatabase", "AnalysisDatabaseCreate", "AnalysisDatabaseUpdate", "AnalysisDatabasePublic",

    # Claude Executor
    "ClaudeExecutorPermission", "ClaudeExecutorPermissionCreate",
    "ClaudeExecutorPermissionUpdate", "ClaudeExecutorPermissionPublic",
    "ClaudeCodeSession", "ClaudeCodeSessionCreate", "ClaudeCodeSessionUpdate", "ClaudeCodeSessionPublic",

    # Forge Session
    "ForgeSession", "ForgeSessionCreate", "ForgeSessionUpdate", "ForgeSessionPublic",
    "ForgeMessage", "ForgeMessageCreate", "ForgeMessagePublic",
    "ForgeStatus", "ForgeChatRequest", "SkillDraftUpdate", "SkillDraftSchema",

    # System Skill (系统级学习技能)
    "SystemSkillStatus",
    "MethodType",
    "SystemSkill",
    "SystemSkillCreate",
    "SystemSkillUpdate",
    "SystemSkillPublic",
    "generate_system_skill_id",
]