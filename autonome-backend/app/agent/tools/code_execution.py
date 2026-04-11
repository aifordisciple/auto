"""
代码执行工具

在 Docker 沙箱中执行 Python 或 R 代码。
"""

import time
import asyncio
from typing import Dict, Any

from app.agent.tools.base import BaseTool, ExecutionContext, ToolResult, ToolCategory
from app.core.logger import log


class CodeExecutionTool(BaseTool):
    """代码执行工具"""

    tool_id = "execute-code"
    name = "代码执行"
    description = "在 Docker 沙箱中执行 Python 或 R 代码，支持安装用户自定义包"
    category = ToolCategory.CODE_EXECUTION

    parameters_schema = {
        "type": "object",
        "required": ["code", "language"],
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的代码内容"
            },
            "language": {
                "type": "string",
                "enum": ["python", "r"],
                "description": "编程语言"
            },
            "timeout": {
                "type": "integer",
                "description": "执行超时时间（秒）",
                "default": 300
            },
            "environment": {
                "type": "object",
                "description": "环境变量",
                "default": {}
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        执行代码

        Args:
            parameters: 包含 code, language, timeout 等参数
            context: 执行上下文

        Returns:
            ToolResult: 执行结果
        """
        from app.tools.bio_tools import run_container

        # 提取参数
        code = parameters.get("code", "")
        language = parameters.get("language", "python")
        timeout = parameters.get("timeout", 300)
        extra_env = parameters.get("environment", {})

        # 构建环境变量
        environment = {
            "TASK_OUT_DIR": context.output_dir,
            "PROJECT_ID": context.project_id,
            "SUPER_EXECUTOR_MODE": "true",
            **extra_env
        }

        log.info(f"🔨 [CodeExecution] 开始执行 {language} 代码, 超时: {timeout}s")

        start_time = time.time()

        try:
            # 执行代码（run_container 是同步函数，需要在线程池中运行）
            loop = asyncio.get_event_loop()
            output, exit_code = await loop.run_in_executor(
                None,
                lambda: run_container(
                    image='autonome-tool-env',
                    command=code,
                    language=language,
                    environment=environment,
                    timeout=timeout,
                    user_id=context.user_id
                )
            )

            execution_time = time.time() - start_time

            # 扫描输出目录获取生成的文件
            generated_files = self._scan_generated_files(context.output_dir)

            if exit_code == 0:
                log.info(f"✅ [CodeExecution] 执行成功, 耗时: {execution_time:.1f}s")
                return ToolResult(
                    success=True,
                    output=output,
                    exit_code=0,
                    execution_time=execution_time,
                    generated_files=generated_files
                )
            else:
                log.error(f"❌ [CodeExecution] 执行失败, exit_code={exit_code}")
                return ToolResult(
                    success=False,
                    output=output,
                    error=self._extract_error(output),
                    exit_code=exit_code,
                    execution_time=execution_time,
                    generated_files=generated_files
                )

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            log.error(f"❌ [CodeExecution] 执行超时 ({timeout}s)")
            return ToolResult(
                success=False,
                output="",
                error=f"执行超时（超过 {timeout} 秒）",
                exit_code=124,  # 标准超时退出码
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = time.time() - start_time
            log.error(f"❌ [CodeExecution] 执行异常: {str(e)}")
            return ToolResult(
                success=False,
                output="",
                error=f"执行异常: {str(e)}",
                exit_code=1,
                execution_time=execution_time
            )

    def _extract_error(self, output: str) -> str:
        """从输出中提取错误信息"""
        if not output:
            return "未知错误"

        # 尝试提取 Python 错误
        if "Traceback" in output:
            lines = output.split("\n")
            error_lines = []
            in_traceback = False
            for line in lines:
                if "Traceback" in line:
                    in_traceback = True
                if in_traceback:
                    error_lines.append(line)
            return "\n".join(error_lines[-10:])  # 最多显示最后 10 行

        # 尝试提取 R 错误
        if "Error:" in output:
            lines = output.split("\n")
            for line in lines:
                if "Error:" in line:
                    return line

        # 返回输出的最后部分
        return output[-500:] if len(output) > 500 else output

    def _scan_generated_files(self, output_dir: str) -> list:
        """扫描输出目录获取生成的文件"""
        import os

        generated_files = []

        if not output_dir or not os.path.exists(output_dir):
            return generated_files

        # 跳过的文件
        skip_files = {'.', '..', 'latest_script.py', 'latest_script.R'}

        try:
            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    if f.startswith('.') or f in skip_files:
                        continue

                    file_path = os.path.join(root, f)
                    try:
                        file_size = os.path.getsize(file_path)
                        ext = os.path.splitext(f)[1].lower()

                        generated_files.append({
                            "path": file_path,
                            "name": f,
                            "size": file_size,
                            "extension": ext
                        })
                    except Exception:
                        continue

            # 按大小排序
            generated_files.sort(key=lambda x: x["size"], reverse=True)

        except Exception as e:
            log.warning(f"[CodeExecution] 扫描输出目录失败: {str(e)}")

        return generated_files[:50]  # 最多返回 50 个文件


# ==========================================
# ✨ Python 和 R 专用工具（便捷类）
# ==========================================

class PythonExecutionTool(CodeExecutionTool):
    """Python 代码执行工具"""

    tool_id = "execute-python"
    name = "Python 代码执行"
    description = "在 Docker 沙箱中执行 Python 代码"

    parameters_schema = {
        "type": "object",
        "required": ["code"],
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码"
            },
            "timeout": {
                "type": "integer",
                "description": "执行超时时间（秒）",
                "default": 300
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        parameters["language"] = "python"
        return await super().execute(parameters, context)


class RExecutionTool(CodeExecutionTool):
    """R 代码执行工具"""

    tool_id = "execute-r"
    name = "R 代码执行"
    description = "在 Docker 沙箱中执行 R 代码"

    parameters_schema = {
        "type": "object",
        "required": ["code"],
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 R 代码"
            },
            "timeout": {
                "type": "integer",
                "description": "执行超时时间（秒）",
                "default": 300
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        parameters["language"] = "r"
        return await super().execute(parameters, context)