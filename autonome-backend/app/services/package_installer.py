"""
Package Installer Service - 用户包安装服务

核心功能：
1. 用户级包安装（Python/R）
2. 包依赖检查与自动安装
3. 磁盘配额管理
4. 安全黑名单验证

设计理念：
- 用户包独立存储，不污染系统环境
- 支持不同用户安装不同版本的同名包
- 安装过程在隔离的 Docker 容器中执行
- 完整的审计日志

环境变量优先级（从高到低）：
1. /app/user_packages/{user_id}/python  (用户级 Python)
2. /app/user_packages/{user_id}/r       (用户级 R)
3. /opt/conda/lib/python3.x/site-packages  (系统级 Python)
4. /opt/conda/lib/R/library  (系统级 R)
"""

import os
import re
import json
import time
import shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

from sqlmodel import Session, select
from app.core.logger import log
from app.models.domain import (
    UserPackage,
    UserPackageCreate,
    UserPackageQuota,
    PackageLanguage,
    PackageStatus,
)


# ==========================================
# ✨ 配置常量
# ==========================================

# 用户包存储路径
USER_PACKAGES_HOST_PATH = "/opt/data1/public/software/systools/autonome/uploads/user_packages"
USER_PACKAGES_CONTAINER_PATH = "/app/user_packages"

# 配额限制
MAX_PACKAGES_PER_USER = 100  # 每用户最多安装包数量
MAX_SIZE_PER_USER = 2 * 1024 * 1024 * 1024  # 每用户最多 2GB

# 包安装超时
PACKAGE_INSTALL_TIMEOUT = 600  # 10 分钟

# ✨ 包黑名单（禁止安装的危险包）
PACKAGE_BLACKLIST = {
    "python": {
        # 系统级危险包
        "setuptools", "pip", "wheel", "distribute",
        # 可能破坏环境的包
        "systemd-python", "dbus-python",
        # 需要特殊权限的包
        "pywin32", "pywinctl",
    },
    "r": {
        # 系统级 R 包
        "base", "utils", "stats", "graphics", "grDevices",
        # 需要特殊编译的包
    }
}

# ✨ 包大小估算（常用包的预估大小，单位：MB）
PACKAGE_SIZE_ESTIMATES = {
    "python": {
        "numpy": 50,
        "pandas": 100,
        "scipy": 80,
        "matplotlib": 60,
        "seaborn": 20,
        "scikit-learn": 100,
        "tensorflow": 500,
        "torch": 800,
        "gseapy": 30,
        "scanpy": 150,
        "anndata": 30,
    },
    "r": {
        "Seurat": 150,
        "ggplot2": 30,
        "dplyr": 20,
        "tidyr": 15,
        "SingleCellExperiment": 100,
        "monocle3": 200,
    }
}


class PackageInstallerError(Exception):
    """包安装错误"""
    pass


class PackageInstaller:
    """
    用户包安装服务

    负责：
    1. 检查包是否可安装（黑名单、配额）
    2. 在 Docker 容器中执行安装
    3. 记录安装结果到数据库
    """

    def __init__(self, session: Session):
        """
        初始化包安装服务

        Args:
            session: SQLModel 数据库会话
        """
        self.session = session

    # ==========================================
    # ✨ 公共 API
    # ==========================================

    def install_package(
        self,
        user_id: int,
        package_name: str,
        language: str,
        version: Optional[str] = None,
    ) -> UserPackage:
        """
        安装包到用户目录

        Args:
            user_id: 用户 ID
            package_name: 包名称
            language: 语言类型 (python/r)
            version: 指定版本（可选）

        Returns:
            UserPackage 记录

        Raises:
            PackageInstallerError: 安装失败
        """
        # 标准化语言类型
        language = language.lower()
        if language not in ["python", "r"]:
            raise PackageInstallerError(f"不支持的语言类型: {language}")

        # 检查黑名单
        if self._is_blacklisted(package_name, language):
            raise PackageInstallerError(f"包 {package_name} 在黑名单中，禁止安装")

        # 检查配额
        quota = self.get_quota(user_id)
        estimated_size = self._estimate_package_size(package_name, language)
        if quota.total_size_bytes + estimated_size > quota.max_size_bytes:
            raise PackageInstallerError(
                f"磁盘配额不足。已使用 {self._format_size(quota.total_size_bytes)}，"
                f"预估需要 {self._format_size(estimated_size)}"
            )

        if quota.total_packages >= quota.max_packages:
            raise PackageInstallerError(
                f"已达到包数量上限 ({quota.max_packages})"
            )

        # 检查是否已安装
        existing = self._get_user_package(user_id, package_name, language)
        if existing and existing.status == PackageStatus.INSTALLED:
            log.info(f"[PackageInstaller] 包 {package_name} 已安装，跳过")
            return existing

        # 创建包记录
        package = UserPackage(
            user_id=user_id,
            name=package_name,
            version=version,
            language=language,
            status=PackageStatus.PENDING,
        )
        self.session.add(package)
        self.session.commit()
        self.session.refresh(package)

        log.info(f"[PackageInstaller] 开始安装包: {package_name} (language={language}, user={user_id})")

        try:
            # 执行安装
            output, exit_code = self._execute_install(
                user_id, package_name, language, version
            )

            if exit_code == 0:
                # 安装成功
                package.status = PackageStatus.INSTALLED
                package.install_path = self._get_user_package_path(user_id, language)
                package.size_bytes = self._calculate_package_size(user_id, package_name, language)
                package.error_message = None

                # 解析安装的版本
                installed_version = self._parse_installed_version(output, language)
                if installed_version:
                    package.version = installed_version

                log.info(f"[PackageInstaller] 包 {package_name} 安装成功")
            else:
                # 安装失败
                package.status = PackageStatus.FAILED
                package.error_message = output[:2000]  # 截断错误信息

                log.error(f"[PackageInstaller] 包 {package_name} 安装失败: {output[:500]}")

            self.session.add(package)
            self.session.commit()
            self.session.refresh(package)

            return package

        except Exception as e:
            log.error(f"[PackageInstaller] 安装异常: {e}")
            package.status = PackageStatus.FAILED
            package.error_message = str(e)
            self.session.add(package)
            self.session.commit()
            raise PackageInstallerError(f"安装失败: {str(e)}")

    def check_package_installed(
        self,
        user_id: int,
        package_name: str,
        language: str,
    ) -> bool:
        """
        检查包是否已安装在用户目录或系统目录

        Args:
            user_id: 用户 ID
            package_name: 包名称
            language: 语言类型

        Returns:
            True 如果包已安装
        """
        # 1. 检查用户目录
        user_pkg = self._get_user_package(user_id, package_name, language)
        if user_pkg and user_pkg.status == PackageStatus.INSTALLED:
            return True

        # 2. 检查系统预装包
        return self._check_system_package(package_name, language)

    def get_user_packages(
        self,
        user_id: int,
        language: Optional[str] = None,
        status: Optional[PackageStatus] = None,
    ) -> List[UserPackage]:
        """
        获取用户安装的包列表

        Args:
            user_id: 用户 ID
            language: 过滤语言类型
            status: 过滤状态

        Returns:
            包列表
        """
        statement = select(UserPackage).where(UserPackage.user_id == user_id)

        if language:
            statement = statement.where(UserPackage.language == language.lower())

        if status:
            statement = statement.where(UserPackage.status == status)

        statement = statement.order_by(UserPackage.created_at.desc())

        return self.session.exec(statement).all()

    def get_quota(self, user_id: int) -> UserPackageQuota:
        """
        获取用户包配额信息

        Args:
            user_id: 用户 ID

        Returns:
            配额信息
        """
        packages = self.get_user_packages(user_id, status=PackageStatus.INSTALLED)

        total_packages = len(packages)
        total_size_bytes = sum(p.size_bytes for p in packages)

        return UserPackageQuota(
            user_id=user_id,
            total_packages=total_packages,
            total_size_bytes=total_size_bytes,
            max_packages=MAX_PACKAGES_PER_USER,
            max_size_bytes=MAX_SIZE_PER_USER,
            available_size_bytes=MAX_SIZE_PER_USER - total_size_bytes,
        )

    def remove_package(
        self,
        user_id: int,
        package_name: str,
        language: str,
    ) -> bool:
        """
        删除用户安装的包

        Args:
            user_id: 用户 ID
            package_name: 包名称
            language: 语言类型

        Returns:
            True 如果删除成功
        """
        package = self._get_user_package(user_id, package_name, language)
        if not package:
            return False

        # 执行删除（在容器中）
        output, exit_code = self._execute_remove(user_id, package_name, language)

        if exit_code == 0:
            package.status = PackageStatus.REMOVED
            self.session.add(package)
            self.session.commit()
            log.info(f"[PackageInstaller] 包 {package_name} 已删除")
            return True
        else:
            log.error(f"[PackageInstaller] 删除包失败: {output}")
            return False

    def check_missing_dependencies(
        self,
        user_id: int,
        required_packages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        检查缺失的依赖包

        Args:
            user_id: 用户 ID
            required_packages: 需要的包列表 [{"name": "numpy", "language": "python"}, ...]

        Returns:
            缺失的包列表
        """
        missing = []
        for pkg in required_packages:
            name = pkg.get("name")
            language = pkg.get("language", "python")

            if not self.check_package_installed(user_id, name, language):
                missing.append({
                    "name": name,
                    "language": language,
                    "version": pkg.get("version"),
                })

        return missing

    # ==========================================
    # ✨ 私有方法
    # ==========================================

    def _execute_install(
        self,
        user_id: int,
        package_name: str,
        language: str,
        version: Optional[str] = None,
    ) -> Tuple[str, int]:
        """
        在 Docker 容器中执行包安装

        Returns:
            (输出日志, 退出码)
        """
        from app.tools.bio_tools import run_container

        user_pkg_dir = f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"

        if language == "python":
            # pip install --target
            target_dir = f"{user_pkg_dir}/python"
            if version:
                cmd = ["pip", "install", "--target", target_dir, f"{package_name}=={version}"]
            else:
                cmd = ["pip", "install", "--target", target_dir, package_name]
        else:  # r
            # Rscript -e "install.packages(...)"
            r_lib_path = f"{user_pkg_dir}/r"
            if version:
                r_code = f'install.packages("{package_name}", lib="{r_lib_path}", version="{version}")'
            else:
                r_code = f'install.packages("{package_name}", lib="{r_lib_path}")'
            cmd = ["Rscript", "-e", r_code]

        log.info(f"[PackageInstaller] 执行安装命令: {' '.join(cmd)}")

        # 使用有网络模式执行安装
        output, exit_code = run_container(
            image='autonome-tool-env',
            command=cmd,
            language=language,
            timeout=PACKAGE_INSTALL_TIMEOUT,
            cli_mode=True,
            user_id=user_id,
            enable_network=True,  # ✨ 启用网络以下载包
        )

        return output, exit_code

    def _execute_remove(
        self,
        user_id: int,
        package_name: str,
        language: str,
    ) -> Tuple[str, int]:
        """
        删除用户包

        Returns:
            (输出日志, 退出码)
        """
        from app.tools.bio_tools import run_container

        user_pkg_dir = f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"

        if language == "python":
            # pip uninstall
            target_dir = f"{user_pkg_dir}/python"
            cmd = ["pip", "uninstall", "-y", "--target", target_dir, package_name]
        else:  # r
            # Rscript -e "remove.packages(...)"
            r_lib_path = f"{user_pkg_dir}/r"
            r_code = f'remove.packages("{package_name}", lib="{r_lib_path}")'
            cmd = ["Rscript", "-e", r_code]

        output, exit_code = run_container(
            image='autonome-tool-env',
            command=cmd,
            language=language,
            timeout=60,
            cli_mode=True,
            user_id=user_id,
            enable_network=False,
        )

        return output, exit_code

    def _is_blacklisted(self, package_name: str, language: str) -> bool:
        """检查包是否在黑名单中"""
        blacklist = PACKAGE_BLACKLIST.get(language, set())
        return package_name.lower() in {b.lower() for b in blacklist}

    def _get_user_package(
        self,
        user_id: int,
        package_name: str,
        language: str,
    ) -> Optional[UserPackage]:
        """获取用户包记录"""
        statement = select(UserPackage).where(
            UserPackage.user_id == user_id,
            UserPackage.name == package_name,
            UserPackage.language == language,
        ).order_by(UserPackage.created_at.desc())

        return self.session.exec(statement).first()

    def _get_user_package_path(self, user_id: int, language: str) -> str:
        """获取用户包安装路径"""
        return f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}/{language}"

    def _check_system_package(self, package_name: str, language: str) -> bool:
        """
        检查系统是否预装了该包

        通过在容器中执行 import/library 调用来检测
        """
        from app.tools.bio_tools import run_container

        if language == "python":
            cmd = ["python", "-c", f"import {package_name}; print('OK')"]
        else:
            cmd = ["Rscript", "-e", f'library({package_name}); print("OK")']

        # 不使用 user_id，这样会检测系统包
        output, exit_code = run_container(
            image='autonome-tool-env',
            command=cmd,
            language=language,
            timeout=30,
            cli_mode=True,
            user_id=None,  # 不使用用户包
            enable_network=False,
        )

        return exit_code == 0 and "OK" in output

    def _estimate_package_size(self, package_name: str, language: str) -> int:
        """估算包大小"""
        estimates = PACKAGE_SIZE_ESTIMATES.get(language, {})
        size_mb = estimates.get(package_name, 50)  # 默认 50MB
        return size_mb * 1024 * 1024

    def _calculate_package_size(self, user_id: int, package_name: str, language: str) -> int:
        """计算实际安装的包大小"""
        host_pkg_path = Path(USER_PACKAGES_HOST_PATH) / f"user_{user_id}" / language

        if not host_pkg_path.exists():
            return 0

        # 查找包目录
        total_size = 0
        for item in host_pkg_path.iterdir():
            if item.name.lower().startswith(package_name.lower()):
                if item.is_file():
                    total_size += item.stat().st_size
                elif item.is_dir():
                    for root, dirs, files in os.walk(item):
                        for f in files:
                            total_size += os.path.getsize(os.path.join(root, f))

        return total_size

    def _parse_installed_version(self, output: str, language: str) -> Optional[str]:
        """从安装日志中解析安装的版本号"""
        if language == "python":
            # pip install 输出格式: Successfully installed numpy-1.21.0
            match = re.search(r"Successfully installed .*?(\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)
        else:  # r
            # R 安装输出格式多样，尝试解析
            match = re.search(r"(\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)

        return None

    def _format_size(self, size_bytes: int) -> str:
        """格式化大小显示"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ==========================================
# ✨ 便捷函数
# ==========================================

def install_package(
    session: Session,
    user_id: int,
    package_name: str,
    language: str,
    version: Optional[str] = None,
) -> UserPackage:
    """
    便捷函数：安装包

    Args:
        session: 数据库会话
        user_id: 用户 ID
        package_name: 包名称
        language: 语言类型
        version: 指定版本

    Returns:
        安装结果
    """
    installer = PackageInstaller(session)
    return installer.install_package(user_id, package_name, language, version)


def check_missing_dependencies(
    session: Session,
    user_id: int,
    required_packages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    便捷函数：检查缺失的依赖

    Args:
        session: 数据库会话
        user_id: 用户 ID
        required_packages: 需要的包列表

    Returns:
        缺失的包列表
    """
    installer = PackageInstaller(session)
    return installer.check_missing_dependencies(user_id, required_packages)


def get_user_packages(
    session: Session,
    user_id: int,
    language: Optional[str] = None,
) -> List[UserPackage]:
    """
    便捷函数：获取用户包列表

    Args:
        session: 数据库会话
        user_id: 用户 ID
        language: 过滤语言类型

    Returns:
        包列表
    """
    installer = PackageInstaller(session)
    return installer.get_user_packages(user_id, language)