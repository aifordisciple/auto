"""
超级执行者 Agent - 外部 AI 代码的"机械手" + 自然语言指令执行器

核心职责：
1. 接收外部 AI 生成的分析方案和代码
2. 智能解析代码块并自动映射文件路径
3. 沙箱执行 + 自动排错（最多 3 次重试）
4. 生成执行战报返回给用户
5. 【新增】支持自然语言指令，调用 LLM 理解并执行操作

状态机流程：
START → MODE_DETECT → [代码块模式?]
                          ↓ Yes
                     PARSE_INPUT → PATH_RESOLVE → EXECUTE
                                                  ↓
                                          [exit_code == 0?]
                                          Yes → GENERATE_REPORT → END
                                          No  → DEBUGGER → EXECUTE (max 3 times)
                                                          ↓
                                                     GENERATE_REPORT → END
                          ↓ No (自然语言模式)
                     LLM_UNDERSTAND → TOOL_EXECUTE → GENERATE_RESPONSE → END

支持的自然语言操作：
- 文件浏览：列出项目文件、查看目录结构
- 数据探查：预览表格、查看文件内容
- 系统操作：查看项目信息、检查文件状态
"""

import os
import re
import json
import time
import asyncio
from typing import TypedDict, List, Dict, Any, Optional, AsyncGenerator, Literal
from dataclasses import dataclass, field

from app.core.logger import log
from app.core.content_filter import preprocess_llm_response
from app.tools.bio_tools import run_container
from app.tools.probe_tools import scan_workspace, peek_tabular_data, inspect_h5ad, inspect_fastq, inspect_bam


# ==========================================
# ✨ 配置常量
# ==========================================
MAX_DEBUG_RETRIES = 3          # Debugger 最大重试次数
EXECUTION_TIMEOUT = 300        # 单个代码块执行超时（5分钟）
HEARTBEAT_INTERVAL = 30        # 心跳间隔（30秒）


# ==========================================
# ✨ 状态定义
# ==========================================

class SuperExecutorState(TypedDict):
    """超级执行者状态"""
    # 输入
    raw_input: str                    # 用户粘贴的外部 AI 输出
    project_id: str
    user_id: int

    # 解析结果
    extracted_code_blocks: List[Dict[str, Any]]  # [{language, code, order}]
    detected_paths: List[str]         # 代码中检测到的路径

    # 路径映射
    path_mappings: Dict[str, str]     # 假路径 -> 真实路径
    unresolved_paths: List[str]       # 无法解析的路径
    resolved_code_blocks: List[Dict[str, Any]]  # 替换后的代码

    # 执行状态
    execution_results: List[Dict[str, Any]]
    current_retry: int
    max_retries: int
    debug_context: Dict[str, Any]

    # 战报
    battle_report: Dict[str, Any]


# ==========================================
# ✨ 代码块数据类
# ==========================================

@dataclass
class CodeBlock:
    """代码块数据结构"""
    language: str           # python, r
    code: str               # 原始代码
    order: int              # 执行顺序
    status: str = "pending" # pending, running, success, failed
    output: str = ""        # 执行输出
    error: str = ""         # 错误信息
    exit_code: int = 0      # 退出码
    retry_count: int = 0    # 重试次数


# ==========================================
# ✨ 自然语言模式相关定义
# ==========================================

# 输入模式类型
InputMode = Literal["code_blocks", "natural_language"]


# 可用工具定义（用于 LLM 调用）
AVAILABLE_TOOLS = {
    "scan_workspace": {
        "description": "扫描指定目录下的所有文件和文件夹，返回目录树结构",
        "parameters": {
            "directory_path": {"type": "string", "description": "要扫描的目录绝对路径"},
            "max_depth": {"type": "integer", "description": "最大扫描深度，默认 3", "default": 3}
        },
        "function": scan_workspace
    },
    "peek_tabular_data": {
        "description": "预览表格文件（CSV/TSV）的结构：表头、维度和前几行数据",
        "parameters": {
            "file_path": {"type": "string", "description": "表格文件的绝对路径"},
            "n_rows": {"type": "integer", "description": "预览行数，默认 5", "default": 5}
        },
        "function": peek_tabular_data
    },
    "inspect_h5ad": {
        "description": "解析 .h5ad 单细胞 AnnData 文件结构",
        "parameters": {
            "file_path": {"type": "string", "description": ".h5ad 文件的绝对路径"}
        },
        "function": inspect_h5ad
    },
    "inspect_fastq": {
        "description": "预览 FASTQ 测序文件的基本信息",
        "parameters": {
            "file_path": {"type": "string", "description": "FASTQ 文件路径"},
            "n_reads": {"type": "integer", "description": "预览的 reads 数量，默认 5", "default": 5}
        },
        "function": inspect_fastq
    },
    "inspect_bam": {
        "description": "预览 BAM 比对文件的基本信息",
        "parameters": {
            "file_path": {"type": "string", "description": "BAM 文件路径"}
        },
        "function": inspect_bam
    }
}


# ==========================================
# ✨ 模式检测函数
# ==========================================

def detect_input_mode(text: str) -> InputMode:
    """
    检测输入模式：代码块模式 or 自然语言模式

    支持多种代码块格式：
    - ```python / ```Python / ```py
    - ```r / ```R
    - ``` （无语言标记但有代码特征）

    Args:
        text: 用户输入文本

    Returns:
        "code_blocks" 或 "natural_language"
    """
    # 检测标准代码块格式（支持可选换行符）
    python_pattern = r'```(?:python|py)\s*[\s\S]*?```'
    r_pattern = r'```(?:r|R)\s*[\s\S]*?```'

    has_python = bool(re.search(python_pattern, text, re.IGNORECASE))
    has_r = bool(re.search(r_pattern, text, re.IGNORECASE))

    if has_python or has_r:
        log.info(f"[SuperExecutor] 检测到代码块模式 (python={has_python}, r={has_r})")
        return "code_blocks"
    else:
        log.info(f"[SuperExecutor] 检测到自然语言模式")
        return "natural_language"


# ==========================================
# ✨ 自然语言处理函数
# ==========================================

async def process_natural_language(
    raw_input: str,
    project_dir: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    处理自然语言指令

    调用 LLM 理解用户意图，并执行相应的工具操作。

    Args:
        raw_input: 用户输入的自然语言指令
        project_dir: 项目目录路径
        api_key: LLM API Key
        base_url: LLM API Base URL
        model_name: LLM 模型名称

    Yields:
        SSE 事件字典
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    log.info(f"[SuperExecutor] 开始处理自然语言指令: {raw_input[:100]}...")

    # 构建工具描述
    tools_desc = "\n".join([
        f"- `{name}`: {info['description']}\n  参数: {json.dumps(info['parameters'], ensure_ascii=False)}"
        for name, info in AVAILABLE_TOOLS.items()
    ])

    system_prompt = f"""你是一个智能助手，帮助用户执行文件和数据分析操作。

用户的项目目录: {project_dir}

可用工具:
{tools_desc}

当用户发出指令时，你需要：
1. 理解用户意图
2. 选择合适的工具
3. 推断必要的参数（如文件路径）

请以 JSON 格式回复，格式如下：
```json
{{"tool": "工具名称", "parameters": {{"参数名": "参数值"}}}}
```

如果用户的指令不需要调用工具（如简单的问候或闲聊），请直接回复文本，不要使用 JSON 格式。

示例：
用户: "列出项目文件"
回复: {{"tool": "scan_workspace", "parameters": {{"directory_path": "{project_dir}"}}}}

用户: "查看 raw_data 目录下的文件"
回复: {{"tool": "scan_workspace", "parameters": {{"directory_path": "{project_dir}/raw_data"}}}}

用户: "预览 counts.csv 文件"
回复: {{"tool": "peek_tabular_data", "parameters": {{"file_path": "{project_dir}/raw_data/counts.csv"}}}}
"""

    try:
        # 推送状态更新
        yield {
            "event": "status_update",
            "data": json.dumps({"status": "understanding", "message": "正在理解您的指令..."})
        }

        # 创建 LLM 客户端
        actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"
        llm = ChatOpenAI(
            api_key=actual_api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.1,
            max_retries=2
        )

        # 调用 LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=raw_input)
        ]

        response = await llm.ainvoke(messages)
        llm_response = response.content

        log.info(f"[SuperExecutor] LLM 响应: {llm_response[:200]}...")

        # 尝试解析 JSON 工具调用
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
        if json_match:
            try:
                tool_call = json.loads(json_match.group(1))
                tool_name = tool_call.get("tool")
                parameters = tool_call.get("parameters", {})

                if tool_name in AVAILABLE_TOOLS:
                    # 推送工具调用信息
                    yield {
                        "event": "tool_call",
                        "data": json.dumps({
                            "tool": tool_name,
                            "parameters": parameters
                        })
                    }

                    # 执行工具
                    tool_info = AVAILABLE_TOOLS[tool_name]
                    tool_func = tool_info["function"]

                    # 推送执行状态
                    yield {
                        "event": "status_update",
                        "data": json.dumps({"status": "executing", "message": f"正在执行 {tool_name}..."})
                    }

                    # 调用工具（同步调用，需要包装为异步）
                    result = tool_func.invoke(parameters)

                    log.info(f"[SuperExecutor] 工具执行完成: {tool_name}")

                    # 推送执行结果
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "tool": tool_name,
                            "result": result
                        })
                    }

                    # 生成最终响应
                    yield {
                        "event": "natural_language_response",
                        "data": json.dumps({
                            "message": f"✅ 操作完成",
                            "tool_used": tool_name,
                            "result_preview": result[:1000] + "..." if len(result) > 1000 else result
                        })
                    }
                else:
                    # 未知工具
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": f"未知工具: {tool_name}"})
                    }

            except json.JSONDecodeError as e:
                log.error(f"[SuperExecutor] JSON 解析失败: {e}")
                yield {
                    "event": "natural_language_response",
                    "data": json.dumps({"message": llm_response})
                }
        else:
            # 没有检测到 JSON，直接返回 LLM 响应
            yield {
                "event": "natural_language_response",
                "data": json.dumps({"message": llm_response})
            }

    except Exception as e:
        log.error(f"[SuperExecutor] 自然语言处理失败: {e}")
        yield {
            "event": "error",
            "data": json.dumps({"error": f"处理失败: {str(e)}"})
        }

    # 完成
    yield {
        "event": "done",
        "data": json.dumps({"message": "[DONE]"})
    }


# ==========================================
# ✨ 核心解析函数
# ==========================================

def extract_code_blocks(text: str) -> List[CodeBlock]:
    """
    从文本中提取代码块

    支持：
    1. ```python ... ```
    2. ```r ... ```
    3. ```R ... ```
    4. 混合多代码块

    Args:
        text: 包含代码块的文本

    Returns:
        代码块列表，按出现顺序排序
    """
    # 🔧 预处理：过滤 thinking 标签
    text = preprocess_llm_response(text)

    blocks = []

    # 匹配 Python 代码块
    python_pattern = r'```python\s*\n([\s\S]*?)```'
    for match in re.finditer(python_pattern, text, re.IGNORECASE):
        blocks.append(CodeBlock(
            language="python",
            code=match.group(1).strip(),
            order=len(blocks)
        ))

    # 匹配 R 代码块
    r_pattern = r'```r\s*\n([\s\S]*?)```'
    for match in re.finditer(r_pattern, text, re.IGNORECASE):
        blocks.append(CodeBlock(
            language="r",
            code=match.group(1).strip(),
            order=len(blocks)
        ))

    log.info(f"[SuperExecutor] 提取到 {len(blocks)} 个代码块")
    return blocks


def extract_file_paths(text: str) -> List[str]:
    """
    从代码中提取文件路径

    检测模式：
    1. 引号包裹的路径字符串
    2. 路径分隔符 / 或 \
    3. 常见文件扩展名

    Args:
        text: 代码文本

    Returns:
        去重后的路径列表
    """
    # 匹配引号中的路径（包含 / 或 \）
    path_pattern = r'["\']([^"\']*(?:/|\\)[^"\']*?)["\']'
    matches = re.findall(path_pattern, text)

    # 过滤掉明显的非文件路径
    valid_paths = []
    for path in matches:
        # 跳过 URL、短于 3 字符的路径、纯数字路径
        if path.startswith('http') or len(path) < 3 or path.isdigit():
            continue
        # 跳过纯变量名（不包含扩展名或路径分隔符）
        if '.' not in path and '/' not in path and '\\' not in path:
            continue
        valid_paths.append(path)

    # 去重
    unique_paths = list(set(valid_paths))
    log.info(f"[SuperExecutor] 检测到 {len(unique_paths)} 个路径")
    return unique_paths


def fuzzy_match_file(filename: str, project_dir: str) -> Optional[str]:
    """
    模糊匹配文件名

    使用 Levenshtein 距离进行模糊匹配

    Args:
        filename: 目标文件名（可能不完整或不精确）
        project_dir: 项目目录

    Returns:
        匹配到的真实路径，未找到返回 None
    """
    import os
    from difflib import SequenceMatcher

    # 扫描项目目录
    all_files = []
    for root, dirs, files in os.walk(project_dir):
        for f in files:
            all_files.append(os.path.join(root, f))

    # 提取目标文件名
    target_name = os.path.basename(filename)

    # 计算相似度
    best_match = None
    best_ratio = 0.0

    for file_path in all_files:
        file_name = os.path.basename(file_path)
        ratio = SequenceMatcher(None, target_name.lower(), file_name.lower()).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = file_path

    # 相似度阈值 0.7
    if best_ratio >= 0.7:
        log.info(f"[SuperExecutor] 模糊匹配: {filename} -> {best_match} (相似度: {best_ratio:.2f})")
        return best_match

    return None


def resolve_paths(
    detected_paths: List[str],
    project_id: str,
    project_dir: str
) -> Dict[str, str]:
    """
    解析文件路径映射

    将外部 AI 输出中的"假路径"映射到项目中的真实文件

    Args:
        detected_paths: 检测到的路径列表
        project_id: 项目 ID
        project_dir: 项目目录

    Returns:
        路径映射字典 {假路径: 真实路径}
    """
    mappings = {}

    for fake_path in detected_paths:
        # 1. 尝试精确匹配
        filename = os.path.basename(fake_path)
        potential_real_path = os.path.join(project_dir, "raw_data", filename)

        if os.path.exists(potential_real_path):
            mappings[fake_path] = potential_real_path
            log.info(f"[SuperExecutor] 精确匹配: {fake_path} -> {potential_real_path}")
            continue

        # 2. 尝试在整个项目目录中搜索
        for subdir in ["raw_data", "results", "references", ""]:
            search_path = os.path.join(project_dir, subdir, filename) if subdir else os.path.join(project_dir, filename)
            if os.path.exists(search_path):
                mappings[fake_path] = search_path
                log.info(f"[SuperExecutor] 搜索匹配: {fake_path} -> {search_path}")
                break
        else:
            # 3. 尝试模糊匹配
            fuzzy_match = fuzzy_match_file(filename, project_dir)
            if fuzzy_match:
                mappings[fake_path] = fuzzy_match
            else:
                log.warning(f"[SuperExecutor] 无法解析路径: {fake_path}")

    return mappings


def apply_path_mappings(code: str, path_mappings: Dict[str, str]) -> str:
    """
    应用路径映射到代码

    将代码中的假路径替换为真实路径

    Args:
        code: 原始代码
        path_mappings: 路径映射字典

    Returns:
        替换后的代码
    """
    result = code
    for fake_path, real_path in path_mappings.items():
        # 转义路径中的特殊字符
        escaped_fake = re.escape(fake_path)
        result = re.sub(escaped_fake, real_path, result)

    return result


# ==========================================
# ✨ 执行函数
# ==========================================

async def execute_code_block(
    code_block: CodeBlock,
    project_id: str,
    task_out_dir: str,
    user_id: int = None
) -> Dict[str, Any]:
    """
    在沙箱中执行单个代码块

    Args:
        code_block: 代码块对象
        project_id: 项目 ID
        task_out_dir: 任务输出目录
        user_id: 用户 ID（用于用户级包管理）

    Returns:
        执行结果字典
    """
    log.info(f"[SuperExecutor] 执行代码块: language={code_block.language}, order={code_block.order}")

    # 确保输出目录存在
    os.makedirs(task_out_dir, exist_ok=True)

    # 构建环境变量
    environment = {
        "TASK_OUT_DIR": task_out_dir,
        "PROJECT_ID": project_id,
        "SUPER_EXECUTOR_MODE": "true"
    }

    # 调用沙箱执行
    output, exit_code = run_container(
        image='autonome-tool-env',
        command=code_block.code,
        language=code_block.language,
        environment=environment,
        timeout=EXECUTION_TIMEOUT,
        user_id=user_id
    )

    return {
        "language": code_block.language,
        "order": code_block.order,
        "output": output,
        "exit_code": exit_code,
        "status": "success" if exit_code == 0 else "failed"
    }


def extract_error_message(output: str) -> str:
    """
    从执行输出中提取错误信息

    检测以下错误模式：
    1. ❌ 标记
    2. Python 异常堆栈 (Traceback)
    3. R 错误信息 (Error in...)

    Args:
        output: 执行输出

    Returns:
        提取的错误信息，无错误返回空字符串
    """
    if "❌" in output:
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if "❌" in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 5)
                return "\n".join(lines[start:end])

    if "Traceback" in output:
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if "Traceback" in line:
                return "\n".join(lines[i:i+10])

    if "Error in" in output or "Error:" in output:
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if "Error" in line:
                return "\n".join(lines[i:i+5])

    return ""


async def fix_code_with_llm(
    code: str,
    error_msg: str,
    language: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> Optional[str]:
    """
    调用 LLM 修复代码

    Args:
        code: 原始代码
        error_msg: 错误信息
        language: 语言类型
        api_key: API Key
        base_url: API Base URL
        model_name: 模型名称

    Returns:
        修复后的代码，失败返回 None
    """
    from app.services.celery_app import fix_code_with_llm as _fix_code_with_llm

    try:
        fixed_code = _fix_code_with_llm(
            code=code,
            error_msg=error_msg,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            language=language,
            timeout=90
        )
        return fixed_code
    except Exception as e:
        log.error(f"[SuperExecutor] LLM 修复失败: {e}")
        return None


# ==========================================
# ✨ 战报生成
# ==========================================

def generate_battle_report(
    execution_results: List[Dict[str, Any]],
    path_mappings: Dict[str, str],
    task_out_dir: str
) -> Dict[str, Any]:
    """
    生成执行战报

    Args:
        execution_results: 执行结果列表
        path_mappings: 路径映射字典
        task_out_dir: 任务输出目录

    Returns:
        战报字典
    """
    # 统计成功/失败数量
    success_count = sum(1 for r in execution_results if r.get("exit_code") == 0)
    failed_count = len(execution_results) - success_count

    # 统计重试次数
    total_retries = sum(r.get("retry_count", 0) for r in execution_results)

    # 扫描输出目录获取生成文件
    generated_files = []
    if os.path.exists(task_out_dir):
        for root, dirs, files in os.walk(task_out_dir):
            for f in files:
                file_path = os.path.join(root, f)
                # 跳过临时文件和脚本文件
                if f.startswith('.') or f in ['latest_script.py', 'latest_script.R']:
                    continue
                file_size = os.path.getsize(file_path)
                generated_files.append({
                    "path": file_path,
                    "name": f,
                    "size": file_size,
                    "extension": os.path.splitext(f)[1].lower()
                })

    # 按文件大小排序
    generated_files.sort(key=lambda x: x["size"], reverse=True)

    return {
        "task_out_dir": task_out_dir,  # 任务输出目录路径
        "success_count": success_count,
        "failed_count": failed_count,
        "total_retries": total_retries,
        "path_mappings": path_mappings,
        "generated_files": generated_files[:50],  # 最多显示 50 个文件
        "execution_summary": [
            {
                "order": r.get("order", 0),
                "language": r.get("language", "unknown"),
                "status": r.get("status", "unknown"),
                "exit_code": r.get("exit_code", -1),
                "retry_count": r.get("retry_count", 0),
                "error": r.get("error", "")[:500] if r.get("error") else ""
            }
            for r in execution_results
        ]
    }


# ==========================================
# ✨ 主执行器类
# ==========================================

class SuperExecutor:
    """超级执行者主类"""

    def __init__(
        self,
        raw_input: str,
        project_id: str,
        user_id: int,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None
    ):
        self.raw_input = raw_input
        self.project_id = project_id
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

        # 项目目录
        self.project_dir = f"/workspace/project_{project_id}"
        self.task_out_dir = f"{self.project_dir}/results/super_executor_{int(time.time())}"

        # 状态
        self.code_blocks: List[CodeBlock] = []
        self.path_mappings: Dict[str, str] = {}
        self.execution_results: List[Dict[str, Any]] = []

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行超级执行者

        支持两种模式：
        1. 代码块模式：提取并执行代码块
        2. 自然语言模式：调用 LLM 理解并执行用户指令

        Yields:
            SSE 事件字典
        """
        log.info(f"🚀 [SuperExecutor] 开始执行 - project_id={self.project_id}")

        # ==========================================
        # ✨ 模式检测
        # ==========================================
        input_mode = detect_input_mode(self.raw_input)

        # 推送模式检测状态
        yield {
            "event": "mode_detected",
            "data": json.dumps({
                "mode": input_mode,
                "message": "检测到代码块模式" if input_mode == "code_blocks" else "检测到自然语言模式"
            })
        }

        # ==========================================
        # ✨ 自然语言模式：调用 LLM 处理
        # ==========================================
        if input_mode == "natural_language":
            log.info(f"[SuperExecutor] 进入自然语言处理模式")

            async for event in process_natural_language(
                raw_input=self.raw_input,
                project_dir=self.project_dir,
                api_key=self.api_key,
                base_url=self.base_url,
                model_name=self.model_name
            ):
                yield event

            return  # 自然语言模式处理完成，直接返回

        # ==========================================
        # ✨ 代码块模式：原有逻辑
        # ==========================================
        log.info(f"[SuperExecutor] 进入代码块执行模式")

        # 事件队列，用于从回调中收集事件
        event_queue = []

        def collect_event(event: Dict[str, Any]):
            """事件收集回调"""
            event_queue.append(event)

        # 1. 解析输入
        yield {
            "event": "status_update",
            "data": json.dumps({"status": "parsing", "message": "正在解析外部 AI 输出..."})
        }

        self.code_blocks = extract_code_blocks(self.raw_input)

        if not self.code_blocks:
            yield {
                "event": "error",
                "data": json.dumps({"error": "未检测到可执行的代码块"})
            }
            return

        yield {
            "event": "code_extracted",
            "data": json.dumps({
                "blocks": [
                    {"language": b.language, "order": b.order, "code_preview": b.code[:200] + "..." if len(b.code) > 200 else b.code}
                    for b in self.code_blocks
                ]
            })
        }

        # 2. 路径解析
        yield {
            "event": "status_update",
            "data": json.dumps({"status": "resolving", "message": "正在解析文件路径..."})
        }

        all_detected_paths = []
        for block in self.code_blocks:
            paths = extract_file_paths(block.code)
            all_detected_paths.extend(paths)

        # 去重
        all_detected_paths = list(set(all_detected_paths))

        self.path_mappings = resolve_paths(
            detected_paths=all_detected_paths,
            project_id=self.project_id,
            project_dir=self.project_dir
        )

        # 检查未解析的路径
        unresolved = [p for p in all_detected_paths if p not in self.path_mappings]

        yield {
            "event": "path_resolved",
            "data": json.dumps({
                "mappings": self.path_mappings,
                "unresolved": unresolved
            })
        }

        # 3. 应用路径映射
        for block in self.code_blocks:
            block.code = apply_path_mappings(block.code, self.path_mappings)

        # 4. 执行代码块
        yield {
            "event": "status_update",
            "data": json.dumps({"status": "executing", "message": "正在执行代码..."})
        }

        for block in self.code_blocks:
            # 清空事件队列
            event_queue.clear()

            # 执行（带回调）
            result = await self._execute_block_with_retry(block, collect_event)
            self.execution_results.append(result)

            # 先输出执行进度
            yield {
                "event": "execution_progress",
                "data": json.dumps({
                    "block_order": block.order,
                    "status": result.get("status"),
                    "exit_code": result.get("exit_code")
                })
            }

            # 输出回调收集的事件（如 debug_retry）
            for event in event_queue:
                yield event

        # 5. 生成战报
        yield {
            "event": "status_update",
            "data": json.dumps({"status": "generating_report", "message": "正在生成执行战报..."})
        }

        battle_report = generate_battle_report(
            execution_results=self.execution_results,
            path_mappings=self.path_mappings,
            task_out_dir=self.task_out_dir
        )

        yield {
            "event": "battle_report",
            "data": json.dumps(battle_report)
        }

        # 6. 完成
        log.info(f"🏁 [SuperExecutor] 执行完成 - 成功: {battle_report['success_count']}, 失败: {battle_report['failed_count']}")

        yield {
            "event": "done",
            "data": json.dumps({"message": "[DONE]"})
        }

    async def _execute_block_with_retry(
        self,
        block: CodeBlock,
        event_callback: callable = None
    ) -> Dict[str, Any]:
        """
        执行单个代码块（带重试机制）

        Args:
            block: 代码块对象
            event_callback: 事件回调函数，用于推送 SSE 事件

        Returns:
            执行结果字典
        """
        retry_count = 0
        last_error = ""

        while retry_count <= MAX_DEBUG_RETRIES:
            # 执行
            result = await execute_code_block(
                code_block=block,
                project_id=self.project_id,
                task_out_dir=self.task_out_dir,
                user_id=self.user_id
            )

            result["retry_count"] = retry_count

            # 检查是否成功
            if result["exit_code"] == 0:
                return result

            # 提取错误信息
            error_msg = extract_error_message(result["output"])
            last_error = error_msg or result["output"][:500]

            # 检查是否需要重试
            if retry_count < MAX_DEBUG_RETRIES:
                retry_count += 1

                log.warning(f"[SuperExecutor] 代码块 {block.order} 执行失败，准备第 {retry_count} 次重试")

                # 推送重试事件（通过回调）
                if event_callback:
                    event_callback({
                        "event": "debug_retry",
                        "data": json.dumps({
                            "block_order": block.order,
                            "attempt": retry_count,
                            "max_retries": MAX_DEBUG_RETRIES,
                            "error": last_error[:500]
                        })
                    })

                # 尝试 LLM 修复
                if self.api_key and self.base_url and self.model_name:
                    fixed_code = await fix_code_with_llm(
                        code=block.code,
                        error_msg=last_error,
                        language=block.language,
                        api_key=self.api_key,
                        base_url=self.base_url,
                        model_name=self.model_name
                    )

                    if fixed_code:
                        block.code = fixed_code
                        log.info(f"[SuperExecutor] 代码已通过 LLM 修复")
                else:
                    log.warning("[SuperExecutor] 未配置 LLM，跳过自动修复")

            else:
                # 达到最大重试次数
                result["error"] = last_error
                return result

        return {
            "language": block.language,
            "order": block.order,
            "output": "",
            "exit_code": 1,
            "status": "failed",
            "retry_count": retry_count,
            "error": f"达到最大重试次数 ({MAX_DEBUG_RETRIES}): {last_error}"
        }


log.info("🦾 超级执行者 Agent 模块已加载")