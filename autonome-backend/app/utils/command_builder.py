"""
命令行参数构建器

根据参数 schema 构建命令行参数列表，支持 Python argparse 和 R getopt
"""

from typing import Optional
from app.core.logger import log


def build_command_line_args(
    parameters: dict,
    schema_props: dict,
    language: str = "python"
) -> list:
    """
    根据参数 schema 构建命令行参数列表

    将用户参数转换为命令行参数格式，支持多种数据类型：
    - 布尔值：True 时添加 flag，False 时跳过
    - 数值：添加 --key value
    - 数组：添加 --key val1,val2,val3
    - 字符串：添加 --key value

    Args:
        parameters: 用户提供的参数字典
        schema_props: 参数 schema 的 properties 字段，包含每个参数的类型定义
        language: 语言类型 "python" 或 "r"，影响参数名格式

    Returns:
        命令行参数列表，如: ['--sample-sheet', '/path/to/file', '--min-umi', '1000']
    """
    args = []

    for key, value in parameters.items():
        # 跳过系统级参数和空值
        if key in ["task_name", "session_id", "project_id", "code", "message",
                   "PROJECT_ID", "TASK_ID", "TASK_OUT_DIR"]:
            continue
        if value is None or value == "":
            continue

        # 获取参数定义
        param_def = schema_props.get(key, {})

        # 验证参数是否在 schema 中定义，跳过未定义的参数
        if not param_def:
            log.warning(f"[build_command_line_args] 跳过未定义参数: {key}={value}")
            continue

        param_type = param_def.get("type", "string").lower() if isinstance(param_def, dict) else "string"

        # 构建命令行参数名
        # Python argparse 支持下划线转连字符（如 --min-umi）
        # R getopt 不支持连字符，保持下划线（如 --min_umi）
        if language.lower() == "r":
            # R getopt：保持下划线
            cli_key = key
        else:
            # Python argparse：下划线转连字符
            cli_key = key.replace("_", "-")

        # 根据类型构建参数
        if param_type == "boolean":
            # 布尔值：True 时添加 flag
            if value:
                args.append(f"--{cli_key}")
        elif param_type in ["number", "integer"]:
            # 数值：添加 --key value
            args.append(f"--{cli_key}")
            args.append(str(value))
        elif param_type == "array":
            # 数组：添加 --key val1,val2,val3
            if isinstance(value, list):
                args.append(f"--{cli_key}")
                args.append(",".join(str(v) for v in value))
        else:
            # 字符串或其他类型：添加 --key value
            args.append(f"--{cli_key}")
            args.append(str(value))

    return args