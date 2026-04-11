"""
工具基类定义

定义所有执行工具的通用接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ToolCategory(str, Enum):
    """工具类别"""
    CODE_EXECUTION = "code_execution"      # 代码执行
    DATA_PROBE = "data_probe"              # 数据探查
    FILE_OPERATION = "file_operation"      # 文件操作
    SKILL_CALL = "skill_call"              # 技能调用


@dataclass
class ExecutionContext:
    """
    执行上下文

    包含工具执行所需的所有环境信息。
    """
    # 项目信息
    project_id: str
    project_dir: str
    user_id: int

    # 输出配置
    output_dir: str

    # 用户配置
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None

    # 运行时信息
    task_id: Optional[str] = None
    session_id: Optional[str] = None

    # 可用资源
    available_files: list = None  # 项目中可用的文件列表

    def __post_init__(self):
        if self.available_files is None:
            self.available_files = []


@dataclass
class ToolResult:
    """
    工具执行结果

    标准化的工具返回结构。
    """
    success: bool
    output: str                            # 标准输出
    error: Optional[str] = None            # 错误信息
    exit_code: int = 0                     # 退出码 (0 = 成功)
    execution_time: float = 0.0            # 执行耗时（秒）

    # 元数据
    metadata: Dict[str, Any] = None        # 额外元数据

    # 生成的文件
    generated_files: list = None           # 生成的文件路径列表

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.generated_files is None:
            self.generated_files = []

    def to_tuple(self) -> Tuple[str, int, Dict[str, Any]]:
        """转换为 (output, exit_code, metadata) 元组"""
        return (self.output, self.exit_code, self.metadata)


class BaseTool(ABC):
    """
    工具基类

    所有执行工具必须继承此类并实现 execute 方法。
    """

    # 工具元数据（子类必须覆盖）
    tool_id: str = "base-tool"
    name: str = "基础工具"
    description: str = "工具基类"
    category: ToolCategory = ToolCategory.CODE_EXECUTION

    # 参数 Schema（JSON Schema 格式）
    parameters_schema: Dict[str, Any] = {}

    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters_schema": self.parameters_schema
        }

    @abstractmethod
    async def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        """
        执行工具

        Args:
            parameters: 工具参数
            context: 执行上下文

        Returns:
            ToolResult: 执行结果
        """
        pass

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        验证参数

        Args:
            parameters: 待验证的参数

        Returns:
            (is_valid, error_message)
        """
        if not self.parameters_schema:
            # 无 schema，默认通过
            return True, None

        # 简单的必填参数检查
        required = self.parameters_schema.get("required", [])
        properties = self.parameters_schema.get("properties", {})

        for param_name in required:
            if param_name not in parameters:
                return False, f"缺少必填参数: {param_name}"

        # 类型检查
        for param_name, param_value in parameters.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                if expected_type:
                    if not self._check_type(param_value, expected_type):
                        return False, f"参数 {param_name} 类型错误，期望 {expected_type}"

        return True, None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """检查值类型"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }

        expected_python_type = type_map.get(expected_type)
        if expected_python_type is None:
            return True  # 未知类型，跳过检查

        # 特殊处理：Python 中 bool 是 int 的子类
        if expected_type == "integer" and isinstance(value, bool):
            return False

        return isinstance(value, expected_python_type)

    def get_parameter_description(self) -> str:
        """获取参数描述（用于 LLM Prompt）"""
        if not self.parameters_schema:
            return "无参数"

        properties = self.parameters_schema.get("properties", {})
        required = self.parameters_schema.get("required", [])

        lines = []
        for param_name, param_info in properties.items():
            req_mark = "（必填）" if param_name in required else "（可选）"
            param_type = param_info.get("type", "any")
            param_desc = param_info.get("description", "")
            default_val = param_info.get("default", "")

            line = f"- {param_name}: {param_type} {req_mark}"
            if param_desc:
                line += f" - {param_desc}"
            if default_val:
                line += f" [默认: {default_val}]"
            lines.append(line)

        return "\n".join(lines)


# ==========================================
# ✨ 辅助函数
# ==========================================

def format_execution_time(seconds: float) -> str:
    """格式化执行时间"""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"