"""
技能验证服务

包含技能代码的铁律校验逻辑
"""

import re
from typing import Tuple


def validate_iron_rules(script_code: str) -> Tuple[bool, str]:
    """
    双保险强制校验 - 确保代码符合三大铁律

    铁律内容：
    1. 代码必须包含参数解析系统 (argparse/optparse/sys.argv/commandArgs)
    2. 表格输出必须明确指定 tab 分割的 tsv 格式
    3. 代码必须有足够的注释密度

    Args:
        script_code: 待验证的脚本代码

    Returns:
        (is_valid, error_message) 元组
        - is_valid: True 表示通过校验
        - error_message: 失败时的错误信息，成功时为空字符串
    """
    if not script_code:
        return False, "代码不能为空"

    # 1. 校验参数系统 (检查是否包含 argparse 或 optparse 或 sys.argv)
    if not re.search(r'(argparse|optparse|sys\.argv|commandArgs)', script_code):
        return False, "拦截：代码未包含参数解析系统！必须使用 argparse (Python) 或 optparse/commandArgs (R)"

    # 2. 校验输出格式 (如果是 pandas 输出，检查是否带 tab 或 tsv)
    if 'to_csv' in script_code:
        if not re.search(r"(sep=[\'\"]\\t[\'\"]|sep='\t'|sep=\"\t\"|\.tsv|sep='\t')", script_code):
            return False, "拦截：表格输出必须明确指定 tab 分割的 tsv 格式！请添加 sep='\\t' 或输出为 .tsv 文件"

    # 3. 校验注释密度 (简单判断是否包含一定数量的注释)
    comment_count = script_code.count('#')
    docstring_count = script_code.count('"""') + script_code.count("'''")
    if comment_count < 3 and docstring_count < 1:
        return False, "拦截：代码缺乏详尽的程序说明注释！请添加至少3行注释或文档字符串"

    return True, ""


__all__ = ["validate_iron_rules"]