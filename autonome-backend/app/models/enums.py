"""
枚举定义模块

集中定义所有枚举类型
"""

from enum import Enum


# ==========================================
# 聊天相关枚举
# ==========================================
class RoleEnum(str, Enum):
    """消息角色枚举"""
    user = "user"
    assistant = "assistant"
    system = "system"


# ==========================================
# 技能相关枚举
# ==========================================
class SkillStatus(str, Enum):
    """SKILL 技能的状态机"""
    DRAFT = "DRAFT"                 # 草稿：AI 刚生成，还未进行沙箱测试
    PRIVATE = "PRIVATE"             # 私有：沙箱测试通过，仅自己可用
    PENDING_REVIEW = "PENDING_REVIEW"  # 待审核：用户已提交，等待管理员审核
    PUBLISHED = "PUBLISHED"         # 已发布：管理员审核通过，全平台可用
    REJECTED = "REJECTED"           # 已驳回：审核不通过
    DEPRECATED = "DEPRECATED"       # 已弃用：不再维护


class SkillVisibility(str, Enum):
    """技能可见性"""
    PRIVATE = "private"             # 仅自己可见
    TEAM = "team"                   # 团队可见
    PUBLIC = "public"               # 公开


class ExecutionMode(str, Enum):
    """技能执行模式"""
    DOCKER = "docker"               # Docker 容器执行（默认）
    NATIVE = "native"               # 原生系统执行（仅官方技能可用）


# ==========================================
# 经验资产相关枚举
# ==========================================
class ExperienceType(str, Enum):
    """经验资产类型"""
    SUCCESSFUL_SESSION = "successful_session"    # 成功会话
    DEBUG_PATTERN = "debug_pattern"              # 调试模式
    CODE_SNIPPET = "code_snippet"                # 代码片段


# ==========================================
# 权限相关枚举
# ==========================================
class PermissionLevel(str, Enum):
    """权限级别枚举"""
    READ = "READ"        # 只读：查看详情、执行技能
    WRITE = "WRITE"      # 读写：编辑技能
    ADMIN = "ADMIN"      # 管理：编辑、分享、删除


# ==========================================
# 用户包相关枚举
# ==========================================
class PackageLanguage(str, Enum):
    """包语言类型"""
    PYTHON = "python"
    R = "r"


class PackageStatus(str, Enum):
    """包安装状态"""
    PENDING = "PENDING"           # 安装中
    INSTALLED = "INSTALLED"       # 已安装
    FAILED = "FAILED"             # 安装失败
    REMOVED = "REMOVED"           # 已删除


# ==========================================
# 数据库相关枚举
# ==========================================
class DatabaseType(str, Enum):
    """数据库类型枚举"""
    ANNOTATION = "annotation"      # 注释数据库：GO、KEGG、InterPro 等
    PATHWAY = "pathway"           # 信号通路：Reactome、WikiPathways 等
    PROTEIN = "protein"           # 蛋白质：UniProt、PDB 等
    VARIANT = "variant"           # 变异：dbSNP、ClinVar 等
    REGULATION = "regulation"     # 调控：ENCODE、TFbind 等
    METABOLISM = "metabolism"     # 代谢：KEGG Compound、HMDB 等
    CUSTOM = "custom"             # 用户自定义数据库


# ==========================================
# Claude 执行器相关枚举
# ==========================================
class ClaudeCodeSessionStatus(str, Enum):
    """Claude Code 会话状态"""
    ACTIVE = "active"      # 活跃中，可以恢复
    EXPIRED = "expired"    # 已过期，需要新建
    CLOSED = "closed"      # 用户主动关闭