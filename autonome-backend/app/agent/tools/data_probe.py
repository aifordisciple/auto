"""
数据探查工具

封装 probe_tools 中的工具，用于数据预览和目录扫描。
"""

import time
from typing import Dict, Any

from app.agent.tools.base import BaseTool, ExecutionContext, ToolResult, ToolCategory
from app.core.logger import log


class DataProbeTool(BaseTool):
    """数据探查工具"""

    tool_id = "data-probe"
    name = "数据探查"
    description = "预览和分析数据文件，支持表格文件、单细胞数据、测序数据等"
    category = ToolCategory.DATA_PROBE

    parameters_schema = {
        "type": "object",
        "required": ["probe_type", "file_path"],
        "properties": {
            "probe_type": {
                "type": "string",
                "enum": ["tabular", "workspace", "h5ad", "fastq", "bam"],
                "description": "探查类型"
            },
            "file_path": {
                "type": "string",
                "description": "文件或目录路径"
            },
            "n_rows": {
                "type": "integer",
                "description": "预览行数（仅用于 tabular 类型）",
                "default": 5
            },
            "n_reads": {
                "type": "integer",
                "description": "预览 reads 数（仅用于 fastq 类型）",
                "default": 5
            },
            "max_depth": {
                "type": "integer",
                "description": "最大扫描深度（仅用于 workspace 类型）",
                "default": 3
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        执行数据探查

        Args:
            parameters: 包含 probe_type, file_path 等参数
            context: 执行上下文

        Returns:
            ToolResult: 探查结果
        """
        from app.tools.probe_tools import (
            peek_tabular_data,
            scan_workspace,
            inspect_h5ad,
            inspect_fastq,
            inspect_bam
        )

        probe_type = parameters.get("probe_type", "tabular")
        file_path = parameters.get("file_path", "")

        log.info(f"🔍 [DataProbe] 开始探查: {probe_type} - {file_path}")

        start_time = time.time()

        try:
            result = None

            if probe_type == "tabular":
                result = peek_tabular_data.invoke({
                    "file_path": file_path,
                    "n_rows": parameters.get("n_rows", 5)
                })
            elif probe_type == "workspace":
                result = scan_workspace.invoke({
                    "directory_path": file_path,
                    "max_depth": parameters.get("max_depth", 3)
                })
            elif probe_type == "h5ad":
                result = inspect_h5ad.invoke({
                    "file_path": file_path
                })
            elif probe_type == "fastq":
                result = inspect_fastq.invoke({
                    "file_path": file_path,
                    "n_reads": parameters.get("n_reads", 5)
                })
            elif probe_type == "bam":
                result = inspect_bam.invoke({
                    "file_path": file_path
                })
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未知的探针类型: {probe_type}",
                    exit_code=1
                )

            execution_time = time.time() - start_time
            log.info(f"✅ [DataProbe] 探查完成, 耗时: {execution_time:.2f}s")

            return ToolResult(
                success=True,
                output=result,
                exit_code=0,
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            log.error(f"❌ [DataProbe] 探查失败: {str(e)}")
            return ToolResult(
                success=False,
                output="",
                error=f"探查失败: {str(e)}",
                exit_code=1,
                execution_time=execution_time
            )


# ==========================================
# ✨ 专用探针工具（便捷类）
# ==========================================

class ScanWorkspaceTool(BaseTool):
    """目录扫描工具"""

    tool_id = "scan-workspace"
    name = "目录扫描"
    description = "扫描指定目录下的所有文件和文件夹，返回目录树结构"
    category = ToolCategory.DATA_PROBE

    parameters_schema = {
        "type": "object",
        "required": ["directory_path"],
        "properties": {
            "directory_path": {
                "type": "string",
                "description": "要扫描的目录路径"
            },
            "max_depth": {
                "type": "integer",
                "description": "最大扫描深度",
                "default": 3
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        probe = DataProbeTool()
        return await probe.execute({
            "probe_type": "workspace",
            "file_path": parameters.get("directory_path", context.project_dir),
            "max_depth": parameters.get("max_depth", 3)
        }, context)


class PeekTabularTool(BaseTool):
    """表格预览工具"""

    tool_id = "peek-tabular"
    name = "表格预览"
    description = "预览表格文件（CSV/TSV）的结构：表头、维度和前几行数据"
    category = ToolCategory.DATA_PROBE

    parameters_schema = {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": "表格文件路径"
            },
            "n_rows": {
                "type": "integer",
                "description": "预览行数",
                "default": 5
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        probe = DataProbeTool()
        return await probe.execute({
            "probe_type": "tabular",
            "file_path": parameters.get("file_path", ""),
            "n_rows": parameters.get("n_rows", 5)
        }, context)


class InspectH5adTool(BaseTool):
    """H5AD 文件检查工具"""

    tool_id = "inspect-h5ad"
    name = "H5AD 检查"
    description = "解析 .h5ad 单细胞 AnnData 文件结构"
    category = ToolCategory.DATA_PROBE

    parameters_schema = {
        "type": "object",
        "required": ["file_path"],
        "properties": {
            "file_path": {
                "type": "string",
                "description": ".h5ad 文件路径"
            }
        }
    }

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        probe = DataProbeTool()
        return await probe.execute({
            "probe_type": "h5ad",
            "file_path": parameters.get("file_path", "")
        }, context)