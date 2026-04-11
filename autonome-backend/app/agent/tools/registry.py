"""
工具注册表

管理所有可用工具，提供统一的工具访问接口。
"""

from typing import Dict, List, Type

from app.agent.tools.base import BaseTool, ToolCategory
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
from app.core.logger import log


# ==========================================
# ✨ 工具注册表
# ==========================================

class ToolRegistry:
    """
    工具注册表

    单例模式，管理所有注册的工具。
    """

    _instance = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self):
        """注册默认工具"""
        # 代码执行工具
        self.register(CodeExecutionTool())
        self.register(PythonExecutionTool())
        self.register(RExecutionTool())

        # 数据探查工具
        self.register(DataProbeTool())
        self.register(ScanWorkspaceTool())
        self.register(PeekTabularTool())
        self.register(InspectH5adTool())

        # 文件操作工具
        self.register(FileOperationTool())

        log.info(f"🔧 [ToolRegistry] 已注册 {len(self._tools)} 个工具")

    def register(self, tool: BaseTool) -> None:
        """
        注册工具

        Args:
            tool: 工具实例
        """
        if tool.tool_id in self._tools:
            log.warning(f"[ToolRegistry] 工具已存在，将覆盖: {tool.tool_id}")

        self._tools[tool.tool_id] = tool
        log.debug(f"[ToolRegistry] 注册工具: {tool.tool_id} - {tool.name}")

    def get(self, tool_id: str) -> BaseTool | None:
        """
        获取工具

        Args:
            tool_id: 工具 ID

        Returns:
            工具实例，不存在则返回 None
        """
        return self._tools.get(tool_id)

    def list_tools(self) -> List[BaseTool]:
        """获取所有工具列表"""
        return list(self._tools.values())

    def get_tools_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """
        按类别获取工具

        Args:
            category: 工具类别

        Returns:
            该类别的工具列表
        """
        return [t for t in self._tools.values() if t.category == category]

    def get_tools_description(self) -> str:
        """
        获取所有工具的描述（用于 LLM Prompt）

        Returns:
            工具描述文本
        """
        lines = []
        for tool in self._tools.values():
            lines.append(f"\n### {tool.name} ({tool.tool_id})")
            lines.append(f"{tool.description}")
            lines.append(f"参数:\n{tool.get_parameter_description()}")

        return "\n".join(lines)

    def get_tools_json(self) -> List[Dict]:
        """
        获取所有工具信息的 JSON 格式

        Returns:
            工具信息列表
        """
        return [tool.get_info() for tool in self._tools.values()]


# ==========================================
# ✨ 全局注册表实例
# ==========================================

# 创建全局实例
_registry = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_tool(tool_id: str) -> BaseTool | None:
    """快捷方法：获取工具"""
    return get_tool_registry().get(tool_id)


def list_all_tools() -> List[BaseTool]:
    """快捷方法：列出所有工具"""
    return get_tool_registry().list_tools()


def get_tools_for_prompt() -> str:
    """快捷方法：获取用于 Prompt 的工具描述"""
    return get_tool_registry().get_tools_description()