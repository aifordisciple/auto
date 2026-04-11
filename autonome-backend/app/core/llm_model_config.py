"""
LLM 模型特性配置

不同 LLM 模型可能有不同的输出特征，需要针对性的处理策略。
此模块定义了各种模型的特性配置，用于优化代码块格式修复和内容过滤。

支持的模型特性：
- CODE_BLOCK_NO_NEWLINE: 代码块标记后缺少换行符
- TOKEN_MERGE: 流式输出时 token 合并
- SPECIAL_THINKING_TAG: 特殊 thinking 标签格式
- INCONSISTENT_JSON_FORMAT: JSON 格式不一致
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from loguru import logger

log = logger.bind(name="llm_model_config")


class ModelOutputFeature(Enum):
    """模型输出特征枚举"""
    # 代码块标记后缺少换行符
    # 例如：```pythonprint('hello') 而非 ```python\nprint('hello')
    CODE_BLOCK_NO_NEWLINE = "code_block_no_newline"

    # 流式输出时 token 可能被错误合并
    # 例如：相邻 token 之间缺少空格
    TOKEN_MERGE = "token_merge"

    # 特殊 thinking 标签格式
    # 例如：DeepSeek 的韩文标签、Claude 的 <thinking> 标签
    SPECIAL_THINKING_TAG = "special_thinking_tag"

    # JSON 格式不一致
    # 例如：key 不带引号、使用单引号等
    INCONSISTENT_JSON_FORMAT = "inconsistent_json_format"

    # 可能输出不完整的代码块
    # 例如：代码块未正确闭合
    INCOMPLETE_CODE_BLOCK = "incomplete_code_block"


@dataclass
class ModelConfig:
    """模型配置数据类"""
    # 模型名称标识
    name: str

    # 模型输出特征列表
    features: List[ModelOutputFeature] = field(default_factory=list)

    # 预处理规则列表
    # 每个规则是一个字典，包含 pattern 和 replacement 键
    preprocess_rules: List[Dict[str, str]] = field(default_factory=list)

    # 后处理规则列表
    postprocess_rules: List[Dict[str, str]] = field(default_factory=list)

    # 模型描述
    description: str = ""


# ==========================================
# 模型配置字典
# ==========================================

MODEL_CONFIGS: Dict[str, ModelConfig] = {
    # GLM-5 智谱清言
    "glm-5": ModelConfig(
        name="glm-5",
        features=[
            ModelOutputFeature.CODE_BLOCK_NO_NEWLINE,
            ModelOutputFeature.INCONSISTENT_JSON_FORMAT,
        ],
        preprocess_rules=[
            # 修复代码块标记后缺少换行符
            {"pattern": r"```(python|json|r|R|json_strategy)\s*([a-zA-Z_])", "replacement": r"```\1\n\2"},
            # 修复 JSON key 使用单引号的情况
            {"pattern": r"'(\w+)':", "replacement": r'"\1":'},
        ],
        description="智谱清言 GLM-5，可能在代码块标记后缺少换行符",
    ),

    # GLM-4
    "glm-4": ModelConfig(
        name="glm-4",
        features=[
            ModelOutputFeature.CODE_BLOCK_NO_NEWLINE,
        ],
        preprocess_rules=[
            {"pattern": r"```(python|json|r|R|json_strategy)\s*([a-zA-Z_])", "replacement": r"```\1\n\2"},
        ],
        description="智谱清言 GLM-4，输出格式相对稳定",
    ),

    # MINIMAX
    "minimax": ModelConfig(
        name="minimax",
        features=[
            ModelOutputFeature.TOKEN_MERGE,
            ModelOutputFeature.CODE_BLOCK_NO_NEWLINE,
        ],
        preprocess_rules=[
            # 修复代码块标记后缺少换行符（更宽松的匹配）
            {"pattern": r"```(\w+)([^\s\n`])", "replacement": r"```\1\n\2"},
        ],
        description="MINIMAX 模型，流式输出时可能出现 token 合并问题",
    ),

    # QWEN 通义千问
    "qwen": ModelConfig(
        name="qwen",
        features=[],
        preprocess_rules=[
            # QWEN 有时会在代码块标记和类型之间添加多余空格
            {"pattern": r"```\s+(python|json|r|R|json_strategy)", "replacement": r"```\1"},
        ],
        description="阿里通义千问，输出格式较为规范",
    ),

    # QWEN2.5
    "qwen2.5": ModelConfig(
        name="qwen2.5",
        features=[],
        preprocess_rules=[
            {"pattern": r"```\s+(python|json|r|R|json_strategy)", "replacement": r"```\1"},
        ],
        description="QWEN2.5 系列",
    ),

    # QWEN3
    "qwen3": ModelConfig(
        name="qwen3",
        features=[],
        preprocess_rules=[
            {"pattern": r"```\s+(python|json|r|R|json_strategy)", "replacement": r"```\1"},
        ],
        description="QWEN3 系列",
    ),

    # DeepSeek
    "deepseek": ModelConfig(
        name="deepseek",
        features=[
            ModelOutputFeature.SPECIAL_THINKING_TAG,
            ModelOutputFeature.TOKEN_MERGE,
        ],
        preprocess_rules=[
            # DeepSeek R1 使用韩文 thinking 标签，已在 content_filter.py 中处理
        ],
        description="DeepSeek 模型，使用韩文 thinking 标签",
    ),

    # DeepSeek R1
    "deepseek-r1": ModelConfig(
        name="deepseek-r1",
        features=[
            ModelOutputFeature.SPECIAL_THINKING_TAG,
            ModelOutputFeature.TOKEN_MERGE,
        ],
        preprocess_rules=[],
        description="DeepSeek R1 推理模型",
    ),

    # Claude
    "claude": ModelConfig(
        name="claude",
        features=[
            ModelOutputFeature.SPECIAL_THINKING_TAG,
        ],
        preprocess_rules=[
            # Claude 使用 <thinking> 标签，已在 content_filter.py 中处理
        ],
        description="Anthropic Claude，使用 <thinking> 扩展思考标签",
    ),

    # GPT-4
    "gpt-4": ModelConfig(
        name="gpt-4",
        features=[],
        preprocess_rules=[],
        description="OpenAI GPT-4，输出格式规范",
    ),

    # GPT-3.5
    "gpt-3.5": ModelConfig(
        name="gpt-3.5",
        features=[],
        preprocess_rules=[],
        description="OpenAI GPT-3.5，输出格式规范",
    ),
}


def get_model_config(model_name: str) -> Optional[ModelConfig]:
    """
    根据模型名称获取配置

    支持精确匹配和模糊匹配：
    - 精确匹配：model_name 完全匹配配置中的 key
    - 模糊匹配：model_name 包含配置中的 key（不区分大小写）

    Args:
        model_name: 模型名称，如 "glm-5", "gpt-4", "qwen3.5-plus" 等

    Returns:
        匹配的模型配置，如果没有匹配则返回 None
    """
    if not model_name:
        return None

    model_lower = model_name.lower()

    # 1. 精确匹配
    if model_lower in MODEL_CONFIGS:
        return MODEL_CONFIGS[model_lower]

    # 2. 模糊匹配
    for key, config in MODEL_CONFIGS.items():
        if key in model_lower:
            log.debug(f"模型 '{model_name}' 模糊匹配到配置 '{key}'")
            return config

    # 3. 没有匹配
    log.debug(f"模型 '{model_name}' 没有匹配的配置，使用默认处理")
    return None


def apply_model_rules(
    content: str,
    model_name: str,
    phase: str = "pre"
) -> str:
    """
    应用模型特定的预处理或后处理规则

    Args:
        content: 原始内容字符串
        model_name: 模型名称
        phase: 处理阶段，"pre" 表示预处理，"post" 表示后处理

    Returns:
        处理后的内容字符串
    """
    if not content or not model_name:
        return content

    config = get_model_config(model_name)
    if not config:
        return content

    # 选择对应的规则列表
    rules = config.preprocess_rules if phase == "pre" else config.postprocess_rules

    # 应用规则
    for rule in rules:
        try:
            pattern = rule.get("pattern", "")
            replacement = rule.get("replacement", "")
            if pattern:
                content = re.sub(pattern, replacement, content)
        except Exception as e:
            log.warning(f"应用模型规则失败: {e}")

    return content


def has_feature(model_name: str, feature: ModelOutputFeature) -> bool:
    """
    检查模型是否具有特定特征

    Args:
        model_name: 模型名称
        feature: 要检查的特征

    Returns:
        如果模型具有该特征返回 True，否则返回 False
    """
    config = get_model_config(model_name)
    if not config:
        return False
    return feature in config.features


def get_model_features(model_name: str) -> List[ModelOutputFeature]:
    """
    获取模型的所有特征

    Args:
        model_name: 模型名称

    Returns:
        模型特征列表
    """
    config = get_model_config(model_name)
    if not config:
        return []
    return config.features