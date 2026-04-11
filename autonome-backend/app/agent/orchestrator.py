"""
步骤编排器

管理执行计划的步骤编排和执行，支持：
- 拓扑排序执行
- 并行执行无依赖步骤
- 实时 SSE 状态推送
- 智能错误处理和重试
"""

import os
import time
import asyncio
import json
from typing import Dict, Any, List, Optional, AsyncGenerator

from app.agent.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    ExecutionStatus,
    ExecutionResult
)
from app.agent.tools import (
    get_tool,
    ExecutionContext
)
from app.core.logger import log


# ==========================================
# ✨ 步骤编排器类
# ==========================================

class StepOrchestrator:
    """
    步骤编排器

    负责执行计划的实际执行，管理步骤状态、错误处理和结果汇总。
    """

    def __init__(
        self,
        plan: ExecutionPlan,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None
    ):
        self.plan = plan
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

        # 执行结果
        self.result = ExecutionResult(
            plan_id=plan.plan_id,
            success=False
        )

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行执行计划

        Yields:
            SSE 事件字典
        """
        log.info(f"🚀 [Orchestrator] 开始执行计划: {self.plan.plan_id}")

        # 记录开始时间
        start_time = time.time()
        self.result.start_time = time.strftime("%Y-%m-%d %H:%M:%S")

        # 创建输出目录
        os.makedirs(self.plan.output_dir, exist_ok=True)

        # 构建执行上下文
        context = ExecutionContext(
            project_id=self.plan.project_id,
            project_dir=f"/workspace/project_{self.plan.project_id}",
            user_id=self.plan.user_id,
            output_dir=self.plan.output_dir,
            api_key=self.api_key,
            base_url=self.base_url,
            model_name=self.model_name
        )

        # 推送执行开始事件
        yield {
            "event": "execution_start",
            "data": json.dumps({
                "plan_id": self.plan.plan_id,
                "total_steps": len(self.plan.steps)
            })
        }

        try:
            # 执行步骤
            async for event in self._execute_steps(context):
                yield event

            # 更新执行结果
            self.plan.update_progress()
            self.result.success = self.plan.failed_steps == 0
            self.result.total_steps = self.plan.total_steps
            self.result.completed_steps = self.plan.completed_steps
            self.result.failed_steps = self.plan.failed_steps

        except Exception as e:
            log.error(f"❌ [Orchestrator] 执行异常: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"error": f"执行异常: {str(e)}"})
            }

        # 记录结束时间
        end_time = time.time()
        self.result.end_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.result.execution_time = end_time - start_time
        self.result.output_dir = self.plan.output_dir

        # 扫描生成的文件
        self.result.generated_files = self._scan_output_dir()

        # 生成步骤摘要
        self.result.step_summaries = [
            {
                "step_id": step.step_id,
                "name": step.name,
                "status": step.status.value,
                "execution_time": step.execution_time,
                "exit_code": step.exit_code,
                "retry_count": step.retry_count,
                "error": step.error[:200] if step.error else None
            }
            for step in self.plan.steps
        ]

        # 推送执行完成事件
        yield {
            "event": "execution_complete",
            "data": json.dumps(self.result.to_dict())
        }

        log.info(f"🏁 [Orchestrator] 执行完成: 成功={self.result.success}, 耗时={self.result.execution_time:.1f}s")

    async def _execute_steps(
        self,
        context: ExecutionContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行所有步骤

        Args:
            context: 执行上下文

        Yields:
            SSE 事件字典
        """
        # 获取执行层级（支持并行执行）
        levels = self.plan.get_parallel_steps()

        for level_idx, level_steps in enumerate(levels):
            log.info(f"[Orchestrator] 执行层级 {level_idx + 1}/{len(levels)}, {len(level_steps)} 个步骤")

            # 同一层级的步骤可以并行执行
            if len(level_steps) == 1:
                # 单步骤，直接执行
                async for event in self._execute_step(level_steps[0], context):
                    yield event
            else:
                # 多步骤，并行执行
                tasks = [
                    self._execute_step_with_events(step, context)
                    for step in level_steps
                ]

                # 并行执行，收集事件
                async for event in self._merge_events(tasks):
                    yield event

    async def _execute_step_with_events(
        self,
        step: ExecutionStep,
        context: ExecutionContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行单个步骤并生成事件"""
        async for event in self._execute_step(step, context):
            yield event

    async def _merge_events(
        self,
        tasks: List[AsyncGenerator[Dict[str, Any], None]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """合并多个异步生成器的事件"""
        # 创建异步生成器迭代器
        async_gen_list = [t.__aiter__() for t in tasks]

        # 使用 asyncio.Queue 来收集事件
        queue = asyncio.Queue()
        active_count = len(async_gen_list)

        async def consume_generator(gen):
            """消费单个生成器，将事件放入队列"""
            nonlocal active_count
            try:
                async for event in gen:
                    await queue.put(event)
            except Exception as e:
                log.error(f"[Orchestrator] 生成器错误: {e}")
            finally:
                active_count -= 1

        # 启动所有消费者任务
        consumer_tasks = [
            asyncio.create_task(consume_generator(gen))
            for gen in async_gen_list
        ]

        # 从队列中读取事件
        while active_count > 0 or not queue.empty():
            try:
                # 使用 wait_for 避免无限等待
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                # 超时后继续检查
                continue

        # 等待所有消费者完成
        await asyncio.gather(*consumer_tasks, return_exceptions=True)

    async def _execute_step(
        self,
        step: ExecutionStep,
        context: ExecutionContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单个步骤

        Args:
            step: 执行步骤
            context: 执行上下文

        Yields:
            SSE 事件字典
        """
        log.info(f"🔨 [Orchestrator] 执行步骤: {step.step_id} - {step.name}")

        # 更新状态
        step.status = ExecutionStatus.RUNNING

        # 推送步骤开始事件
        yield {
            "event": "step_start",
            "data": json.dumps({
                "step_id": step.step_id,
                "name": step.name,
                "tool_id": step.tool_id
            })
        }

        # 获取工具
        tool = get_tool(step.tool_id)
        if not tool:
            step.status = ExecutionStatus.FAILED
            step.error = f"工具不存在: {step.tool_id}"
            yield {
                "event": "step_error",
                "data": json.dumps({
                    "step_id": step.step_id,
                    "error": step.error
                })
            }
            return

        # 执行工具（带重试）
        retry_count = 0
        max_retries = step.max_retries if step.retry_on_failure else 0

        while retry_count <= max_retries:
            start_time = time.time()

            try:
                result = await tool.execute(step.parameters, context)
                execution_time = time.time() - start_time

                step.execution_time = execution_time
                step.output = result.output
                step.exit_code = result.exit_code
                step.generated_files = result.generated_files

                if result.success:
                    step.status = ExecutionStatus.SUCCESS
                    step.retry_count = retry_count

                    yield {
                        "event": "step_complete",
                        "data": json.dumps({
                            "step_id": step.step_id,
                            "status": "success",
                            "execution_time": execution_time,
                            "output_preview": result.output[:500] if result.output else None,
                            "generated_files": len(result.generated_files)
                        })
                    }

                    log.info(f"✅ [Orchestrator] 步骤完成: {step.step_id}, 耗时: {execution_time:.1f}s")
                    return

                else:
                    step.error = result.error or "执行失败"

                    if retry_count < max_retries:
                        retry_count += 1
                        step.retry_count = retry_count

                        log.warning(f"⚠️ [Orchestrator] 步骤失败，重试 {retry_count}/{max_retries}: {step.step_id}")

                        yield {
                            "event": "step_retry",
                            "data": json.dumps({
                                "step_id": step.step_id,
                                "retry_count": retry_count,
                                "error": step.error
                            })
                        }

                        # 等待一段时间后重试
                        await asyncio.sleep(1.5 ** retry_count)
                        continue
                    else:
                        step.status = ExecutionStatus.FAILED
                        yield {
                            "event": "step_error",
                            "data": json.dumps({
                                "step_id": step.step_id,
                                "error": step.error,
                                "retry_count": retry_count
                            })
                        }

                        log.error(f"❌ [Orchestrator] 步骤失败: {step.step_id}")
                        return

            except Exception as e:
                execution_time = time.time() - start_time
                step.execution_time = execution_time
                step.error = f"执行异常: {str(e)}"

                if retry_count < max_retries:
                    retry_count += 1
                    step.retry_count = retry_count
                    await asyncio.sleep(1.5 ** retry_count)
                    continue
                else:
                    step.status = ExecutionStatus.FAILED
                    yield {
                        "event": "step_error",
                        "data": json.dumps({
                            "step_id": step.step_id,
                            "error": step.error
                        })
                    }
                    return

    def _scan_output_dir(self) -> List[Dict[str, Any]]:
        """扫描输出目录获取生成的文件"""
        generated_files = []

        if not os.path.exists(self.plan.output_dir):
            return generated_files

        for root, dirs, files in os.walk(self.plan.output_dir):
            for f in files:
                if f.startswith('.'):
                    continue

                file_path = os.path.join(root, f)
                try:
                    file_size = os.path.getsize(file_path)
                    ext = os.path.splitext(f)[1].lower()

                    generated_files.append({
                        "path": file_path,
                        "name": f,
                        "size": file_size,
                        "extension": ext
                    })
                except Exception:
                    continue

        generated_files.sort(key=lambda x: x["size"], reverse=True)
        return generated_files[:50]


# ==========================================
# ✨ 模块初始化
# ==========================================

log.info("🎯 步骤编排器模块已加载")