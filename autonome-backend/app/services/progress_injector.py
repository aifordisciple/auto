"""
脚本进度标记注入器 - 在执行脚本中注入结构化进度报告。

程序说明：
在执行前，向生成的 Python/R 脚本中注入进度报告辅助函数。
脚本在关键步骤调用这些函数，输出 __AUTONOME_PROGRESS__ 标记行。
SSE 端点解析这些标记行，推送结构化进度事件给前端，
前端据此渲染进度条和步骤描述，替代原始 Docker 日志的可读性问题。

进度标记格式：
__AUTONOME_PROGRESS__:<step>:<total>:<message>__

辅助函数：
Python: __autonome_progress__(step, total, message)
R:      __autonome_progress__(step, total, message)
"""
from app.core.logger import log

# Python 进度辅助函数（注入到脚本开头）
PYTHON_PROGRESS_HELPER = '''
import sys as __sys
def __autonome_progress__(step, total, message):
    """报告分析进度，格式: __AUTONOME_PROGRESS__:step:total:message__"""
    __sys.stdout.write(f"__AUTONOME_PROGRESS__:{step}:{total}:{message}__\\n")
    __sys.stdout.flush()
'''

# R 进度辅助函数（注入到脚本开头）
R_PROGRESS_HELPER = '''
__autonome_progress__ <- function(step, total, message) {
  cat(sprintf("__AUTONOME_PROGRESS__:%d:%d:%s__\\n", step, total, message))
}
'''

# 进度标记解析正则
import re
PROGRESS_PATTERN = re.compile(r'__AUTONOME_PROGRESS__:(\d+):(\d+):([^_].*?)__')


def inject_progress_helper(code: str, language: str) -> str:
    """
    在脚本开头注入进度报告辅助函数。

    Args:
        code: 原始脚本代码
        language: 脚本语言 (python / r)

    Returns:
        注入辅助函数后的代码
    """
    if language == 'python':
        return PYTHON_PROGRESS_HELPER.lstrip('\n') + '\n' + code
    elif language in ('r', 'R'):
        return R_PROGRESS_HELPER.lstrip('\n') + '\n' + code
    else:
        return code


def parse_progress_line(line: str) -> dict | None:
    """
    解析日志行中的进度标记。

    Args:
        line: 日志行文本

    Returns:
        如果包含进度标记，返回 {"step": int, "total": int, "message": str, "percent": float}
        否则返回 None
    """
    match = PROGRESS_PATTERN.search(line)
    if not match:
        return None
    step = int(match.group(1))
    total = int(match.group(2))
    message = match.group(3).strip()
    percent = (step / total * 100) if total > 0 else 0
    return {
        "step": step,
        "total": total,
        "message": message,
        "percent": round(percent, 1),
    }


def is_system_log_line(line: str) -> bool:
    """
    判断日志行是否为系统日志（pip install、apt-get 等环境准备输出）。

    系统日志特征：
    - pip install / pip3 install
    - Collecting / Downloading / Installing
    - apt-get / apt
    - Requirement already satisfied
    - WARNING: (pip 警告)
    - 空行或纯空白

    Args:
        line: 日志行文本

    Returns:
        True 表示系统日志，应在前端默认折叠
    """
    system_patterns = [
        r'^\s*(Collecting|Downloading|Installing|Requirement already|Successfully installed)',
        r'^\s*(pip|pip3)\s',
        r'^\s*(apt-get|apt)\s',
        r'^\s*WARNING:\s',
        r'^\s*Looking in indexes',
        r'^\s*Processing\s',
        r'^\s*Preparing metadata',
        r'^\s*Building wheel',
        r'^\s*Running setup\.py',
        r'^\s*Created wheel',
        r'^\s*Stored in directory',
    ]
    for pattern in system_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return not line.strip()


def classify_log_line(line: str) -> tuple[str, dict | None]:
    """
    分类日志行：系统日志 / 分析日志 / 进度事件。

    Args:
        line: Docker 输出的原始日志行

    Returns:
        (category, progress_data) 元组:
        - category: "progress" | "system" | "analysis"
        - progress_data: 仅 category=="progress" 时非 None
    """
    # 优先检测进度标记
    progress = parse_progress_line(line)
    if progress:
        return ("progress", progress)

    # 检测系统日志
    if is_system_log_line(line):
        return ("system", None)

    # 默认：分析日志
    return ("analysis", None)


def enhance_llm_prompt_for_progress() -> str:
    """
    返回用于增强 ADHOC_SYSTEM_PROMPT 的进度标记说明文本。

    告知 LLM 在生成的分析代码中调用 __autonome_progress__ 函数，
    将分析流程分解为若干步骤并报告进度。

    Returns:
        进度标记使用说明文本
    """
    return """
进度报告要求（新增）：
- 在代码的关键步骤调用进度报告函数：
  * Python: __autonome_progress__(step, total, message)
  * R:      __autonome_progress__(step, total, message)
- 将分析流程分解为 3-6 个关键步骤，如：
  * step 1: "加载数据"
  * step 2: "数据预处理"
  * step 3: "执行分析"
  * step 4: "生成图表"
  * step 5: "保存结果"
- 每个步骤调用一次 __autonome_progress__，step 从 1 递增
- 进度消息使用中文，简洁描述当前步骤（不超过 15 字）
- 示例（Python）：
  __autonome_progress__(1, 4, "加载表达矩阵")
  df = pd.read_csv(args.input, sep='\\t')
  __autonome_progress__(2, 4, "数据标准化")
  ...
"""
