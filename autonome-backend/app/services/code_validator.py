"""
LLM 生成代码语法校验器 - 在策略包展示前校验代码质量。

程序说明：
对 _generate_strategy_pack_streaming() 生成的代码进行语法检查和静态分析，
提前发现语法错误、缺失导入、输出路径问题等常见问题，
减少用户在 Docker 沙箱执行时才发现错误的挫败感。

校验维度：
1. 语法检查：Python ast.parse / R parse
2. 关键模式检查：是否有 import、是否正确使用 TASK_OUT_DIR 等
3. 输出有效性：检查是否有输出文件写入指令

返回 ValidationResult 包含：pass/fail 状态、问题列表、修复建议。
"""
import ast
import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.logger import log


@dataclass
class ValidationIssue:
    """单个校验问题"""
    line: Optional[int] = None
    column: Optional[int] = None
    severity: str = "error"  # error, warning, info
    message: str = ""
    suggestion: str = ""


@dataclass
class ValidationResult:
    """代码校验结果"""
    language: str
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0

    @property
    def status_text(self) -> str:
        if not self.is_valid:
            return f"❌ {self.error_count} 个错误, {self.warning_count} 个警告"
        if self.warning_count > 0:
            return f"⚠️ 语法检查通过, {self.warning_count} 个建议"
        return "✅ 语法检查通过"

    @property
    def status_icon(self) -> str:
        if not self.is_valid:
            return "error"
        if self.warning_count > 0:
            return "warning"
        return "success"


def validate_generated_code(code: str, language: str = "python") -> ValidationResult:
    """
    校验 LLM 生成的代码。

    Args:
        code: LLM 生成的完整代码
        language: 代码语言 (python, r)

    Returns:
        ValidationResult: 校验结果
    """
    if language == "python":
        return _validate_python_code(code)
    elif language in ("r", "R"):
        return _validate_r_code(code)
    else:
        return ValidationResult(
            language=language,
            is_valid=True,
            issues=[ValidationIssue(
                severity="warning",
                message=f"不支持 {language} 语言的语法校验",
                suggestion="将手动检查代码",
            )],
            warning_count=1,
        )


def _validate_python_code(code: str) -> ValidationResult:
    """Python 代码语法和模式检查"""
    issues: List[ValidationIssue] = []

    # 1. AST 语法检查
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        issues.append(ValidationIssue(
            line=e.lineno,
            column=e.offset,
            severity="error",
            message=f"语法错误: {e.msg}",
            suggestion=f"请检查第 {e.lineno} 行的 {e.text}",
        ))
        return ValidationResult(
            language="python",
            is_valid=False,
            issues=issues,
            error_count=1,
        )

    # 2. 关键模式检查
    _check_python_imports(code, issues)
    _check_python_output_dir(code, issues)
    _check_python_argparse(code, issues)
    _check_python_print_statements(tree, issues)

    # 3. 统计
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity != "error")

    log.info(
        f"[CodeValidator] Python 校验完成: errors={error_count}, warnings={warning_count}"
    )

    return ValidationResult(
        language="python",
        is_valid=error_count == 0,
        issues=issues,
        error_count=error_count,
        warning_count=warning_count,
    )


def _check_python_imports(code: str, issues: List[ValidationIssue]) -> None:
    """检查必要的库导入"""
    # 常见生信分析需要的库
    common_imports = {
        r'\bpd\b': 'pandas',
        r'\bnp\b': 'numpy',
        r'\bplt\b': 'matplotlib',
        r'\bsns\b': 'seaborn',
        r'\bsk\b': 'scikit-learn',
        r'\bscipy\b': 'scipy',
    }

    for usage_pattern, lib_name in common_imports.items():
        if re.search(usage_pattern, code):
            import_pattern = rf'import\s+{lib_name}\b|from\s+{lib_name}\s+import'
            if not re.search(import_pattern, code):
                issues.append(ValidationIssue(
                    severity="warning",
                    message=f"使用了 {lib_name} 但未导入",
                    suggestion=f"在代码开头添加: import {lib_name}",
                ))


def _check_python_output_dir(code: str, issues: List[ValidationIssue]) -> None:
    """检查是否正确使用 TASK_OUT_DIR 环境变量"""
    if 'TASK_OUT_DIR' not in code:
        issues.append(ValidationIssue(
            severity="warning",
            message="代码未使用 TASK_OUT_DIR 环境变量",
            suggestion="使用 os.environ['TASK_OUT_DIR'] 获取输出目录路径",
        ))


def _check_python_argparse(code: str, issues: List[ValidationIssue]) -> None:
    """检查 argparse 使用是否正确"""
    if 'argparse' not in code:
        issues.append(ValidationIssue(
            severity="error",
            message="Python 代码必须使用 argparse 定义参数",
            suggestion="请在代码中添加 argparse.ArgumentParser",
        ))


def _check_python_print_statements(tree: ast.AST, issues: List[ValidationIssue]) -> None:
    """检查是否有可能导致混淆的 print 语句"""
    # 统计 print 调用次数，如果过多可能干扰日志解析
    print_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'print':
                print_count += 1
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'write':
                # stdout.write 也算输出
                pass

    if print_count > 20:
        issues.append(ValidationIssue(
            severity="info",
            message=f"代码中有 {print_count} 个 print 语句，可能影响日志可读性",
            suggestion="考虑减少不必要的 print 或使用 logger",
        ))


def _validate_r_code(code: str) -> ValidationResult:
    """R 代码语法和模式检查"""
    issues: List[ValidationIssue] = []

    # 1. 尝试解析 R 代码（使用 subprocess 调用 R 的 parse）
    try:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.R', delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ['Rscript', '-e', f'parse(file="{tmp_path}")'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # 提取错误行号
                error_msg = result.stderr.strip()
                line_match = re.search(r'line (\d+)', error_msg)
                issues.append(ValidationIssue(
                    line=int(line_match.group(1)) if line_match else None,
                    severity="error",
                    message=f"R 语法错误: {error_msg[:200]}",
                    suggestion="请检查对应行的语法",
                ))
        finally:
            import os
            os.unlink(tmp_path)
    except FileNotFoundError:
        issues.append(ValidationIssue(
            severity="info",
            message="Rscript 未安装，跳过 R 语法检查",
            suggestion="",
        ))
    except Exception as e:
        log.warning(f"[CodeValidator] R 语法检查失败: {e}")

    # 2. 关键模式检查
    if 'optparse' not in code and 'commandArgs' not in code:
        issues.append(ValidationIssue(
            severity="error",
            message="R 代码必须使用 optparse 或 commandArgs 定义参数",
            suggestion="请使用 library(optparse) 并在代码中解析参数",
        ))

    if 'TASK_OUT_DIR' not in code:
        issues.append(ValidationIssue(
            severity="warning",
            message="代码未使用 TASK_OUT_DIR 环境变量",
            suggestion="使用 Sys.getenv('TASK_OUT_DIR') 获取输出目录",
        ))

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity != "error")

    log.info(
        f"[CodeValidator] R 校验完成: errors={error_count}, warnings={warning_count}"
    )

    return ValidationResult(
        language="r",
        is_valid=error_count == 0,
        issues=issues,
        error_count=error_count,
        warning_count=warning_count,
    )


async def auto_fix_generated_code(
    code: str,
    language: str,
    instruction: str,
    issues: list,
    session: Any = None,
    user_id: Any = None,
) -> dict:
    """
    使用 LLM Agent 自动修复即席分析生成代码中的问题。

    程序说明：
    当 validate_generated_code 发现语法错误或关键模式问题时，
    调用此函数启动一个独立的 LLM Agent（非 thinking 模型），
    专门针对校验发现的问题进行代码修复。
    Agent 会收到原始代码、校验问题列表和原始分析需求作为上下文。

    Args:
        code: 原始生成的代码
        language: 代码语言 (python, r)
        instruction: 用户原始分析需求
        issues: ValidationIssue 列表（从 validate_generated_code 获取）
        session: 数据库会话
        user_id: 用户 ID

    Returns:
        {"fixed_code": str, "changes_description": str, "success": bool}
    """
    from app.utils.llm_config import get_fast_llm_config
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    # 构建问题描述文本
    issue_descriptions = []
    for issue in issues:
        location = f"第{issue.line}行" if issue.line else "未知位置"
        severity_icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "")
        issue_descriptions.append(
            f"{severity_icon} [{issue.severity}] {location}: {issue.message}\n"
            f"   建议: {issue.suggestion}"
        )
    issues_text = "\n\n".join(issue_descriptions)

    fix_prompt = f"""你是一个生物信息学代码修复专家。请修复以下{language}代码中的问题。

原始分析需求：{instruction}

代码校验发现以下问题：
{issues_text}

当前代码：
```{language}
{code}
```

请修复所有语法错误和关键模式问题，输出修复后的完整代码。
输出要求：
1. 只输出修复后的完整代码，不要包含 markdown 标记或解释文字
2. 保持原有的代码结构和逻辑不变，只修复校验发现的问题
3. 确保所有参数通过 argparse/Python 或 optparse/commandArgs/R 正确接收
4. 确保输出目录使用 TASK_OUT_DIR 环境变量
5. 确保所有使用的库都正确导入"""

    try:
        llm_config = get_fast_llm_config(session, user_id)
        llm = ChatOpenAI(
            api_key=llm_config.api_key or "not-needed",
            base_url=llm_config.base_url,
            model=llm_config.model_name,
            temperature=0.0,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", fix_prompt),
            ("human", "请修复代码中的所有问题，直接输出修复后的完整代码。"),
        ])

        chain = prompt | llm
        response = await chain.ainvoke({})
        fixed_code = response.content.strip()

        # 清理可能的 markdown 代码块标记
        if fixed_code.startswith("```"):
            lines = fixed_code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            fixed_code = "\n".join(lines)

        # 重新校验修复后的代码
        re_validation = validate_generated_code(fixed_code, language)

        log.info(
            f"[CodeValidator] LLM 自动修复完成: "
            f"原始错误={len([i for i in issues if i.severity == 'error'])}, "
            f"修复后错误={re_validation.error_count}, "
            f"警告={re_validation.warning_count}"
        )

        return {
            "fixed_code": fixed_code,
            "changes_description": f"自动修复了 {len(issues)} 个问题"
                f"（{len([i for i in issues if i.severity == 'error'])} 个错误, "
                f"{len([i for i in issues if i.severity == 'warning'])} 个警告）",
            "success": re_validation.is_valid,
            "re_validation": {
                "is_valid": re_validation.is_valid,
                "status_text": re_validation.status_text,
                "status_icon": re_validation.status_icon,
                "issues": [
                    {"severity": i.severity, "message": i.message, "suggestion": i.suggestion}
                    for i in re_validation.issues
                ],
            },
        }
    except Exception as e:
        log.error(f"[CodeValidator] LLM 自动修复失败: {e}")
        return {
            "fixed_code": code,  # 返回原始代码作为降级
            "changes_description": f"自动修复失败: {str(e)}",
            "success": False,
        }
