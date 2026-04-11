"""
Package Management API 路由 - 用户包管理接口

提供：
1. 包安装接口
2. 包检查接口
3. 包列表查询
4. 包删除接口
5. 配额查询接口

设计理念：
- 用户包独立存储，不污染系统环境
- 完整的安装日志和审计追踪
- 配额管理防止滥用
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User,
    UserPackage,
    UserPackageCreate,
    UserPackagePublic,
    UserPackageQuota,
    PackageStatus,
)
from app.core.database import Session, get_session
from app.services.package_installer import (
    PackageInstaller,
    PackageInstallerError,
    install_package,
)


router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

class PackageInstallRequest(BaseModel):
    """包安装请求"""
    name: str = Field(..., description="包名称", max_length=255)
    version: Optional[str] = Field(default=None, description="指定版本", max_length=100)
    language: str = Field(default="python", description="语言类型: python/r")


class PackageInstallResponse(BaseModel):
    """包安装响应"""
    success: bool
    package: Optional[UserPackagePublic] = None
    message: str
    error: Optional[str] = None


class PackageCheckRequest(BaseModel):
    """包检查请求"""
    packages: List[Dict[str, str]] = Field(
        ...,
        description="要检查的包列表，如 [{'name': 'numpy', 'language': 'python'}]"
    )


class PackageCheckResponse(BaseModel):
    """包检查响应"""
    installed: List[Dict[str, str]] = Field(description="已安装的包")
    missing: List[Dict[str, str]] = Field(description="缺失的包")


class PackageListResponse(BaseModel):
    """包列表响应"""
    packages: List[UserPackagePublic]
    total: int
    quota: UserPackageQuota


class QuotaResponse(BaseModel):
    """配额响应"""
    quota: UserPackageQuota


class RemovePackageResponse(BaseModel):
    """删除包响应"""
    success: bool
    message: str


# ==========================================
# API 路由
# ==========================================

@router.post("/install", response_model=PackageInstallResponse)
async def api_install_package(
    request: PackageInstallRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    安装包到用户目录

    流程：
    1. 检查黑名单和配额
    2. 在 Docker 容器中执行安装（有网络）
    3. 记录安装结果到数据库

    Args:
        request: 安装请求（包名、版本、语言）
        session: 数据库会话
        current_user: 当前用户

    Returns:
        安装结果
    """
    log.info(f"[PackageAPI] 用户 {current_user.id} 请求安装包: {request.name} ({request.language})")

    try:
        installer = PackageInstaller(session)
        package = installer.install_package(
            user_id=current_user.id,
            package_name=request.name,
            language=request.language,
            version=request.version,
        )

        if package.status == PackageStatus.INSTALLED:
            return PackageInstallResponse(
                success=True,
                package=UserPackagePublic.model_validate(package),
                message=f"包 {request.name} 安装成功",
            )
        else:
            return PackageInstallResponse(
                success=False,
                package=UserPackagePublic.model_validate(package),
                message=f"包 {request.name} 安装失败",
                error=package.error_message,
            )

    except PackageInstallerError as e:
        log.error(f"[PackageAPI] 安装失败: {e}")
        return PackageInstallResponse(
            success=False,
            message=f"安装失败: {str(e)}",
            error=str(e),
        )
    except Exception as e:
        log.error(f"[PackageAPI] 安装异常: {e}")
        raise HTTPException(status_code=500, detail=f"安装异常: {str(e)}")


@router.post("/check", response_model=PackageCheckResponse)
async def api_check_packages(
    request: PackageCheckRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    检查包是否已安装

    同时检查用户目录和系统预装包

    Args:
        request: 检查请求（包列表）
        session: 数据库会话
        current_user: 当前用户

    Returns:
        已安装和缺失的包列表
    """
    installer = PackageInstaller(session)

    installed = []
    missing = []

    for pkg in request.packages:
        name = pkg.get("name")
        language = pkg.get("language", "python")

        if installer.check_package_installed(current_user.id, name, language):
            installed.append(pkg)
        else:
            missing.append(pkg)

    return PackageCheckResponse(
        installed=installed,
        missing=missing,
    )


@router.get("/list", response_model=PackageListResponse)
async def api_list_packages(
    language: Optional[str] = None,
    status: Optional[PackageStatus] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取用户安装的包列表

    Args:
        language: 过滤语言类型 (python/r)
        status: 过滤状态
        session: 数据库会话
        current_user: 当前用户

    Returns:
        包列表和配额信息
    """
    installer = PackageInstaller(session)

    packages = installer.get_user_packages(
        user_id=current_user.id,
        language=language,
        status=status,
    )

    quota = installer.get_quota(current_user.id)

    return PackageListResponse(
        packages=[UserPackagePublic.model_validate(p) for p in packages],
        total=len(packages),
        quota=quota,
    )


@router.get("/quota", response_model=QuotaResponse)
async def api_get_quota(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取用户包配额信息

    Returns:
        配额详情（已用空间、剩余空间、包数量等）
    """
    installer = PackageInstaller(session)
    quota = installer.get_quota(current_user.id)

    return QuotaResponse(quota=quota)


@router.delete("/{package_id}", response_model=RemovePackageResponse)
async def api_remove_package(
    package_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    删除用户安装的包

    Args:
        package_id: 包记录 ID
        session: 数据库会话
        current_user: 当前用户

    Returns:
        删除结果
    """
    from sqlmodel import select

    # 查找包记录
    statement = select(UserPackage).where(
        UserPackage.id == package_id,
        UserPackage.user_id == current_user.id,
    )
    package = session.exec(statement).first()

    if not package:
        raise HTTPException(status_code=404, detail="包不存在")

    installer = PackageInstaller(session)
    success = installer.remove_package(
        user_id=current_user.id,
        package_name=package.name,
        language=package.language,
    )

    if success:
        return RemovePackageResponse(
            success=True,
            message=f"包 {package.name} 已删除",
        )
    else:
        return RemovePackageResponse(
            success=False,
            message=f"删除包 {package.name} 失败",
        )


@router.get("/search")
async def api_search_packages(
    q: str,
    language: str = "python",
    limit: int = 10,
):
    """
    搜索可安装的包

    通过 PyPI/CRAN API 搜索包信息

    Args:
        q: 搜索关键词
        language: 语言类型
        limit: 返回数量限制

    Returns:
        搜索结果列表
    """
    import requests

    results = []

    if language.lower() == "python":
        # PyPI 搜索 API
        try:
            response = requests.get(
                "https://pypi.org/simple/",
                timeout=5,
            )
            # PyPI simple API 返回所有包名，我们做简单过滤
            if response.status_code == 200:
                # 简单的前缀匹配
                all_packages = response.text.split('\n')
                matching = [
                    pkg for pkg in all_packages
                    if q.lower() in pkg.lower()
                ][:limit]

                for pkg in matching:
                    # 提取包名
                    if '<a href="' in pkg:
                        name = pkg.split('>')[1].split('<')[0] if '>' in pkg else pkg
                        results.append({
                            "name": name,
                            "language": "python",
                            "source": "pypi",
                        })
        except Exception as e:
            log.warning(f"[PackageAPI] PyPI 搜索失败: {e}")

    elif language.lower() == "r":
        # CRAN 搜索（简化实现）
        # 实际项目中应该调用 CRAN API 或使用本地包数据库
        pass

    return {
        "query": q,
        "language": language,
        "results": results[:limit],
    }


@router.get("/system-packages")
async def api_list_system_packages(
    language: str = "python",
):
    """
    获取系统预装的包列表

    返回 conda 环境中预安装的包

    Args:
        language: 语言类型

    Returns:
        系统包列表
    """
    from app.tools.bio_tools import run_container

    if language.lower() == "python":
        cmd = ["pip", "list", "--format=json"]
    else:
        cmd = ["Rscript", "-e", 'writeLines(paste(names(installed.packages()), collapse="\\n"))']

    output, exit_code = run_container(
        image='autonome-tool-env',
        command=cmd,
        language=language,
        timeout=30,
        cli_mode=True,
        user_id=None,  # 不使用用户包
        enable_network=False,
    )

    if exit_code == 0:
        if language.lower() == "python":
            import json
            try:
                packages = json.loads(output)
                return {
                    "language": "python",
                    "packages": packages,
                    "total": len(packages),
                }
            except:
                return {
                    "language": "python",
                    "packages": [],
                    "raw_output": output,
                }
        else:
            packages = output.strip().split('\n')
            return {
                "language": "r",
                "packages": [{"name": p} for p in packages if p.strip()],
                "total": len(packages),
            }
    else:
        raise HTTPException(status_code=500, detail=f"获取系统包列表失败: {output}")