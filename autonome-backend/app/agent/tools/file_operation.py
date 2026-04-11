"""
文件操作工具

提供文件和目录操作：复制、移动、删除、创建目录等。
"""

import os
import shutil
import time
from typing import Dict, Any

from app.agent.tools.base import BaseTool, ExecutionContext, ToolResult, ToolCategory
from app.core.logger import log


class FileOperationTool(BaseTool):
    """文件操作工具"""

    tool_id = "file-operation"
    name = "文件操作"
    description = "文件和目录操作：复制、移动、删除、创建目录"
    category = ToolCategory.FILE_OPERATION

    parameters_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["copy", "move", "delete", "mkdir", "list", "exists"],
                "description": "操作类型"
            },
            "source": {
                "type": "string",
                "description": "源文件/目录路径"
            },
            "destination": {
                "type": "string",
                "description": "目标路径"
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归操作（用于删除目录）",
                "default": False
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        执行文件操作

        Args:
            parameters: 包含 operation, source, destination 等参数
            context: 执行上下文

        Returns:
            ToolResult: 操作结果
        """
        operation = parameters.get("operation", "")
        source = parameters.get("source", "")
        destination = parameters.get("destination", "")
        recursive = parameters.get("recursive", False)

        log.info(f"📁 [FileOperation] 执行 {operation}: {source} -> {destination}")

        start_time = time.time()

        # 安全检查函数
        def safe_path(path: str) -> str:
            """检查路径是否在项目目录内"""
            if not path:
                return path

            abs_path = os.path.abspath(path)
            project_dir = os.path.abspath(context.project_dir)

            # 允许访问项目目录及其子目录
            if not abs_path.startswith(project_dir):
                raise ValueError(f"路径超出项目目录范围: {path}")

            return abs_path

        try:
            result_msg = ""

            if operation == "copy":
                if not source or not destination:
                    return ToolResult(
                        success=False,
                        output="",
                        error="复制操作需要 source 和 destination 参数",
                        exit_code=1
                    )

                src = safe_path(source)
                dst = safe_path(destination)

                if not os.path.exists(src):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"源文件不存在: {source}",
                        exit_code=1
                    )

                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst), exist_ok=True)

                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

                result_msg = f"文件已复制: {source} -> {destination}"

            elif operation == "move":
                if not source or not destination:
                    return ToolResult(
                        success=False,
                        output="",
                        error="移动操作需要 source 和 destination 参数",
                        exit_code=1
                    )

                src = safe_path(source)
                dst = safe_path(destination)

                if not os.path.exists(src):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"源文件不存在: {source}",
                        exit_code=1
                    )

                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)

                result_msg = f"文件已移动: {source} -> {destination}"

            elif operation == "delete":
                if not source:
                    return ToolResult(
                        success=False,
                        output="",
                        error="删除操作需要 source 参数",
                        exit_code=1
                    )

                src = safe_path(source)

                if not os.path.exists(src):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"文件不存在: {source}",
                        exit_code=1
                    )

                if os.path.isdir(src):
                    if recursive:
                        shutil.rmtree(src)
                    else:
                        os.rmdir(src)  # 只能删除空目录
                else:
                    os.remove(src)

                result_msg = f"已删除: {source}"

            elif operation == "mkdir":
                if not destination:
                    return ToolResult(
                        success=False,
                        output="",
                        error="创建目录操作需要 destination 参数",
                        exit_code=1
                    )

                dst = safe_path(destination)
                os.makedirs(dst, exist_ok=True)

                result_msg = f"目录已创建: {destination}"

            elif operation == "list":
                if not source:
                    source = context.project_dir

                src = safe_path(source)

                if not os.path.exists(src):
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"目录不存在: {source}",
                        exit_code=1
                    )

                entries = os.listdir(src)
                files = []
                dirs = []

                for entry in entries:
                    if entry.startswith('.'):
                        continue
                    full_path = os.path.join(src, entry)
                    if os.path.isdir(full_path):
                        dirs.append(entry)
                    else:
                        files.append(entry)

                result_msg = f"目录: {source}\n"
                result_msg += f"文件夹 ({len(dirs)}): {', '.join(dirs[:10])}\n"
                result_msg += f"文件 ({len(files)}): {', '.join(files[:10])}"
                if len(files) > 10:
                    result_msg += f"... 共 {len(files)} 个文件"

            elif operation == "exists":
                if not source:
                    return ToolResult(
                        success=False,
                        output="",
                        error="检查存在需要 source 参数",
                        exit_code=1
                    )

                # exists 操作不需要安全检查（只读操作）
                exists = os.path.exists(source)
                result_msg = f"{'存在' if exists else '不存在'}: {source}"

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未知操作: {operation}",
                    exit_code=1
                )

            execution_time = time.time() - start_time
            log.info(f"✅ [FileOperation] 操作完成: {result_msg}")

            return ToolResult(
                success=True,
                output=result_msg,
                exit_code=0,
                execution_time=execution_time
            )

        except ValueError as e:
            # 安全检查失败
            execution_time = time.time() - start_time
            log.error(f"❌ [FileOperation] 安全检查失败: {str(e)}")
            return ToolResult(
                success=False,
                output="",
                error=f"安全检查失败: {str(e)}",
                exit_code=1,
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = time.time() - start_time
            log.error(f"❌ [FileOperation] 操作失败: {str(e)}")
            return ToolResult(
                success=False,
                output="",
                error=f"操作失败: {str(e)}",
                exit_code=1,
                execution_time=execution_time
            )