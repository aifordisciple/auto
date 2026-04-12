# -*- coding: utf-8 -*-
"""
LLM 输出内容过滤器

过滤 thinking 标签等非必要内容。
"""

import re
from app.core.logger import log


# 编译正则模式（性能优化）
THINKING_TAG_PATTERNS = [
    # DeepSeek R1 韩文格式
    re.compile(r"심풀.*?심풀", re.DOTALL),
    # DeepSeek R1 变体: <think>...</think>
    re.compile(r"<think>.*?</think>|《.*?》|<think[^>]*>.*?</think[^>]*>", re.DOTALL | re.IGNORECASE),
    # Claude extended thinking
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE),
    # 其他模型变体
    re.compile(r"\|begin_thought\|.*?\|end_thought\|", re.DOTALL),
]

# Parameter 标签过滤模式
# 某些 LLM 可能输出 <parameter name="...">...</parameter> 格式的标签
PARAMETER_TAG_PATTERNS = [
    re.compile(r"<parameter[^>]*>.*?</parameter>", re.DOTALL | re.IGNORECASE),
]

# 系统标签过滤模式 - 防止内部结构化输出泄漏到前端
# json_intent 是纯内部路由信号，绝不应暴露给用户
# json_strategy / json_blueprint / json_interactive_plot 由前端解析，不过滤
SYSTEM_INTENT_TAG_PATTERNS = [
    re.compile(r"```json_intent\s*.*?```", re.DOTALL),
]

# V2: 沙箱结构化输出锚点标记过滤
# [AUTONOME_RESULT_START] ... [AUTONOME_RESULT_END] 是沙箱规划器的内部输出，
# 绝不应暴露给用户
SANDBOX_RESULT_TAG_PATTERNS = [
    re.compile(r"\[AUTONOME_RESULT_START\][\s\S]*?\[AUTONOME_RESULT_END\]", re.DOTALL),
    # 也过滤单独出现的标记（可能跨 chunk 被分割）
    re.compile(r"\[AUTONOME_RESULT_START\]", re.DOTALL),
    re.compile(r"\[AUTONOME_RESULT_END\]", re.DOTALL),
]

# V2: 所有需要过滤的系统标签模式（合并）
ALL_SYSTEM_TAG_PATTERNS = SYSTEM_INTENT_TAG_PATTERNS + SANDBOX_RESULT_TAG_PATTERNS

# 支持的代码块类型列表（可扩展）
# 用于修复不同 LLM 模型输出中代码块格式问题
SUPPORTED_CODE_BLOCK_TYPES = [
    # 编程语言
    "python", "Python", "py",
    "r", "R",
    "bash", "shell", "sh", "zsh",
    "javascript", "js", "typescript", "ts",
    "java", "c", "cpp", "go", "rust",
    # 自定义类型（策略卡片相关）
    "json_strategy", "json_intent", "json_blueprint",
    # 数据格式
    "json", "yaml", "xml", "html", "css",
    # 文档格式
    "markdown", "md",
]


def _preprocess_for_model(content: str, model_name: str = None) -> str:
    """
    模型特定预处理

    不同 LLM 模型可能有不同的输出特征，需要针对性的处理策略。
    使用 llm_model_config 模块中的配置进行预处理。

    Args:
        content: 原始内容字符串
        model_name: 模型名称（如 "glm-5", "minimax", "qwen"）

    Returns:
        预处理后的内容字符串
    """
    if not model_name or not content:
        return content

    # 使用 llm_model_config 模块中的配置进行预处理
    try:
        from app.core.llm_model_config import apply_model_rules
        content = apply_model_rules(content, model_name, phase="pre")
    except ImportError:
        # 如果模块不可用，使用内置的简单规则
        log.debug("llm_model_config 模块不可用，使用内置规则")
        content = _apply_builtin_model_rules(content, model_name)

    return content


def _apply_builtin_model_rules(content: str, model_name: str) -> str:
    """
    内置模型规则（备用）

    当 llm_model_config 模块不可用时使用。
    """
    model_lower = model_name.lower()

    # GLM-5 特殊处理：可能在代码块标记后缺少换行
    if "glm" in model_lower:
        content = re.sub(
            r'```(python|Python|r|R|json_strategy|json|json_intent|json_blueprint)\s*([a-zA-Z_])',
            r'```\1\n\2',
            content
        )

    # MINIMAX 特殊处理：流式输出时可能合并 token
    elif "minimax" in model_lower:
        content = re.sub(
            r'```(\w+)([^\s\n`])',
            r'```\1\n\2',
            content
        )

    # QWEN 特殊处理：可能有特殊的格式化行为
    elif "qwen" in model_lower:
        content = re.sub(
            r'```\s+(python|Python|r|R|json_strategy|json)',
            r'```\1',
            content
        )

    return content


def _fix_code_block_start_markers(content: str) -> str:
    """
    修复代码块开始标记

    处理代码块标记后缺少换行符的情况。

    Args:
        content: 原始内容字符串

    Returns:
        修复后的内容字符串
    """
    if not content:
        return content

    # 构建动态正则表达式
    block_types = "|".join(re.escape(t) for t in SUPPORTED_CODE_BLOCK_TYPES)

    # 修复：```pythonprint... -> ```python\nprint...
    content = re.sub(
        rf'```({block_types})([^\n\s`])',
        r'```\1\n\2',
        content
    )

    # 修复：``` python -> ```python (移除标记和类型之间的空格)
    content = re.sub(
        rf'```\s+({block_types})',
        r'```\1',
        content
    )

    return content


def _fix_code_block_end_markers(content: str) -> str:
    """
    修复代码块结束标记

    处理代码块结束标记后紧跟非换行符的情况。

    Args:
        content: 原始内容字符串

    Returns:
        修复后的内容字符串
    """
    if not content:
        return content

    # 修复：```**图表特点** -> ```\n**图表特点**
    # 修复：```# 标题 -> ```\n# 标题
    # 注意：只处理紧跟 markdown 格式符号的情况，避免误修复
    content = re.sub(
        r'```(\*\*|#{|`)',
        r'```\n\1',
        content
    )

    return content


def _fix_adjacent_code_blocks(content: str) -> str:
    """
    修复相邻代码块粘连

    处理两个代码块之间缺少换行符的情况。

    Args:
        content: 原始内容字符串

    Returns:
        修复后的内容字符串
    """
    if not content:
        return content

    # 构建动态正则表达式
    block_types = "|".join(re.escape(t) for t in SUPPORTED_CODE_BLOCK_TYPES)

    # 修复：``````json_strategy -> ```\n\n```json_strategy
    # 两个代码块之间应该有空行分隔
    content = re.sub(
        rf'```\s*```({block_types})',
        r'```\n\n```\1',
        content
    )

    return content


def fix_code_block_format(content: str, model_name: str = None) -> str:
    """
    修复 LLM 流式输出中代码块格式问题（增强版）

    某些 LLM API（如 DeepSeek、GLM-5、MINIMAX）在流式输出时 token 可能被错误合并，
    导致代码块标记和内容之间缺少换行符。

    支持的特性：
    1. 多种代码块类型（python, r, json_strategy 等）
    2. 不同 LLM 模型的特殊处理
    3. 更健壮的边界条件处理

    例如：
    - "```rsuppress..." -> "```r\nsuppress..."
    - "``````json_strategy" -> "```\n\n```json_strategy"
    - GLM-5: "```pythonprint..." -> "```python\nprint..."

    Args:
        content: 原始内容字符串
        model_name: 模型名称（可选），用于模型特定处理

    Returns:
        修复格式后的内容字符串
    """
    if not content:
        return content

    # 1. 模型特定预处理
    content = _preprocess_for_model(content, model_name)

    # 2. 通用代码块格式修复
    content = _fix_code_block_start_markers(content)
    content = _fix_code_block_end_markers(content)
    content = _fix_adjacent_code_blocks(content)

    return content


def filter_thinking_content(content: str, debug: bool = False, model_name: str = None, is_streaming: bool = False) -> str:
    """
    过滤 LLM 输出中的 thinking 标签和修复代码块格式

    Args:
        content: 原始内容字符串
        debug: 是否开启调试模式（保留 thinking 内容，仅标记）
        model_name: 模型名称（可选），用于模型特定的代码块格式修复
        is_streaming: 是否为流式处理模式（流式模式下不执行 strip，避免丢失纯换行符 token）

    Returns:
        过滤和修复后的内容字符串
    """
    if not content:
        return content

    original_len = len(content)

    if debug:
        def mark_thinking(match):
            return f"\n[DEBUG-THINKING]: {match.group(0)[:50]}...[/DEBUG-THINKING]\n"
        for pattern in THINKING_TAG_PATTERNS:
            content = pattern.sub(mark_thinking, content)
        # Parameter 标签也标记
        for pattern in PARAMETER_TAG_PATTERNS:
            content = pattern.sub(mark_thinking, content)
        # 系统意图标签也标记
        for pattern in ALL_SYSTEM_TAG_PATTERNS:
            content = pattern.sub(mark_thinking, content)
    else:
        for pattern in THINKING_TAG_PATTERNS:
            content = pattern.sub("", content)
        # 过滤 parameter 标签
        for pattern in PARAMETER_TAG_PATTERNS:
            content = pattern.sub("", content)
        # 过滤 json_intent 系统标签（防止内部路由信号泄漏到前端）
        for pattern in SYSTEM_INTENT_TAG_PATTERNS:
            content = pattern.sub("", content)
        # V2: 过滤沙箱结构化输出锚点标记（防止 [AUTONOME_RESULT_START/END] 泄漏）
        for pattern in SANDBOX_RESULT_TAG_PATTERNS:
            content = pattern.sub("", content)

    # 🔧 修复代码块格式问题（某些 LLM 流式输出时换行符丢失）
    # 传递模型名称以支持模型特定的格式修复
    content = fix_code_block_format(content, model_name=model_name)

    content = re.sub(r"\n{3,}", "\n\n", content)

    # 🔧 关键修复：流式模式下不执行 strip，避免丢失纯换行符 token
    # 流式输出时，每个 token 单独处理，如果 token 只有换行符，strip 会返回空字符串
    if not is_streaming:
        content = content.strip()

    filtered_len = len(content)
    if original_len != filtered_len:
        log.debug(f"过滤 thinking/parameter 内容: 原长度 {original_len} -> 过滤后 {filtered_len}")

    return content


def preprocess_llm_response(content: str, model_name: str = None) -> str:
    """
    预处理 LLM 响应内容，用于代码块/JSON 提取前

    此函数应在任何解析操作（如提取代码块、JSON、策略卡片）之前调用，
    确保 thinking 内容不会干扰解析逻辑。

    Args:
        content: 原始 LLM 响应内容
        model_name: 模型名称（可选），用于模型特定的处理

    Returns:
        预处理后的内容（已过滤 thinking 标签，已修复代码块格式）
    """
    return filter_thinking_content(content, model_name=model_name)


def is_thinking_only_response(content: str, model_name: str = None) -> bool:
    """
    检查响应是否仅包含 thinking 内容

    Args:
        content: 原始内容字符串
        model_name: 模型名称（可选）

    Returns:
        如果内容过滤后为空，返回 true
    """
    if not content or not content.strip():
        return True
    filtered = filter_thinking_content(content, model_name=model_name)
    return not filtered or not filtered.strip()


# ==========================================
# V2: 流式感知过滤 — 跨 chunk 有状态过滤
# ==========================================

class StreamContentFilter:
    """
    流式内容过滤器（有状态）

    解决问题：流式传输时，系统标签（如 [AUTONOME_RESULT_START]）可能被分割到
    两个 SSE chunk 中，导致逐块过滤遗漏。

    工作原理：
    1. 维护一个滑动窗口缓冲区，保留最近 N 个字符
    2. 每个 chunk 先追加到缓冲区
    3. 在缓冲区上执行所有过滤模式
    4. 返回过滤后的新增内容
    5. 缓冲区只保留最后 N 个字符（防止内存增长）
    """

    # 滑动窗口大小（足够覆盖最长的系统标签模式）
    WINDOW_SIZE = 200

    def __init__(self, model_name: str = None):
        self.model_name = model_name
        self._buffer = ""
        self._filtered_offset = 0  # 已过滤内容的偏移量

    def filter_chunk(self, chunk: str) -> str:
        """
        过滤一个流式 chunk

        Args:
            chunk: 新的流式内容块

        Returns:
            过滤后的内容（可能为空字符串）
        """
        if not chunk:
            return chunk

        # 追加到缓冲区
        self._buffer += chunk

        # 在缓冲区上执行所有过滤
        filtered = self._buffer

        # 过滤 thinking 标签
        for pattern in THINKING_TAG_PATTERNS:
            filtered = pattern.sub("", filtered)

        # 过滤 parameter 标签
        for pattern in PARAMETER_TAG_PATTERNS:
            filtered = pattern.sub("", filtered)

        # 过滤所有系统标签
        for pattern in ALL_SYSTEM_TAG_PATTERNS:
            filtered = pattern.sub("", filtered)

        # 修复代码块格式
        filtered = fix_code_block_format(filtered, model_name=self.model_name)

        # 计算新增的过滤后内容
        new_filtered = filtered[self._filtered_offset:]
        self._filtered_offset = len(filtered)

        # 维护滑动窗口：只保留最后 WINDOW_SIZE 个字符
        if len(self._buffer) > self.WINDOW_SIZE * 2:
            excess = len(self._buffer) - self.WINDOW_SIZE
            self._buffer = self._buffer[excess:]
            self._filtered_offset = max(0, self._filtered_offset - excess)

        return new_filtered

    def flush(self) -> str:
        """
        刷新缓冲区，返回剩余内容

        在流式传输结束时调用，确保所有内容都被处理。

        Returns:
            缓冲区中剩余的过滤后内容
        """
        if not self._buffer:
            return ""

        # 最终过滤
        filtered = filter_thinking_content(
            self._buffer,
            model_name=self.model_name,
            is_streaming=True
        )

        new_filtered = filtered[self._filtered_offset:]

        # 重置状态
        self._buffer = ""
        self._filtered_offset = 0

        return new_filtered

    def reset(self) -> None:
        """重置过滤器状态"""
        self._buffer = ""
        self._filtered_offset = 0


def filter_stream_chunk(
    chunk: str,
    model_name: str = None,
    _filter_state: dict = None
) -> str:
    """
    便捷函数：过滤流式 chunk（无状态版本，适用于简单场景）

    对于跨 chunk 边界的标签，此函数可能遗漏。
    如需完整的有状态过滤，请使用 StreamContentFilter 类。

    Args:
        chunk: 流式内容块
        model_name: 模型名称
        _filter_state: 可选的状态字典（用于跨调用保持状态）

    Returns:
        过滤后的内容
    """
    if not chunk:
        return chunk

    result = chunk

    # 快速检查：如果 chunk 中不包含任何特殊标签，直接返回
    if not any(marker in result for marker in [
        "json_intent", "[AUTONOME_RESULT_START]", "[AUTONOME_RESULT_END]",
        "<think", "<thinking>", "<parameter", "심풀", "|begin_thought|"
    ]):
        return result

    # 执行过滤
    for pattern in ALL_SYSTEM_TAG_PATTERNS:
        result = pattern.sub("", result)

    for pattern in THINKING_TAG_PATTERNS:
        result = pattern.sub("", result)

    for pattern in PARAMETER_TAG_PATTERNS:
        result = pattern.sub("", result)

    return result