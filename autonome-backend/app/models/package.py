"""
用户包管理模型

包含用户包模型及其创建/公开/配额模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime

from app.models.uuid import generate_package_id
from app.models.enums import PackageLanguage, PackageStatus


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 用户包管理模型 (UserPackage)
# ==========================================
class UserPackage(SQLModel, table=True):
    """
    用户包管理表 - 记录用户安装的 Python/R 包

    核心设计理念：
    - 用户级隔离：每个用户有独立的包目录，互不干扰
    - 系统环境保护：用户包不影响系统预置的 conda 包
    - 版本锁定：记录安装的精确版本，便于复现和审计
    - 配额管理：限制每用户的包存储空间

    环境变量优先级（从高到低）：
    1. /app/user_packages/{user_id}/python  (用户级 Python)
    2. /app/user_packages/{user_id}/r       (用户级 R)
    3. /opt/conda/lib/python3.x/site-packages  (系统级 Python)
    4. /opt/conda/lib/R/library  (系统级 R)
    """
    __tablename__ = "userpackage"

    id: Optional[int] = Field(default=None, primary_key=True)
    package_id: str = Field(
        default_factory=generate_package_id,
        unique=True, index=True, max_length=50,
        description="包记录唯一标识"
    )

    # 所属用户
    user_id: int = Field(foreign_key="user.id", index=True, description="包所属用户")

    # 包信息
    name: str = Field(max_length=255, description="包名称")
    version: Optional[str] = Field(default=None, max_length=100, description="安装的版本号")
    language: str = Field(max_length=20, description="语言类型: python/r")

    # 安装信息
    status: PackageStatus = Field(default=PackageStatus.PENDING, description="安装状态")
    install_source: Optional[str] = Field(default=None, max_length=100, description="安装源: pip/cran/bioconda")
    install_command: Optional[str] = Field(default=None, description="完整的安装命令")

    # 存储信息
    size_bytes: int = Field(default=0, description="包大小（字节）")
    install_path: Optional[str] = Field(default=None, description="实际安装路径")

    # 错误信息
    error_message: Optional[str] = Field(default=None, description="安装失败时的错误信息")

    # 元数据
    description: Optional[str] = Field(default=None, description="包描述")
    homepage: Optional[str] = Field(default=None, max_length=500, description="包主页 URL")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)


class UserPackageCreate(SQLModel):
    """创建用户包请求"""
    name: str = Field(max_length=255, description="包名称")
    version: Optional[str] = Field(default=None, max_length=100, description="指定版本")
    language: str = Field(max_length=20, description="语言类型: python/r")


class UserPackagePublic(SQLModel):
    """用户包公开信息"""
    id: int
    package_id: str
    name: str
    version: Optional[str]
    language: str
    status: PackageStatus
    size_bytes: int
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class UserPackageQuota(SQLModel):
    """用户包配额信息"""
    user_id: int
    total_packages: int = Field(description="已安装包数量")
    total_size_bytes: int = Field(description="已使用空间（字节）")
    max_packages: int = Field(default=100, description="最大包数量")
    max_size_bytes: int = Field(default=2 * 1024 * 1024 * 1024, description="最大空间（2GB）")
    available_size_bytes: int = Field(description="剩余可用空间")