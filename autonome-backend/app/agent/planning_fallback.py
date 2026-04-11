"""
规划降级处理器 (Planning Fallback) - 自动降级机制

核心功能:
1. 监控规划执行状态
2. 自动检测失败并降级
3. 提供降级链: FULL_PARALLEL → DUAL_AGENT → SINGLE_AGENT → MINIMAL

降级策略:
- 当部分专家失败时，使用剩余成功报告继续
- 当多数专家失败时，自动降级到更简单的模式
- 当首席研究员失败时，返回错误信息

Author: Autonome AI Team
Created: 2026-03-21
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio
import time

from app.core.logger import log


class DegradationLevel(str, Enum):
    """
    降级等级枚举

    FULL_PARALLEL: 4 专家 + PI 仲裁
    DUAL_AGENT: 数据架构师 + PI
    SINGLE_AGENT: PI 直接输出
    MINIMAL: 最小可行蓝图
    """
    FULL_PARALLEL = "full_parallel"
    DUAL_AGENT = "dual_agent"
    SINGLE_AGENT = "single_agent"
    MINIMAL = "minimal"


@dataclass
class FallbackResult:
    """
    降级结果数据结构

    Attributes:
        status: 最终状态（success / degraded / failed）
        blueprint: 生成的蓝图
        degradation_level: 最终降级等级
        degradation_history: 降级历史记录
        error: 错误信息（如有）
    """
    status: str
    blueprint: Optional[Dict[str, Any]]
    degradation_level: DegradationLevel
    degradation_history: List[Dict[str, Any]]
    error: Optional[str] = None


class PlanningFallback:
    """
    规划降级处理器

    核心功能:
    - 自动监控规划执行
    - 检测失败并自动降级
    - 记录降级历史

    降级链:
    ```
    FULL_PARALLEL (4专家+PI)
        ↓ 部分失败（<2个成功）
    DUAL_AGENT (数据架构师+PI)
        ↓ 失败
    SINGLE_AGENT (PI直接输出)
        ↓ 失败
    MINIMAL (最小可行蓝图)
    ```

    使用示例:
    ```python
    fallback = PlanningFallback()

    result = await fallback.execute_with_fallback(
        planning_func=my_planning_function,
        context=planning_context,
        initial_level=DegradationLevel.FULL_PARALLEL
    )
    ```
    """

    # 降级链映射
    DEGRADATION_CHAIN = {
        DegradationLevel.FULL_PARALLEL: DegradationLevel.DUAL_AGENT,
        DegradationLevel.DUAL_AGENT: DegradationLevel.SINGLE_AGENT,
        DegradationLevel.SINGLE_AGENT: DegradationLevel.MINIMAL,
        DegradationLevel.MINIMAL: None,  # 无法再降级
    }

    def __init__(self, max_retries: int = 3, timeout_per_level: float = 30.0):
        """
        初始化降级处理器

        Args:
            max_retries: 每个等级最大重试次数
            timeout_per_level: 每个等级超时时间（秒）
        """
        self.max_retries = max_retries
        self.timeout_per_level = timeout_per_level
        self.degradation_history: List[Dict[str, Any]] = []

    async def execute_with_fallback(
        self,
        planning_func: Callable,
        context: Any,
        initial_level: DegradationLevel = DegradationLevel.FULL_PARALLEL
    ) -> FallbackResult:
        """
        执行规划并自动降级

        核心方法：尝试在当前等级执行规划，失败时自动降级

        Args:
            planning_func: 规划函数（异步）
            context: 规划上下文
            initial_level: 初始降级等级

        Returns:
            FallbackResult 包含最终结果和降级历史
        """
        self.degradation_history = []
        current_level = initial_level
        attempts = 0

        log.info(f"🔄 [Fallback] 开始执行，初始等级: {current_level.value}")

        while current_level is not None and attempts < self.max_retries * 4:
            attempts += 1
            start_time = time.time()

            try:
                # 带超时执行
                result = await asyncio.wait_for(
                    planning_func(context, current_level),
                    timeout=self.timeout_per_level
                )

                elapsed = time.time() - start_time

                # 检查结果
                if result and result.get("status") in ["success", "success_with_degradation"]:
                    log.info(f"✅ [Fallback] 规划成功，等级: {current_level.value}, 耗时: {elapsed:.2f}s")

                    return FallbackResult(
                        status=result.get("status"),
                        blueprint=result.get("blueprint"),
                        degradation_level=current_level,
                        degradation_history=self.degradation_history
                    )

                # 结果无效，尝试降级
                log.warning(f"⚠️ [Fallback] 规划结果无效，尝试降级")
                current_level = self._degrade(current_level, "结果无效")

            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                log.warning(f"⚠️ [Fallback] 超时，等级: {current_level.value}, 耗时: {elapsed:.2f}s")
                current_level = self._degrade(current_level, "执行超时")

            except Exception as e:
                elapsed = time.time() - start_time
                log.error(f"❌ [Fallback] 执行失败: {e}, 等级: {current_level.value}")
                current_level = self._degrade(current_level, f"异常: {str(e)[:100]}")

        # 所有等级都失败
        log.error(f"❌ [Fallback] 所有降级尝试均失败")

        return FallbackResult(
            status="failed",
            blueprint=None,
            degradation_level=DegradationLevel.MINIMAL,
            degradation_history=self.degradation_history,
            error="所有规划尝试均失败"
        )

    def _degrade(self, current_level: DegradationLevel, reason: str) -> Optional[DegradationLevel]:
        """
        执行降级

        Args:
            current_level: 当前等级
            reason: 降级原因

        Returns:
            降级后的等级，None 表示无法再降级
        """
        next_level = self.DEGRADATION_CHAIN.get(current_level)

        # 记录降级历史
        self.degradation_history.append({
            "from_level": current_level.value,
            "to_level": next_level.value if next_level else None,
            "reason": reason,
            "timestamp": time.time()
        })

        if next_level:
            log.info(f"🔄 [Fallback] 降级: {current_level.value} → {next_level.value}, 原因: {reason}")
        else:
            log.warning(f"⚠️ [Fallback] 无法再降级，当前等级: {current_level.value}")

        return next_level

    def get_minimal_blueprint(self, user_request: str, project_id: int) -> Dict[str, Any]:
        """
        生成最小可行蓝图

        当所有降级都失败时，返回一个最小可行的蓝图结构

        Args:
            user_request: 用户请求
            project_id: 项目 ID

        Returns:
            最小蓝图字典
        """
        return {
            "project_goal": user_request[:200] if user_request else "未知任务",
            "is_complex_task": True,
            "tasks": [
                {
                    "task_id": "task_1",
                    "name": "数据探查",
                    "tool": "peek_tabular_data",
                    "depends_on": [],
                    "expected_input": f"/workspace/project_{project_id}/raw_data/",
                    "expected_output": None,
                    "instruction": "预览数据结构，确认格式和维度",
                    "parameters": {}
                }
            ],
            "metadata": {
                "is_minimal": True,
                "degradation_history": self.degradation_history
            }
        }


def should_degrade(
    expert_reports: Any,
    threshold: float = 0.5
) -> bool:
    """
    判断是否应该降级

    基于专家报告成功率判断是否需要降级

    Args:
        expert_reports: ExpertReports 对象
        threshold: 成功率阈值（默认 0.5）

    Returns:
        True 表示应该降级
    """
    if not hasattr(expert_reports, 'get_success_count'):
        return True

    success_count = expert_reports.get_success_count()
    total_count = 4  # 4 个专家

    success_rate = success_count / total_count

    return success_rate < threshold


def get_degradation_message(
    original_level: DegradationLevel,
    final_level: DegradationLevel,
    failed_agents: List[str]
) -> str:
    """
    生成降级提示消息

    Args:
        original_level: 原始等级
        final_level: 最终等级
        failed_agents: 失败的 Agent 列表

    Returns:
        用户友好的降级消息
    """
    if original_level == final_level:
        return ""

    level_names = {
        DegradationLevel.FULL_PARALLEL: "全专家并行模式",
        DegradationLevel.DUAL_AGENT: "双 Agent 模式",
        DegradationLevel.SINGLE_AGENT: "单 Agent 模式",
        DegradationLevel.MINIMAL: "最小模式"
    }

    original_name = level_names.get(original_level, original_level.value)
    final_name = level_names.get(final_level, final_level.value)

    message = f"由于规划资源限制，已从 {original_name} 自动降级到 {final_name}"

    if failed_agents:
        agent_names = {
            "data_qc": "数据质控专家",
            "algorithm": "算法统计专家",
            "annotation": "系统生物学专家",
            "visualization": "可视化设计师"
        }
        failed_names = [agent_names.get(a, a) for a in failed_agents]
        message += f"。失败专家: {', '.join(failed_names)}"

    return message


log.info("🔄 PlanningFallback 模块已加载")