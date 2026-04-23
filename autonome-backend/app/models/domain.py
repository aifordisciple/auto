"""
领域模型模块 - 向后兼容入口

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

注意：此文件保持向后兼容，所有模型从子模块导入。
新代码应直接从子模块导入以提高可读性。
"""

# ==========================================
# 枚举类型
# ==========================================
from app.models.enums import (
    RoleEnum,
    SkillStatus,
    SkillVisibility,
    ExecutionMode,
    ExperienceType,
    PermissionLevel,
    PackageLanguage,
    PackageStatus,
    DatabaseType,
    LiteratureStatus,
    ChunkType,
)

# ==========================================
# UUID 生成函数
# ==========================================
from app.models.uuid import (
    generate_project_id,
    generate_session_id,
    generate_msg_id,
    generate_skill_id,
    generate_share_token,
    generate_experience_id,
    generate_package_id,
    generate_literature_id,
    generate_chunk_id,
    generate_note_id,
    generate_ltag_id,
)

# ==========================================
# 工具函数
# ==========================================
from app.models.uuid import get_utc_now

# ==========================================
# 用户模型
# ==========================================
from app.models.user import (
    User,
    OAuthAccount,
    ActiveSession,
    BillingAccount,
)

# ==========================================
# 项目模型
# ==========================================
from app.models.project import (
    Project,
    DataFile,
    ProjectUpdate,
    PublicDataset,
)

# ==========================================
# 聊天模型
# ==========================================
from app.models.chat import (
    ChatSession,
    ChatMessage,
    MessageBookmark,
    SessionSummaryCache,
    ChatSessionTag,
    SessionTagRelation,
)

# ==========================================
# 消息队列模型
# ==========================================
from app.models.chat_queue import (
    ChatQueueItem,
    QueueItemStatus,
)

# ==========================================
# 任务模型
# ==========================================
from app.models.task import TaskRecord

# ==========================================
# 系统配置模型
# ==========================================
from app.models.config import SystemConfig

# ==========================================
# 技能模型
# ==========================================
from app.models.skill import (
    # 资产模型
    SkillAssetBase,
    SkillAsset,
    SkillAssetCreate,
    SkillAssetUpdate,
    SkillAssetPublic,
    # 版本模型
    SkillVersion,
    # 执行历史
    SkillExecutionHistory,
    # 收藏
    SkillFavorite,
    # 评价
    SkillReview,
    # 推荐
    SkillRecommendationLog,
    SkillMatchingFeedback,
    # 分享
    ResultShare,
    # 草稿模型
    DraftStatus,
    TriggerSource,
    PendingSkillDraft,
    PendingSkillDraftCreate,
    PendingSkillDraftPublic,
    PendingSkillDraftUpdate,
)

# ==========================================
# 经验资产模型
# ==========================================
from app.models.experience import (
    ExperienceAsset,
    ExperienceAssetCreate,
    ExperienceAssetUpdate,
    ExperienceAssetPublic,
)

# ==========================================
# 用户组和分享模型
# ==========================================
from app.models.sharing import (
    UserGroup,
    UserGroupMember,
    SkillShare,
    SkillShareGroup,
    SkillShareCreate,
    SkillShareUpdate,
    SkillSharePublic,
)

# ==========================================
# 用户包管理模型
# ==========================================
from app.models.package import (
    UserPackage,
    UserPackageCreate,
    UserPackagePublic,
    UserPackageQuota,
)

# ==========================================
# 参考基因组模型
# ==========================================
from app.models.genome import (
    GenomeAsset,
    GenomeAssetCreate,
    GenomeAssetUpdate,
    GenomeAssetPublic,
)

# ==========================================
# 分析数据库模型
# ==========================================
from app.models.database import (
    AnalysisDatabase,
    AnalysisDatabaseCreate,
    AnalysisDatabaseUpdate,
    AnalysisDatabasePublic,
)

# ==========================================
# 学习中心模型
# ==========================================
from app.models.learning import (
    Literature,
    LiteratureCreate,
    LiteratureUpdate,
    LiteraturePublic,
    LiteratureChunk,
    LiteratureChunkCreate,
    LiteratureChunkUpdate,
    LiteratureChunkPublic,
    LiteratureNote,
    LiteratureNoteCreate,
    LiteratureNoteUpdate,
    LiteratureNotePublic,
    LiteratureTag,
    LiteratureTagCreate,
    LiteratureTagUpdate,
    LiteratureTagPublic,
)

# ==========================================
# RBAC 权限模型
# ==========================================
from app.models.rbac import (
    Role,
    Permission,
    AuditLog,
)

# ==========================================
# 导入其他模型以确保数据库表被创建
# ==========================================
from app.models.skill_template import SkillTemplate  # noqa: F401
from app.models.forge_session import ForgeSession, ForgeMessage  # noqa: F401

# ==========================================
# 计费模型导入（放在文件末尾避免循环导入）
# ==========================================
from app.models.billing import Wallet, ComputeRecord, TransactionLedger, ResourceFlavor  # noqa: F401


# ==========================================
# 统一导出所有模型
# ==========================================
__all__ = [
    # 枚举
    "RoleEnum",
    "SkillStatus",
    "SkillVisibility",
    "ExecutionMode",
    "ExperienceType",
    "PermissionLevel",
    "PackageLanguage",
    "PackageStatus",
    "DatabaseType",
    "LiteratureStatus",
    "ChunkType",
    # UUID 生成函数
    "generate_project_id",
    "generate_session_id",
    "generate_msg_id",
    "generate_skill_id",
    "generate_share_token",
    "generate_experience_id",
    "generate_package_id",
    "generate_literature_id",
    "generate_chunk_id",
    "generate_note_id",
    "generate_ltag_id",
    # 工具函数
    "get_utc_now",
    # 用户模型
    "User",
    "OAuthAccount",
    "ActiveSession",
    "BillingAccount",
    # 项目模型
    "Project",
    "DataFile",
    "ProjectUpdate",
    "PublicDataset",
    # 聊天模型
    "ChatSession",
    "ChatMessage",
    "MessageBookmark",
    "SessionSummaryCache",
    "ChatSessionTag",
    "SessionTagRelation",
    # 消息队列模型
    "ChatQueueItem",
    "QueueItemStatus",
    # 任务模型
    "TaskRecord",
    # 系统配置
    "SystemConfig",
    # 技能模型
    "SkillAssetBase",
    "SkillAsset",
    "SkillAssetCreate",
    "SkillAssetUpdate",
    "SkillAssetPublic",
    "SkillVersion",
    "SkillExecutionHistory",
    "SkillFavorite",
    "SkillReview",
    "SkillRecommendationLog",
    "SkillMatchingFeedback",
    "ResultShare",
    # 技能草稿模型
    "DraftStatus",
    "TriggerSource",
    "PendingSkillDraft",
    "PendingSkillDraftCreate",
    "PendingSkillDraftPublic",
    "PendingSkillDraftUpdate",
    # 经验资产
    "ExperienceAsset",
    "ExperienceAssetCreate",
    "ExperienceAssetUpdate",
    "ExperienceAssetPublic",
    # 用户组和分享
    "UserGroup",
    "UserGroupMember",
    "SkillShare",
    "SkillShareGroup",
    "SkillShareCreate",
    "SkillShareUpdate",
    "SkillSharePublic",
    # 用户包管理
    "UserPackage",
    "UserPackageCreate",
    "UserPackagePublic",
    "UserPackageQuota",
    # 参考基因组
    "GenomeAsset",
    "GenomeAssetCreate",
    "GenomeAssetUpdate",
    "GenomeAssetPublic",
    # 分析数据库
    "AnalysisDatabase",
    "AnalysisDatabaseCreate",
    "AnalysisDatabaseUpdate",
    "AnalysisDatabasePublic",
    # 学习中心
    "Literature",
    "LiteratureCreate",
    "LiteratureUpdate",
    "LiteraturePublic",
    "LiteratureChunk",
    "LiteratureChunkCreate",
    "LiteratureChunkUpdate",
    "LiteratureChunkPublic",
    "LiteratureNote",
    "LiteratureNoteCreate",
    "LiteratureNoteUpdate",
    "LiteratureNotePublic",
    "LiteratureTag",
    "LiteratureTagCreate",
    "LiteratureTagUpdate",
    "LiteratureTagPublic",
    # RBAC 权限模型
    "Role",
    "Permission",
    "AuditLog",
]
