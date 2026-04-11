"""
ANSI 转义序列清洗工具

用于清洗 Claude Code 等 CLI 工具输出的 ANSI 转义序列，
确保输出可以被正确解析。
"""

import re
from typing import Optional


class ANSICleaner:
    """
    ANSI 转义序列清洗器

    支持的 ANSI 序列类型：
    - CSI (Control Sequence Introducer): ESC[...A-Z
    - OSC (Operating System Command): ESC]...BEL/ST
    - DCS (Device Control String): ESC P...ESC\\
    - SOS (Start of String): ESC X...ESC\\
    - PM (Privacy Message): ESC ^...BEL
    """

    # CSI 序列模式: ESC [ ... (0-9;)* A-Za-z
    CSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

    # 扩展 dsr 模式: ESC [ > (0-9;)* (特指某些终端的扩展)
    ESCAPE_EXTENDED_PATTERN = re.compile(r'\x1b[>=]')

    # OSC 序列模式: ESC ] ... BEL 或 ESC ] ... ST
    OSC_PATTERN = re.compile(r'\x1b\][^\x07]*(?:\x07|\x1b\\)')
    # 简化版 OSC 模式（匹配到 BEL 或字符串结束）
    OSC_SIMPLE_PATTERN = re.compile(r'\x1b\][^\x07]*\x07')

    # DCS 序列模式: ESC P ... ESC \\
    DCS_PATTERN = re.compile(r'\x1bP[\s\S]*?(?:\x1b\\|\x9c)')

    # 控制字符（需要移除的）
    CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

    # 完整的 ANSI 清洗模式（按顺序执行）
    PATTERNS = [
        (CSI_PATTERN, ''),           # CSI 序列
        (OSC_SIMPLE_PATTERN, ''),     # OSC 序列
        (DCS_PATTERN, ''),           # DCS 序列
        (CONTROL_CHARS_PATTERN, ''), # 控制字符
    ]

    @classmethod
    def clean(cls, text: str) -> str:
        """
        清洗文本中的所有 ANSI 转义序列

        Args:
            text: 包含 ANSI 转义序列的文本

        Returns:
            清洗后的文本
        """
        if not text:
            return text

        result = text

        # 按顺序应用所有清洗模式
        for pattern, replacement in cls.PATTERNS:
            result = pattern.sub(replacement, result)

        return result

    @classmethod
    def clean_lines(cls, text: str) -> list[str]:
        """
        清洗文本并按行分割

        Args:
            text: 包含 ANSI 转义序列的文本

        Returns:
            清洗后的行列表
        """
        cleaned = cls.clean(text)
        return [line for line in cleaned.split('\n') if line.strip()]

    @classmethod
    def strip_escape_codes(cls, text: str) -> str:
        """
        移除所有转义序列的简写方法

        Args:
            text: 包含转义序列的文本

        Returns:
            清洗后的文本
        """
        return cls.clean(text)


def clean_ansi(text: str) -> str:
    """
    便捷函数：清洗 ANSI 转义序列

    Args:
        text: 包含 ANSI 转义序列的文本

    Returns:
        清洗后的文本
    """
    return ANSICleaner.clean(text)


def strip_ansi(text: str) -> str:
    """
    便捷函数：移除 ANSI 转义序列（与 clean_ansi 相同）

    Args:
        text: 包含 ANSI 转义序列的文本

    Returns:
        清洗后的文本
    """
    return ANSICleaner.clean(text)
