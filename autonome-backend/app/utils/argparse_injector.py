"""
argparse 参数注入工具

支持 Python argparse 和 R getopt 的参数自动注入
"""

import re
from typing import Optional

from app.core.logger import log


def inject_python_argparse_params(code: str, user_params: dict, log_msg=None) -> str:
    """
    将用户参数注入到使用 argparse 的 Python 代码中。

    工作原理：
    1. 检测 Python 代码中的 argparse 参数定义
    2. 在 parse_args() 调用后注入参数覆盖代码
    3. 这样即使命令行参数未传入，脚本也能获取参数值

    Args:
        code: 原始 Python 代码
        user_params: 用户传递的参数字典
        log_msg: 日志函数（可选）

    Returns:
        修改后的 Python 代码
    """
    if not user_params:
        return code

    # 构建参数注入代码
    inject_lines = ["# ===== 📥 自动注入的用户参数 ====="]
    for key, value in user_params.items():
        # 将参数名转换为 Python 变量名格式
        py_var_name = key.lstrip('-').replace('-', '_')

        # 根据值的类型生成对应的 Python 赋值语句
        if isinstance(value, bool):
            py_value = "True" if value else "False"
        elif isinstance(value, (int, float)):
            py_value = str(value)
        elif isinstance(value, str):
            escaped_value = value.replace('\\', '\\\\').replace("'", "\\'")
            py_value = f"'{escaped_value}'"
        elif isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                items = ', '.join(f"'{v}'" for v in value)
            else:
                items = ', '.join(str(v) for v in value)
            py_value = f"[{items}]"
        else:
            escaped_value = str(value).replace('\\', '\\\\').replace("'", "\\'")
            py_value = f"'{escaped_value}'"

        inject_lines.append(f'args.{py_var_name} = {py_value}')
        inject_lines.append(f'if args.{py_var_name}: print(f"📌 参数 {py_var_name} 已注入:", args.{py_var_name})')

    inject_lines.append("# ===== 📥 参数注入结束 =====")
    inject_code = '\n'.join(inject_lines)

    # 在 parse_args() 调用后插入参数注入代码
    pattern = r'(args\s*=\s*parser\.parse_args\([^)]*\))'

    if re.search(pattern, code):
        new_code = re.sub(pattern, r'\1\n' + inject_code, code)
        if log_msg:
            log_msg(f"✅ 已注入 {len(user_params)} 个参数到 Python 代码中")
            log_msg(f"   参数列表: {list(user_params.keys())}")
        return new_code
    else:
        if log_msg:
            log_msg(f"⚠️ 未找到 parse_args 调用，在代码开头添加参数定义")

        args_init = "import argparse\nargs = argparse.Namespace()\n"
        for key, value in user_params.items():
            py_var_name = key.lstrip('-').replace('-', '_')
            if isinstance(value, bool):
                py_value = "True" if value else "False"
            elif isinstance(value, (int, float)):
                py_value = str(value)
            elif isinstance(value, str):
                escaped_value = value.replace('\\', '\\\\').replace("'", "\\'")
                py_value = f"'{escaped_value}'"
            else:
                escaped_value = str(value).replace('\\', '\\\\').replace("'", "\\'")
                py_value = f"'{escaped_value}'"
            args_init += f'args.{py_var_name} = {py_value}\n'

        return args_init + "\n" + code


def inject_r_argparse_params(code: str, user_params: dict, log_msg=None) -> str:
    """
    将用户参数注入到使用 argparse 的 R 代码中。

    Args:
        code: 原始 R 代码
        user_params: 用户传递的参数字典
        log_msg: 日志函数（可选）

    Returns:
        修改后的 R 代码
    """
    if not user_params:
        return code

    # 构建参数注入代码
    inject_lines = ["# ===== 📥 自动注入的用户参数 ====="]
    for key, value in user_params.items():
        r_var_name = key.lstrip('-').replace('-', '_')

        if isinstance(value, bool):
            r_value = "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            r_value = str(value)
        elif isinstance(value, str):
            escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
            r_value = f'"{escaped_value}"'
        elif isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                items = ', '.join(f'"{v}"' for v in value)
            else:
                items = ', '.join(str(v) for v in value)
            r_value = f"c({items})"
        else:
            escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
            r_value = f'"{escaped_value}"'

        inject_lines.append(f'opt${r_var_name} <- {r_value}')
        inject_lines.append(f'if (!is.null(opt${r_var_name})) cat("📌 参数 {r_var_name} 已注入: ", opt${r_var_name}, "\\n")')

    inject_lines.append("# ===== 📥 参数注入结束 =====")
    inject_code = '\n'.join(inject_lines)

    pattern = r'(opt\s*[<-]\s*parse_args\s*\([^)]+\))'

    if re.search(pattern, code):
        new_code = re.sub(pattern, r'\1\n' + inject_code, code)
        if log_msg:
            log_msg(f"✅ 已注入 {len(user_params)} 个参数到 R 代码中")
            log_msg(f"   参数列表: {list(user_params.keys())}")
        return new_code
    else:
        if log_msg:
            log_msg(f"⚠️ 未找到 parse_args 调用，在代码开头添加参数定义")

        opt_init = "opt <- list()\n"
        for key, value in user_params.items():
            r_var_name = key.lstrip('-').replace('-', '_')
            if isinstance(value, bool):
                r_value = "TRUE" if value else "FALSE"
            elif isinstance(value, (int, float)):
                r_value = str(value)
            elif isinstance(value, str):
                escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
                r_value = f'"{escaped_value}"'
            else:
                escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
                r_value = f'"{escaped_value}"'
            opt_init += f'opt${r_var_name} <- {r_value}\n'

        return opt_init + "\n" + code