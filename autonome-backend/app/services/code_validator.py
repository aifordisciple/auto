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
4. 硬检查（反思自循环）：CNS 规范强制性规则，不通过则代码必须重写

返回 ValidationResult 包含：pass/fail 状态、问题列表、修复建议。
HardCheckResult 包含：通过/失败状态、结构化批评文本（可直接注入 LLM prompt）。
"""
import ast
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

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


# =========================================================================
# 反思自循环：硬检查规则引擎
# =========================================================================
# 硬检查是针对 CNS 级代码规范的强制性规则检查，不依赖 LLM。
# 检查未通过 → 生成结构化批评 → 代码打回 LLM 重写。
# 检查通过 → 代码可进入后续流程。
#
# 设计原则：
# - 纯规则匹配（正则 + AST），延迟 < 10ms
# - 批评文本可直接注入 LLM rewrite prompt
# - 与 validate_generated_code() 互补：validate 做语法检查，hard_check 做规范检查
# =========================================================================

# 反思自循环最大重试次数
MAX_REFLECTION_RETRIES = 2


@dataclass
class HardCheckResult:
    """硬检查结果 — 不通过则代码必须打回 LLM 重写"""
    passed: bool
    critique: str = ""           # 结构化批评文本，可直接注入 LLM prompt
    failed_checks: List[str] = field(default_factory=list)  # 失败的检查项 ID 列表
    warnings: List[str] = field(default_factory=list)       # 警告项（不阻塞通过）


# 硬检查规则定义
# 每条规则包含：
#   id: 规则唯一标识
#   check: 检查逻辑函数 (code, language) -> (passed: bool, detail: str)
#   critique_template: 失败时的批评模板，{detail} 会被替换为具体问题描述
#   applies_to: 适用语言限制 (None = 所有语言)
#   applies_to_visualization: 仅当代码含可视化时检查
#   severity: "error" = 不通过阻塞 / "warning" = 警告不阻塞

def _check_argparse_or_optparse(code: str, language: str) -> tuple:
    """检查是否使用参数解析系统"""
    if language == "python":
        if 'argparse' not in code:
            return False, "代码未使用 argparse 定义参数，所有输入必须通过 argparse 接收"
    elif language in ("r", "R"):
        if 'optparse' not in code and 'commandArgs' not in code:
            return False, "代码未使用 optparse 或 commandArgs 定义参数，所有输入必须通过命令行参数接收"
    return True, ""


def _check_task_out_dir(code: str, language: str) -> tuple:
    """检查是否使用 TASK_OUT_DIR 环境变量"""
    if 'TASK_OUT_DIR' not in code:
        return False, "代码未使用 TASK_OUT_DIR 环境变量，所有输出必须写入 TASK_OUT_DIR"
    return True, ""


def _check_ggsci_palette(code: str, language: str) -> tuple:
    """检查 R 代码是否使用 ggsci 学术配色"""
    if language not in ("r", "R"):
        return True, ""
    # 仅当代码包含 ggplot 可视化时检查
    if not re.search(r'ggplot\s*\(|ggsave\s*\(', code):
        return True, ""
    # 检查 ggsci 调色板函数
    ggsci_patterns = [
        r'scale_(fill|color|colour)_(npg|jco|lancet|nejm|d3|aaas|uchicago|igv|futurama|startrek|tron)',
        r'scale_(fill|color|colour)_manual',
        r'ggsci::',
    ]
    for pattern in ggsci_patterns:
        if re.search(pattern, code):
            return True, ""
    return False, "R 代码中使用了 ggplot2 可视化但未使用 ggsci 学术期刊配色（如 scale_fill_npg()），必须使用 ggsci 配色方案以符合 CNS 发表标准"


def _check_dual_format_output(code: str, language: str) -> tuple:
    """检查图表是否双格式输出（PDF + PNG）"""
    # 仅当代码包含图表保存时检查
    has_plot_save = bool(
        re.search(r'ggsave\s*\(', code) or
        re.search(r'plt\.savefig\s*\(', code) or
        re.search(r'pdf\s*\(', code) or
        re.search(r'png\s*\(', code) or
        re.search(r'cairo_pdf\s*\(', code) or
        re.search(r'pdf\(', code)
    )
    if not has_plot_save:
        return True, ""

    # 检查是否同时有 PDF 和 PNG 输出
    has_pdf = bool(re.search(r'cairo_pdf\s*\(|pdf\s*\(|\.pdf["\']', code))
    has_png = bool(re.search(r'png\s*\(|\.png["\']', code))

    if not has_pdf:
        return False, "代码只输出了 PNG 格式，CNS 级图表必须同时输出 PDF（cairo_pdf 设备）+ PNG(dpi>=300) 双格式"
    if not has_png:
        return False, "代码只输出了 PDF 格式，CNS 级图表必须同时输出 PDF（cairo_pdf 设备）+ PNG(dpi>=300) 双格式"

    # 检查 PNG dpi
    if language in ("r", "R"):
        if not re.search(r'dpi\s*=\s*\d{3}', code):
            return False, "PNG 输出未指定 dpi>=300，CNS 级图表要求高分辨率输出"
    else:
        if not re.search(r'dpi\s*=\s*[34]\d{2}', code):
            return False, "PNG 输出未指定 dpi>=300，CNS 级图表要求高分辨率输出"

    return True, ""


def _check_no_hardcoded_paths(code: str, language: str) -> tuple:
    """检查是否存在硬编码的 /workspace/ 路径（而非通过参数接收）"""
    # 查找硬编码的 /workspace/ 路径（排除注释行和字符串赋值给参数的情况）
    hardcoded = re.findall(r'["\'](/workspace/[^"\']+)["\']', code)
    if not hardcoded:
        return True, ""

    # 排除 TASK_OUT_DIR 拼接写法
    real_hardcoded = []
    for path in hardcoded:
        # 跳过注释中的路径
        line_with_path = [l for l in code.split('\n') if path in l and not l.strip().startswith('#')]
        if not line_with_path:
            continue
        # 跳过 argparser default 中的路径（这是允许的）
        if 'default' in line_with_path[0] and 'add_argument' in line_with_path[0]:
            continue
        # 跳过变量赋值中的路径（如 output_dir = os.path.join(...)）
        if 'os.path.join' in line_with_path[0] or 'file.path' in line_with_path[0]:
            continue
        real_hardcoded.append(path)

    if real_hardcoded:
        paths_str = ", ".join(real_hardcoded[:3])
        return False, f"代码中硬编码了文件路径（{paths_str}），所有输入文件路径必须通过 argparse/optparse 参数传入，不得直接写在代码中"
    return True, ""


def _check_intermediate_data_saving(code: str, language: str) -> tuple:
    """检查是否保存中间数据文件（CSV/TSV）"""
    # 仅当代码包含数据分析（非纯可视化）时检查
    has_analysis = bool(
        re.search(r'(DESeq|edgeR|limma|t\.test|wilcox|aov|kmeans|hclust|prcomp|pca)', code, re.IGNORECASE)
    )
    if not has_analysis:
        return True, ""

    has_data_save = bool(
        re.search(r'(write\.csv|write\.table|write_csv|to_csv|to_csv|fwrite)', code) or
        re.search(r'(write\.xlsx|write_xlsx|write\.tsv)', code) or
        re.search(r'saveRDS|save\.RDS', code)
    )
    if not has_data_save:
        # 警告但不阻塞
        return False, "分析结果仅以图表输出，未保存中间数据文件（CSV/TSV），CNS 规范建议同时保存中间数据供审稿人检查"

    return True, ""


def _check_import_completeness(code: str, language: str) -> tuple:
    """检查所有使用的库是否都已导入"""
    if language == "python":
        # 常见生信库的使用检测
        lib_patterns = {
            r'\bpd\.': 'pandas',
            r'\bnp\.': 'numpy',
            r'\bplt\.': 'matplotlib',
            r'\bsns\.': 'seaborn',
            r'\bsk\.|sklearn\b': 'scikit-learn',
            r'\bscipy\.': 'scipy',
            r'\bgoatools\b': 'goatools',
            r'\bgseapy\b': 'gseapy',
        }
        missing = []
        for usage_pattern, lib_name in lib_patterns.items():
            if re.search(usage_pattern, code):
                import_pattern = rf'import\s+{lib_name}\b|from\s+{lib_name}\s+import'
                if not re.search(import_pattern, code):
                    missing.append(lib_name)
        if missing:
            return False, f"代码中使用了 {'/'.join(missing)} 但未导入，必须在代码开头添加相应的 import 语句"

    elif language in ("r", "R"):
        # R 库使用检测
        r_lib_patterns = {
            r'library\s*\(\s*(\w+)': True,  # library() 形式
            r'(\w+)::': True,                # pkg::fun 形式
        }
        # 检查是否使用了未 library() 加载的包
        # R 的检查比 Python 复杂，仅检查 DESeq2/edgeR/limma 等关键包
        bio_pkgs = {
            r'\bDESeq\b': 'DESeq2',
            r'\bglmQLFit\b|\bcalcNormFactors\b': 'edgeR',
            r'\blmFit\b|\beBayes\b': 'limma',
            r'\bComplexHeatmap\b': 'ComplexHeatmap',
        }
        missing = []
        for usage_pattern, pkg_name in bio_pkgs.items():
            if re.search(usage_pattern, code):
                if not re.search(rf'library\s*\(\s*{pkg_name}\b', code):
                    missing.append(pkg_name)
        if missing:
            return False, f"代码中使用了 {'/'.join(missing)} 但未 library() 加载，必须添加相应的 library() 调用"

    return True, ""


# 硬检查规则列表（按优先级排列）
HARD_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "argparse_or_optparse",
        "name": "参数解析系统",
        "check": _check_argparse_or_optparse,
        "severity": "error",
    },
    {
        "id": "task_out_dir",
        "name": "TASK_OUT_DIR 输出目录",
        "check": _check_task_out_dir,
        "severity": "error",
    },
    {
        "id": "no_hardcoded_paths",
        "name": "禁止硬编码路径",
        "check": _check_no_hardcoded_paths,
        "severity": "error",
    },
    {
        "id": "import_completeness",
        "name": "库导入完整性",
        "check": _check_import_completeness,
        "severity": "error",
    },
    {
        "id": "ggsci_palette",
        "name": "ggsci 学术配色",
        "check": _check_ggsci_palette,
        "severity": "error",
        "applies_to": ["r", "R"],
    },
    {
        "id": "dual_format_output",
        "name": "双格式输出（PDF+PNG）",
        "check": _check_dual_format_output,
        "severity": "error",
    },
    {
        "id": "intermediate_data_saving",
        "name": "中间数据保存",
        "check": _check_intermediate_data_saving,
        "severity": "warning",
    },
]


def run_hard_checks(code: str, language: str) -> HardCheckResult:
    """
    对生成的代码运行所有硬检查规则。

    规则引擎执行流程：
    1. 遍历 HARD_CHECKS 中每条规则
    2. 跳过不适用于当前语言的规则
    3. 执行检查逻辑
    4. 收集失败的检查项，生成结构化批评文本

    Args:
        code: 待检查的完整代码
        language: 代码语言 (python / r)

    Returns:
        HardCheckResult: 包含通过/失败状态和批评文本
    """
    failed_checks = []
    warnings = []
    critique_parts = []

    for rule in HARD_CHECKS:
        # 检查语言适用性
        applies_to = rule.get("applies_to")
        if applies_to and language.lower() not in [a.lower() for a in applies_to]:
            continue

        check_fn = rule["check"]
        try:
            passed, detail = check_fn(code, language)
        except Exception as e:
            log.warning(f"[CodeValidator] 硬检查规则 '{rule['id']}' 执行异常: {e}")
            continue

        if not passed:
            if rule.get("severity") == "warning":
                warnings.append(rule["id"])
                if detail:
                    critique_parts.append(f"  ⚠️ [{rule['name']}] {detail}")
            else:
                failed_checks.append(rule["id"])
                critique_parts.append(f"  ❌ [{rule['name']}] {detail}")

    passed = len(failed_checks) == 0

    # 构建结构化批评文本
    critique = ""
    if not passed:
        lang_display = "Python" if language in ("python",) else "R"
        param_sys = "argparse" if language in ("python",) else "optparse/commandArgs"
        output_var = "os.environ['TASK_OUT_DIR']" if language in ("python",) else "Sys.getenv('TASK_OUT_DIR')"

        critique = f"""你的 {lang_display} 代码未通过以下 CNS 级质量规范检查，请根据批评逐项修复后重新输出完整代码：

{chr(10).join(critique_parts)}

修复要求：
- 所有输入文件路径必须通过 {param_sys} 参数接收，禁止硬编码路径
- 所有输出文件必须写入 {output_var} 目录
- 保持原代码的分析逻辑和策略不变，只修复检查发现的问题
- 请直接输出修复后的完整代码（用 ```{language} 包裹）"""
    elif warnings:
        critique = "\n".join(critique_parts)

    log.info(
        f"[CodeValidator] 硬检查完成: language={language}, "
        f"passed={passed}, failed={failed_checks}, warnings={warnings}"
    )

    return HardCheckResult(
        passed=passed,
        critique=critique,
        failed_checks=failed_checks,
        warnings=warnings,
    )


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

        # 使用 SystemMessage/HumanMessage 直接传递，
        # 避免 ChatPromptTemplate.from_messages 将代码中的 {} 误解析为模板变量
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=fix_prompt),
            HumanMessage(content="请修复代码中的所有问题，直接输出修复后的完整代码。"),
        ]

        response = await llm.ainvoke(messages)
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


async def review_generated_code(
    code: str,
    language: str,
    instruction: str,
    file_profiles_text: str = "",
    session: Any = None,
    user_id: Any = None,
) -> dict:
    """
    代码审核 Agent — 独立的代码审查和修复 Agent。

    程序说明：
    与 auto_fix_generated_code 不同，本函数启动一个完整的代码审核 Agent，
    从多个维度深入审查代码质量，不仅修复语法问题，还检查：
    1. 代码逻辑正确性（是否真正实现了用户需求）
    2. CNS 级作图规范（前序需求中强制要求的 ggplot2/ggsci/双格式输出等）
    3. 参数解析完整性（argparse/optparse 参数是否与 parameter_schema 一致）
    4. 错误处理和边界情况
    5. 库导入完整性
    6. 生物信息学最佳实践

    审核 Agent 会先输出审核报告，再输出修复后的完整代码。

    Args:
        code: 原始生成的代码
        language: 代码语言 (python, r)
        instruction: 用户原始分析需求
        file_profiles_text: 输入文件探查结果文本（用于校验列名引用是否正确）
        session: 数据库会话
        user_id: 用户 ID

    Returns:
        {
            "review_report": str,       # 审核报告摘要
            "issues_found": list,        # 发现的问题列表
            "fixed_code": str | None,    # 修复后的代码
            "changes_description": str,  # 修改说明
            "success": bool,             # 审核是否通过
            "re_validation": dict | None # 重新校验结果
        }
    """
    from app.utils.llm_config import get_fast_llm_config
    from langchain_openai import ChatOpenAI

    # 构建上下文注入文本
    profiles_context = ""
    if file_profiles_text:
        profiles_context = f"\n输入文件探查结果（代码中的列名必须与此一致）：\n{file_profiles_text[:2000]}\n"

    # 语言特定的额外审核规则
    if language in ("r", "R"):
        cns_rules = """
**CNS 作图规范审核（R 语言，极其重要）：**
- 是否使用了 ggsci 包的学术期刊配色（scale_fill_npg/jco/lancet 等）？
- 是否使用了学术主题（theme_bw/theme_minimal/theme_classic）而非默认灰色背景？
- 每个图形是否同时输出了 PDF（cairo_pdf 设备）和 PNG（dpi≥300）两种格式？
- 热图是否使用了 ComplexHeatmap 包？
- 是否保存了中间数据文件（CSV/TSV）？
- 是否使用了 set.seed() 确保可重复性？"""
    else:
        cns_rules = """
**Python 作图审核（Python 作图应优先使用 R，若确实使用 Python）：**
- 是否使用了 matplotlib/seaborn 的学术风格（seaborn.set_style('whitegrid') 等）？
- 图形是否同时保存了 PDF 和 PNG（dpi≥300）？
- 是否保存了中间数据文件（CSV/TSV）？"""

    review_prompt = f"""你是一个生物信息学高级代码审核专家。请对以下即席分析代码进行全面的代码审核。

用户分析需求：{instruction}
代码语言：{language}
{profiles_context}
当前代码：
```{language}
{code}
```

请从以下维度逐项审核代码：

**1. 正确性审核（CRITICAL）：**
- 代码逻辑是否正确实现了用户的分析需求？
- 数据读取路径是否正确（是否使用了正确的文件路径变量）？
- 分析步骤是否完整（数据加载 → 预处理 → 核心分析 → 结果输出）？
- 列名和数据字段引用是否正确（如有文件探查结果，必须严格使用探查出的列名）？

**2. 参数处理审核（CRITICAL）：**
- Python: argparse 定义是否与 parameter_schema 中的参数数量和名称一致？
- R: optparse/commandArgs 定义是否完整？
- 所有命令行参数是否都正确参与代码逻辑？
- 默认值是否符合生信经验？

**3. 输出路径审核（CRITICAL）：**
- 是否使用 TASK_OUT_DIR 环境变量？
- 所有输出文件（图形、数据表）是否写入 TASK_OUT_DIR？
- 没有硬编码路径（如 /tmp, /output, ~/ 等）？

**4. 作图质量审核：**
{cns_rules}

**5. 错误处理和健壮性：**
- 文件读取是否有错误处理（文件不存在等）？
- 关键计算步骤是否有适当的检查（如空值、NA 值处理）？
- 列名查找失败是否有友好错误提示？

**6. 库导入审核：**
- 所有使用的库是否都已导入/加载？
- 导入的库是否都在代码中实际使用了（无冗余导入）？

**7. 生物信息学最佳实践：**
- 统计检验方法是否正确（如 p 值校正方法、检验类型选择等）？
- 数据标准化/归一化方法是否合理？
- 聚类方法参数是否合理？

请按以下 JSON 格式输出审核结果：
```json
{{
  "review_report": "审核报告摘要（中文，2-4句概述审核结论）",
  "overall_verdict": "pass" | "minor_issues" | "major_issues",
  "issues_found": [
    {{
      "severity": "error" | "warning" | "info",
      "category": "正确性/参数处理/输出路径/作图质量/错误处理/库导入/最佳实践",
      "description": "问题描述（中文）",
      "suggestion": "修复建议"
    }}
  ],
  "fixed_code": "修复后的完整代码（若无修改则为 null）",
  "changes_description": "修改内容说明（中文，1-2句）"
}}
```

注意事项：
- 如果代码质量高、无明显问题，overall_verdict 设为 "pass"，issues_found 为空数组，fixed_code 为 null
- 如果有小问题（如配色建议、注释缺失），overall_verdict 设为 "minor_issues"
- 如果有严重问题（如语法错误、逻辑缺陷、参数不匹配），overall_verdict 设为 "major_issues" 并给出 fixed_code
- 修复代码时保持原有结构和逻辑不变，只修复发现的问题
- 修复后确保代码完整可执行"""

    try:
        llm_config = get_fast_llm_config(session, user_id)
        llm = ChatOpenAI(
            api_key=llm_config.api_key or "not-needed",
            base_url=llm_config.base_url,
            model=llm_config.model_name,
            temperature=0.0,
        )

        # 使用 SystemMessage/HumanMessage 直接传递，
        # 避免 ChatPromptTemplate.from_messages 将代码中的 {} 误解析为模板变量
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=review_prompt),
            HumanMessage(content="请对以上代码进行全面审核，输出严格 JSON 格式的审核结果。"),
        ]

        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # 清理 markdown 标记
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        import json as json_mod
        from json_repair import repair_json
        repaired = repair_json(raw)
        result = json_mod.loads(repaired)

        # 校验审核结果完整性
        if result.get("overall_verdict") == "pass":
            log.info("[CodeReviewer] 代码审核通过，无需修改")
            return {
                "review_report": result.get("review_report", "代码审核通过"),
                "overall_verdict": "pass",
                "issues_found": result.get("issues_found", []),
                "fixed_code": None,
                "changes_description": "代码审核通过，无需修改",
                "success": True,
                "re_validation": None,
            }

        # 有修改建议时，重新校验修复后的代码
        fixed_code = result.get("fixed_code")
        if fixed_code:
            re_validation = validate_generated_code(fixed_code, language)
            re_val_data = {
                "is_valid": re_validation.is_valid,
                "status_text": re_validation.status_text,
                "status_icon": re_validation.status_icon,
                "issues": [
                    {"severity": i.severity, "message": i.message, "suggestion": i.suggestion}
                    for i in re_validation.issues
                ],
            }

            issue_count = len(result.get("issues_found", []))
            error_count = len([i for i in result.get("issues_found", []) if i.get("severity") == "error"])

            log.info(
                f"[CodeReviewer] 代码审核完成: verdict={result.get('overall_verdict')}, "
                f"issues={issue_count}, errors={error_count}, "
                f"re-validate={re_validation.is_valid}"
            )

            return {
                "review_report": result.get("review_report", ""),
                "overall_verdict": result.get("overall_verdict", "minor_issues"),
                "issues_found": result.get("issues_found", []),
                "fixed_code": fixed_code,
                "changes_description": result.get("changes_description", f"修复了 {issue_count} 个问题"),
                "success": re_validation.is_valid,
                "re_validation": re_val_data,
            }
        else:
            # 有审核问题但无修复代码（仅建议）
            return {
                "review_report": result.get("review_report", ""),
                "overall_verdict": result.get("overall_verdict", "minor_issues"),
                "issues_found": result.get("issues_found", []),
                "fixed_code": None,
                "changes_description": result.get("changes_description", "发现代码问题但无法自动修复"),
                "success": True,
                "re_validation": None,
            }

    except Exception as e:
        log.error(f"[CodeReviewer] 代码审核 Agent 失败: {e}")
        return {
            "review_report": f"代码审核失败: {str(e)}",
            "overall_verdict": "major_issues",
            "issues_found": [],
            "fixed_code": None,
            "changes_description": "审核 Agent 异常，代码可能未经审核",
            "success": False,
            "re_validation": None,
        }
