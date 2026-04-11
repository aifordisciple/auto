"""
高级执行器任务

包含蓝图执行和超级执行者 Celery 任务
"""

import json
import asyncio
import traceback

from celery import Celery
from sqlmodel import Session

from app.core.database import engine
from app.core.logger import log
from app.models.domain import User
from app.services.task_logger import redis_client


def register_executor_tasks(celery_app: Celery):
    """
    注册高级执行器任务到 Celery

    Args:
        celery_app: Celery 应用实例
    """

    @celery_app.task(bind=True, soft_time_limit=3600, time_limit=3700)
    def execute_blueprint_task(self, payload: dict):
        """
        蓝图执行 Celery 任务

        将复杂任务蓝图迁移到 Celery 后台执行，解决以下问题：
        1. 长时间运行的 DAG 任务占用 HTTP 连接
        2. 服务重启时任务丢失
        3. 无法水平扩展 Worker

        Args:
            payload: 任务载荷，包含:
                - blueprint_json: 蓝图数据
                - project_id: 项目 ID
                - user_id: 用户 ID
                - api_key: OpenAI API Key
                - base_url: API Base URL
                - model_name: 模型名称
                - enable_visual_review: 是否启用视觉审稿
                - max_review_attempts: 最大审稿重试次数

        Returns:
            {
                "success": true/false,
                "message": "执行结果描述",
                "stats": {...},
                "cost_credits": 5.0
            }
        """
        from app.services.blueprint_runner import run_blueprint_sync

        task_id = self.request.id

        blueprint_data = payload.get("blueprint_json", {})
        project_id = payload.get("project_id", "1")
        user_id = payload.get("user_id", 1)
        api_key = payload.get("api_key", "")
        base_url = payload.get("base_url", "https://api.openai.com/v1")
        model_name = payload.get("model_name", "gpt-3.5-turbo")
        enable_visual_review = payload.get("enable_visual_review", True)
        max_review_attempts = payload.get("max_review_attempts", 2)

        log.info(f"🚀 [BlueprintTask] 开始执行蓝图任务 - task_id={task_id}")
        log.info(f"📋 [BlueprintTask] 项目: {project_id}, 用户: {user_id}")
        log.info(f"📋 [BlueprintTask] 任务数: {len(blueprint_data.get('tasks', []))}")

        result = run_blueprint_sync(
            task_id=task_id,
            blueprint_data=blueprint_data,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            project_id=project_id,
            user_id=user_id,
            enable_visual_review=enable_visual_review,
            max_review_attempts=max_review_attempts
        )

        log.info(f"🏁 [BlueprintTask] 蓝图任务完成 - task_id={task_id}, success={result.get('success')}")

        return result

    @celery_app.task(bind=True, soft_time_limit=1800, time_limit=1900)
    def execute_super_executor_task(self, payload: dict):
        """
        超级执行者 Celery 任务

        接收外部 AI 输出，自动解析代码、映射路径、沙箱执行、自动排错。

        Args:
            payload: 任务载荷，包含:
                - raw_input: 用户粘贴的外部 AI 输出
                - project_id: 项目 ID
                - user_id: 用户 ID
                - api_key: OpenAI API Key
                - base_url: API Base URL
                - model_name: 模型名称
                - version: 执行器版本

        Returns:
            {
                "success": true/false,
                "message": "执行结果描述",
                "cost_credits": 3.0
            }
        """
        from app.agent.super_executor_agent import SuperExecutor
        from app.api.routes.super_executor import (
            push_event_to_redis,
            set_task_info,
            SUPER_EXECUTOR_EVENTS_PREFIX,
            SUPER_EXECUTOR_INFO_PREFIX
        )

        task_id = self.request.id

        raw_input = payload.get("raw_input", "")
        project_id = payload.get("project_id", "1")
        user_id = payload.get("user_id", 1)
        api_key = payload.get("api_key", "")
        base_url = payload.get("base_url", "https://api.openai.com/v1")
        model_name = payload.get("model_name", "gpt-3.5-turbo")
        version = payload.get("version", "v4")

        log.info(f"🚀 [SuperExecutorTask] 开始执行 - task_id={task_id}, version={version}")
        log.info(f"📋 [SuperExecutorTask] 项目: {project_id}, 用户: {user_id}")

        # 设置任务元数据
        redis = redis_client
        set_task_info(
            redis_client=redis,
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
            raw_input_preview=raw_input[:500]
        )

        # 费用累计
        cost_credits = 3.0  # 基础费用

        try:
            # 根据版本选择执行器
            if version == "v4":
                from app.agent.super_executor_v4 import SuperExecutorV4
                executor = SuperExecutorV4(
                    raw_input=raw_input,
                    project_id=project_id,
                    user_id=user_id,
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name
                )
                log.info(f"🦾 [SuperExecutorTask] 使用 V4 执行器（三步流程）")
            else:
                executor = SuperExecutor(
                    raw_input=raw_input,
                    project_id=project_id,
                    user_id=user_id,
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name
                )
                log.info(f"🦾 [SuperExecutorTask] 使用 V3 执行器")

            # 定义事件推送回调
            async def run_executor():
                results = []
                async for event in executor.run():
                    event_type = event.get("event", "message")
                    event_data_raw = event.get("data", "{}")

                    if isinstance(event_data_raw, str):
                        try:
                            event_data = json.loads(event_data_raw)
                        except json.JSONDecodeError:
                            event_data = {"raw": event_data_raw}
                    else:
                        event_data = event_data_raw

                    push_event_to_redis(
                        redis_client=redis,
                        task_id=task_id,
                        event_type=event_type,
                        data=event_data
                    )

                    results.append(event)

                    if event_type == "done":
                        break

                return results

            # 运行执行器
            asyncio.run(run_executor())

            # 更新任务状态
            redis.hset(f"{SUPER_EXECUTOR_INFO_PREFIX}{task_id}", "status", "completed")

            # 计算最终费用
            if version == "v4":
                if hasattr(executor, 'context') and executor.context.phase_3_result:
                    cost_credits += executor.context.phase_3_result.execution_time / 60 * 0.5
            else:
                cost_credits += len(executor.execution_results) * 0.5

            log.info(f"🏁 [SuperExecutorTask] 执行完成 - task_id={task_id}")

            return {
                "success": True,
                "message": "超级执行完成",
                "cost_credits": cost_credits
            }

        except Exception as e:
            error_trace = traceback.format_exc()
            log.error(f"❌ [SuperExecutorTask] 执行失败: {str(e)}\n{error_trace}")

            # 推送错误事件
            push_event_to_redis(
                redis_client=redis,
                task_id=task_id,
                event_type="error",
                data={"error": str(e), "trace": error_trace[:1000]}
            )

            # 更新任务状态
            redis.hset(f"{SUPER_EXECUTOR_INFO_PREFIX}{task_id}", "status", "failed")

            # 推送 done 事件
            push_event_to_redis(
                redis_client=redis,
                task_id=task_id,
                event_type="done",
                data={"message": "[DONE]", "error": str(e)}
            )

            return {
                "success": False,
                "message": f"执行失败: {str(e)}",
                "cost_credits": cost_credits
            }

        finally:
            _deduct_super_executor_credits(user_id, cost_credits)

    def _deduct_super_executor_credits(user_id: int, cost_credits: float) -> None:
        """扣除用户积分"""
        if cost_credits <= 0:
            return

        try:
            with Session(engine) as session:
                db_user = session.get(User, user_id)
                if db_user and db_user.billing:
                    db_user.billing.credits_balance -= cost_credits
                    if db_user.billing.credits_balance < 0:
                        db_user.billing.credits_balance = 0
                    session.commit()
                    log.info(f"💰 [SuperExecutorTask] 扣费成功: user={user_id}, cost={cost_credits}")
        except Exception as e:
            log.error(f"❌ [SuperExecutorTask] 扣费失败: user={user_id}, error={str(e)}")

    return {
        "execute_blueprint_task": execute_blueprint_task,
        "execute_super_executor_task": execute_super_executor_task,
    }