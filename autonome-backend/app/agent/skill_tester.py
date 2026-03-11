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
from typing import Dict, Any, List, Optional, Tuple, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass, asdict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from app.core.logger import log

# 尝试导入沙箱执行工具
try:
    from app.tools.bio_tools import run_container
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    log.warning("[Skill Tester] bio_tools 未找到，沙箱测试功能将受限")


def _run_sandbox_code(code: str, language: str = "python") -> str:
    """
    执行沙箱代码的封装函数

    Args:
        code: 要执行的代码
        language: 语言类型 "python" 或 "r"
    """
    try:
        result_output, exit_code = run_container(
            image='autonome-tool-env',
            command=code,
            language=language
        )
        return result_output
    except Exception as e:
        log.error(f"[Sandbox] 执行失败: {e}")
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

        # 文件路径参数 - 生成简单的测试文件
        if param_type == "string" and param_format == "filepath":
            # 根据参数名推断文件类型
            if "csv" in param_name.lower() or "csv" in str(param_default).lower():
                test_files[f"{param_name}.csv"] = "id,value,name\n1,100,test1\n2,200,test2\n"
            elif "tsv" in param_name.lower() or "tsv" in str(param_default).lower():
                test_files[f"{param_name}.tsv"] = "id\tvalue\tname\n1\t100\ttest1\n2\t200\ttest2\n"
            elif "matrix" in param_name.lower() or "expression" in param_name.lower():
                test_files[f"{param_name}.tsv"] = "gene\tsample1\tsample2\nGENE1\t10.5\t12.3\nGENE2\t8.2\t9.1\n"
            elif "bam" in param_name.lower():
                # BAM 文件无法简单创建，跳过
                test_params[param_name] = f"/tmp/test_{param_name}.bam"
                continue
            elif "fasta" in param_name.lower() or "fa" in param_name.lower():
                test_files[f"{param_name}.fa"] = ">seq1\nATCGATCG\n>seq2\nGCTAGCTA\n"
            elif "fastq" in param_name.lower() or "fq" in param_name.lower():
                test_files[f"{param_name}.fq"] = "@read1\nATCGATCG\n+\nIIIIIIII\n@read2\nGCTAGCTA\n+\nIIIIIIII\n"
            else:
                # 默认生成简单的 TSV 文件
                test_files[f"{param_name}.tsv"] = "col1\tcol2\nval1\tval2\n"

            test_params[param_name] = f"/tmp/skill_test_workdir/{param_name}.tsv"

        # 目录路径参数
        elif param_type == "string" and param_format == "directorypath":
            test_params[param_name] = "/tmp/skill_test_workdir/output"

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
    model_name: str
) -> Dict[str, Any]:
    """
    根据参数 Schema 生成测试数据

    优先使用快速规则生成，失败时回退到 LLM 生成
    """
    # 优先使用快速生成（无需 LLM）
    try:
        fast_result = generate_test_data_fast(parameters_schema, executor_type)
        if fast_result.get("test_params") or fast_result.get("test_files"):
            return fast_result
    except Exception as e:
        log.warning(f"[TestDataGen] 快速生成失败: {e}，尝试 LLM 生成")

    # 回退到 LLM 生成
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.3,
        timeout=30  # 30秒超时
    )

    properties = parameters_schema.get("properties", {})

    prompt = f"""你是一个专业的生信测试数据生成器。请根据以下参数定义生成测试数据。

【参数定义】
{json.dumps(parameters_schema, indent=2, ensure_ascii=False)}

【要求】
1. 对于 FilePath 类型参数：生成最小化的测试文件内容（如几行 CSV/TSV 数据）
2. 对于 DirectoryPath 类型参数：说明需要创建的目录结构
3. 对于数值参数：生成合理的测试值（边界值、典型值）
4. 对于字符串参数：生成有意义的测试字符串

请输出 JSON 格式：
```json
{{
  "test_files": {{
    "文件名": "文件内容"
  }},
  "test_params": {{
    "参数名": 测试值
  }},
  "test_scenarios": [
    {{"name": "场景1", "params": {{}}, "expected": "预期结果描述"}}
  ]
}}
```

只输出 JSON，不要其他文字。"""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content

        # 提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # 尝试直接解析
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])

    except Exception as e:
        log.error(f"[TestDataGen] LLM 生成测试数据失败: {e}")

    return {"test_files": {}, "test_params": {}, "test_scenarios": []}


def create_test_files(test_files: Dict[str, str], work_dir: str) -> Dict[str, str]:
    """
    创建测试文件到工作目录

    Returns:
        文件名到实际路径的映射
    """
    file_paths = {}

    for filename, content in test_files.items():
        filepath = os.path.join(work_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w') as f:
            f.write(content)

        file_paths[filename] = filepath
        log.info(f"[TestDataGen] 创建测试文件: {filepath}")

    return file_paths


# ==========================================
# 代码提取工具
# ==========================================

def extract_code_from_response(text: str) -> str:
    """
    从 LLM 的回复中提取修复后的代码
    """
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
    error_markers = [
        ('Traceback', 'Python 错误'),
        ('Error:', '运行时错误'),
        ('Exception:', '异常'),
        ('错误:', '错误'),
        ('❌', '执行失败'),
        ('Failed', '失败'),
        ('segmentation fault', '段错误'),
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
    work_dir = tempfile.mkdtemp(prefix="skill_test_")
    log.info(f"[Skill Tester] 工作目录: {work_dir}")

    current_code = script_code
    execution_logs = ""
    test_results = []
    overall_success = True

    # ==========================================
    # 步骤1：生成测试数据和测试场景
    # ==========================================
    test_data = {"test_files": {}, "test_params": {}, "test_scenarios": []}

    if auto_generate_data and parameters_schema:
        log.info("[Skill Tester] 正在生成测试数据...")
        test_data = await generate_test_data(
            parameters_schema, executor_type, api_key, base_url, model_name
        )

        # 创建测试文件
        if test_data.get("test_files"):
            file_paths = create_test_files(test_data["test_files"], work_dir)
            execution_logs += f"\n📁 已创建测试文件: {list(file_paths.keys())}\n"

    # 如果没有自动生成场景，使用默认场景
    scenarios = test_data.get("test_scenarios", [])
    if not scenarios:
        scenarios = [{"name": "默认测试", "params": {}, "expected": "代码正常执行"}]

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

            # 构建测试代码
            test_setup = _build_test_setup(scenario_params, work_dir, test_data.get("test_files", {}), language=language)
            full_test_code = f"{test_setup}\n\n{current_code}"

            # 执行沙箱
            try:
                output = _run_sandbox_code(full_test_code, language=language)
            except Exception as e:
                output = f"❌ 沙箱执行异常: {str(e)}"

            # 检查结果
            is_success, error_msg = check_execution_success(output)
            execution_logs += f"\n{output}\n"

            if is_success:
                scenario_success = True
                execution_logs += f"\n✅ 场景 [{scenario_name}] 测试通过！\n"
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

    return {
        "status": "success" if overall_success else "partial" if passed > 0 else "failed",
        "final_code": current_code,
        "logs": execution_logs,
        "attempts": sum(r["attempts"] for r in test_results),
        "test_scenarios": test_results,
        "work_dir": work_dir
    }


def _build_test_setup(
    scenario_params: Dict[str, Any],
    work_dir: str,
    test_files: Dict[str, str],
    language: str = "python"
) -> str:
    """
    构建测试前置代码

    Args:
        scenario_params: 测试场景参数
        work_dir: 工作目录
        test_files: 测试文件映射
        language: 语言类型 "python" 或 "r"
    """
    if language.lower() == "r":
        # R 语言的测试环境设置
        setup_lines = [
            "# ===== 自动注入的测试环境 (R) =====",
            f"setwd('{work_dir}')",  # 切换到工作目录
        ]

        # 处理用户指定的测试指令
        user_instruction = scenario_params.get("_user_instruction", "")
        if user_instruction:
            setup_lines.append(f"# 用户测试指令\n{user_instruction}")
            del scenario_params["_user_instruction"]

        # 对于 R，我们需要模拟命令行参数
        # 使用 optparse 或 commandArgs 的脚本会在运行时解析参数
        # 这里我们设置环境变量或直接修改脚本逻辑比较复杂
        # 简化处理：将参数作为 R 变量注入
        if scenario_params:
            setup_lines.append("# 测试参数注入")
            for key, value in scenario_params.items():
                if isinstance(value, bool):
                    r_value = "TRUE" if value else "FALSE"
                elif isinstance(value, (int, float)):
                    r_value = str(value)
                elif isinstance(value, str):
                    r_value = f'"{value}"'
                else:
                    r_value = f'"{json.dumps(value)}"'
                setup_lines.append(f"{key} <- {r_value}")

        # 添加测试文件路径
        if test_files:
            for filename in test_files:
                var_name = filename.upper().replace('.', '_')
                setup_lines.append(f"TEST_FILE_{var_name} <- '{work_dir}/{filename}'")

        setup_lines.append("# ===== 测试环境准备完成 =====\n")

    else:
        # Python 语言的测试环境设置
        setup_lines = [
            "# ===== 自动注入的测试环境 (Python) =====",
            "import sys",
            "import os",
            f"os.chdir('{work_dir}')",  # 切换到工作目录
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
                if isinstance(value, bool):
                    if value:
                        args.append(f"--{key}")
                elif isinstance(value, (list, dict)):
                    args.append(f"--{key}")
                    args.append(json.dumps(value))
                else:
                    args.append(f"--{key}")
                    args.append(str(value))

            setup_lines.append(f"sys.argv = {args}")

        # 添加测试文件路径到环境变量
        if test_files:
            for filename in test_files:
                setup_lines.append(f"TEST_FILE_{filename.upper().replace('.', '_')} = '{work_dir}/{filename}'")

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
    work_dir = tempfile.mkdtemp(prefix="skill_test_")
    yield emit(TestLogEvent(type="log", message=f"📁 工作目录: {work_dir}"))

    current_code = script_code
    test_results = []
    overall_success = True

    # ==========================================
    # 步骤1：生成测试数据和测试场景
    # ==========================================
    yield emit(TestLogEvent(type="status", message="generating_test_data"))
    test_data = {"test_files": {}, "test_params": {}, "test_scenarios": []}

    if auto_generate_data and parameters_schema:
        yield emit(TestLogEvent(type="log", message="🔄 正在生成测试数据..."))
        test_data = await generate_test_data(
            parameters_schema, executor_type, api_key, base_url, model_name
        )

        # 创建测试文件
        if test_data.get("test_files"):
            file_paths = create_test_files(test_data["test_files"], work_dir)
            yield emit(TestLogEvent(type="log", message=f"✅ 已创建测试文件: {list(file_paths.keys())}"))

    # 如果没有自动生成场景，使用默认场景
    scenarios = test_data.get("test_scenarios", [])
    if not scenarios:
        scenarios = [{"name": "默认测试", "params": {}, "expected": "代码正常执行"}]

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

            # 构建测试代码
            test_setup = _build_test_setup(scenario_params.copy(), work_dir, test_data.get("test_files", {}), language=language)
            full_test_code = f"{test_setup}\n\n{current_code}"

            # 执行沙箱
            yield emit(TestLogEvent(type="status", message=f"executing_scenario_{scenario_idx + 1}"))
            try:
                output = _run_sandbox_code(full_test_code, language=language)
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

    # 返回最终结果
    yield emit(TestLogEvent(type="result", data={
        "status": "success" if overall_success else "partial" if passed > 0 else "failed",
        "final_code": current_code,
        "logs": final_logs,
        "attempts": sum(r["attempts"] for r in test_results),
        "test_scenarios": test_results,
        "work_dir": work_dir
    }))


log.info("🧪 SKILL Tester (增强版 + 流式日志) 已加载")