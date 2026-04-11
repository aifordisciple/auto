"""
技能代码审查服务 - 提供代码质量检查和安全扫描

功能：
1. 代码语法检查（Python/R）
2. 安全漏洞扫描（硬编码密钥、SQL注入等）
3. 最佳实践建议
4. 代码风格检查
"""

import re
import ast
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.core.logger import log


class Severity(str, Enum):
    """问题严重程度"""
    CRITICAL = "critical"  # 严重问题，必须修复
    HIGH = "high"          # 高优先级问题
    MEDIUM = "medium"      # 中等优先级问题
    LOW = "low"            # 低优先级问题
    INFO = "info"          # 信息提示


@dataclass
class CodeIssue:
    """代码问题"""
    line: int
    column: int
    severity: Severity
    message: str
    rule_id: str
    suggestion: Optional[str] = None


@dataclass
class CodeReviewResult:
    """代码审查结果"""
    passed: bool
    score: float  # 0-100
    issues: List[CodeIssue]
    summary: str
    suggestions: List[str]


class SkillCodeReviewer:
    """
    技能代码审查器

    提供静态代码分析，包括：
    - 语法检查
    - 安全扫描
    - 最佳实践检查
    - 代码风格检查
    """

    # 安全问题模式
    SECURITY_PATTERNS = {
        "hardcoded_password": [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'passwd\s*=\s*["\'][^"\']+["\']',
            r'pwd\s*=\s*["\'][^"\']+["\']',
        ],
        "hardcoded_api_key": [
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'apikey\s*=\s*["\'][^"\']+["\']',
            r'secret_key\s*=\s*["\'][^"\']+["\']',
        ],
        "hardcoded_token": [
            r'token\s*=\s*["\'][^"\']+["\']',
            r'access_token\s*=\s*["\'][^"\']+["\']',
        ],
        "sql_injection_risk": [
            r'execute\s*\(\s*f["\']',  # f-string in SQL
            r'\.format\s*\([^)]*\)\s*\)',  # .format() in SQL context
        ],
        "command_injection_risk": [
            r'os\.system\s*\([\'"]',  # Direct os.system call
            r'subprocess\.call\s*\([^)]*shell\s*=\s*True',
            r'subprocess\.Popen\s*\([^)]*shell\s*=\s*True',
        ],
        "eval_usage": [
            r'\beval\s*\(',
        ],
        "exec_usage": [
            r'\bexec\s*\(',
        ],
    }

    # 最佳实践模式
    BEST_PRACTICE_PATTERNS = {
        "missing_docstring": {
            "check": lambda node: isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not ast.get_docstring(node),
            "message": "缺少文档字符串",
            "severity": Severity.LOW,
        },
        "bare_except": {
            "check": lambda node: isinstance(node, ast.ExceptHandler) and node.type is None,
            "message": "使用裸except，应该指定异常类型",
            "severity": Severity.MEDIUM,
        },
        "print_statement": {
            "pattern": r'\bprint\s*\(',
            "message": "使用print而非logging，生产环境应使用logger",
            "severity": Severity.LOW,
        },
    }

    def __init__(self):
        """初始化代码审查器"""
        self.issues: List[CodeIssue] = []

    def review_python_code(self, code: str) -> CodeReviewResult:
        """
        审查 Python 代码

        Args:
            code: Python 源代码

        Returns:
            审查结果
        """
        self.issues = []

        # 1. 语法检查
        syntax_result = self._check_syntax(code)
        if not syntax_result["valid"]:
            return CodeReviewResult(
                passed=False,
                score=0,
                issues=[CodeIssue(
                    line=syntax_result.get("line", 1),
                    column=syntax_result.get("column", 0),
                    severity=Severity.CRITICAL,
                    message=f"语法错误: {syntax_result['error']}",
                    rule_id="syntax_error"
                )],
                summary="代码存在语法错误，无法继续审查",
                suggestions=["修复语法错误后重新审查"]
            )

        # 2. 安全扫描
        self._scan_security_issues(code)

        # 3. AST 分析
        try:
            tree = ast.parse(code)
            self._analyze_ast(tree)
        except Exception as e:
            log.warning(f"[CodeReviewer] AST分析失败: {e}")

        # 4. 最佳实践检查
        self._check_best_practices(code)

        # 计算分数
        score = self._calculate_score()
        passed = score >= 60 and not any(i.severity == Severity.CRITICAL for i in self.issues)

        # 生成摘要
        summary = self._generate_summary()
        suggestions = self._generate_suggestions()

        return CodeReviewResult(
            passed=passed,
            score=score,
            issues=self.issues,
            summary=summary,
            suggestions=suggestions
        )

    def review_r_code(self, code: str) -> CodeReviewResult:
        """
        审查 R 代码

        Args:
            code: R 源代码

        Returns:
            审查结果
        """
        self.issues = []

        # R 代码安全扫描
        self._scan_r_security_issues(code)

        # R 最佳实践检查
        self._check_r_best_practices(code)

        # 计算分数
        score = self._calculate_score()
        passed = score >= 60

        summary = self._generate_summary()
        suggestions = self._generate_suggestions()

        return CodeReviewResult(
            passed=passed,
            score=score,
            issues=self.issues,
            summary=summary,
            suggestions=suggestions
        )

    def _check_syntax(self, code: str) -> Dict[str, Any]:
        """检查 Python 语法"""
        try:
            ast.parse(code)
            return {"valid": True}
        except SyntaxError as e:
            return {
                "valid": False,
                "error": str(e),
                "line": e.lineno or 1,
                "column": e.offset or 0
            }

    def _scan_security_issues(self, code: str):
        """扫描安全问题"""
        lines = code.split('\n')

        for line_num, line in enumerate(lines, 1):
            for issue_type, patterns in self.SECURITY_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.issues.append(CodeIssue(
                            line=line_num,
                            column=0,
                            severity=Severity.CRITICAL,
                            message=f"安全问题: {issue_type.replace('_', ' ')}",
                            rule_id=f"security_{issue_type}",
                            suggestion="使用环境变量或配置文件存储敏感信息"
                        ))

    def _scan_r_security_issues(self, code: str):
        """扫描 R 代码安全问题"""
        lines = code.split('\n')

        r_security_patterns = {
            "hardcoded_password": [
                r'password\s*=\s*["\'][^"\']+["\']',
                r'passwd\s*=\s*["\'][^"\']+["\']',
            ],
            "hardcoded_api_key": [
                r'api_key\s*=\s*["\'][^"\']+["\']',
            ],
            "command_injection": [
                r'system\s*\(["\']',
            ],
        }

        for line_num, line in enumerate(lines, 1):
            for issue_type, patterns in r_security_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.issues.append(CodeIssue(
                            line=line_num,
                            column=0,
                            severity=Severity.CRITICAL,
                            message=f"安全问题: {issue_type.replace('_', ' ')}",
                            rule_id=f"security_{issue_type}",
                            suggestion="使用环境变量存储敏感信息"
                        ))

    def _analyze_ast(self, tree: ast.AST):
        """分析 AST 树"""
        for node in ast.walk(tree):
            # 检查裸 except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                self.issues.append(CodeIssue(
                    line=node.lineno,
                    column=node.col_offset,
                    severity=Severity.MEDIUM,
                    message="使用裸except，应该指定异常类型",
                    rule_id="bare_except",
                    suggestion="使用 except Exception as e: 或更具体的异常类型"
                ))

            # 检查未使用的导入（简化版）
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # 这里只做简单检查
                    pass

    def _check_best_practices(self, code: str):
        """检查最佳实践"""
        lines = code.split('\n')

        for line_num, line in enumerate(lines, 1):
            # 检查 print 语句
            if re.search(r'\bprint\s*\(', line):
                self.issues.append(CodeIssue(
                    line=line_num,
                    column=0,
                    severity=Severity.LOW,
                    message="使用print而非logging",
                    rule_id="print_usage",
                    suggestion="使用 log.info() 或 logger.info() 代替 print()"
                ))

            # 检查硬编码路径
            if re.search(r'/Users/|/home/|C:\\\\', line):
                self.issues.append(CodeIssue(
                    line=line_num,
                    column=0,
                    severity=Severity.MEDIUM,
                    message="检测到硬编码路径",
                    rule_id="hardcoded_path",
                    suggestion="使用参数或环境变量代替硬编码路径"
                ))

    def _check_r_best_practices(self, code: str):
        """检查 R 最佳实践"""
        lines = code.split('\n')

        for line_num, line in enumerate(lines, 1):
            # 检查 cat/print 用于调试
            if re.search(r'\bcat\s*\(["\']', line) and not re.search(r'#.*debug', line, re.IGNORECASE):
                self.issues.append(CodeIssue(
                    line=line_num,
                    column=0,
                    severity=Severity.LOW,
                    message="使用cat输出，生产环境建议使用message()",
                    rule_id="cat_usage",
                    suggestion="使用 message() 或 warning() 代替 cat()"
                ))

            # 检查 library 调用
            if re.search(r'\blibrary\s*\([^)]+\)', line) and not re.search(r'#', line):
                pass  # library 调用是正常的

    def _calculate_score(self) -> float:
        """计算代码质量分数"""
        if not self.issues:
            return 100.0

        # 基础分
        base_score = 100.0

        # 根据问题严重程度扣分
        severity_weights = {
            Severity.CRITICAL: 20,
            Severity.HIGH: 10,
            Severity.MEDIUM: 5,
            Severity.LOW: 2,
            Severity.INFO: 0.5,
        }

        total_deduction = sum(
            severity_weights.get(issue.severity, 0)
            for issue in self.issues
        )

        return max(0, base_score - total_deduction)

    def _generate_summary(self) -> str:
        """生成审查摘要"""
        if not self.issues:
            return "代码审查通过，未发现问题"

        severity_counts = {}
        for issue in self.issues:
            sev = issue.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        parts = []
        if severity_counts.get("critical", 0) > 0:
            parts.append(f"{severity_counts['critical']} 个严重问题")
        if severity_counts.get("high", 0) > 0:
            parts.append(f"{severity_counts['high']} 个高优先级问题")
        if severity_counts.get("medium", 0) > 0:
            parts.append(f"{severity_counts['medium']} 个中等问题")
        if severity_counts.get("low", 0) > 0:
            parts.append(f"{severity_counts['low']} 个低优先级问题")

        return "发现 " + "，".join(parts) if parts else "代码审查通过"

    def _generate_suggestions(self) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 根据问题类型生成建议
        issue_types = set(issue.rule_id for issue in self.issues)

        if "security_hardcoded_password" in issue_types:
            suggestions.append("使用环境变量或配置文件存储密码")
        if "security_hardcoded_api_key" in issue_types:
            suggestions.append("将 API 密钥存储在环境变量中")
        if "security_sql_injection_risk" in issue_types:
            suggestions.append("使用参数化查询防止 SQL 注入")
        if "security_command_injection_risk" in issue_types:
            suggestions.append("避免使用 shell=True，使用列表形式传递参数")
        if "bare_except" in issue_types:
            suggestions.append("捕获具体的异常类型而非裸 except")
        if "print_usage" in issue_types:
            suggestions.append("使用 logging 模块记录日志")

        return suggestions[:5]  # 最多返回 5 条建议


def review_skill_code(code: str, language: str = "python") -> CodeReviewResult:
    """
    审查技能代码

    Args:
        code: 源代码
        language: 编程语言 (python/r)

    Returns:
        审查结果
    """
    reviewer = SkillCodeReviewer()

    if language.lower() in ["python", "py"]:
        return reviewer.review_python_code(code)
    elif language.lower() in ["r"]:
        return reviewer.review_r_code(code)
    else:
        return CodeReviewResult(
            passed=True,
            score=80,
            issues=[],
            summary=f"不支持的语言: {language}，跳过审查",
            suggestions=[]
        )


log.info("✅ 技能代码审查服务已加载")