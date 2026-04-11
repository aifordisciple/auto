"""
超级执行者 V4 - 三步执行流程

核心创新：
1. Phase 1 - 探查阶段：生成并执行探查代码，获取文件详细结构
2. Phase 2 - 安装依赖：解析依赖，使用 conda 安装缺失的包
3. Phase 3 - 执行分析：基于探查结果生成并执行最终脚本

状态机流程：
START → PHASE_1_EXPLORE → PHASE_2_INSTALL_DEPS → PHASE_3_EXECUTE → END
             ↓                    ↓                    ↓
       [探测代码生成]        [conda安装]          [分析执行+重试]
       [沙箱执行]           [启用网络]            [生成战报]
"""

import os
import re
import json
import time
import uuid
import asyncio
from enum import Enum
from typing import TypedDict, List, Dict, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field

from app.core.logger import log
from app.tools.bio_tools import run_container


# ==========================================
# ✨ 配置常量
# ==========================================
MAX_DEBUG_RETRIES = 3          # Debugger 最大重试次数
EXECUTION_TIMEOUT = 600        # 脚本执行超时（10分钟）
INSTALL_TIMEOUT = 600          # 包安装超时（10分钟）
HEARTBEAT_INTERVAL = 30        # 心跳间隔（30秒）


# ==========================================
# ✨ 状态机定义
# ==========================================

class ExecutionPhase(str, Enum):
    """执行阶段状态机"""
    IDLE = "idle"
    PHASE_1_EXPLORING = "phase_1_exploring"
    PHASE_1_COMPLETE = "phase_1_complete"
    PHASE_2_INSTALLING = "phase_2_installing"
    PHASE_2_COMPLETE = "phase_2_complete"
    PHASE_3_EXECUTING = "phase_3_executing"
    PHASE_3_COMPLETE = "phase_3_complete"
    COMPLETED = "completed"
    ERROR = "error"


class SSEEventType(str, Enum):
    """SSE 事件类型"""
    # 阶段状态
    PHASE_CHANGE = "phase_change"
    STATUS_UPDATE = "status_update"

    # Phase 1 事件
    EXPLORATION_START = "exploration_start"
    EXPLORATION_PROGRESS = "exploration_progress"
    EXPLORATION_COMPLETE = "exploration_complete"
    FILES_DETECTED = "files_detected"

    # Phase 2 事件
    DEPENDENCY_RESOLVE_START = "dependency_resolve_start"
    DEPENDENCY_RESOLVE_COMPLETE = "dependency_resolve_complete"
    INSTALL_START = "install_start"
    INSTALL_PROGRESS = "install_progress"
    INSTALL_COMPLETE = "install_complete"

    # Phase 3 事件
    SCRIPT_GENERATED = "script_generated"
    EXECUTION_START = "execution_start"
    EXECUTION_PROGRESS = "execution_progress"
    EXECUTION_OUTPUT = "execution_output"
    DEBUG_RETRY = "debug_retry"
    EXECUTION_COMPLETE = "execution_complete"

    # 最终结果
    BATTLE_REPORT = "battle_report"
    MESSAGE = "message"
    ERROR = "error"
    DONE = "done"
    HEARTBEAT = "heartbeat"


# ==========================================
# ✨ 数据类定义
# ==========================================

@dataclass
class FileInfo:
    """探测到的文件信息"""
    path: str                    # 文件路径
    file_type: str               # 文件类型 (csv, tsv, h5ad, fastq, bam, etc.)
    size_bytes: int              # 文件大小
    columns: List[str] = field(default_factory=list)  # 表格列名（如适用）
    n_rows: Optional[int] = None  # 行数（如适用）
    preview: Optional[str] = None  # 预览内容


@dataclass
class ExplorationResult:
    """Phase 1 探查结果"""
    detected_files: List[FileInfo]           # 探测到的文件
    inferred_intent: str                     # 推断的用户意图
    suggested_packages: List[str]            # 建议安装的包
    environment_context: Dict[str, Any]      # 环境上下文
    exploration_script: str                  # 生成的探查脚本
    exploration_output: str                  # 探查脚本输出
    success: bool
    error_message: Optional[str] = None


@dataclass
class PackageInstallResult:
    """单个包安装结果"""
    package_name: str
    version: str
    status: str  # "installed", "skipped", "failed"
    install_time: float
    error_message: Optional[str] = None


@dataclass
class DependencyInstallResult:
    """Phase 2 依赖安装结果"""
    packages_to_install: List[str]           # 需要安装的包列表
    installed_packages: List[PackageInstallResult]  # 安装结果
    skipped_packages: List[str]              # 跳过的包（已存在）
    failed_packages: List[str]               # 安装失败的包
    total_install_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class ExecutionResult:
    """Phase 3 执行结果"""
    script: str                    # 最终执行脚本
    stdout: str                    # 标准输出
    stderr: str                    # 错误输出
    exit_code: int                 # 退出码
    execution_time: float          # 执行时间
    generated_files: List[Dict[str, Any]]  # 生成的文件
    retry_count: int               # 重试次数
    success: bool
    error_message: Optional[str] = None


@dataclass
class SuperExecutorV4Context:
    """V4 完整执行上下文"""
    # 基础信息
    task_id: str
    project_id: str
    project_dir: str
    output_dir: str
    user_id: int
    raw_input: str

    # 阶段状态
    current_phase: ExecutionPhase = ExecutionPhase.IDLE

    # 各阶段结果
    phase_1_result: Optional[ExplorationResult] = None
    phase_2_result: Optional[DependencyInstallResult] = None
    phase_3_result: Optional[ExecutionResult] = None

    # LLM 配置
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


@dataclass
class GeneratedScript:
    """LLM 生成的脚本"""
    code: str                    # 生成的 Python 脚本
    user_intent: str             # 理解的用户意图
    detected_paths: List[str]    # 检测到的文件路径
    path_mappings: Dict[str, str] = field(default_factory=dict)
    includes_r_code: bool = False  # 是否包含 R 代码调用


# ==========================================
# ✨ LLM Prompt 模板
# ==========================================

# 系统预装包列表
PREINSTALLED_PACKAGES = {
    'numpy', 'pandas', 'scipy', 'matplotlib', 'seaborn',
    'scanpy', 'anndata', 'scikit-learn', 'requests',
    'biopython', 'pysam', 'h5py', 'numba', 'statsmodels'
}

EXPLORATION_GENERATOR_SYSTEM_PROMPT = """你是一个智能数据探查专家。你的任务是生成 Python 代码来探查用户命令中可能用到的文件。

## 核心任务

1. 分析用户命令，推断可能需要的数据文件
2. 生成探查代码，获取文件的详细结构信息
3. 根据文件类型，推断需要的 Python 包

## 项目信息

- 项目目录: {project_dir}
- 原始数据目录: {project_dir}/raw_data/
- 结果输出目录: {output_dir}/
- 可用文件列表:
{available_files}

## 探查代码要求

1. 使用 os 模块检查文件是否存在
2. 对于表格文件（csv, tsv, xlsx）：
   - 读取前 5 行预览
   - 获取列名列表
   - 统计行数和列数
3. 对于单细胞数据（h5ad）：
   - 读取 obs, var, obsm 等结构
   - 获取细胞数和基因数
4. 对于测序文件（fastq, bam）：
   - 统计 reads 数量
   - 计算平均长度和 GC 含量

## 输出格式

请以 JSON 格式回复：

```json
{{
    "inferred_intent": "用户意图描述（中文）",
    "detected_file_patterns": ["可能用到的文件名模式"],
    "suggested_packages": ["推断需要的包，如 scanpy, pandas, gseapy 等"],
    "exploration_script": "生成的探查 Python 代码"
}}
```

## 注意事项

1. 探查代码必须安全，不能修改或删除文件
2. 探查代码必须处理文件不存在的情况
3. 探查代码必须设置合理的超时（避免读取超大文件）
4. 输出必须包含足够的信息用于后续分析

## 示例

用户命令: "对 counts.csv 做差异表达分析"

输出:
```json
{{
    "inferred_intent": "对 counts.csv 文件进行差异表达分析",
    "detected_file_patterns": ["counts.csv"],
    "suggested_packages": ["pandas", "scanpy", "scipy"],
    "exploration_script": "import os\\nimport pandas as pd\\n\\nfile_path = '{project_dir}/raw_data/counts.csv'\\nif os.path.exists(file_path):\\n    df = pd.read_csv(file_path, nrows=5)\\n    print(f'Columns: {{list(df.columns)}}')\\n    print(f'Shape preview: {{df.shape}}')\\nelse:\\n    print(f'File not found: {{file_path}}')"
}}
```
"""

DEPENDENCY_RESOLVER_SYSTEM_PROMPT = """你是一个 Python/R 依赖解析专家。根据用户命令和探查结果，确定需要安装的包。

## 核心任务

1. 分析用户命令中的分析需求
2. 结合探查结果中的文件类型
3. 确定需要的包及其版本（如有特殊要求）

## 已探查信息

{exploration_result}

## 用户命令

{raw_input}

## 系统预装包列表

以下包已在系统中安装，无需安装：
- numpy, pandas, scipy, matplotlib, seaborn
- scanpy, anndata
- scikit-learn
- requests, aiohttp
- biopython, pysam
- h5py, numba, statsmodels

## 输出格式

请以 JSON 格式回复：

```json
{{
    "required_packages": [
        {{
            "name": "包名",
            "version": "版本（可选，留空表示最新版）",
            "reason": "为什么需要这个包",
            "conda_channel": "conda-forge 或 bioconda 或 defaults"
        }}
    ],
    "install_order": ["按依赖顺序排列的包名"],
    "estimated_install_time": 预估安装时间（秒）
}}
```

## 注意事项

1. 检查是否已在系统预装列表中
2. 考虑包之间的依赖关系
3. 生信相关包优先从 bioconda 安装
4. 如果用户命令不需要额外包，返回空列表
"""

ANALYSIS_SCRIPT_GENERATOR_PROMPT = """你是一个智能分析脚本生成专家。根据探查结果和用户命令，生成完整的分析脚本。

## 探查结果

{exploration_result}

## 已安装的依赖

{installed_packages}

## 用户命令

{raw_input}

## 项目信息

- 项目目录: {project_dir}
- 输出目录: {output_dir}
- 探测到的文件路径: {detected_file_paths}

## 输出格式

请以 JSON 格式回复：

```json
{{
    "user_intent": "用户意图描述（中文）",
    "script": "完整的 Python 分析脚本",
    "expected_outputs": ["预期生成的输出文件"],
    "estimated_runtime": 预估运行时间（秒）
}}
```

## 脚本要求

1. 所有输出文件必须保存到 {output_dir}
2. 使用 print() 输出执行进度
3. 包含适当的错误处理
4. 如果有图表，保存为 PDF 或 PNG
5. 结果文件命名要有意义
6. 在脚本开头添加必要的 import 语句

## 注意事项

1. 使用探测到的真实文件路径
2. 如果需要 R 代码，使用 subprocess 调用 Rscript
3. 添加中文注释说明关键步骤
"""


# ==========================================
# ✨ 工具函数
# ==========================================

def scan_project_files(project_dir: str, max_depth: int = 4) -> List[str]:
    """
    扫描项目目录中的所有文件

    Args:
        project_dir: 项目目录路径
        max_depth: 最大扫描深度

    Returns:
        文件路径列表
    """
    files = []

    if not os.path.exists(project_dir):
        log.warning(f"[V4] 项目目录不存在: {project_dir}")
        return files

    for root, dirs, filenames in os.walk(project_dir):
        # 计算当前深度
        depth = root.replace(project_dir, '').count(os.sep)
        if depth > max_depth:
            continue

        for filename in filenames:
            # 跳过隐藏文件和临时文件
            if filename.startswith('.') or filename.endswith('.tmp'):
                continue

            file_path = os.path.join(root, filename)
            # 返回相对于项目目录的路径
            rel_path = os.path.relpath(file_path, project_dir)
            files.append(rel_path)

    log.info(f"[V4] 扫描到 {len(files)} 个文件")
    return files


def extract_generated_files(output_dir: str) -> List[Dict[str, Any]]:
    """
    提取输出目录中生成的文件

    Args:
        output_dir: 输出目录路径

    Returns:
        文件信息列表
    """
    files = []

    if not os.path.exists(output_dir):
        return files

    for root, dirs, filenames in os.walk(output_dir):
        for filename in filenames:
            # 跳过临时文件和脚本文件
            if filename.startswith('.') or filename in ['latest_script.py', 'latest_script.R', 'temp_script.R']:
                continue

            file_path = os.path.join(root, filename)
            file_size = os.path.getsize(file_path)

            files.append({
                "path": file_path,
                "name": filename,
                "size": file_size,
                "extension": os.path.splitext(filename)[1].lower()
            })

    # 按文件大小排序
    files.sort(key=lambda x: x["size"], reverse=True)

    return files[:50]  # 最多返回 50 个文件


def extract_error_message(output: str) -> str:
    """
    从执行输出中提取错误信息

    Args:
        output: 执行输出

    Returns:
        提取的错误信息
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

    return output[:500] if output else "未知错误"


# ==========================================
# ✨ 探查代码生成器
# ==========================================

class ExplorationCodeGenerator:
    """探查代码生成器 - 使用 LLM 生成探查脚本"""

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    async def generate(
        self,
        raw_input: str,
        project_dir: str,
        output_dir: str,
        available_files: List[str]
    ) -> GeneratedScript:
        """
        生成探查脚本

        Args:
            raw_input: 用户原始输入
            project_dir: 项目目录
            output_dir: 输出目录
            available_files: 可用文件列表

        Returns:
            GeneratedScript 对象
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        log.info(f"[V4] 开始生成探查脚本，输入长度: {len(raw_input)}")

        # 构建可用文件列表字符串
        files_str = "\n".join([f"  - {f}" for f in available_files[:100]])

        # 构建 System Prompt
        system_prompt = EXPLORATION_GENERATOR_SYSTEM_PROMPT.format(
            project_dir=project_dir,
            output_dir=output_dir,
            available_files=files_str if files_str else "  (无文件)"
        )

        try:
            # 创建 LLM 客户端
            actual_api_key = self.api_key if (self.api_key and self.api_key.strip() != "") else "ollama-local"
            llm = ChatOpenAI(
                api_key=actual_api_key,
                base_url=self.base_url,
                model=self.model_name,
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

            log.info(f"[V4] LLM 响应长度: {len(llm_response)}")

            # 解析 JSON 响应
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(llm_response)

            script_code = data.get("exploration_script", "")
            user_intent = data.get("inferred_intent", "探查文件结构")
            suggested_packages = data.get("suggested_packages", [])

            log.info(f"[V4] 探查脚本生成完成，长度: {len(script_code)}")

            return GeneratedScript(
                code=script_code,
                user_intent=user_intent,
                detected_paths=data.get("detected_file_patterns", []),
                path_mappings={},
                includes_r_code=False
            )

        except Exception as e:
            log.error(f"[V4] 探查脚本生成失败: {e}")
            # 返回默认探查脚本
            return GeneratedScript(
                code=self._get_default_exploration_script(project_dir, output_dir),
                user_intent="探查项目文件",
                detected_paths=[],
                path_mappings={},
                includes_r_code=False
            )

    def _get_default_exploration_script(self, project_dir: str, output_dir: str) -> str:
        """获取默认探查脚本"""
        return f'''
import os
import pandas as pd

project_dir = "{project_dir}"
print(f"扫描项目目录: {{project_dir}}")

# 列出所有文件
for root, dirs, files in os.walk(project_dir):
    for f in files:
        if not f.startswith('.'):
            print(f"  - {{os.path.join(root, f)}}")

# 尝试预览 csv/tsv 文件
raw_data_dir = os.path.join(project_dir, "raw_data")
if os.path.exists(raw_data_dir):
    for f in os.listdir(raw_data_dir):
        if f.endswith('.csv') or f.endswith('.tsv'):
            file_path = os.path.join(raw_data_dir, f)
            try:
                df = pd.read_csv(file_path, nrows=5)
                print(f"\\n文件: {{f}}")
                print(f"列名: {{list(df.columns)}}")
                print(f"维度: {{df.shape}}")
            except Exception as e:
                print(f"无法读取 {{f}}: {{e}}")
'''


# ==========================================
# ✨ 依赖解析器
# ==========================================

class DependencyResolver:
    """依赖解析器 - 解析需要的包"""

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    async def resolve(
        self,
        raw_input: str,
        exploration_result: ExplorationResult
    ) -> List[Dict[str, str]]:
        """
        解析依赖

        Args:
            raw_input: 用户原始输入
            exploration_result: 探查结果

        Returns:
            需要安装的包列表
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        log.info(f"[V4] 开始解析依赖")

        # 构建探查结果摘要
        exploration_summary = {
            "inferred_intent": exploration_result.inferred_intent,
            "suggested_packages": exploration_result.suggested_packages,
            "detected_files": [
                {"path": f.path, "type": f.file_type}
                for f in exploration_result.detected_files
            ]
        }

        system_prompt = DEPENDENCY_RESOLVER_SYSTEM_PROMPT.format(
            exploration_result=json.dumps(exploration_summary, ensure_ascii=False, indent=2),
            raw_input=raw_input
        )

        try:
            actual_api_key = self.api_key if (self.api_key and self.api_key.strip() != "") else "ollama-local"
            llm = ChatOpenAI(
                api_key=actual_api_key,
                base_url=self.base_url,
                model=self.model_name,
                temperature=0.1,
                max_retries=2
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="请解析依赖并返回 JSON 格式结果")
            ]

            response = await llm.ainvoke(messages)
            llm_response = response.content

            # 解析 JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(llm_response)

            required_packages = data.get("required_packages", [])

            # 过滤掉已预装的包
            packages_to_install = []
            for pkg in required_packages:
                name = pkg.get("name", "")
                if name and name.lower() not in PREINSTALLED_PACKAGES:
                    packages_to_install.append(pkg)

            log.info(f"[V4] 需要安装的包: {[p['name'] for p in packages_to_install]}")

            return packages_to_install

        except Exception as e:
            log.error(f"[V4] 依赖解析失败: {e}")
            # 使用探查结果中的建议包
            return [
                {"name": pkg, "version": "", "reason": "从探查结果推断", "conda_channel": "conda-forge"}
                for pkg in exploration_result.suggested_packages
                if pkg.lower() not in PREINSTALLED_PACKAGES
            ]


# ==========================================
# ✨ 分析脚本生成器
# ==========================================

class AnalysisScriptGenerator:
    """分析脚本生成器 - 基于探查结果生成最终脚本"""

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    async def generate(
        self,
        raw_input: str,
        exploration_result: ExplorationResult,
        installed_packages: List[PackageInstallResult],
        context: SuperExecutorV4Context
    ) -> GeneratedScript:
        """
        生成分析脚本

        Args:
            raw_input: 用户原始输入
            exploration_result: 探查结果
            installed_packages: 已安装的包
            context: 执行上下文

        Returns:
            GeneratedScript 对象
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        log.info(f"[V4] 开始生成分析脚本")

        # 构建探查结果摘要
        exploration_summary = {
            "inferred_intent": exploration_result.inferred_intent,
            "detected_files": [
                {"path": f.path, "type": f.file_type, "columns": f.columns[:10] if f.columns else []}
                for f in exploration_result.detected_files
            ],
            "exploration_output": exploration_result.exploration_output[:2000] if exploration_result.exploration_output else ""
        }

        # 构建已安装包列表
        installed_pkg_names = [p.package_name for p in installed_packages if p.status == "installed"]

        system_prompt = ANALYSIS_SCRIPT_GENERATOR_PROMPT.format(
            exploration_result=json.dumps(exploration_summary, ensure_ascii=False, indent=2),
            installed_packages=json.dumps(installed_pkg_names, ensure_ascii=False),
            raw_input=raw_input,
            project_dir=context.project_dir,
            output_dir=context.output_dir,
            detected_file_paths=[f.path for f in exploration_result.detected_files]
        )

        try:
            actual_api_key = self.api_key if (self.api_key and self.api_key.strip() != "") else "ollama-local"
            llm = ChatOpenAI(
                api_key=actual_api_key,
                base_url=self.base_url,
                model=self.model_name,
                temperature=0.1,
                max_retries=2
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=raw_input)
            ]

            response = await llm.ainvoke(messages)
            llm_response = response.content

            # 解析 JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(llm_response)

            script_code = data.get("script", "")
            user_intent = data.get("user_intent", exploration_result.inferred_intent)

            log.info(f"[V4] 分析脚本生成完成，长度: {len(script_code)}")

            return GeneratedScript(
                code=script_code,
                user_intent=user_intent,
                detected_paths=[f.path for f in exploration_result.detected_files],
                path_mappings={},
                includes_r_code="Rscript" in script_code or "r_code =" in script_code
            )

        except Exception as e:
            log.error(f"[V4] 分析脚本生成失败: {e}")
            raise


# ==========================================
# ✨ Conda 安装服务 - 改造为用户级安装
# ==========================================

class CondaInstallerService:
    """Conda 包安装服务 - 用户级环境安装（Conda 只读后的适配）

    设计原则：
    1. 系统级 Conda 目录只读，不可写入
    2. 优先使用 pip --target 安装到用户目录（快速、轻量）
    3. 必要时使用用户级 Conda 环境安装（需要特定版本/渠道时）
    """

    CONDA_CONTAINER_PATH = "/opt/conda"
    USER_PACKAGES_CONTAINER_PATH = "/app/user_packages"

    async def install_packages(
        self,
        packages: List[Dict[str, str]],
        user_id: int,
        output_dir: str,
    ) -> DependencyInstallResult:
        """
        在用户级环境中安装包

        Args:
            packages: 包列表 [{"name": "scanpy", "version": "1.9.0", "conda_channel": "bioconda"}]
            user_id: 用户 ID
            output_dir: 输出目录

        Returns:
            DependencyInstallResult
        """
        log.info(f"[V4] 开始安装包: {[p['name'] for p in packages]}")

        start_time = time.time()

        # ✨ 分类：预装包、pip 包、conda 包
        preinstalled, pip_packages, conda_packages = self._classify_packages(packages)

        log.info(f"[V4] 分类结果: 预装={len(preinstalled)}, pip={len(pip_packages)}, conda={len(conda_packages)}")

        installed = []

        # 1. 预装包直接标记
        for pkg_name in preinstalled:
            installed.append(PackageInstallResult(
                package_name=pkg_name,
                version="preinstalled",
                status="skipped",
                install_time=0.0,
            ))

        # 2. 使用 pip 安装（优先）
        if pip_packages:
            pip_result = await self._install_via_pip(pip_packages, user_id, output_dir)
            installed.extend(pip_result)

        # 3. 使用用户级 Conda 安装（必要时）
        if conda_packages:
            conda_result = await self._install_via_conda(conda_packages, user_id, output_dir)
            installed.extend(conda_result)

        total_time = time.time() - start_time

        log.info(f"[V4] 包安装完成，耗时: {total_time:.2f}s")

        return DependencyInstallResult(
            packages_to_install=[p["name"] for p in packages],
            installed_packages=installed,
            skipped_packages=list(preinstalled),
            failed_packages=[p.package_name for p in installed if p.status == "failed"],
            total_install_time=total_time,
            success=all(p.status != "failed" for p in installed),
            error_message=None,
        )

    def _classify_packages(self, packages: List[Dict]) -> tuple:
        """分类包：预装包、pip 包、conda 包"""
        preinstalled = set()
        pip_packages = []
        conda_packages = []

        for pkg in packages:
            name = pkg.get("name", "").lower()
            if not name:
                continue

            # 检查是否预装
            if name in PREINSTALLED_PACKAGES:
                preinstalled.add(name)
                continue

            # 检查是否需要 conda（bioconda 专用包）
            conda_channel = pkg.get("conda_channel", "")
            if conda_channel in ["bioconda", "conda-forge"] and name in BIOCONDA_PACKAGES:
                conda_packages.append(pkg)
            else:
                # 默认使用 pip
                pip_packages.append(pkg)

        return preinstalled, pip_packages, conda_packages

    async def _install_via_pip(
        self,
        packages: List[Dict],
        user_id: int,
        output_dir: str
    ) -> List[PackageInstallResult]:
        """使用 pip --target 安装到用户目录"""
        install_script = self._build_pip_install_script(packages, user_id)

        output, exit_code, billing_info = run_container(
            image='autonome-tool-env',
            command=install_script,
            language="python",
            environment={"TASK_OUT_DIR": output_dir},
            timeout=INSTALL_TIMEOUT,
            user_id=user_id,
            enable_network=True,  # 启用网络以下载包
            cli_mode=False,
        )

        return self._parse_pip_output(output, packages)

    async def _install_via_conda(
        self,
        packages: List[Dict],
        user_id: int,
        output_dir: str
    ) -> List[PackageInstallResult]:
        """使用用户级 Conda 环境安装"""
        install_script = self._build_conda_install_script(packages, user_id)

        output, exit_code, billing_info = run_container(
            image='autonome-tool-env',
            command=install_script,
            language="python",
            environment={"TASK_OUT_DIR": output_dir},
            timeout=INSTALL_TIMEOUT,
            user_id=user_id,
            enable_network=True,  # 启用网络以下载包
            cli_mode=False,
        )

        return self._parse_conda_output(output, packages)

    def _build_pip_install_script(self, packages: List[Dict], user_id: int) -> str:
        """构建 pip 用户级安装脚本"""
        user_pkg_dir = f"{self.USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"
        target_dir = f"{user_pkg_dir}/python"

        pkg_specs = []
        for pkg in packages:
            name = pkg.get("name", "")
            version = pkg.get("version")
            if version:
                pkg_specs.append(f"{name}=={version}")
            else:
                pkg_specs.append(name)

        return f'''
import subprocess
import sys
import os

# ✨ 用户级包安装路径
target_dir = "{target_dir}"
os.makedirs(target_dir, exist_ok=True)

packages = {pkg_specs}
print(f"📦 使用 pip 安装到用户目录: {{target_dir}}")
print(f"📥 将安装: {{packages}}")

for pkg in packages:
    cmd = ["pip", "install", "--target", target_dir, pkg]
    print(f"执行: {{' '.join(cmd)}}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)

    if result.returncode != 0:
        print(f"❌ 安装 {{pkg}} 失败: {{result.stderr}}")
        sys.exit(1)
    print(f"✅ 已安装: {{pkg}}")

print("✅ 所有包安装完成!")
'''

    def _build_conda_install_script(self, packages: List[Dict], user_id: int) -> str:
        """构建用户级 Conda 安装脚本"""
        user_pkg_dir = f"{self.USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"
        user_envs_dir = f"{user_pkg_dir}/conda_envs"
        user_pkgs_dir = f"{user_pkg_dir}/conda_pkgs"

        pkg_names = [pkg.get("name", "") for pkg in packages]
        channels = set()
        for pkg in packages:
            ch = pkg.get("conda_channel", "conda-forge")
            channels.add(ch)

        channel_args = []
        for ch in ["conda-forge", "bioconda"]:
            if ch in channels:
                channel_args.extend(["-c", ch])

        return f'''
import subprocess
import sys
import os

# ✨ 设置用户级 Conda 环境变量
os.environ["CONDA_ENVS_PATH"] = "{user_envs_dir}"
os.environ["CONDA_PKGS_DIRS"] = "{user_pkgs_dir}"

conda_path = "{self.CONDA_CONTAINER_PATH}/bin/conda"
env_name = "user_env"

# 检查用户环境是否存在
result = subprocess.run([conda_path, "env", "list"], capture_output=True, text=True)
if env_name not in result.stdout:
    print(f"🔧 创建用户 Conda 环境: {{env_name}}")
    create_cmd = [conda_path, "create", "-y", "-n", env_name, "python=3.10"]
    result = subprocess.run(create_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ 创建环境失败: {{result.stderr}}")
        sys.exit(1)

# 安装包到用户环境
packages = {pkg_names}
channels = {channel_args}

print(f"📦 使用 Conda 安装到用户环境: {{env_name}}")
print(f"📥 将安装: {{packages}}")

install_cmd = [conda_path, "install", "-y", "-n", env_name] + channels + packages
print(f"执行: {{' '.join(install_cmd)}}")

result = subprocess.run(install_cmd, capture_output=True, text=True)
print(result.stdout)

if result.returncode != 0:
    print(f"❌ 安装失败: {{result.stderr}}")
    sys.exit(1)

print("✅ 所有 Conda 包安装完成!")
'''

    def _parse_pip_output(self, output: str, packages: List[Dict]) -> List[PackageInstallResult]:
        """解析 pip 安装输出"""
        results = []
        for pkg in packages:
            name = pkg.get("name", "")
            if f"Successfully installed {name}" in output or f"已安装: {name}" in output:
                results.append(PackageInstallResult(
                    package_name=name,
                    version=pkg.get("version", "latest"),
                    status="installed",
                    install_time=0.0,
                ))
            else:
                results.append(PackageInstallResult(
                    package_name=name,
                    version="",
                    status="failed",
                    install_time=0.0,
                    error_message=output[:200],
                ))
        return results

    def _parse_conda_output(self, output: str, packages: List[Dict]) -> List[PackageInstallResult]:
        """解析 Conda 安装输出"""
        results = []
        for pkg in packages:
            name = pkg.get("name", "")
            if name in output.lower() and "error" not in output.lower():
                results.append(PackageInstallResult(
                    package_name=name,
                    version=pkg.get("version", "latest"),
                    status="installed",
                    install_time=0.0,
                ))
            else:
                results.append(PackageInstallResult(
                    package_name=name,
                    version="",
                    status="failed",
                    install_time=0.0,
                    error_message=output[:200],
                ))
        return results


# ✨ Bioconda 专用包列表（需要用 Conda 安装而非 pip）
BIOCONDA_PACKAGES = {
    "samtools", "bwa", "bowtie2", "hisat2", "star", "salmon", "kallisto",
    "fastqc", "multiqc", "trimmomatic", "cutadapt", "macs2", "deeptools",
    "nextflow", "snakemake", "cellranger", "seurat", "monocle3"
}


# ==========================================
# ✨ 脚本执行器
# ==========================================

class ScriptExecutor:
    """沙箱脚本执行器"""

    async def execute(
        self,
        script: str,
        context: SuperExecutorV4Context,
        enable_network: bool = False,
    ) -> ExecutionResult:
        """
        在沙箱中执行脚本

        Args:
            script: Python 脚本代码
            context: 执行上下文
            enable_network: 是否启用网络

        Returns:
            ExecutionResult 对象
        """
        log.info(f"[V4] 开始执行脚本，长度: {len(script)}")

        start_time = time.time()

        # 确保输出目录存在
        os.makedirs(context.output_dir, exist_ok=True)

        # 构建环境变量
        environment = {
            "TASK_OUT_DIR": context.output_dir,
            "PROJECT_ID": context.project_id,
            "PROJECT_DIR": context.project_dir,
            "SUPER_EXECUTOR_MODE": "v4"
        }

        # 调用沙箱执行
        output, exit_code, billing_info = run_container(
            image='autonome-tool-env',
            command=script,
            language="python",
            environment=environment,
            timeout=EXECUTION_TIMEOUT,
            user_id=context.user_id,
            enable_network=enable_network,
        )

        execution_time = time.time() - start_time

        # 提取生成的文件
        generated_files = extract_generated_files(context.output_dir)

        log.info(f"[V4] 脚本执行完成，退出码: {exit_code}, 耗时: {execution_time:.2f}s")

        return ExecutionResult(
            script=script,
            stdout=output,
            stderr="",
            exit_code=exit_code,
            execution_time=execution_time,
            generated_files=generated_files,
            retry_count=0,
            success=(exit_code == 0),
        )


# ==========================================
# ✨ 主执行器类
# ==========================================

class SuperExecutorV4:
    """超级执行者 V4 - 三步执行流程"""

    def __init__(
        self,
        raw_input: str,
        project_id: str,
        user_id: int,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None
    ):
        self.context = SuperExecutorV4Context(
            task_id=str(uuid.uuid4()),
            project_id=project_id,
            project_dir=f"/workspace/project_{project_id}",
            output_dir=f"/workspace/project_{project_id}/results/v4_{int(time.time())}",
            user_id=user_id,
            raw_input=raw_input,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
        )

        # 组件（延迟初始化）
        self._exploration_generator = None
        self._dependency_resolver = None
        self._conda_installer = None
        self._script_generator = None
        self._script_executor = None

    def _get_exploration_generator(self):
        """延迟初始化探查代码生成器"""
        if not self._exploration_generator and self.context.api_key and self.context.base_url and self.context.model_name:
            self._exploration_generator = ExplorationCodeGenerator(
                self.context.api_key, self.context.base_url, self.context.model_name
            )
        return self._exploration_generator

    def _get_dependency_resolver(self):
        """延迟初始化依赖解析器"""
        if not self._dependency_resolver and self.context.api_key and self.context.base_url and self.context.model_name:
            self._dependency_resolver = DependencyResolver(
                self.context.api_key, self.context.base_url, self.context.model_name
            )
        return self._dependency_resolver

    def _get_script_generator(self):
        """延迟初始化脚本生成器"""
        if not self._script_generator and self.context.api_key and self.context.base_url and self.context.model_name:
            self._script_generator = AnalysisScriptGenerator(
                self.context.api_key, self.context.base_url, self.context.model_name
            )
        return self._script_generator

    def _get_conda_installer(self):
        """延迟初始化 Conda 安装器"""
        if not self._conda_installer:
            self._conda_installer = CondaInstallerService()
        return self._conda_installer

    def _get_script_executor(self):
        """延迟初始化脚本执行器"""
        if not self._script_executor:
            self._script_executor = ScriptExecutor()
        return self._script_executor

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行三步执行流程

        Yields:
            SSE 事件字典
        """
        log.info(f"🚀 [SuperExecutorV4] 开始执行 - project_id={self.context.project_id}")

        try:
            # 启动事件
            yield self._create_event(SSEEventType.STATUS_UPDATE, {
                "status": "initializing",
                "phase": "idle",
                "message": "正在初始化执行环境..."
            })

            # ==========================================
            # Phase 1: 探查阶段
            # ==========================================
            async for event in self._run_phase_1():
                yield event

            if self.context.current_phase == ExecutionPhase.ERROR:
                return

            # ==========================================
            # Phase 2: 安装依赖阶段
            # ==========================================
            if self._needs_dependency_install():
                async for event in self._run_phase_2():
                    yield event

                if self.context.current_phase == ExecutionPhase.ERROR:
                    return
            else:
                yield self._create_event(SSEEventType.STATUS_UPDATE, {
                    "status": "skipping_install",
                    "message": "无需安装额外依赖，跳过依赖安装阶段"
                })
                self.context.current_phase = ExecutionPhase.PHASE_2_COMPLETE

            # ==========================================
            # Phase 3: 执行分析阶段
            # ==========================================
            async for event in self._run_phase_3():
                yield event

            # 完成
            yield self._create_event(SSEEventType.DONE, {"message": "[DONE]"})

        except Exception as e:
            log.error(f"[V4] 执行异常: {e}")
            yield self._create_event(SSEEventType.ERROR, {"error": str(e)})

    async def _run_phase_1(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Phase 1: 探查阶段"""
        self.context.current_phase = ExecutionPhase.PHASE_1_EXPLORING

        yield self._create_event(SSEEventType.PHASE_CHANGE, {
            "phase": "exploration",
            "message": "进入探查阶段"
        })

        # 1. 扫描项目文件
        available_files = scan_project_files(self.context.project_dir)

        yield self._create_event(SSEEventType.FILES_DETECTED, {
            "file_count": len(available_files),
            "files": available_files[:20]
        })

        # 2. 检查 LLM 配置
        exploration_generator = self._get_exploration_generator()
        if not exploration_generator:
            yield self._create_event(SSEEventType.ERROR, {
                "error": "未配置 LLM，无法生成探查脚本"
            })
            self.context.current_phase = ExecutionPhase.ERROR
            return

        # 3. 生成探查代码
        yield self._create_event(SSEEventType.EXPLORATION_START, {
            "message": "正在生成探查代码..."
        })

        try:
            exploration_script = await exploration_generator.generate(
                raw_input=self.context.raw_input,
                project_dir=self.context.project_dir,
                output_dir=self.context.output_dir,
                available_files=available_files,
            )
        except Exception as e:
            log.error(f"[V4] 探查脚本生成失败: {e}")
            yield self._create_event(SSEEventType.ERROR, {
                "error": f"探查脚本生成失败: {str(e)}"
            })
            self.context.current_phase = ExecutionPhase.ERROR
            return

        # 4. 执行探查代码
        yield self._create_event(SSEEventType.EXPLORATION_PROGRESS, {
            "message": "正在执行探查代码..."
        })

        script_executor = self._get_script_executor()
        result = await script_executor.execute(
            script=exploration_script.code,
            context=self.context,
            enable_network=False,
        )

        # 5. 解析探查结果
        exploration_result = ExplorationResult(
            detected_files=self._parse_detected_files(result.stdout, self.context.project_dir),
            inferred_intent=exploration_script.user_intent,
            suggested_packages=exploration_script.detected_paths if isinstance(exploration_script.detected_paths, list) and all(isinstance(p, str) for p in exploration_script.detected_paths) else [],
            environment_context={"project_dir": self.context.project_dir},
            exploration_script=exploration_script.code,
            exploration_output=result.stdout,
            success=result.success,
        )

        # 从探查脚本中提取建议的包
        if hasattr(exploration_script, 'user_intent'):
            # 如果 LLM 返回了 suggested_packages，需要从原始响应中提取
            pass

        self.context.phase_1_result = exploration_result
        self.context.current_phase = ExecutionPhase.PHASE_1_COMPLETE

        yield self._create_event(SSEEventType.EXPLORATION_COMPLETE, {
            "success": exploration_result.success,
            "detected_files": [f.__dict__ for f in exploration_result.detected_files],
            "inferred_intent": exploration_result.inferred_intent,
            "suggested_packages": exploration_result.suggested_packages,
            "exploration_output": result.stdout[:2000] if result.stdout else "",
        })

    async def _run_phase_2(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Phase 2: 安装依赖阶段"""
        self.context.current_phase = ExecutionPhase.PHASE_2_INSTALLING

        yield self._create_event(SSEEventType.PHASE_CHANGE, {
            "phase": "installing",
            "message": "进入依赖安装阶段"
        })

        # 1. 解析依赖
        yield self._create_event(SSEEventType.DEPENDENCY_RESOLVE_START, {
            "message": "正在解析依赖..."
        })

        dependency_resolver = self._get_dependency_resolver()
        if not dependency_resolver:
            # 跳过安装
            self.context.current_phase = ExecutionPhase.PHASE_2_COMPLETE
            yield self._create_event(SSEEventType.INSTALL_COMPLETE, {
                "message": "未配置 LLM，跳过依赖解析",
                "installed": [],
                "skipped": [],
                "failed": [],
            })
            return

        packages = await dependency_resolver.resolve(
            raw_input=self.context.raw_input,
            exploration_result=self.context.phase_1_result,
        )

        yield self._create_event(SSEEventType.DEPENDENCY_RESOLVE_COMPLETE, {
            "packages": packages,
            "count": len(packages),
        })

        if not packages:
            self.context.current_phase = ExecutionPhase.PHASE_2_COMPLETE
            yield self._create_event(SSEEventType.INSTALL_COMPLETE, {
                "message": "无需安装额外依赖",
                "installed": [],
                "skipped": [],
                "failed": [],
            })
            return

        # 2. 安装依赖
        yield self._create_event(SSEEventType.INSTALL_START, {
            "message": f"开始安装 {len(packages)} 个依赖包...",
            "packages": [p["name"] for p in packages],
        })

        conda_installer = self._get_conda_installer()
        install_result = await conda_installer.install_packages(
            packages=packages,
            user_id=self.context.user_id,
            output_dir=self.context.output_dir,
        )

        self.context.phase_2_result = install_result
        self.context.current_phase = ExecutionPhase.PHASE_2_COMPLETE

        yield self._create_event(SSEEventType.INSTALL_COMPLETE, {
            "success": install_result.success,
            "installed": [p.__dict__ for p in install_result.installed_packages],
            "skipped": install_result.skipped_packages,
            "failed": install_result.failed_packages,
            "total_time": install_result.total_install_time,
        })

    async def _run_phase_3(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Phase 3: 执行分析阶段"""
        self.context.current_phase = ExecutionPhase.PHASE_3_EXECUTING

        yield self._create_event(SSEEventType.PHASE_CHANGE, {
            "phase": "executing",
            "message": "进入分析执行阶段"
        })

        # 1. 生成分析脚本
        yield self._create_event(SSEEventType.STATUS_UPDATE, {
            "message": "正在生成分析脚本..."
        })

        script_generator = self._get_script_generator()
        if not script_generator:
            yield self._create_event(SSEEventType.ERROR, {
                "error": "未配置 LLM，无法生成分析脚本"
            })
            self.context.current_phase = ExecutionPhase.ERROR
            return

        installed_packages = []
        if self.context.phase_2_result:
            installed_packages = self.context.phase_2_result.installed_packages

        try:
            script = await script_generator.generate(
                raw_input=self.context.raw_input,
                exploration_result=self.context.phase_1_result,
                installed_packages=installed_packages,
                context=self.context,
            )
        except Exception as e:
            log.error(f"[V4] 分析脚本生成失败: {e}")
            yield self._create_event(SSEEventType.ERROR, {
                "error": f"分析脚本生成失败: {str(e)}"
            })
            self.context.current_phase = ExecutionPhase.ERROR
            return

        yield self._create_event(SSEEventType.SCRIPT_GENERATED, {
            "user_intent": script.user_intent,
            "code_preview": script.code[:500] + "..." if len(script.code) > 500 else script.code,
        })

        # 2. 执行脚本（带重试）
        retry_count = 0
        current_script = script.code
        last_result = None
        script_executor = self._get_script_executor()

        while retry_count <= MAX_DEBUG_RETRIES:
            yield self._create_event(SSEEventType.EXECUTION_START, {
                "message": f"正在执行分析脚本..." + (f" (重试 {retry_count}/{MAX_DEBUG_RETRIES})" if retry_count > 0 else ""),
                "retry_count": retry_count,
            })

            result = await script_executor.execute(
                script=current_script,
                context=self.context,
                enable_network=False,
            )

            last_result = result
            result.retry_count = retry_count

            if result.success:
                break

            # 执行失败，尝试修复
            if retry_count < MAX_DEBUG_RETRIES:
                retry_count += 1

                yield self._create_event(SSEEventType.DEBUG_RETRY, {
                    "attempt": retry_count,
                    "max_retries": MAX_DEBUG_RETRIES,
                    "error": extract_error_message(result.stdout)[:500],
                })

                # LLM 修复
                try:
                    fixed_script = await self._fix_script_with_llm(
                        script=current_script,
                        error_msg=extract_error_message(result.stdout),
                    )
                    if fixed_script:
                        current_script = fixed_script
                        log.info(f"[V4] 脚本已通过 LLM 修复")
                except Exception as e:
                    log.error(f"[V4] LLM 修复失败: {e}")
            else:
                break

        # 3. 生成战报
        if last_result:
            self.context.phase_3_result = last_result
            self.context.current_phase = ExecutionPhase.PHASE_3_COMPLETE

            battle_report = self._generate_battle_report(last_result, retry_count)

            yield self._create_event(SSEEventType.BATTLE_REPORT, battle_report)

            yield self._create_event(SSEEventType.MESSAGE, {
                "type": "text",
                "content": self._format_report_as_markdown(battle_report),
            })

    async def _fix_script_with_llm(
        self,
        script: str,
        error_msg: str,
    ) -> Optional[str]:
        """
        调用 LLM 修复脚本

        Args:
            script: 原始脚本
            error_msg: 错误信息

        Returns:
            修复后的脚本，失败返回 None
        """
        from app.services.celery_app import fix_code_with_llm

        try:
            fixed_script = fix_code_with_llm(
                code=script,
                error_msg=error_msg,
                api_key=self.context.api_key,
                base_url=self.context.base_url,
                model_name=self.context.model_name,
                language="python",
                timeout=90
            )
            return fixed_script
        except Exception as e:
            log.error(f"[V4] LLM 修复失败: {e}")
            return None

    def _parse_detected_files(self, output: str, project_dir: str) -> List[FileInfo]:
        """从探查输出中解析检测到的文件"""
        files = []

        # 简单解析：查找文件路径
        lines = output.split("\n")
        for line in lines:
            # 查找包含文件路径的行
            if project_dir in line or ".csv" in line or ".tsv" in line or ".h5ad" in line:
                # 尝试提取路径
                import re
                matches = re.findall(r'[\w/\-\.]+\.(csv|tsv|h5ad|fastq|bam|txt)', line)
                for match in matches:
                    path = match
                    files.append(FileInfo(
                        path=path,
                        file_type=match.split('.')[-1],
                        size_bytes=0,
                        columns=[],
                    ))

        return files[:10]  # 最多返回 10 个文件

    def _needs_dependency_install(self) -> bool:
        """检查是否需要安装依赖"""
        if not self.context.phase_1_result:
            return False
        return len(self.context.phase_1_result.suggested_packages) > 0

    def _create_event(self, event_type: SSEEventType, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建 SSE 事件"""
        return {
            "event": event_type.value,
            "data": json.dumps(data, ensure_ascii=False),
        }

    def _generate_battle_report(self, result: ExecutionResult, retry_count: int) -> Dict[str, Any]:
        """生成战报字典"""
        return {
            "task_out_dir": self.context.output_dir,
            "success": result.success,
            "execution_time": round(result.execution_time, 2),
            "exit_code": result.exit_code,
            "user_intent": self.context.phase_1_result.inferred_intent if self.context.phase_1_result else "执行用户指令",
            "generated_files": result.generated_files,
            "retry_count": retry_count,
            "stdout_preview": result.stdout[:1000] if result.stdout else "",
            "error_message": extract_error_message(result.stdout) if not result.success else "",
            "phase_1_result": {
                "inferred_intent": self.context.phase_1_result.inferred_intent,
                "detected_files_count": len(self.context.phase_1_result.detected_files),
            } if self.context.phase_1_result else None,
            "phase_2_result": {
                "installed": [p.package_name for p in self.context.phase_2_result.installed_packages if p.status == "installed"],
                "skipped": self.context.phase_2_result.skipped_packages,
                "failed": self.context.phase_2_result.failed_packages,
            } if self.context.phase_2_result else None,
        }

    def _format_report_as_markdown(self, report: Dict[str, Any]) -> str:
        """将战报格式化为 Markdown"""
        status_emoji = "✅" if report.get("success") else "❌"

        md = f"""

> ⚡ **超级执行者 V4 执行完成**

{status_emoji} **{report.get('user_intent', '执行用户指令')}**

- 执行时间: {report.get('execution_time', 0):.2f} 秒
- 重试次数: {report.get('retry_count', 0)}
- 输出目录: `{report.get('task_out_dir', '')}`

```json_battle_report
{json.dumps(report, ensure_ascii=False, indent=2)}
```
"""
        return md


log.info("🦾 超级执行者 V4 模块已加载")