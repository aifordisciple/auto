"""
SKILL Tester - 沙箱自动化测试引擎 (增强版)

功能：
1. AI 自动构造测试数据
2. 使用不同参数进行多轮测试
3. 测试失败时自动反馈并修复代码
4. 支持参数 Schema 解析，智能生成测试用例
"""

import re
import json
import os
import tempfile
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass, asdict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from app.core.logger import log
from app.core.content_filter import preprocess_llm_response

# 尝试导入沙箱执行工具
try:
    from app.tools.bio_tools import run_container
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    log.warning("[Skill Tester] bio_tools 未找到，沙箱测试功能将受限")


def _run_sandbox_code(code: str, language: str = "python", timeout: int = 120) -> str:
    """
    执行沙箱代码的封装函数（同步版本）

    Args:
        code: 要执行的代码
        language: 语言类型 "python" 或 "r"
        timeout: 执行超时时间（秒）

    Returns:
        执行输出
    """
    try:
        result_output, exit_code = run_container(
            image='autonome-tool-env',
            command=code,
            language=language,
            timeout=timeout
        )
        return result_output
    except Exception as e:
        log.error(f"[Sandbox] 执行失败: {e}")
        raise


async def _run_sandbox_code_async(code: str, language: str = "python", timeout: int = 120) -> str:
    """
    异步执行沙箱代码（使用 asyncio.to_thread 避免阻塞事件循环）

    Args:
        code: 要执行的代码
        language: 语言类型 "python" 或 "r"
        timeout: 执行超时时间（秒）

    Returns:
        执行输出
    """
    try:
        result = await asyncio.to_thread(
            _run_sandbox_code, code, language, timeout
        )
        return result
    except Exception as e:
        log.error(f"[Sandbox] 异步执行失败: {e}")
        raise


# ==========================================
# 测试数据生成器
# ==========================================

def generate_test_data_fast(
    parameters_schema: Dict[str, Any],
    executor_type: str
) -> Dict[str, Any]:
    """
    根据参数 Schema 快速生成测试数据（无需 LLM）

    根据参数类型自动推断并生成最小化测试数据
    """
    properties = parameters_schema.get("properties", {})
    test_files = {}
    test_params = {}
    test_scenarios = []

    for param_name, param_def in properties.items():
        param_type = param_def.get("type", "string")
        param_format = param_def.get("format", "")
        param_default = param_def.get("default")
        param_desc = param_def.get("description", "").lower()

        # 文件路径参数 - 生成测试文件
        if param_type == "string" and param_format == "filepath":
            # 根据参数名和描述推断文件类型和内容
            name_lower = param_name.lower()
            combined = f"{name_lower} {param_desc} {str(param_default).lower()}"

            # ===== 根据参数名/描述推断数据格式 =====

            # PCA/表达矩阵类数据（数值矩阵）
            if any(kw in combined for kw in ["pca", "matrix", "expression", "count", "tpm", "fpkm", "rpkm", "umi", "exp"]):
                # 生成数值表达矩阵：行=基因，列=样本
                test_files[param_name] = "\t".join(["gene", "sample1", "sample2", "sample3"]) + "\n"
                for i in range(1, 11):  # 10个基因，3个样本
                    test_files[param_name] += "\t".join([f"GENE{i}", str(10 + i), str(15 + i), str(20 + i)]) + "\n"

            # 分组文件
            elif any(kw in combined for kw in ["group", "sample", "meta", "phenotype"]):
                # 生成分组信息：样本名 + 分组
                test_files[param_name] = "sample\tgroup\nsample1\tcontrol\nsample2\tcontrol\nsample3\ttreat\n"

            # 颜色配置文件
            elif any(kw in combined for kw in ["color", "palette"]):
                # 生成颜色配置
                test_files[param_name] = "group\tcolor\ncontrol\t#3498db\ntreat\t#e74c3c\n"

            # CSV 格式
            elif "csv" in combined:
                test_files[param_name] = "id,value,name\n1,100,test1\n2,200,test2\n"

            # TSV 格式
            elif "tsv" in combined:
                test_files[param_name] = "id\tvalue\tname\n1\t100\ttest1\n2\t200\ttest2\n"

            # BAM 文件（无法创建，跳过）
            elif "bam" in name_lower:
                test_params[param_name] = f"__PLACEHOLDER__/{param_name}.bam"
                continue

            # FASTA 格式
            elif any(kw in combined for kw in ["fasta", "fa", "sequence"]):
                test_files[param_name] = ">seq1\nATCGATCG\n>seq2\nGCTAGCTA\n"

            # FASTQ 格式
            elif any(kw in combined for kw in ["fastq", "fq", "read"]):
                test_files[param_name] = "@read1\nATCGATCG\n+\nIIIIIIII\n@read2\nGCTAGCTA\n+\nIIIIIIII\n"

            # 默认：生成数值矩阵格式（更通用）
            else:
                # 生成一个小型数值矩阵作为默认
                test_files[param_name] = "\t".join(["id", "col1", "col2", "col3"]) + "\n"
                test_files[param_name] += "row1\t1.5\t2.3\t3.1\nrow2\t4.2\t5.1\t6.0\nrow3\t7.8\t8.5\t9.2\n"

            # 使用占位符标记
            test_params[param_name] = f"__PLACEHOLDER__/{param_name}"

        # 目录路径参数
        elif param_type == "string" and param_format == "directorypath":
            test_params[param_name] = "__PLACEHOLDER__/output"

        # 数值参数
        elif param_type == "integer":
            test_params[param_name] = param_default if param_default is not None else 4
        elif param_type == "number":
            test_params[param_name] = param_default if param_default is not None else 0.05

        # 布尔参数
        elif param_type == "boolean":
            test_params[param_name] = param_default if param_default is not None else True

        # 枚举参数
        elif param_type == "string" and "enum" in param_def:
            enum_values = param_def["enum"]
            test_params[param_name] = enum_values[0] if enum_values else "default"

        # 普通字符串参数
        elif param_type == "string":
            test_params[param_name] = param_default if param_default is not None else "test_value"

    # 生成默认测试场景
    if test_params:
        test_scenarios.append({
            "name": "默认参数测试",
            "params": test_params.copy(),
            "expected": "代码正常执行"
        })

    log.info(f"[TestDataGen] 快速生成测试数据: {len(test_files)} 个文件, {len(test_params)} 个参数")

    return {
        "test_files": test_files,
        "test_params": test_params,
        "test_scenarios": test_scenarios
    }


async def generate_test_data(
    parameters_schema: Dict[str, Any],
    executor_type: str,
    api_key: str,
    base_url: str,
    model_name: str,
    script_code: str = None
) -> Dict[str, Any]:
    """
    根据参数 Schema 和脚本代码智能生成测试数据

    使用 LLM 分析脚本的输入输出要求，生成合理的测试数据
    """
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.3,
        timeout=180  # 180秒超时，适应复杂脚本的测试数据生成
    )

    properties = parameters_schema.get("properties", {})

    # 构建提示词，包含脚本代码分析
    script_preview = script_code[:3000] if script_code else "未提供脚本代码"

    prompt = f"""你是一个专业的生信测试数据生成器。请分析以下脚本和参数定义，生成最小但有效的测试数据。

【执行器类型】
{executor_type}

【脚本代码预览】
```
{script_preview}
```

【参数定义】
{json.dumps(parameters_schema, indent=2, ensure_ascii=False)}

【关键要求】
1. **分析脚本的输入格式**：
   - 检查 read.table/read.csv/read.delim 等 R 函数的参数
   - 检查 pandas.read_csv/read_table 等 Python 函数的参数
   - 确定：header 是否存在、分隔符是什么、row.names/索引列是哪一列

2. **生成匹配的数据格式**：
   - 如果脚本期望数值矩阵（如 PCA），生成数值数据
   - 如果脚本期望分组信息，生成样本-分组映射
   - 确保列名、行名与脚本期望的一致

3. **最小数据原则**：
   - 只需要 3-5 行数据即可测试
   - 数值要合理（如基因表达量 0-100）

4. **重要**：test_files 的 key 必须是参数名（如 input_file, expression_matrix 等），而不是文件名。

请输出 JSON 格式：
```json
{{
  "test_files": {{
    "参数名": "文件内容（使用 \\n 换行，\\t 分隔）"
  }},
  "test_params": {{
  }},
  "data_format_notes": "简要说明生成的数据格式理由"
}}
```

注意：test_params 可以留空，系统会自动填充文件路径。

只输出 JSON，不要其他文字。"""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content

        # 提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            # 尝试直接解析
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
            else:
                return {"test_files": {}, "test_params": {}, "test_scenarios": []}

        # 后处理：将文件路径参数转换为占位符格式
        test_files = result.get("test_files", {})
        test_params = result.get("test_params", {})

        # 对于每个 test_file，对应的参数值应该是占位符路径
        for param_name in test_files.keys():
            # 使用占位符标记，_prepare_test_files 会将其替换为实际路径
            test_params[param_name] = f"__PLACEHOLDER__/{param_name}"

        result["test_params"] = test_params
        log.info(f"[TestDataGen] LLM 生成测试数据: files={list(test_files.keys())}, params={test_params}")
        return result

    except Exception as e:
        log.error(f"[TestDataGen] LLM 生成测试数据失败: {e}")

    return {"test_files": {}, "test_params": {}, "test_scenarios": []}


def create_test_files(test_files: Dict[str, str], work_dir: str) -> Dict[str, str]:
    """
    创建测试文件到工作目录

    Args:
        test_files: 参数名 -> 文件内容的映射
        work_dir: 工作目录

    Returns:
        文件名（参数名）到实际路径的映射
    """
    file_paths = {}

    for param_name, content in test_files.items():
        # 如果参数名没有扩展名，根据内容格式添加默认扩展名
        filename = param_name
        if '.' not in param_name:
            # 根据内容判断格式
            if content.startswith('<') or content.startswith('>'):
                filename = f"{param_name}.fasta"
            elif ',' in content.split('\n')[0]:
                filename = f"{param_name}.csv"
            else:
                # 默认使用 TSV 格式
                filename = f"{param_name}.tsv"

        filepath = os.path.join(work_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # 确保文件内容以换行符结尾，避免 "incomplete final line" 警告
        if content and not content.endswith('\n'):
            content = content + '\n'

        with open(filepath, 'w') as f:
            f.write(content)

        # 注意：返回的 key 仍然是原始参数名，以便后续匹配
        file_paths[param_name] = filepath
        log.info(f"[TestDataGen] 创建测试文件: {filepath} (参数名: {param_name})")

    return file_paths


# ==========================================
# 代码提取工具
# ==========================================

def extract_code_from_response(text: str) -> str:
    """
    从 LLM 的回复中提取修复后的代码
    """
    # 🔧 预处理：过滤 thinking 标签
    text = preprocess_llm_response(text)

    # 优先匹配 ```python ... ``` 格式
    pattern = r'```(?:python|r)\s*(.*?)\s*```'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 匹配 ***python ... *** 格式
    pattern = r'\*\*\*(?:python|r)\s*(.*?)\s*\*\*\*'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 如果没有代码块标记，尝试直接返回整个文本
    if 'def ' in text or 'import ' in text or 'library(' in text:
        return text.strip()

    return text.strip()


# ==========================================
# 执行结果检查
# ==========================================

def _get_file_type(filename: str) -> str:
    """
    根据文件扩展名判断文件类型

    Returns:
        文件类型: 'image', 'pdf', 'data', 'script', 'text', 'other'
    """
    ext = filename.lower().split('.')[-1] if '.' in filename else ''

    image_exts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']
    pdf_exts = ['pdf']
    data_exts = ['csv', 'tsv', 'xls', 'xlsx', 'json', 'xml']
    script_exts = ['py', 'r', 'sh', 'pl', 'nf']
    text_exts = ['txt', 'md', 'log', 'yaml', 'yml', 'toml']

    if ext in image_exts:
        return 'image'
    elif ext in pdf_exts:
        return 'pdf'
    elif ext in data_exts:
        return 'data'
    elif ext in script_exts:
        return 'script'
    elif ext in text_exts:
        return 'text'
    else:
        return 'other'


def check_execution_success(output: str) -> Tuple[bool, str]:
    """
    检查沙箱执行结果是否成功

    Returns:
        (is_success, error_message)
    """
    if not output:
        return False, "执行无输出"

    output_str = str(output)

    # 错误标记
    # 注意：R 的错误格式是 "Error in ..."（无冒号），Python 是 "Error: ..."
    error_markers = [
        ('Traceback', 'Python 错误'),
        ('Error in ', 'R 运行时错误'),  # R 错误格式: "Error in function_name(...)"
        ('Error:', '运行时错误'),
        ('Exception:', '异常'),
        ('错误:', '错误'),
        ('❌', '执行失败'),
        ('Failed', '失败'),
        ('segmentation fault', '段错误'),
        ('Execution halted', 'R 执行终止'),  # R 脚本执行中止
    ]

    for marker, desc in error_markers:
        if marker in output_str:
            # 尝试提取错误信息
            lines = output_str.split('\n')
            error_lines = []
            capture = False
            for line in lines:
                if marker in line:
                    capture = True
                if capture:
                    error_lines.append(line)
            return False, '\n'.join(error_lines[:10])  # 最多返回10行错误

    # 成功标记
    success_markers = ['✅', '成功', '完成', 'Success', 'Done']
    for marker in success_markers:
        if marker in output_str:
            return True, ""

    # 如果没有错误标记，且有一定输出，认为成功
    if len(output_str) > 10 and 'Error' not in output_str:
        return True, ""

    return True, ""


# ==========================================
# 安全检查
# ==========================================

def security_check(script_code: str) -> Tuple[bool, str]:
    """
    静态代码安全扫描
    """
    dangerous_keywords = [
        'os.environ', 'subprocess.call', 'subprocess.run', 'subprocess.Popen',
        'eval(', 'exec(', '__import__', 'socket.socket',
        'requests.get', 'requests.post', 'urllib.request',
        'shutil.rmtree', 'os.system', 'os.popen',
    ]

    r_dangerous_keywords = ['system(', 'system2(', 'shell(']

    all_dangerous = dangerous_keywords + r_dangerous_keywords

    lines = script_code.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        for keyword in all_dangerous:
            if keyword in line:
                return False, f"安全警报：代码包含高风险关键字 ({keyword})"

    return True, ""


# ==========================================
# 主测试函数
# ==========================================

async def auto_test_and_heal_skill(
    script_code: str,
    test_instruction: str,
    api_key: str,
    base_url: str,
    model_name: str,
    parameters_schema: Dict[str, Any] = None,
    auto_generate_data: bool = True,
    max_test_rounds: int = 3,
    executor_type: str = "Python_env"
) -> Dict[str, Any]:
    """
    沙箱自动化测试引擎（增强版）

    功能：
    1. 自动生成测试数据
    2. 多轮参数测试
    3. 测试失败自动修复

    Args:
        script_code: 需要测试的代码
        test_instruction: 测试参数指令
        api_key: API Key
        base_url: API Base URL
        model_name: 模型名称
        parameters_schema: 参数 Schema（用于生成测试数据）
        auto_generate_data: 是否自动生成测试数据
        max_test_rounds: 最大测试轮数
        executor_type: 执行器类型 (Python_env / R_env)

    Returns:
        测试结果字典
    """
    log.info(f"🧪 [Skill Tester] 启动自动化测试引擎... 执行器类型: {executor_type}")

    # 确定语言类型
    language = "r" if executor_type == "R_env" else "python"

    if not SANDBOX_AVAILABLE:
        log.warning("[Skill Tester] 沙箱不可用")
        return {
            "status": "skipped",
            "final_code": script_code,
            "logs": "沙箱执行环境不可用",
            "attempts": 0,
            "test_scenarios": []
        }

    # 安全检查
    is_safe, security_msg = security_check(script_code)
    if not is_safe:
        return {
            "status": "rejected",
            "final_code": script_code,
            "logs": security_msg,
            "attempts": 0,
            "test_scenarios": []
        }

    # 初始化 LLM
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1
    )

    # 准备工作目录
    # 关键修复：在容器内直接使用 /workspace，而不是 HOST_UPLOAD_DIR
    # HOST_UPLOAD_DIR 是宿主机路径，用于 run_container 的挂载配置
    # 在容器内，我们只能访问挂载后的 /workspace
    container_upload_dir = "/workspace"
    work_dir_name = f"skill_test_{os.urandom(4).hex()}"
    work_dir = os.path.join(container_upload_dir, work_dir_name)
    os.makedirs(work_dir, exist_ok=True)

    # 容器内路径（与 work_dir 相同）
    container_work_dir = work_dir

    log.info(f"[Skill Tester] 工作目录: {work_dir}")

    current_code = script_code
    execution_logs = ""
    test_results = []
    overall_success = True
    output_files = []  # 记录输出文件列表

    # ==========================================
    # 步骤1：生成测试数据和测试场景
    # ==========================================
    test_data = {"test_files": {}, "test_params": {}, "test_scenarios": []}

    if auto_generate_data and parameters_schema:
        log.info("[Skill Tester] 正在生成测试数据...")
        test_data = await generate_test_data(
            parameters_schema, executor_type, api_key, base_url, model_name,
            script_code=script_code
        )

        # 创建测试文件
        if test_data.get("test_files"):
            file_paths = create_test_files(test_data["test_files"], work_dir)
            execution_logs += f"\n📁 已创建测试文件: {list(file_paths.keys())}\n"

    # 如果没有自动生成场景，使用默认场景
    scenarios = test_data.get("test_scenarios", [])
    if not scenarios:
        # 使用 LLM 生成的 test_params 作为默认参数
        default_params = test_data.get("test_params", {})
        scenarios = [{"name": "默认测试", "params": default_params, "expected": "代码正常执行"}]

    # 合并用户提供的测试参数
    if test_instruction:
        scenarios.insert(0, {
            "name": "用户指定参数测试",
            "params": {"_user_instruction": test_instruction},
            "expected": "使用用户指定参数执行"
        })

    execution_logs += f"\n🧪 计划执行 {len(scenarios)} 个测试场景\n"

    # ==========================================
    # 步骤2：执行多轮测试
    # ==========================================
    for scenario_idx, scenario in enumerate(scenarios):
        scenario_name = scenario.get("name", f"场景{scenario_idx + 1}")
        scenario_params = scenario.get("params", {})
        expected = scenario.get("expected", "")

        execution_logs += f"\n{'='*50}\n"
        execution_logs += f"🔍 测试场景: {scenario_name}\n"
        execution_logs += f"   参数: {json.dumps(scenario_params, ensure_ascii=False)}\n"
        execution_logs += f"{'='*50}\n"

        scenario_success = False
        attempts = 0
        max_retries = 3

        # 测试-修复循环
        while attempts < max_retries and not scenario_success:
            attempts += 1
            execution_logs += f"\n▶️ 尝试 {attempts}/{max_retries}\n"

            # 构建测试代码（使用容器内路径）
            test_setup = _build_test_setup(
                scenario_params, work_dir, test_data.get("test_files", {}),
                language=language, container_work_dir=container_work_dir
            )
            full_test_code = f"{test_setup}\n\n{current_code}"

            # 执行沙箱（异步调用，避免阻塞事件循环）
            try:
                output = await _run_sandbox_code_async(full_test_code, language=language)
            except Exception as e:
                output = f"❌ 沙箱执行异常: {str(e)}"

            # 检查结果
            is_success, error_msg = check_execution_success(output)
            execution_logs += f"\n{output}\n"

            if is_success:
                scenario_success = True
                execution_logs += f"\n✅ 场景 [{scenario_name}] 测试通过！\n"

                # 收集输出文件
                try:
                    for f in os.listdir(work_dir):
                        if f not in test_data.get("test_files", {}):
                            output_files.append(os.path.join(work_dir, f))
                except:
                    pass
            else:
                execution_logs += f"\n❌ 场景 [{scenario_name}] 测试失败\n"
                execution_logs += f"错误信息: {error_msg}\n"

                if attempts < max_retries:
                    # 调用 AI 修复
                    execution_logs += "\n🔧 正在调用 Debugger 修复代码...\n"

                    fix_result = await _fix_code_with_llm(
                        llm, current_code, error_msg, scenario_params
                    )

                    if fix_result:
                        current_code = fix_result
                        execution_logs += "✅ Debugger 已生成修复代码\n"
                    else:
                        execution_logs += "❌ Debugger 修复失败，跳过此场景\n"
                        break

        # 记录场景结果
        test_results.append({
            "scenario": scenario_name,
            "success": scenario_success,
            "attempts": attempts,
            "error": error_msg if not scenario_success else None
        })

        if not scenario_success:
            overall_success = False

    # ==========================================
    # 步骤3：汇总结果
    # ==========================================
    execution_logs += f"\n{'='*50}\n"
    execution_logs += "📊 测试汇总\n"
    execution_logs += f"{'='*50}\n"

    passed = sum(1 for r in test_results if r["success"])
    total = len(test_results)

    for r in test_results:
        status = "✅ 通过" if r["success"] else "❌ 失败"
        execution_logs += f"  {r['scenario']}: {status} (尝试 {r['attempts']} 次)\n"

    execution_logs += f"\n总计: {passed}/{total} 场景通过\n"

    # 收集所有输出文件
    all_output_files = []
    # 收集所有输出文件（递归扫描子目录）
    input_files = set(test_data.get("test_files", {}).keys())

    def collect_output_files(directory: str, base_dir: str = None):
        """递归收集目录下的所有输出文件"""
        if base_dir is None:
            base_dir = directory
        files = []
        try:
            for f in os.listdir(directory):
                file_path = os.path.join(directory, f)
                if os.path.isfile(file_path):
                    # 排除测试输入文件和脚本文件
                    if f not in input_files and not f.endswith('.R') and not f.endswith('.py'):
                        rel_path = os.path.relpath(file_path, base_dir)
                        file_info = {
                            "name": rel_path,
                            "path": file_path,
                            "size": os.path.getsize(file_path),
                            "type": _get_file_type(f)
                        }

                        # 为文本和表格文件添加预览内容
                        file_type = _get_file_type(f)
                        if file_type in ['data', 'text'] and os.path.getsize(file_path) < 100 * 1024:  # 小于 100KB
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='replace') as fp:
                                    # 只读取前 500 行用于预览
                                    lines = []
                                    for i, line in enumerate(fp):
                                        if i >= 500:
                                            break
                                        lines.append(line)
                                    file_info["preview"] = ''.join(lines)
                            except Exception as e:
                                log.warning(f"[Skill Tester] 读取文件预览失败 {file_path}: {e}")

                        files.append(file_info)
                elif os.path.isdir(file_path):
                    files.extend(collect_output_files(file_path, base_dir))
        except Exception as e:
            log.warning(f"[Skill Tester] 扫描目录失败 {directory}: {e}")
        return files

    all_output_files = collect_output_files(work_dir)

    return {
        "status": "success" if overall_success else "partial" if passed > 0 else "failed",
        "final_code": current_code,
        "logs": execution_logs,
        "attempts": sum(r["attempts"] for r in test_results),
        "test_scenarios": test_results,
        "work_dir": work_dir,
        "output_files": all_output_files
    }


def _prepare_test_files(
    scenario_params: Dict[str, Any],
    work_dir: str,
    test_files: Dict[str, str],
    language: str = "python",
    container_work_dir: str = None
) -> tuple:
    """
    准备测试文件并构造命令行参数

    简化方案：不注入代码，而是直接构造命令行参数
    让脚本以真实命令行方式执行

    Args:
        scenario_params: 测试场景参数（可能包含 __PLACEHOLDER__ 占位符）
        work_dir: 工作目录（宿主机路径，用于创建文件）
        test_files: 测试文件映射（参数名 -> 文件内容）
        language: 语言类型 "python" 或 "r"
        container_work_dir: 容器内路径

    Returns:
        (cmd_args, resolved_params) - 命令行参数列表和解析后的参数字典
    """
    effective_work_dir = container_work_dir or work_dir
    resolved_params = {}
    cmd_args = []

    # 获取工作目录下所有已创建的文件
    existing_files = set()
    try:
        for f in os.listdir(work_dir):
            if os.path.isfile(os.path.join(work_dir, f)):
                existing_files.add(f)
    except:
        pass

    for key, value in scenario_params.items():
        # 替换占位符路径为实际的容器内路径
        if isinstance(value, str) and value.startswith("__PLACEHOLDER__/"):
            param_name = value.replace("__PLACEHOLDER__/", "")

            # 查找匹配的文件：优先精确匹配参数名，其次匹配带扩展名的文件
            actual_filename = None
            if param_name in existing_files:
                actual_filename = param_name
            else:
                # 查找以参数名开头的文件（如 input_file.tsv）
                for f in existing_files:
                    if f.startswith(param_name) or f.startswith(param_name.replace('.', '_')):
                        actual_filename = f
                        break

            if actual_filename:
                actual_path = f"{effective_work_dir}/{actual_filename}"
            else:
                # 回退：使用参数名作为文件名
                actual_path = f"{effective_work_dir}/{param_name}"

            resolved_params[key] = actual_path
            cmd_args.extend([f"--{key}", actual_path])
            log.info(f"[TestPrep] 参数 --{key} 映射到文件: {actual_path}")
        elif isinstance(value, bool):
            # R 的 getopt 需要所有参数都有值，即使是布尔参数
            # 传递 "TRUE" 或 "FALSE" 字符串
            resolved_params[key] = value
            cmd_args.extend([f"--{key}", "TRUE" if value else "FALSE"])
        elif isinstance(value, (int, float)):
            resolved_params[key] = value
            cmd_args.extend([f"--{key}", str(value)])
        elif isinstance(value, str):
            # 空字符串也需要传递
            resolved_params[key] = value
            cmd_args.extend([f"--{key}", value if value else ""])
        else:
            resolved_params[key] = value
            cmd_args.extend([f"--{key}", json.dumps(value)])

    return cmd_args, resolved_params


def _run_script_with_args(
    script_code: str,
    cmd_args: list,
    work_dir: str,
    language: str = "python",
    timeout: int = 120
) -> str:
    """
    直接以命令行方式执行脚本

    Args:
        script_code: 脚本代码
        cmd_args: 命令行参数列表（如 ["--input_file", "/path/to/file"]）
        work_dir: 工作目录
        language: 语言类型
        timeout: 超时时间

    Returns:
        执行输出
    """
    import os
    from app.tools.bio_tools import run_container

    # 将脚本写入工作目录
    if language.lower() == "r":
        script_file = os.path.join(work_dir, "test_script.R")
        cmd = ["Rscript", f"/workspace/{os.path.basename(work_dir)}/test_script.R"]
    else:
        script_file = os.path.join(work_dir, "test_script.py")
        cmd = ["python", f"/workspace/{os.path.basename(work_dir)}/test_script.py"]

    # 写入脚本
    with open(script_file, 'w', encoding='utf-8') as f:
        f.write(script_code)

    # 构建完整命令
    full_cmd = cmd + cmd_args

    log.info(f"[Skill Tester] 执行命令: {' '.join(full_cmd)}")

    # 使用 Docker API 直接执行命令
    try:
        import docker
        import json as json_module

        client = docker.from_env()

        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/opt/data1/public/software/systools/autonome/uploads")
        conda_host_path = "/opt/data1/public/software/systools/autonome/autonome_conda"

        env_list = [
            "PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin",
            "CONDA_PREFIX=/opt/conda"
        ]

        # 关键修复：设置容器工作目录为测试工作目录
        # 这样脚本中使用相对路径时，文件会写入正确的目录
        container_work_dir = f"/workspace/{os.path.basename(work_dir)}"
        log.info(f"[Skill Tester] 容器工作目录: {container_work_dir}")

        container = client.containers.run(
            image='autonome-tool-env',
            command=full_cmd,
            platform="linux/amd64",
            volumes={
                host_upload_dir: {'bind': '/workspace', 'mode': 'rw'},
                conda_host_path: {'bind': '/opt/conda', 'mode': 'rw'}
            },
            environment=env_list,
            working_dir=container_work_dir,  # 使用测试工作目录，而非 /app
            mem_limit='4g',
            network_disabled=True,
            detach=True,
            tty=True
        )

        # 等待执行完成
        result = container.wait(timeout=timeout)
        exit_code = result['StatusCode']

        # 获取输出
        output = container.logs(stdout=True, stderr=True).decode('utf-8', errors='replace')

        # 清理容器
        container.remove()

        return output, exit_code

    except Exception as e:
        log.error(f"[Skill Tester] Docker 执行失败: {e}")
        return f"❌ 执行失败: {str(e)}", 1


def _build_test_setup(
    scenario_params: Dict[str, Any],
    work_dir: str,
    test_files: Dict[str, str],
    language: str = "python",
    container_work_dir: str = None
) -> str:
    """
    构建测试前置代码（仅用于 Python sys.argv 注入，R 脚本不再使用此方法）

    注意：R 脚本测试已改用直接命令行执行方式，不再需要注入代码
    """
    effective_work_dir = container_work_dir or work_dir

    if language.lower() == "r":
        # R 语言：不再注入代码，直接返回空字符串
        # 实际执行通过 _run_script_with_args 完成
        return ""

    else:
        # Python 语言的测试环境设置
        setup_lines = [
            "# ===== 自动注入的测试环境 (Python) =====",
            "import sys",
            "import os",
            f"os.makedirs('{effective_work_dir}', exist_ok=True)",
            f"os.chdir('{effective_work_dir}')",
        ]

        # 处理用户指定的测试指令
        user_instruction = scenario_params.get("_user_instruction", "")
        if user_instruction:
            setup_lines.append(f"# 用户测试指令\n{user_instruction}")
            del scenario_params["_user_instruction"]

        # 构建命令行参数
        if scenario_params:
            args = ["script.py"]
            for key, value in scenario_params.items():
                # 替换占位符路径为实际的容器内路径
                if isinstance(value, str) and value.startswith("__PLACEHOLDER__/"):
                    filename_part = value.replace("__PLACEHOLDER__/", "")
                    actual_path = f"{effective_work_dir}/{filename_part}"
                    args.append(f"--{key}")
                    args.append(actual_path)
                elif isinstance(value, bool):
                    if value:
                        args.append(f"--{key}")
                elif isinstance(value, (list, dict)):
                    args.append(f"--{key}")
                    args.append(json.dumps(value))
                else:
                    args.append(f"--{key}")
                    args.append(str(value))

            setup_lines.append(f"sys.argv = {args}")

        setup_lines.append("# ===== 测试环境准备完成 =====\n")

    return "\n".join(setup_lines)


async def _fix_code_with_llm(
    llm: ChatOpenAI,
    current_code: str,
    error_msg: str,
    scenario_params: Dict[str, Any]
) -> Optional[str]:
    """
    调用 LLM 修复代码
    """
    fix_prompt = f"""你是高级生信 Debugger。代码测试失败，请修复代码。

【原始代码】
```python
{current_code}
```

【错误信息】
{error_msg}

【测试参数】
{json.dumps(scenario_params, ensure_ascii=False, indent=2)}

【修复要求】
1. 分析错误原因
2. 保持原有的参数解析系统（argparse/commandArgs）
3. 保持原有的详细注释
4. 输出完整的修复后代码

请直接输出修复后的完整代码，使用 ```python 包裹。"""

    try:
        response = await llm.ainvoke([HumanMessage(content=fix_prompt)])
        fixed_code = extract_code_from_response(response.content)

        if fixed_code and len(fixed_code) > 50:
            return fixed_code

    except Exception as e:
        log.error(f"[Debugger] 修复失败: {e}")

    return None


# ==========================================
# 便捷接口
# ==========================================

async def quick_test_skill(
    script_code: str,
    api_key: str,
    base_url: str,
    model_name: str,
    test_data_hint: str = None
) -> Dict[str, Any]:
    """
    快速测试技能（简化版接口）

    用于没有参数 Schema 的情况，用户可提供数据提示
    """
    return await auto_test_and_heal_skill(
        script_code=script_code,
        test_instruction=test_data_hint or "",
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        parameters_schema=None,
        auto_generate_data=False
    )


# ==========================================
# 流式日志事件类型
# ==========================================

@dataclass
class TestLogEvent:
    """测试日志事件"""
    type: str  # 'log', 'status', 'result', 'error'
    message: str = ""
    data: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ==========================================
# 流式日志版本 - 用于 SSE 实时推送
# ==========================================

async def auto_test_and_heal_skill_stream(
    script_code: str,
    test_instruction: str,
    api_key: str,
    base_url: str,
    model_name: str,
    parameters_schema: Dict[str, Any] = None,
    auto_generate_data: bool = True,
    max_test_rounds: int = 3,
    executor_type: str = "Python_env"
) -> AsyncGenerator[str, None]:
    """
    沙箱自动化测试引擎（流式日志版本）

    使用生成器实时 yield 日志事件，支持 SSE 流式响应

    Yields:
        JSON 格式的日志事件字符串
    """
    def emit(event: TestLogEvent) -> str:
        return f"data: {event.to_json()}\n\n"

    log.info(f"🧪 [Skill Tester] 启动自动化测试引擎 (流式模式)... 执行器类型: {executor_type}")

    # 确定语言类型
    language = "r" if executor_type == "R_env" else "python"

    # 检查沙箱可用性
    if not SANDBOX_AVAILABLE:
        yield emit(TestLogEvent(type="log", message="⚠️ 沙箱执行环境不可用"))
        yield emit(TestLogEvent(type="result", data={
            "status": "skipped",
            "final_code": script_code,
            "logs": "沙箱执行环境不可用",
            "attempts": 0,
            "test_scenarios": []
        }))
        return

    # 安全检查
    is_safe, security_msg = security_check(script_code)
    if not is_safe:
        yield emit(TestLogEvent(type="log", message=f"🚫 {security_msg}"))
        yield emit(TestLogEvent(type="result", data={
            "status": "rejected",
            "final_code": script_code,
            "logs": security_msg,
            "attempts": 0,
            "test_scenarios": []
        }))
        return

    yield emit(TestLogEvent(type="status", message="initializing"))
    yield emit(TestLogEvent(type="log", message="🧪 启动自动化测试引擎..."))

    # 初始化 LLM
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1
    )

    # 准备工作目录
    # 关键修复：在容器内直接使用 /workspace，而不是 HOST_UPLOAD_DIR
    container_upload_dir = "/workspace"
    work_dir_name = f"skill_test_{os.urandom(4).hex()}"
    work_dir = os.path.join(container_upload_dir, work_dir_name)
    os.makedirs(work_dir, exist_ok=True)

    # 容器内路径（与 work_dir 相同）
    container_work_dir = work_dir

    yield emit(TestLogEvent(type="log", message=f"📁 工作目录: {container_work_dir}"))

    current_code = script_code
    test_results = []
    overall_success = True
    output_files = []  # 记录输出文件

    # ==========================================
    # 步骤1：生成测试数据和测试场景
    # ==========================================
    yield emit(TestLogEvent(type="status", message="generating_test_data"))
    test_data = {"test_files": {}, "test_params": {}, "test_scenarios": []}

    if auto_generate_data and parameters_schema:
        yield emit(TestLogEvent(type="log", message="🔄 正在生成测试数据..."))
        test_data = await generate_test_data(
            parameters_schema, executor_type, api_key, base_url, model_name,
            script_code=script_code
        )

        # 创建测试文件
        if test_data.get("test_files"):
            file_paths = create_test_files(test_data["test_files"], work_dir)
            yield emit(TestLogEvent(type="log", message=f"✅ 已创建测试文件: {list(file_paths.keys())}"))

    # 如果没有自动生成场景，使用默认场景
    scenarios = test_data.get("test_scenarios", [])
    if not scenarios:
        # 使用 LLM 生成的 test_params 作为默认参数
        default_params = test_data.get("test_params", {})
        scenarios = [{"name": "默认测试", "params": default_params, "expected": "代码正常执行"}]

    # 合并用户提供的测试参数
    if test_instruction:
        scenarios.insert(0, {
            "name": "用户指定参数测试",
            "params": {"_user_instruction": test_instruction},
            "expected": "使用用户指定参数执行"
        })

    yield emit(TestLogEvent(type="log", message=f"\n📋 计划执行 {len(scenarios)} 个测试场景"))

    # ==========================================
    # 步骤2：执行多轮测试
    # ==========================================
    yield emit(TestLogEvent(type="status", message="running_tests"))

    for scenario_idx, scenario in enumerate(scenarios):
        scenario_name = scenario.get("name", f"场景{scenario_idx + 1}")
        scenario_params = scenario.get("params", {})

        yield emit(TestLogEvent(type="log", message=f"\n{'─' * 40}"))
        yield emit(TestLogEvent(type="log", message=f"🔍 测试场景: {scenario_name}"))
        yield emit(TestLogEvent(type="log", message=f"   参数: {json.dumps(scenario_params, ensure_ascii=False)}"))

        scenario_success = False
        attempts = 0
        max_retries = 3
        error_msg = ""

        # 测试-修复循环
        while attempts < max_retries and not scenario_success:
            attempts += 1
            yield emit(TestLogEvent(type="log", message=f"\n▶️ 尝试 {attempts}/{max_retries}"))

            # 执行沙箱
            yield emit(TestLogEvent(type="status", message=f"executing_scenario_{scenario_idx + 1}"))

            try:
                if language.lower() == "r":
                    # R 脚本：直接构造命令行执行
                    cmd_args, resolved_params = _prepare_test_files(
                        scenario_params.copy(), work_dir, test_data.get("test_files", {}),
                        language=language, container_work_dir=container_work_dir
                    )

                    output, exit_code = await asyncio.to_thread(
                        _run_script_with_args,
                        current_code, cmd_args, work_dir, language
                    )
                else:
                    # Python 脚本：使用 sys.argv 注入方式
                    test_setup = _build_test_setup(
                        scenario_params.copy(), work_dir, test_data.get("test_files", {}),
                        language=language, container_work_dir=container_work_dir
                    )
                    full_test_code = f"{test_setup}\n\n{current_code}"
                    output = await _run_sandbox_code_async(full_test_code, language=language)

            except Exception as e:
                output = f"❌ 沙箱执行异常: {str(e)}"

            # 检查结果
            is_success, error_msg = check_execution_success(output)

            # 输出执行结果（截断过长的输出）
            if len(output) > 500:
                yield emit(TestLogEvent(type="log", message=f"\n📤 执行输出:\n{output[:500]}..."))
            else:
                yield emit(TestLogEvent(type="log", message=f"\n📤 执行输出:\n{output}"))

            if is_success:
                scenario_success = True
                yield emit(TestLogEvent(type="log", message=f"✅ 场景 [{scenario_name}] 测试通过！"))

                # 收集输出文件
                try:
                    for f in os.listdir(work_dir):
                        if f not in test_data.get("test_files", {}):
                            output_files.append(os.path.join(work_dir, f))
                except:
                    pass
            else:
                yield emit(TestLogEvent(type="log", message=f"❌ 场景 [{scenario_name}] 测试失败"))
                yield emit(TestLogEvent(type="log", message=f"   错误: {error_msg[:200] if len(error_msg) > 200 else error_msg}"))

                if attempts < max_retries:
                    # 调用 AI 修复
                    yield emit(TestLogEvent(type="status", message="fixing_code"))
                    yield emit(TestLogEvent(type="log", message="🔧 正在调用 Debugger 修复代码..."))

                    fix_result = await _fix_code_with_llm(
                        llm, current_code, error_msg, scenario_params
                    )

                    if fix_result:
                        current_code = fix_result
                        yield emit(TestLogEvent(type="log", message="✅ Debugger 已生成修复代码"))
                    else:
                        yield emit(TestLogEvent(type="log", message="❌ Debugger 修复失败，跳过此场景"))
                        break

        # 记录场景结果
        test_results.append({
            "scenario": scenario_name,
            "success": scenario_success,
            "attempts": attempts,
            "error": error_msg if not scenario_success else None
        })

        if not scenario_success:
            overall_success = False

    # ==========================================
    # 步骤3：汇总结果
    # ==========================================
    yield emit(TestLogEvent(type="status", message="summarizing"))
    yield emit(TestLogEvent(type="log", message=f"\n{'═' * 40}"))
    yield emit(TestLogEvent(type="log", message="📊 测试汇总"))
    yield emit(TestLogEvent(type="log", message=f"{'═' * 40}"))

    passed = sum(1 for r in test_results if r["success"])
    total = len(test_results)

    for r in test_results:
        status = "✅ 通过" if r["success"] else "❌ 失败"
        yield emit(TestLogEvent(type="log", message=f"  {r['scenario']}: {status} (尝试 {r['attempts']} 次)"))

    yield emit(TestLogEvent(type="log", message=f"\n📈 总计: {passed}/{total} 场景通过"))

    # 构建最终日志
    final_logs = f"\n🧪 测试完成: {passed}/{total} 场景通过"
    if overall_success:
        yield emit(TestLogEvent(type="log", message="\n🎉 自动测试全部通过！"))
    elif passed > 0:
        yield emit(TestLogEvent(type="log", message="\n⚠️ 部分测试场景通过"))
    else:
        yield emit(TestLogEvent(type="log", message="\n❌ 自动测试失败"))

    # 收集所有输出文件（递归扫描子目录）
    input_files = set(test_data.get("test_files", {}).keys())

    def collect_output_files(directory: str, base_dir: str = None):
        """递归收集目录下的所有输出文件"""
        if base_dir is None:
            base_dir = directory
        files = []
        try:
            for f in os.listdir(directory):
                file_path = os.path.join(directory, f)
                if os.path.isfile(file_path):
                    # 排除测试输入文件和脚本文件
                    if f not in input_files and not f.endswith('.R') and not f.endswith('.py'):
                        rel_path = os.path.relpath(file_path, base_dir)
                        file_info = {
                            "name": rel_path,
                            "path": file_path,
                            "size": os.path.getsize(file_path),
                            "type": _get_file_type(f)
                        }

                        # 为文本和表格文件添加预览内容
                        file_type = _get_file_type(f)
                        if file_type in ['data', 'text'] and os.path.getsize(file_path) < 100 * 1024:  # 小于 100KB
                            try:
                                with open(file_path, 'r', encoding='utf-8', errors='replace') as fp:
                                    # 只读取前 500 行用于预览
                                    lines = []
                                    for i, line in enumerate(fp):
                                        if i >= 500:
                                            break
                                        lines.append(line)
                                    file_info["preview"] = ''.join(lines)
                            except Exception as e:
                                log.warning(f"[Skill Tester] 读取文件预览失败 {file_path}: {e}")

                        files.append(file_info)
                elif os.path.isdir(file_path):
                    files.extend(collect_output_files(file_path, base_dir))
        except Exception as e:
            log.warning(f"[Skill Tester] 扫描目录失败 {directory}: {e}")
        return files

    all_output_files = collect_output_files(work_dir)

    # 发送文件树事件
    if all_output_files:
        yield emit(TestLogEvent(type="file_tree", message="📁 测试输出文件"))
        for file_info in all_output_files:
            yield emit(TestLogEvent(type="file_item", data=file_info))

    # 返回最终结果
    yield emit(TestLogEvent(type="result", data={
        "status": "success" if overall_success else "partial" if passed > 0 else "failed",
        "final_code": current_code,
        "logs": final_logs,
        "attempts": sum(r["attempts"] for r in test_results),
        "test_scenarios": test_results,
        "work_dir": work_dir,
        "output_files": all_output_files
    }))


log.info("🧪 SKILL Tester (增强版 + 流式日志) 已加载")