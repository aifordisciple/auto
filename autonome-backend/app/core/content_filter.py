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
    re.compile(r"<think>.*?</think>|<think[^>]*>.*?</think[^>]*>", re.DOTALL | re.IGNORECASE),
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

# 系统标签过滤模式 - 已移除 Agent 相关标签
ALL_SYSTEM_TAG_PATTERNS = []

# 支持的代码块类型列表（可扩展）
# 用于修复不同 LLM 模型输出中代码块格式问题
SUPPORTED_CODE_BLOCK_TYPES = [
    # 编程语言
    "python", "Python", "py",
    "r", "R",
    "bash", "shell", "sh", "zsh",
    "javascript", "js", "typescript", "ts",
    "java", "c", "cpp", "go", "rust",
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
# V2: 流式感知过滤 — 跨 chunk 有状态过滤
# ==========================================

class StreamContentFilter:
    """
    流式内容过滤器（有状态，支持思考内容透传）

    解决问题：流式传输时，思考标签（如<think>、<thinking>）可能被分割到
    多个 SSE chunk 中，导致逐块过滤遗漏或内容泄漏。

    核心设计：有状态的思考标签检测
    - 一旦检测到思考标签开始，进入“思考模式”
    - 思考模式下，所有内容被缓冲不输出
    - 检测到思考标签结束，退出思考模式
    - 思考模式外的内容正常输出
    """

    # 思考标签的开始和结束标记
    THINKING_START_MARKERS = ["<think>", "<think ", "<thinking>", "<thinking "]
    THINKING_END_MARKERS = ["</think>", "</thinking>"]

    def __init__(self, model_name: str = None):
        self.model_name = model_name
        self._in_thinking = False
        self._buffer = ""
        # ✨ 思考内容缓冲：思考期间的内容不再丢弃，而是透传给前端
        self._thinking_buffer = ""

    def filter_chunk(self, chunk: str) -> tuple:
        """
        过滤一个 SSE chunk，返回 (content, content_type) 元组

        content_type:
          - "text": 正常回复内容
          - "thinking": 思考过程内容
          - "": 无内容（应跳过）

        ✨ 思考内容不再被丢弃，而是以 "thinking" 类型透传给前端，
        前端可以在可折叠的思考框中展示。
        """
        if not chunk:
            return ("", "")

        self._buffer += chunk
        output = ""
        thinking_output = ""

        while self._buffer:
            if self._in_thinking:
                end_pos, trim_from_thinking = self._find_end_marker()
                if end_pos is not None:
                    # ✨ 思考标签结束：将缓冲的思考内容输出
                    # 跨 buffer 匹配时，从 _thinking_buffer 尾部截掉 end marker 的前半部分
                    if trim_from_thinking > 0:
                        thinking_output += self._thinking_buffer[:-trim_from_thinking]
                    else:
                        thinking_output += self._thinking_buffer
                    self._thinking_buffer = ""
                    self._buffer = self._buffer[end_pos:]
                    self._in_thinking = False
                else:
                    # ✨ 思考标签未结束：将新内容加入思考缓冲
                    thinking_output += self._thinking_buffer
                    self._thinking_buffer = ""
                    # 当前 buffer 全部是思考内容
                    self._thinking_buffer = self._buffer
                    self._buffer = ""
                    break
            else:
                start_pos, marker_len = self._find_start_marker()
                if start_pos is not None:
                    if start_pos > 0:
                        output += self._buffer[:start_pos]
                    # ✨ 进入思考模式：跳过开始标记，后续内容进入思考缓冲
                    self._buffer = self._buffer[start_pos + marker_len:]
                    self._in_thinking = True
                else:
                    safe_end = len(self._buffer)
                    for marker in self.THINKING_START_MARKERS:
                        for i in range(1, len(marker)):
                            if self._buffer.endswith(marker[:i]):
                                safe_end = min(safe_end, len(self._buffer) - i)

                    if safe_end > 0:
                        output += self._buffer[:safe_end]
                        self._buffer = self._buffer[safe_end:]
                    else:
                        break

        if output:
            output = fix_code_block_format(output, model_name=self.model_name)

        # ✨ 优先返回思考内容（如果有），否则返回正常内容
        # 这样前端可以区分思考过程和正式回复
        if thinking_output:
            return (thinking_output, "thinking")
        return (output, "text")

    def _find_start_marker(self) -> tuple:
        earliest_pos = None
        earliest_len = None
        for marker in self.THINKING_START_MARKERS:
            pos = self._buffer.find(marker)
            if pos != -1:
                if earliest_pos is None or pos < earliest_pos:
                    earliest_pos = pos
                    earliest_len = len(marker)
        return (earliest_pos, earliest_len)

    def _find_end_marker(self):
        """
        查找思考结束标记，支持跨 _thinking_buffer 和 _buffer 的拆分匹配。

        当 end marker 被 SSE chunk 边界拆分时，前半部分在 _thinking_buffer 尾部，
        后半部分在 _buffer 头部。必须拼接后才能匹配。

        Returns:
            (end_pos, trim_from_thinking) 元组:
            - end_pos: end marker 在 _buffer 中的结束位置（None 表示未找到）
            - trim_from_thinking: 需要从 _thinking_buffer 尾部截掉的字符数
              （跨 buffer 匹配时 > 0，普通匹配时 = 0）
        """
        earliest_end = None
        earliest_trim = 0
        for marker in self.THINKING_END_MARKERS:
            # 1. 在 _buffer 中直接查找完整 marker
            pos = self._buffer.find(marker)
            if pos != -1:
                end = pos + len(marker)
                if earliest_end is None or end < earliest_end:
                    earliest_end = end
                    earliest_trim = 0
                continue

            # 2. 跨 buffer 拆分查找：marker 前半在 _thinking_buffer 尾部，后半在 _buffer 头部
            for split_point in range(1, len(marker)):
                prefix = marker[:split_point]
                suffix = marker[split_point:]
                if self._thinking_buffer.endswith(prefix) and self._buffer.startswith(suffix):
                    end = len(suffix)
                    if earliest_end is None or end < earliest_end:
                        earliest_end = end
                        earliest_trim = split_point  # 从 thinking_buffer 尾部截掉 marker 前半
                    break

        return (earliest_end, earliest_trim)

    def flush(self) -> tuple:
        """刷新缓冲区，返回剩余内容"""
        if self._in_thinking:
            # ✨ 返回剩余的思考内容
            thinking = self._thinking_buffer
            self._thinking_buffer = ""
            self._buffer = ""
            self._in_thinking = False
            return (thinking, "thinking") if thinking else ("", "")

        output = self._buffer
        self._buffer = ""

        if output:
            output = fix_code_block_format(output, model_name=self.model_name)

        return (output, "text") if output else ("", "")

    def reset(self) -> None:
        self._buffer = ""
        self._thinking_buffer = ""
        self._in_thinking = False


def filter_stream_chunk(
    chunk: str,
    model_name: str = None,
    _filter_state: dict = None
) -> str:
    if not chunk:
        return chunk

    result = chunk

    if not any(marker in result for marker in [
        "json_intent", "[AUTONOME_RESULT_START]", "[AUTONOME_RESULT_END]",
        "<think", "<thinking>", "<parameter", "|begin_thought|"
    ]):
        return result

    for pattern in ALL_SYSTEM_TAG_PATTERNS:
        result = pattern.sub("", result)

    for pattern in THINKING_TAG_PATTERNS:
        result = pattern.sub("", result)

    for pattern in PARAMETER_TAG_PATTERNS:
        result = pattern.sub("", result)

    return result
