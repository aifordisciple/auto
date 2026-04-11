"""
智能错误诊断服务 - 分析执行错误并提供修复建议

核心功能：
1. 解析错误日志，识别错误类型
2. 生成用户友好的错误描述
3. 提供具体的修复建议
4. 支持自动修复常见错误

错误类型识别：
- ModuleNotFoundError: 缺少依赖包
- FileNotFoundError: 文件路径错误
- PermissionError: 权限问题
- MemoryError: 内存不足
- TimeoutError: 执行超时
- SyntaxError: 语法错误
- KeyError/ValueError: 数据问题

@created: 2026-03-31
@author: AI Assistant
"""

import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from app.core.logger import log


# ==========================================
# 错误类型定义
# ==========================================

class ErrorType(Enum):
    """错误类型枚举"""
    MODULE_NOT_FOUND = "module_not_found"        # 缺少依赖包
    FILE_NOT_FOUND = "file_not_found"            # 文件路径错误
    PERMISSION_DENIED = "permission_denied"      # 权限问题
    MEMORY_ERROR = "memory_error"                # 内存不足
    TIMEOUT_ERROR = "timeout_error"              # 执行超时
    SYNTAX_ERROR = "syntax_error"                # 语法错误
    DATA_ERROR = "data_error"                    # 数据问题（KeyError/ValueError）
    NETWORK_ERROR = "network_error"              # 网络问题
    CONFIG_ERROR = "config_error"                # 配置错误
    UNKNOWN_ERROR = "unknown_error"              # 未知错误


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"          # 轻微，可继续
    MEDIUM = "medium"    # 中等，需要处理
    HIGH = "high"        # 严重，阻止执行
    CRITICAL = "critical"  # 致命，系统级问题


@dataclass
class FixSuggestion:
    """修复建议"""
    action: str                              # 操作类型：install, correct_path, fix_syntax, etc.
    description: str                         # 用户友好的描述
    auto_fixable: bool = False               # 是否可自动修复
    fix_command: Optional[str] = None        # 自动修复命令
    fix_code: Optional[str] = None           # 自动修复代码
    manual_steps: List[str] = field(default_factory=list)  # 手动修复步骤


@dataclass
class ErrorDiagnosis:
    """错误诊断结果"""
    error_type: ErrorType
    severity: ErrorSeverity
    title: str                                    # 简短标题
    message: str                                  # 用户友好的错误描述
    original_error: str                           # 原始错误信息
    line_number: Optional[int] = None             # 错误行号
    module_name: Optional[str] = None             # 缺失的模块名
    file_path: Optional[str] = None               # 涉及的文件路径
    suggestions: List[FixSuggestion] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # 额外上下文

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "original_error": self.original_error,
            "line_number": self.line_number,
            "module_name": self.module_name,
            "file_path": self.file_path,
            "suggestions": [
                {
                    "action": s.action,
                    "description": s.description,
                    "auto_fixable": s.auto_fixable,
                    "fix_command": s.fix_command,
                    "fix_code": s.fix_code,
                    "manual_steps": s.manual_steps
                }
                for s in self.suggestions
            ],
            "context": self.context
        }


# ==========================================
# 错误诊断服务
# ==========================================

class ErrorDiagnosticService:
    """
    智能错误诊断服务

    功能：
    1. 解析错误日志，识别错误类型
    2. 提取关键信息（模块名、文件路径、行号等）
    3. 生成用户友好的错误描述
    4. 提供具体的修复建议
    """

    # 错误模式匹配规则
    ERROR_PATTERNS = {
        ErrorType.MODULE_NOT_FOUND: [
            r"ModuleNotFoundError: No module named '([^']+)'",
            r"ImportError: No module named '([^']+)'",
            r"library\(([^)]+)\) : there is no package called",
            r"Error in library\(([^)]+)\) : there is no package called",
            r"package '([^']+)' was not found",
        ],
        ErrorType.FILE_NOT_FOUND: [
            r"FileNotFoundError: \[Errno \d+\] No such file or directory: '([^']+)'",
            r"FileNotFoundError: '([^']+)'",
            r"cannot open file '([^']+)'",
            r"No such file or directory: '([^']+)'",
        ],
        ErrorType.PERMISSION_DENIED: [
            r"PermissionError: \[Errno \d+\] Permission denied: '([^']+)'",
            r"Permission denied: '([^']+)'",
            r"Error: cannot write to '([^']+)'",
        ],
        ErrorType.MEMORY_ERROR: [
            r"MemoryError",
            r"cannot allocate memory",
            r"Out of memory",
        ],
        ErrorType.TIMEOUT_ERROR: [
            r"TimeoutError",
            r"timed out after",
            r"执行超时",
            r"Execution timeout",
        ],
        ErrorType.SYNTAX_ERROR: [
            r"SyntaxError: (.+) \(([^\)]+)\) line (\d+)",
            r"SyntaxError: (.+) at line (\d+)",
            r"unexpected token",
            r"unexpected symbol",
        ],
        ErrorType.DATA_ERROR: [
            r"KeyError: '([^']+)'",
            r"ValueError: (.+)",
            r"TypeError: (.+)",
            r"IndexError: (.+)",
        ],
        ErrorType.NETWORK_ERROR: [
            r"ConnectionError",
            r"Network is unreachable",
            r"Connection refused",
            r"Name or service not known",
        ],
    }

    # 常见模块别名映射
    MODULE_ALIASES = {
        "plt": "matplotlib",
        "pd": "pandas",
        "np": "numpy",
        "sns": "seaborn",
        "sklearn": "scikit-learn",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "Bio": "biopython",
        "scanpy": "scanpy",
        "anndata": "anndata",
    }

    # R 包名称映射
    R_PACKAGE_ALIASES = {
        "Seurat": "Seurat",
        "ggplot2": "ggplot2",
        "dplyr": "dplyr",
        "tidyr": "tidyr",
        "DESeq2": "DESeq2",
        "edgeR": "edgeR",
        "limma": "limma",
        "SingleCellExperiment": "SingleCellExperiment",
    }

    def __init__(self):
        """初始化错误诊断服务"""
        log.info("[ErrorDiagnostic] 错误诊断服务初始化完成")

    def diagnose(
        self,
        error_log: str,
        exit_code: int,
        language: str = "python",
        context: Optional[Dict] = None
    ) -> ErrorDiagnosis:
        """
        诊断错误

        Args:
            error_log: 错误日志
            exit_code: 退出码
            language: 语言类型
            context: 额外上下文（代码、参数等）

        Returns:
            ErrorDiagnosis 诊断结果
        """
        context = context or {}

        # 1. 尝试匹配已知错误模式
        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, error_log, re.IGNORECASE | re.MULTILINE)
                if match:
                    diagnosis = self._create_diagnosis(
                        error_type=error_type,
                        error_log=error_log,
                        match=match,
                        language=language,
                        context=context
                    )
                    log.info(f"[ErrorDiagnostic] 识别错误类型: {error_type.value}")
                    return diagnosis

        # 2. 无法识别的错误
        return self._create_unknown_diagnosis(error_log, exit_code, context)

    def _create_diagnosis(
        self,
        error_type: ErrorType,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """
        创建诊断结果

        Args:
            error_type: 错误类型
            error_log: 原始错误日志
            match: 正则匹配结果
            language: 语言类型
            context: 上下文

        Returns:
            ErrorDiagnosis
        """
        if error_type == ErrorType.MODULE_NOT_FOUND:
            return self._diagnose_module_not_found(error_log, match, language, context)
        elif error_type == ErrorType.FILE_NOT_FOUND:
            return self._diagnose_file_not_found(error_log, match, language, context)
        elif error_type == ErrorType.PERMISSION_DENIED:
            return self._diagnose_permission_denied(error_log, match, language, context)
        elif error_type == ErrorType.MEMORY_ERROR:
            return self._diagnose_memory_error(error_log, match, language, context)
        elif error_type == ErrorType.TIMEOUT_ERROR:
            return self._diagnose_timeout_error(error_log, match, language, context)
        elif error_type == ErrorType.SYNTAX_ERROR:
            return self._diagnose_syntax_error(error_log, match, language, context)
        elif error_type == ErrorType.DATA_ERROR:
            return self._diagnose_data_error(error_log, match, language, context)
        elif error_type == ErrorType.NETWORK_ERROR:
            return self._diagnose_network_error(error_log, match, language, context)
        else:
            return self._create_unknown_diagnosis(error_log, 1, context)

    # ==========================================
    # 各类错误诊断方法
    # ==========================================

    def _diagnose_module_not_found(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断模块缺失错误"""
        module_name = match.group(1) if match.groups() else "unknown"

        # 处理模块别名
        actual_module = self.MODULE_ALIASES.get(module_name, module_name)

        suggestions = []

        if language.lower() == "r":
            # R 包安装建议
            suggestions.append(FixSuggestion(
                action="install_package",
                description=f"安装 R 包: {module_name}",
                auto_fixable=True,
                fix_command=f"install.packages('{module_name}')",
                manual_steps=[
                    f"在 R 控制台运行: install.packages('{module_name}')",
                    "如果使用 Bioconductor: BiocManager::install('{module_name}')"
                ]
            ))
        else:
            # Python 包安装建议
            suggestions.append(FixSuggestion(
                action="install_package",
                description=f"安装 Python 包: {actual_module}",
                auto_fixable=True,
                fix_command=f"pip install {actual_module}",
                manual_steps=[
                    f"运行命令: pip install {actual_module}",
                    f"如果使用 conda: conda install -c conda-forge {actual_module}",
                    "如果是 BioPython: pip install biopython"
                ]
            ))

        return ErrorDiagnosis(
            error_type=ErrorType.MODULE_NOT_FOUND,
            severity=ErrorSeverity.MEDIUM,
            title="缺少依赖包",
            message=f"缺少必要的{'Python' if language.lower() != 'r' else 'R'}包: {module_name}",
            original_error=error_log,
            module_name=module_name,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_file_not_found(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断文件未找到错误"""
        file_path = match.group(1) if match.groups() else "unknown"

        suggestions = [
            FixSuggestion(
                action="check_path",
                description="检查文件路径是否正确",
                auto_fixable=False,
                manual_steps=[
                    f"确认文件是否存在: {file_path}",
                    "检查路径是否使用相对路径（建议使用绝对路径）",
                    "确认文件名大小写是否正确（区分大小写）",
                    "如果是上传文件，检查文件是否已成功上传"
                ]
            ),
            FixSuggestion(
                action="use_correct_path",
                description="使用正确的文件路径",
                auto_fixable=True,
                fix_code=f"# 建议使用绝对路径\nfile_path = '/workspace/your_file.txt'",
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.FILE_NOT_FOUND,
            severity=ErrorSeverity.HIGH,
            title="文件路径错误",
            message=f"找不到指定的文件: {file_path}",
            original_error=error_log,
            file_path=file_path,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_permission_denied(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断权限错误"""
        file_path = match.group(1) if match.groups() else "unknown"

        suggestions = [
            FixSuggestion(
                action="check_permission",
                description="检查文件权限",
                auto_fixable=True,
                fix_command=f"chmod 644 {file_path}",
                manual_steps=[
                    "检查文件是否有写入权限",
                    "确认是否在正确的目录下操作",
                    "如果是输出文件，确认目标目录存在且有写入权限"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.PERMISSION_DENIED,
            severity=ErrorSeverity.MEDIUM,
            title="权限不足",
            message=f"没有权限访问文件: {file_path}",
            original_error=error_log,
            file_path=file_path,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_memory_error(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断内存错误"""
        suggestions = [
            FixSuggestion(
                action="reduce_data",
                description="减少数据量或优化内存使用",
                auto_fixable=False,
                manual_steps=[
                    "减少一次性加载的数据量",
                    "使用分块处理大数据集",
                    "检查是否有不必要的变量占用内存",
                    "尝试使用更节省内存的数据类型",
                    "如果处理图像，尝试降低分辨率"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.MEMORY_ERROR,
            severity=ErrorSeverity.HIGH,
            title="内存不足",
            message="数据量较大，内存不足。建议减少数据量或优化代码。",
            original_error=error_log,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_timeout_error(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断超时错误"""
        suggestions = [
            FixSuggestion(
                action="optimize_code",
                description="优化代码或减少数据量",
                auto_fixable=False,
                manual_steps=[
                    "检查代码是否有死循环或低效算法",
                    "减少数据处理量",
                    "使用向量化操作代替循环",
                    "考虑分批处理数据"
                ]
            ),
            FixSuggestion(
                action="increase_timeout",
                description="延长执行超时时间",
                auto_fixable=False,
                manual_steps=[
                    "联系管理员调整任务超时设置",
                    "将任务拆分为多个小任务"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.TIMEOUT_ERROR,
            severity=ErrorSeverity.HIGH,
            title="执行超时",
            message="任务执行时间过长。建议优化代码或减少数据量。",
            original_error=error_log,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_syntax_error(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断语法错误"""
        # 尝试提取行号
        line_number = None
        error_detail = "语法错误"

        line_match = re.search(r"line (\d+)", error_log)
        if line_match:
            line_number = int(line_match.group(1))

        suggestions = [
            FixSuggestion(
                action="fix_syntax",
                description="修复语法错误",
                auto_fixable=False,
                manual_steps=[
                    f"检查第 {line_number} 行附近的代码",
                    "确认括号、引号是否配对",
                    "检查缩进是否正确",
                    "确认是否有拼写错误"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.SYNTAX_ERROR,
            severity=ErrorSeverity.HIGH,
            title="语法错误",
            message=f"代码存在语法错误{f'，在第 {line_number} 行附近' if line_number else ''}",
            original_error=error_log,
            line_number=line_number,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_data_error(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断数据错误"""
        error_detail = match.group(1) if match.groups() else "数据错误"

        suggestions = [
            FixSuggestion(
                action="check_data",
                description="检查数据和数据处理逻辑",
                auto_fixable=False,
                manual_steps=[
                    "检查数据是否存在缺失值",
                    "确认数据类型是否正确",
                    "检查数组/列表索引是否越界",
                    "打印中间结果进行调试"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.DATA_ERROR,
            severity=ErrorSeverity.MEDIUM,
            title="数据处理错误",
            message=f"数据处理时发生错误: {error_detail}",
            original_error=error_log,
            suggestions=suggestions,
            context=context
        )

    def _diagnose_network_error(
        self,
        error_log: str,
        match: re.Match,
        language: str,
        context: Dict
    ) -> ErrorDiagnosis:
        """诊断网络错误"""
        suggestions = [
            FixSuggestion(
                action="check_network",
                description="检查网络连接或使用离线模式",
                auto_fixable=False,
                manual_steps=[
                    "当前环境默认禁用网络",
                    "如需网络访问，请联系管理员",
                    "考虑使用本地数据文件",
                    "将需要下载的资源提前准备好"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.NETWORK_ERROR,
            severity=ErrorSeverity.HIGH,
            title="网络访问受限",
            message="当前环境网络访问受限，无法访问外部资源。",
            original_error=error_log,
            suggestions=suggestions,
            context=context
        )

    def _create_unknown_diagnosis(
        self,
        error_log: str,
        exit_code: int,
        context: Dict
    ) -> ErrorDiagnosis:
        """创建未知错误诊断"""
        # 提取最后几行作为关键信息
        lines = error_log.strip().split('\n')
        last_lines = '\n'.join(lines[-5:]) if len(lines) > 5 else error_log

        suggestions = [
            FixSuggestion(
                action="view_log",
                description="查看详细错误日志",
                auto_fixable=False,
                manual_steps=[
                    "检查错误日志中的详细信息",
                    "搜索错误信息寻找解决方案",
                    "联系技术支持获取帮助"
                ]
            )
        ]

        return ErrorDiagnosis(
            error_type=ErrorType.UNKNOWN_ERROR,
            severity=ErrorSeverity.MEDIUM,
            title="执行错误",
            message="代码执行过程中发生错误，请查看详细日志。",
            original_error=last_lines,
            suggestions=suggestions,
            context={"full_log": error_log, "exit_code": exit_code}
        )

    # ==========================================
    # 批量诊断
    # ==========================================

    def diagnose_batch(
        self,
        errors: List[Dict]
    ) -> List[ErrorDiagnosis]:
        """
        批量诊断错误

        Args:
            errors: 错误列表，每个元素包含 error_log, exit_code, language

        Returns:
            诊断结果列表
        """
        results = []
        for error in errors:
            diagnosis = self.diagnose(
                error_log=error.get("error_log", ""),
                exit_code=error.get("exit_code", 1),
                language=error.get("language", "python"),
                context=error.get("context")
            )
            results.append(diagnosis)

        return results


# ==========================================
# 全局单例
# ==========================================

_error_diagnostic: Optional[ErrorDiagnosticService] = None


def get_error_diagnostic() -> ErrorDiagnosticService:
    """获取错误诊断服务单例"""
    global _error_diagnostic
    if _error_diagnostic is None:
        _error_diagnostic = ErrorDiagnosticService()
    return _error_diagnostic


# ==========================================
# 便捷函数
# ==========================================

def diagnose_error(
    error_log: str,
    exit_code: int = 1,
    language: str = "python",
    context: Optional[Dict] = None
) -> Dict:
    """
    诊断错误（便捷函数）

    Args:
        error_log: 错误日志
        exit_code: 退出码
        language: 语言类型
        context: 额外上下文

    Returns:
        诊断结果字典
    """
    service = get_error_diagnostic()
    diagnosis = service.diagnose(error_log, exit_code, language, context)
    return diagnosis.to_dict()


log.info("✅ 智能错误诊断服务已加载")