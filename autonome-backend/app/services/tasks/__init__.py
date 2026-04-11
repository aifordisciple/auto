"""
Celery 异步任务模块

包含所有 Celery 任务定义，按功能分类

任务分类：
- pipeline_tasks: 流水线任务（RNA-Seq QC、Variant Calling、scRNA 分析等）
- sandbox_tasks: 沙箱执行任务（Python/R 代码执行）
- skill_bundle_tasks: SKILL Bundle 执行任务
- executor_tasks: 高级执行器任务（蓝图执行、超级执行者）
"""

from app.services.tasks.pipeline_tasks import register_pipeline_tasks
from app.services.tasks.sandbox_tasks import register_sandbox_tasks
from app.services.tasks.skill_bundle_tasks import register_skill_bundle_tasks
from app.services.tasks.executor_tasks import register_executor_tasks


def register_all_tasks(celery_app):
    """
    注册所有任务到 Celery

    Args:
        celery_app: Celery 应用实例

    Returns:
        注册的任务字典
    """
    tasks = {}

    # 注册流水线任务
    pipeline_tasks = register_pipeline_tasks(celery_app)
    tasks.update(pipeline_tasks)

    # 注册沙箱任务
    sandbox_tasks = register_sandbox_tasks(celery_app)
    tasks.update(sandbox_tasks)

    # 注册 SKILL Bundle 任务
    skill_bundle_tasks = register_skill_bundle_tasks(celery_app)
    tasks.update(skill_bundle_tasks)

    # 注册高级执行器任务
    executor_tasks = register_executor_tasks(celery_app)
    tasks.update(executor_tasks)

    return tasks


__all__ = [
    "register_all_tasks",
    "register_pipeline_tasks",
    "register_sandbox_tasks",
    "register_skill_bundle_tasks",
    "register_executor_tasks",
]