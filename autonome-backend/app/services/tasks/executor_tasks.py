"""
高级执行器任务

包含蓝图执行 Celery 任务
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

    return {
        "execute_blueprint_task": execute_blueprint_task,
    }
