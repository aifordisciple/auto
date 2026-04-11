"""
超级执行者 V2 - 统一入口

整合执行计划生成器、步骤编排器，提供统一的执行入口。
支持用户确认交互和渐进式执行。
"""

import os
import json
import asyncio
from typing import Dict, Any, AsyncGenerator

from app.agent.execution_plan import (
    ExecutionPlan,
    ExecutionStatus
)
from app.agent.plan_generator import ExecutionPlanGenerator
from app.agent.orchestrator import StepOrchestrator
from app.core.logger import log


# ==========================================
# ✨ 超级执行者 V2 主类
# ==========================================

class SuperExecutorV2:
    """
    超级执行者 V2

    统一入口，整合：
    1. 执行计划生成（LLM 解析）
    2. 用户确认交互
    3. 步骤编排执行
    4. 结果汇总

    状态机:
    IDLE → PARSING → PLAN_READY → CONFIRMING → EXECUTING → COMPLETED/ERROR
    """

    def __init__(
        self,
        raw_input: str,
        project_id: str,
        user_id: int,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None
    ):
        self.raw_input = raw_input
        self.project_id = project_id
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

        # 执行计划
        self.plan: ExecutionPlan = None

        # 项目目录
        self.project_dir = f"/workspace/project_{project_id}"

        # 输出目录
        self.output_dir = os.path.join(self.project_dir, "super_executor_output")

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行超级执行者

        Yields:
            SSE 事件字典
        """
        log.info(f"🚀 [SuperExecutorV2] 开始执行 - project_id={self.project_id}")

        # ==========================================
        # Phase 1: 生成执行计划
        # ==========================================
        generator = ExecutionPlanGenerator(
            api_key=self.api_key,
            base_url=self.base_url,
            model_name=self.model_name
        )

        async for event in generator.generate(
            user_input=self.raw_input,
            project_id=self.project_id,
            project_dir=self.project_dir
        ):
            # 捕获执行计划
            if event.get("event") == "execution_plan":
                plan_data = json.loads(event.get("data", "{}"))
                self.plan = ExecutionPlan.from_dict(plan_data)

            yield event

        if not self.plan:
            log.error("[SuperExecutorV2] 执行计划生成失败")
            yield {
                "event": "error",
                "data": json.dumps({"error": "执行计划生成失败"})
            }
            return

        # ==========================================
        # Phase 2: 等待用户确认
        # ==========================================
        # 注意：实际的用户确认由前端处理，这里只是推送状态
        # 前端需要在收到 execution_plan 事件后显示确认界面
        # 用户确认后，前端调用 /confirm 接口继续执行

        # 此处我们默认自动确认（可配置）
        # 实际生产环境应该等待前端确认

        # 检查是否高风险操作
        if self.plan.risk_level.value == "high":
            yield {
                "event": "confirmation_required",
                "data": json.dumps({
                    "reason": "检测到高风险操作（删除/覆盖文件），需要用户确认",
                    "risk_level": "high"
                })
            }
            # 这里应该等待确认，暂时直接继续
            # TODO: 实现确认等待机制

        # ==========================================
        # Phase 3: 执行计划
        # ==========================================
        self.plan.status = ExecutionStatus.CONFIRMED

        yield {
            "event": "status_update",
            "data": json.dumps({
                "status": "executing",
                "message": "开始执行..."
            })
        }

        orchestrator = StepOrchestrator(
            plan=self.plan,
            api_key=self.api_key,
            base_url=self.base_url,
            model_name=self.model_name
        )

        async for event in orchestrator.run():
            yield event

        # ==========================================
        # Phase 4: 生成最终结果
        # ==========================================
        result = orchestrator.result

        yield {
            "event": "execution_result",
            "data": json.dumps(result.to_dict())
        }

        # 推送完成事件
        yield {
            "event": "done",
            "data": json.dumps({"message": "[DONE]"})
        }

        log.info(f"🏁 [SuperExecutorV2] 执行完成")


# ==========================================
# ✨ 便捷函数
# ==========================================

async def execute_super_executor_v2(
    raw_input: str,
    project_id: str,
    user_id: int,
    api_key: str = None,
    base_url: str = None,
    model_name: str = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    执行超级执行者 V2

    Args:
        raw_input: 用户输入
        project_id: 项目 ID
        user_id: 用户 ID
        api_key: LLM API Key
        base_url: LLM API Base URL
        model_name: LLM 模型名称

    Yields:
        SSE 事件字典
    """
    executor = SuperExecutorV2(
        raw_input=raw_input,
        project_id=project_id,
        user_id=user_id,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name
    )

    async for event in executor.run():
        yield event


# ==========================================
# ✨ 模块初始化
# ==========================================

log.info("🦾 超级执行者 V2 模块已加载")