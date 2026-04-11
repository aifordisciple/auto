"""
结果提取器

从 Claude Code 等工具的输出中提取 [AUTONOME_RESULT_START] ... [AUTONOME_RESULT_END]
包裹的 JSON 结果。
"""

import re
import json
from typing import Optional, Dict, Any


class ResultExtractor:
    """
    从 Claude Code 输出中提取 JSON 结果

    输出格式：
    [AUTONOME_RESULT_START]
    { "key": "value", ... }
    [AUTONOME_RESULT_END]
    """

    # 主结果提取模式
    RESULT_PATTERN = re.compile(
        r'\[AUTONOME_RESULT_START\]\s*([\s\S]*?)\s*\[AUTONOME_RESULT_END\]',
        re.MULTILINE
    )

    # 备选结果提取模式（单行版本）
    RESULT_PATTERN_SINGLE_LINE = re.compile(
        r'\[AUTONOME_RESULT_START\]\s*(\{[\s\S]*?\})\s*\[AUTONOME_RESULT_END\]',
        re.MULTILINE
    )

    @classmethod
    def extract(cls, output: str) -> Optional[Dict[str, Any]]:
        """
        从输出中提取 JSON 结果

        Args:
            output: Claude Code 等工具的完整输出

        Returns:
            解析后的 JSON 字典，如果提取失败则返回 None
        """
        if not output:
            return None

        # 尝试主模式（多行）
        match = cls.RESULT_PATTERN.search(output)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                # JSON 解析失败，尝试修复
                return cls._try_fix_and_parse(json_str)

        # 尝试备选模式（单行）
        match = cls.RESULT_PATTERN_SINGLE_LINE.search(output)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return cls._try_fix_and_parse(json_str)

        return None

    @classmethod
    def _try_fix_and_parse(cls, json_str: str) -> Optional[Dict[str, Any]]:
        """
        尝试修复损坏的 JSON 并解析

        Args:
            json_str: JSON 字符串

        Returns:
            解析后的字典，如果修复失败则返回 None
        """
        # 移除尾部的逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 移除单行注释
        json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)

        # 移除多行注释
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    @classmethod
    def extract_multiple(cls, output: str) -> list[Dict[str, Any]]:
        """
        从输出中提取多个 JSON 结果

        Args:
            output: Claude Code 等工具的完整输出

        Returns:
            解析后的 JSON 字典列表
        """
        results = []
        for match in cls.RESULT_PATTERN.finditer(output):
            json_str = match.group(1).strip()
            try:
                results.append(json.loads(json_str))
            except json.JSONDecodeError:
                fixed = cls._try_fix_and_parse(json_str)
                if fixed:
                    results.append(fixed)
        return results

    @classmethod
    def has_result(cls, output: str) -> bool:
        """
        检查输出中是否包含结果块

        Args:
            output: Claude Code 等工具的完整输出

        Returns:
            True 如果包含结果块
        """
        return cls.RESULT_PATTERN.search(output) is not None


def extract_result(output: str) -> Optional[Dict[str, Any]]:
    """
    便捷函数：从 Claude Code 输出中提取 JSON 结果

    Args:
        output: Claude Code 等工具的完整输出

    Returns:
        解析后的 JSON 字典，如果提取失败则返回 None
    """
    return ResultExtractor.extract(output)


def has_result(output: str) -> bool:
    """
    便捷函数：检查输出中是否包含结果块

    Args:
        output: Claude Code 等工具的完整输出

    Returns:
        True 如果包含结果块
    """
    return ResultExtractor.has_result(output)
