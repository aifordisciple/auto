"""
错误诊断和修复 API

提供错误诊断和一键修复功能

API 端点：
- POST /api/error/diagnose - 诊断错误
- POST /api/error/fix - 一键修复（安装依赖包等）
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.services.error_diagnostic_service import get_error_diagnostic, ErrorType

router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

class DiagnoseRequest(BaseModel):
    """诊断请求"""
    error_log: str
    exit_code: int = 1
    language: str = "python"
    context: Optional[Dict[str, Any]] = None


class FixRequest(BaseModel):
    """修复请求"""
    error_type: str
    module_name: Optional[str] = None
    file_path: Optional[str] = None
    language: str = "python"


class FixResponse(BaseModel):
    """修复响应"""
    success: bool
    message: str
    action: str
    details: Optional[Dict[str, Any]] = None


# ==========================================
# API 端点
# ==========================================

@router.post("/diagnose")
def diagnose_error(
    request: DiagnoseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    诊断执行错误

    分析错误日志，识别错误类型，提供修复建议
    """
    service = get_error_diagnostic()

    diagnosis = service.diagnose(
        error_log=request.error_log,
        exit_code=request.exit_code,
        language=request.language,
        context=request.context
    )

    log.info(f"[ErrorAPI] 用户 {current_user.id} 诊断错误: {diagnosis.error_type.value}")

    return {
        "status": "success",
        "diagnosis": diagnosis.to_dict()
    }


@router.post("/fix", response_model=FixResponse)
def fix_error(
    request: FixRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    一键修复错误

    根据错误类型自动执行修复操作：
    - 安装缺失的依赖包
    - 修正常见路径问题
    - 提供修复代码
    """
    try:
        error_type = ErrorType(request.error_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知的错误类型: {request.error_type}")

    if error_type == ErrorType.MODULE_NOT_FOUND:
        return _fix_module_not_found(request, current_user)
    elif error_type == ErrorType.FILE_NOT_FOUND:
        return _fix_file_not_found(request, current_user)
    elif error_type == ErrorType.PERMISSION_DENIED:
        return _fix_permission_denied(request, current_user)
    else:
        return FixResponse(
            success=False,
            message="此错误类型不支持自动修复",
            action="manual"
        )


def _fix_module_not_found(request: FixRequest, user: User) -> FixResponse:
    """
    修复模块缺失错误

    自动安装缺失的 Python/R 包
    """
    module_name = request.module_name
    if not module_name:
        return FixResponse(
            success=False,
            message="缺少模块名称",
            action="install_package"
        )

    # 模块别名映射
    module_aliases = {
        "plt": "matplotlib",
        "pd": "pandas",
        "np": "numpy",
        "sns": "seaborn",
        "sklearn": "scikit-learn",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "Bio": "biopython",
    }

    actual_module = module_aliases.get(module_name, module_name)

    if request.language.lower() == "r":
        # R 包安装
        install_command = f"install.packages('{module_name}')"
        return FixResponse(
            success=True,
            message=f"请在 R 环境中运行: {install_command}",
            action="install_package",
            details={
                "module_name": module_name,
                "install_command": install_command,
                "note": "R 包安装可能需要几分钟时间"
            }
        )
    else:
        # Python 包安装
        install_command = f"pip install {actual_module}"

        log.info(f"[ErrorAPI] 用户 {user.id} 请求安装包: {actual_module}")

        return FixResponse(
            success=True,
            message=f"安装命令已生成: {install_command}",
            action="install_package",
            details={
                "module_name": actual_module,
                "install_command": install_command,
                "conda_command": f"conda install -c conda-forge {actual_module}",
                "note": "包将在下次执行时自动安装"
            }
        )


def _fix_file_not_found(request: FixRequest, user: User) -> FixResponse:
    """
    修复文件路径错误

    提供路径修正建议
    """
    file_path = request.file_path
    if not file_path:
        return FixResponse(
            success=False,
            message="缺少文件路径",
            action="check_path"
        )

    # 常见路径修正建议
    suggestions = []

    # 检查是否使用了相对路径
    if not file_path.startswith('/'):
        suggestions.append(f"建议使用绝对路径: /workspace/{file_path}")

    # 检查是否在 uploads 目录
    if 'uploads' not in file_path and not file_path.startswith('/app/'):
        suggestions.append(f"文件可能在: /workspace/{file_path}")

    return FixResponse(
        success=True,
        message="请检查文件路径是否正确",
        action="check_path",
        details={
            "original_path": file_path,
            "suggestions": suggestions,
            "common_paths": [
                "/workspace/ - 上传文件目录",
                "/app/skills/ - 技能脚本目录",
                "/app/biosource/ - 生信脚本库"
            ]
        }
    )


def _fix_permission_denied(request: FixRequest, user: User) -> FixResponse:
    """
    修复权限错误

    提供权限修复建议
    """
    file_path = request.file_path
    if not file_path:
        return FixResponse(
            success=False,
            message="缺少文件路径",
            action="check_permission"
        )

    return FixResponse(
        success=True,
        message="权限修复建议已生成",
        action="check_permission",
        details={
            "file_path": file_path,
            "suggestions": [
                "确保输出目录存在且有写入权限",
                "使用 /workspace/ 目录存放输出文件",
                "检查文件是否被其他进程占用"
            ],
            "fix_command": f"chmod 644 {file_path}" if file_path else None
        }
    )


@router.get("/common-errors")
def get_common_errors():
    """
    获取常见错误及其解决方案

    用于前端展示错误帮助文档
    """
    return {
        "status": "success",
        "errors": [
            {
                "type": "module_not_found",
                "title": "缺少依赖包",
                "description": "代码使用了未安装的 Python/R 包",
                "solution": "安装缺失的包，或使用已安装的替代包",
                "auto_fixable": True
            },
            {
                "type": "file_not_found",
                "title": "文件路径错误",
                "description": "指定的文件不存在或路径不正确",
                "solution": "检查文件路径，使用绝对路径",
                "auto_fixable": False
            },
            {
                "type": "memory_error",
                "title": "内存不足",
                "description": "数据量过大，超出可用内存",
                "solution": "减少数据量，使用分块处理，优化内存使用",
                "auto_fixable": False
            },
            {
                "type": "timeout_error",
                "title": "执行超时",
                "description": "任务执行时间过长",
                "solution": "优化代码，减少计算量，或拆分任务",
                "auto_fixable": False
            },
            {
                "type": "syntax_error",
                "title": "语法错误",
                "description": "代码存在语法错误",
                "solution": "检查代码语法，修复错误",
                "auto_fixable": False
            },
            {
                "type": "data_error",
                "title": "数据处理错误",
                "description": "数据处理时发生错误（如 KeyError, ValueError）",
                "solution": "检查数据格式和类型，处理缺失值",
                "auto_fixable": False
            }
        ]
    }


log.info("🔧 错误诊断 API 路由已加载")