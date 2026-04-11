"""
工具系统模块

超级执行者 V2 的工具系统，支持：
- 代码执行 (Python/R)
- 数据探查
- 文件操作
- 技能调用
"""

from app.agent.tools.base import (
    BaseTool,
    ExecutionContext,
    ToolResult,
    ToolCategory
)
from app.agent.tools.code_execution import (
    CodeExecutionTool,
    PythonExecutionTool,
    RExecutionTool
)
from app.agent.tools.data_probe import (
    DataProbeTool,
    ScanWorkspaceTool,
    PeekTabularTool,
    InspectH5adTool
)
from app.agent.tools.file_operation import FileOperationTool
from app.agent.tools.registry import (
    ToolRegistry,
    get_tool_registry,
    get_tool,
    list_all_tools,
    get_tools_for_prompt
)

from app.core.logger import log
log.info("🔧 执行工具模块已加载")