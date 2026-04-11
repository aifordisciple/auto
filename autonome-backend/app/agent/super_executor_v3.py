"""
超级执行者 V3 - 统一脚本生成与执行引擎

核心创新：
1. 统一入口：不再区分代码块模式和自然语言模式
2. LLM 脚本生成：将混合输入（自然语言 + 代码块 + 执行说明）转换为单个 Python 脚本
3. R 代码支持：通过 subprocess 调用 Rscript
4. 上下文传递：单个脚本内部自然共享变量和中间结果

状态机流程：
START → SCAN_FILES → GENERATE_SCRIPT → EXECUTE_SCRIPT → GENERATE_REPORT → END
                                              ↓
                                      [exit_code != 0?]
                                              ↓
                                     DEBUG_RETRY (max 3) → EXECUTE_SCRIPT
                                              ↓
                                    GENERATE_REPORT → END
"""

import os
import re
import json
import time
import asyncio
from typing import TypedDict, List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field

from app.core.logger import log
from app.tools.bio_tools import run_container


# ==========================================
# ✨ 配置常量
# ==========================================
MAX_DEBUG_RETRIES = 3          # Debugger 最大重试次数
EXECUTION_TIMEOUT = 600        # 脚本执行超时（10分钟）
HEARTBEAT_INTERVAL = 30        # 心跳间隔（30秒）


# ==========================================
# ✨ 数据类定义
# ==========================================

@dataclass
class ExecutionContext:
    """执行上下文"""
    project_id: str
    project_dir: str
    output_dir: str
    user_id: int
    available_files: List[str] = field(default_factory=list)


@dataclass
class GeneratedScript:
    """LLM 生成的脚本"""
    code: str                    # 生成的 Python 脚本
    user_intent: str             # 理解的用户意图
    detected_paths: List[str]    # 检测到的文件路径
    path_mappings: Dict[str, str] = field(default_factory=dict)
    includes_r_code: bool = False  # 是否包含 R 代码调用


@dataclass
class ExecutionReport:
    """执行战报"""
    success: bool
    execution_time: float
    generated_files: List[Dict[str, Any]]
    stdout: str
    stderr: str
    exit_code: int
    path_mappings: Dict[str, str]
    user_intent: str
    output_dir: str
    retry_count: int


# ==========================================
# ✨ LLM Prompt 模板
# ==========================================

SCRIPT_GENERATOR_SYSTEM_PROMPT = """你是一个智能脚本生成专家。你的任务是将用户的混合输入（自然语言、代码块、执行说明）转换为**一个完整的可执行 Python 脚本**。

## 核心规则

1. **单一脚本输出**：无论输入多么复杂，只输出一个 Python 脚本
2. **R 代码封装**：如有 R 代码，通过 subprocess 调用 Rscript，并在脚本中动态生成 R 脚本
3. **路径映射**：自动检测输入中的文件路径，并使用提供的真实路径
4. **错误处理**：每个关键步骤添加 try-except，打印友好的错误信息
5. **进度输出**：使用 print() 输出执行进度，方便调试
6. **结果收集**：在脚本末尾收集生成的文件路径，打印到标准输出

## 项目信息

- 项目目录: {project_dir}
- 原始数据目录: {project_dir}/raw_data/
- 结果输出目录: {output_dir}/
- 可用文件列表:
{available_files}

## 输出格式

请以 JSON 格式回复：

```json
{{
    "user_intent": "用户意图的简短描述（中文）",
    "detected_paths": ["检测到的路径1", "检测到的路径2"],
    "script": "完整的 Python 脚本代码"
}}
```

## 路径处理规则

1. 如果用户输入中的路径在"可用文件列表"中有匹配，使用完整路径
2. 如果路径不存在但有相似文件名，使用 fuzzy_match 提示
3. 输出文件必须保存到 {output_dir}/ 目录

## R 代码调用示例

如果用户输入包含 R 代码，按以下方式封装：

```python
import subprocess
import os

r_code = '''
# R 代码内容
library(ggplot2)
# ...
'''

r_script_path = os.path.join(output_dir, "temp_script.R")
with open(r_script_path, 'w') as f:
    f.write(r_code)

result = subprocess.run(['Rscript', r_script_path], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"R 执行错误: {{result.stderr}}")
```

## 常见场景示例

### 场景 1：列出项目文件
输入: "列出项目中的所有文件"
输出脚本:
```python
import os

project_dir = "{project_dir}"
for root, dirs, files in os.walk(project_dir):
    level = root.replace(project_dir, '').count(os.sep)
    indent = ' ' * 2 * level
    print(f'{{indent}}{{os.path.basename(root)}}/')
    subindent = ' ' * 2 * (level + 1)
    for file in files:
        print(f'{{subindent}}{{file}}')
```

### 场景 2：预览 CSV 文件
输入: "查看 counts.csv 的前几行"
输出脚本:
```python
import pandas as pd

csv_path = "{project_dir}/raw_data/counts.csv"
df = pd.read_csv(csv_path, nrows=5)
print(df.to_string())
print(f"\\n总行数: {{len(pd.read_csv(csv_path))}}")
```

### 场景 3：混合 Python 和 R 代码
输入: 用户提供了 Python 数据处理代码和 R 绘图代码
输出脚本: 在 Python 中完成数据处理，保存中间结果，然后调用 Rscript 执行 R 绘图代码
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
        log.warning(f"[V3] 项目目录不存在: {project_dir}")
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

    log.info(f"[V3] 扫描到 {len(files)} 个文件")
    return files


def fuzzy_match_file(filename: str, project_dir: str, available_files: List[str]) -> Optional[str]:
    """
    模糊匹配文件名

    Args:
        filename: 目标文件名（可能不完整或不精确）
        project_dir: 项目目录
        available_files: 可用文件列表（相对路径）

    Returns:
        匹配到的真实路径，未找到返回 None
    """
    from difflib import SequenceMatcher

    # 提取目标文件名
    target_name = os.path.basename(filename).lower()

    best_match = None
    best_ratio = 0.0

    for file_path in available_files:
        file_name = os.path.basename(file_path).lower()
        ratio = SequenceMatcher(None, target_name, file_name).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = file_path

    # 相似度阈值 0.7
    if best_ratio >= 0.7:
        real_path = os.path.join(project_dir, best_match)
        log.info(f"[V3] 模糊匹配: {filename} -> {real_path} (相似度: {best_ratio:.2f})")
        return real_path

    return None


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
# ✨ LLM 脚本生成器
# ==========================================

class UnifiedScriptGenerator:
    """统一脚本生成器 - 使用 LLM 生成单一 Python 脚本"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    async def generate(
        self,
        raw_input: str,
        context: ExecutionContext
    ) -> GeneratedScript:
        """
        生成统一 Python 脚本

        Args:
            raw_input: 用户原始输入（可能包含自然语言 + 代码块）
            context: 执行上下文

        Returns:
            GeneratedScript 对象
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        log.info(f"[V3] 开始生成脚本，输入长度: {len(raw_input)}")

        # 构建可用文件列表字符串
        files_str = "\n".join([f"  - {f}" for f in context.available_files[:100]])  # 最多显示 100 个

        # 构建 System Prompt
        system_prompt = SCRIPT_GENERATOR_SYSTEM_PROMPT.format(
            project_dir=context.project_dir,
            output_dir=context.output_dir,
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

            log.info(f"[V3] LLM 响应长度: {len(llm_response)}")

            # 解析 JSON 响应
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # 尝试直接解析
                data = json.loads(llm_response)

            script_code = data.get("script", "")
            user_intent = data.get("user_intent", "执行用户指令")
            detected_paths = data.get("detected_paths", [])

            # 处理路径映射
            path_mappings = {}
            for path in detected_paths:
                # 1. 尝试精确匹配
                filename = os.path.basename(path)

                # 检查是否在可用文件列表中
                for available_file in context.available_files:
                    if os.path.basename(available_file) == filename:
                        real_path = os.path.join(context.project_dir, available_file)
                        path_mappings[path] = real_path
                        break
                else:
                    # 2. 尝试模糊匹配
                    fuzzy_match = fuzzy_match_file(path, context.project_dir, context.available_files)
                    if fuzzy_match:
                        path_mappings[path] = fuzzy_match

            # 应用路径映射到脚本
            for fake_path, real_path in path_mappings.items():
                script_code = script_code.replace(fake_path, real_path)

            # 检查是否包含 R 代码
            includes_r_code = "Rscript" in script_code or "r_code =" in script_code

            log.info(f"[V3] 脚本生成完成，长度: {len(script_code)}, 包含 R: {includes_r_code}")

            return GeneratedScript(
                code=script_code,
                user_intent=user_intent,
                detected_paths=detected_paths,
                path_mappings=path_mappings,
                includes_r_code=includes_r_code
            )

        except json.JSONDecodeError as e:
            log.error(f"[V3] JSON 解析失败: {e}")

            # 回退：尝试从响应中提取 Python 代码块
            code_match = re.search(r'```python\s*([\s\S]*?)\s*```', llm_response)
            if code_match:
                return GeneratedScript(
                    code=code_match.group(1).strip(),
                    user_intent="执行用户代码",
                    detected_paths=[],
                    includes_r_code=False
                )

            raise ValueError(f"无法解析 LLM 响应: {e}")

        except Exception as e:
            log.error(f"[V3] 脚本生成失败: {e}")
            raise


# ==========================================
# ✨ 脚本执行器
# ==========================================

class ScriptExecutor:
    """沙箱脚本执行器"""

    async def execute(
        self,
        script: str,
        context: ExecutionContext
    ) -> ExecutionReport:
        """
        在沙箱中执行脚本

        Args:
            script: Python 脚本代码
            context: 执行上下文

        Returns:
            ExecutionReport 对象
        """
        log.info(f"[V3] 开始执行脚本，长度: {len(script)}")

        start_time = time.time()

        # 确保输出目录存在
        os.makedirs(context.output_dir, exist_ok=True)

        # 构建环境变量
        environment = {
            "TASK_OUT_DIR": context.output_dir,
            "PROJECT_ID": context.project_id,
            "PROJECT_DIR": context.project_dir,
            "SUPER_EXECUTOR_MODE": "v3"
        }

        # 调用沙箱执行
        output, exit_code, billing_info = run_container(
            image='autonome-tool-env',
            command=script,
            language="python",
            environment=environment,
            timeout=EXECUTION_TIMEOUT,
            user_id=context.user_id
        )

        execution_time = time.time() - start_time

        # 提取生成的文件
        generated_files = extract_generated_files(context.output_dir)

        # 分离 stdout 和 stderr
        # Docker 日志中 stdout 和 stderr 混在一起，我们用标记区分
        stdout = output
        stderr = ""

        log.info(f"[V3] 脚本执行完成，退出码: {exit_code}, 耗时: {execution_time:.2f}s")

        return ExecutionReport(
            success=(exit_code == 0),
            execution_time=execution_time,
            generated_files=generated_files,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            path_mappings={},
            user_intent="",
            output_dir=context.output_dir,
            retry_count=0
        )


# ==========================================
# ✨ 主执行器类
# ==========================================

class SuperExecutorV3:
    """超级执行者 V3 - 统一入口"""

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
        self.output_dir = f"{self.project_dir}/results/super_executor_v3_{int(time.time())}"

        # 组件
        self.script_generator = UnifiedScriptGenerator(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name
        ) if api_key and base_url and model_name else None

        self.script_executor = ScriptExecutor()

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行超级执行者 V3

        Yields:
            SSE 事件字典
        """
        log.info(f"🚀 [SuperExecutorV3] 开始执行 - project_id={self.project_id}")

        # 推送启动事件
        yield {
            "event": "status_update",
            "data": json.dumps({
                "status": "initializing",
                "message": "正在初始化执行环境..."
            })
        }

        # ==========================================
        # Step 1: 扫描项目文件
        # ==========================================
        yield {
            "event": "status_update",
            "data": json.dumps({
                "status": "scanning",
                "message": "正在扫描项目文件..."
            })
        }

        available_files = scan_project_files(self.project_dir)

        context = ExecutionContext(
            project_id=self.project_id,
            project_dir=self.project_dir,
            output_dir=self.output_dir,
            user_id=self.user_id,
            available_files=available_files
        )

        yield {
            "event": "files_scanned",
            "data": json.dumps({
                "file_count": len(available_files),
                "files": available_files[:20]  # 只显示前 20 个
            })
        }

        # ==========================================
        # Step 2: 生成脚本
        # ==========================================
        if not self.script_generator:
            yield {
                "event": "error",
                "data": json.dumps({"error": "未配置 LLM，无法生成脚本"})
            }
            return

        yield {
            "event": "status_update",
            "data": json.dumps({
                "status": "generating",
                "message": "正在分析您的指令并生成执行脚本..."
            })
        }

        try:
            generated_script = await self.script_generator.generate(
                raw_input=self.raw_input,
                context=context
            )
        except Exception as e:
            log.error(f"[V3] 脚本生成失败: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": f"脚本生成失败: {str(e)}"})
            }
            return

        # 推送脚本生成事件
        yield {
            "event": "script_generated",
            "data": json.dumps({
                "user_intent": generated_script.user_intent,
                "code_preview": generated_script.code[:500] + "..." if len(generated_script.code) > 500 else generated_script.code,
                "detected_paths": generated_script.detected_paths,
                "path_mappings": generated_script.path_mappings,
                "includes_r_code": generated_script.includes_r_code
            })
        }

        # ==========================================
        # Step 3: 执行脚本（带重试）
        # ==========================================
        retry_count = 0
        current_script = generated_script.code
        last_report = None

        while retry_count <= MAX_DEBUG_RETRIES:
            yield {
                "event": "status_update",
                "data": json.dumps({
                    "status": "executing",
                    "message": f"正在执行脚本..." + (f" (重试 {retry_count}/{MAX_DEBUG_RETRIES})" if retry_count > 0 else "")
                })
            }

            # 执行脚本
            report = await self.script_executor.execute(current_script, context)
            report.path_mappings = generated_script.path_mappings
            report.user_intent = generated_script.user_intent
            report.retry_count = retry_count

            last_report = report

            # 检查执行结果
            if report.success:
                break

            # 执行失败，尝试修复
            if retry_count < MAX_DEBUG_RETRIES:
                retry_count += 1

                yield {
                    "event": "debug_retry",
                    "data": json.dumps({
                        "attempt": retry_count,
                        "max_retries": MAX_DEBUG_RETRIES,
                        "error": extract_error_message(report.stdout)[:500]
                    })
                }

                # 尝试 LLM 修复
                try:
                    fixed_script = await self._fix_script_with_llm(
                        script=current_script,
                        error_msg=extract_error_message(report.stdout),
                        context=context
                    )
                    if fixed_script:
                        current_script = fixed_script
                        log.info(f"[V3] 脚本已通过 LLM 修复")
                    else:
                        log.warning("[V3] LLM 修复返回空结果，使用原脚本重试")
                except Exception as e:
                    log.error(f"[V3] LLM 修复失败: {e}")
            else:
                # 达到最大重试次数
                log.warning(f"[V3] 达到最大重试次数 {MAX_DEBUG_RETRIES}")
                break

        # ==========================================
        # Step 4: 生成战报
        # ==========================================
        if last_report:
            yield {
                "event": "status_update",
                "data": json.dumps({
                    "status": "generating_report",
                    "message": "正在生成执行战报..."
                })
            }

            battle_report = self._generate_battle_report(last_report)

            yield {
                "event": "execution_report",
                "data": json.dumps(battle_report)
            }

            # 推送最终消息
            ai_full_response = self._format_report_as_markdown(battle_report)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "text",
                    "content": ai_full_response
                })
            }

        # 完成
        log.info(f"🏁 [SuperExecutorV3] 执行完成")

        yield {
            "event": "done",
            "data": json.dumps({"message": "[DONE]"})
        }

    async def _fix_script_with_llm(
        self,
        script: str,
        error_msg: str,
        context: ExecutionContext
    ) -> Optional[str]:
        """
        调用 LLM 修复脚本

        Args:
            script: 原始脚本
            error_msg: 错误信息
            context: 执行上下文

        Returns:
            修复后的脚本，失败返回 None
        """
        from app.services.celery_app import fix_code_with_llm

        try:
            fixed_script = fix_code_with_llm(
                code=script,
                error_msg=error_msg,
                api_key=self.api_key,
                base_url=self.base_url,
                model_name=self.model_name,
                language="python",
                timeout=90
            )
            return fixed_script
        except Exception as e:
            log.error(f"[V3] LLM 修复失败: {e}")
            return None

    def _generate_battle_report(self, report: ExecutionReport) -> Dict[str, Any]:
        """
        生成战报字典

        Args:
            report: 执行报告

        Returns:
            战报字典
        """
        return {
            "task_out_dir": report.output_dir,
            "success": report.success,
            "execution_time": round(report.execution_time, 2),
            "exit_code": report.exit_code,
            "user_intent": report.user_intent,
            "path_mappings": report.path_mappings,
            "generated_files": report.generated_files,
            "retry_count": report.retry_count,
            "stdout_preview": report.stdout[:1000] if report.stdout else "",
            "error_message": extract_error_message(report.stdout) if not report.success else "",
            # 兼容 V1 格式
            "success_count": 1 if report.success else 0,
            "failed_count": 0 if report.success else 1,
            "total_retries": report.retry_count,
            "execution_summary": [{
                "order": 0,
                "language": "python",
                "status": "success" if report.success else "failed",
                "exit_code": report.exit_code,
                "retry_count": report.retry_count,
                "error": extract_error_message(report.stdout) if not report.success else ""
            }]
        }

    def _format_report_as_markdown(self, report: Dict[str, Any]) -> str:
        """
        将战报格式化为 Markdown

        Args:
            report: 战报字典

        Returns:
            Markdown 格式的战报
        """
        status_emoji = "✅" if report.get("success") else "❌"

        md = f"""\n\n> ⚡ **超级执行者 V3 执行完成**

{status_emoji} **{report.get('user_intent', '执行用户指令')}**

- 执行时间: {report.get('execution_time', 0):.2f} 秒
- 重试次数: {report.get('retry_count', 0)}
- 输出目录: `{report.get('task_out_dir', '')}`

```json_battle_report
{json.dumps(report, ensure_ascii=False, indent=2)}
```
"""
        return md


log.info("🦾 超级执行者 V3 模块已加载")