"""
LLM Token 预算控制器

功能：
1. 输入 token 计数和预算检查
2. 动态调整输出 token 限制
3. 预算超限告警和降级策略

使用场景：
- Agent 对话：控制上下文窗口，防止超限
- 技能锻造：限制代码输出长度
- 批量任务：防止单任务占用过多 token

@created: 2026-04-08
@author: Performance Optimization Team
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class BudgetLevel(Enum):
    """预算级别"""
    UNLIMITED = "unlimited"      # 无限制（管理员使用）
    HIGH = "high"               # 高预算（复杂任务）
    NORMAL = "normal"           # 正常预算（标准对话）
    LOW = "low"                 # 低预算（简单查询）
    CRITICAL = "critical"       # 临界预算（紧急降级）


@dataclass
class TokenBudget:
    """Token 预算配置"""
    # 总预算（输入 + 输出）
    total_budget: int = 128000

    # 输出 token 限制
    max_output_tokens: int = 8192

    # 输入 token 警戒线（超过则警告）
    input_warning_threshold: float = 0.7  # 70%

    # 输入 token 临界线（超过则强制降级）
    input_critical_threshold: float = 0.9  # 90%

    # 预算级别
    level: BudgetLevel = BudgetLevel.NORMAL


# ==========================================
# 预设预算配置
# ==========================================

BUDGET_PRESETS: Dict[BudgetLevel, TokenBudget] = {
    BudgetLevel.UNLIMITED: TokenBudget(
        total_budget=200000,
        max_output_tokens=32000,
        level=BudgetLevel.UNLIMITED
    ),
    BudgetLevel.HIGH: TokenBudget(
        total_budget=128000,
        max_output_tokens=16384,
        level=BudgetLevel.HIGH
    ),
    BudgetLevel.NORMAL: TokenBudget(
        total_budget=64000,
        max_output_tokens=8192,
        level=BudgetLevel.NORMAL
    ),
    BudgetLevel.LOW: TokenBudget(
        total_budget=32000,
        max_output_tokens=4096,
        level=BudgetLevel.LOW
    ),
    BudgetLevel.CRITICAL: TokenBudget(
        total_budget=16000,
        max_output_tokens=2048,
        level=BudgetLevel.CRITICAL
    ),
}


class TokenBudgetController:
    """
    Token 预算控制器

    功能：
    1. 估算文本 token 数量（使用 tiktoken 或启发式方法）
    2. 检查输入是否超出预算
    3. 动态计算可用的输出 token
    4. 提供降级策略建议
    """

    # 默认编码器（GPT-4/claude 兼容）
    DEFAULT_CHARS_PER_TOKEN = 4  # 英文约 4 字符/token，中文约 2 字符/token

    def __init__(self, budget: TokenBudget = None):
        """
        初始化预算控制器

        Args:
            budget: 预算配置，默认使用 NORMAL 级别
        """
        self.budget = budget or BUDGET_PRESETS[BudgetLevel.NORMAL]
        self._tiktoken_encoder = None

    def _get_encoder(self):
        """
        获取 tiktoken 编码器（延迟加载）

        Returns:
            tiktoken 编码器，如果不可用则返回 None
        """
        if self._tiktoken_encoder is not None:
            return self._tiktoken_encoder

        try:
            import tiktoken
            self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            return self._tiktoken_encoder
        except ImportError:
            logger.warning("[TokenBudget] tiktoken 未安装，使用启发式估算")
            return None
        except Exception as e:
            logger.warning(f"[TokenBudget] tiktoken 初始化失败: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量

        Args:
            text: 输入文本

        Returns:
            token 数量
        """
        if not text:
            return 0

        encoder = self._get_encoder()
        if encoder:
            try:
                return len(encoder.encode(text))
            except Exception as e:
                logger.debug(f"[TokenBudget] tiktoken 编码失败: {e}")

        # 启发式估算：中英文混合
        # 英文约 4 字符/token，中文约 2 字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars

        estimated_tokens = (
            chinese_chars // 2 +
            other_chars // self.DEFAULT_CHARS_PER_TOKEN +
            10  # 误差缓冲
        )

        return max(1, estimated_tokens)

    def check_budget(self, input_text: str) -> Dict[str, Any]:
        """
        检查输入是否超出预算

        Args:
            input_text: 输入文本（通常是 prompt + context）

        Returns:
            检查结果：
            {
                "input_tokens": int,
                "available_output": int,
                "is_within_budget": bool,
                "warning_level": str,
                "suggestion": str
            }
        """
        input_tokens = self.count_tokens(input_text)
        total_budget = self.budget.total_budget

        # 计算可用输出 token
        available_output = max(
            0,
            min(
                self.budget.max_output_tokens,
                total_budget - input_tokens
            )
        )

        # 检查预算状态
        usage_ratio = input_tokens / total_budget

        if usage_ratio >= self.budget.input_critical_threshold:
            warning_level = "critical"
            is_within_budget = False
            suggestion = "输入超出临界预算！建议精简上下文或使用更短的 prompt。"
        elif usage_ratio >= self.budget.input_warning_threshold:
            warning_level = "warning"
            is_within_budget = True
            suggestion = "输入接近预算上限，输出长度将被限制。"
        else:
            warning_level = "normal"
            is_within_budget = True
            suggestion = "预算充足。"

        result = {
            "input_tokens": input_tokens,
            "available_output_tokens": available_output,
            "total_budget": total_budget,
            "usage_ratio": round(usage_ratio, 2),
            "is_within_budget": is_within_budget,
            "warning_level": warning_level,
            "suggestion": suggestion,
            "budget_level": self.budget.level.value
        }

        # 日志记录
        if warning_level == "critical":
            logger.warning(f"[TokenBudget] 预算临界! 输入={input_tokens}, 可用输出={available_output}")
        elif warning_level == "warning":
            logger.info(f"[TokenBudget] 预算警告: 输入={input_tokens}, 使用率={usage_ratio:.1%}")

        return result

    def calculate_max_tokens(self, input_text: str, min_output: int = 512) -> int:
        """
        计算实际可用的 max_tokens

        Args:
            input_text: 输入文本
            min_output: 最小输出 token 数

        Returns:
            建议的 max_tokens 值
        """
        check_result = self.check_budget(input_text)
        available = check_result["available_output_tokens"]

        # 如果可用输出小于最小值，返回最小值
        if available < min_output:
            logger.warning(
                f"[TokenBudget] 可用输出 token ({available}) 小于最小值 ({min_output})，"
                f"建议精简输入或降低预算级别"
            )
            return min_output

        return available

    def set_budget_level(self, level: BudgetLevel) -> None:
        """
        设置预算级别

        Args:
            level: 预算级别
        """
        self.budget = BUDGET_PRESETS.get(level, BUDGET_PRESETS[BudgetLevel.NORMAL])
        logger.info(f"[TokenBudget] 预算级别设置为: {level.value}")


# ==========================================
# 全局实例
# ==========================================

_default_controller: Optional[TokenBudgetController] = None


def get_token_budget_controller(level: BudgetLevel = BudgetLevel.NORMAL) -> TokenBudgetController:
    """
    获取 Token 预算控制器实例

    Args:
        level: 预算级别

    Returns:
        TokenBudgetController 实例
    """
    global _default_controller

    if _default_controller is None:
        _default_controller = TokenBudgetController()

    if level != _default_controller.budget.level:
        _default_controller.set_budget_level(level)

    return _default_controller


# ==========================================
# 便捷函数
# ==========================================

def estimate_tokens(text: str) -> int:
    """
    快速估算 token 数量

    Args:
        text: 输入文本

    Returns:
        估算的 token 数量
    """
    controller = get_token_budget_controller()
    return controller.count_tokens(text)


def check_llm_budget(input_text: str, level: BudgetLevel = BudgetLevel.NORMAL) -> Dict[str, Any]:
    """
    检查 LLM 调用预算

    Args:
        input_text: 输入文本（prompt + context）
        level: 预算级别

    Returns:
        预算检查结果
    """
    controller = get_token_budget_controller(level)
    return controller.check_budget(input_text)


def get_max_tokens_for_input(input_text: str, level: BudgetLevel = BudgetLevel.NORMAL) -> int:
    """
    根据输入动态计算 max_tokens

    Args:
        input_text: 输入文本
        level: 预算级别

    Returns:
        建议的 max_tokens 值
    """
    controller = get_token_budget_controller(level)
    return controller.calculate_max_tokens(input_text)