# -*- coding: utf-8 -*-
"""
定时任务模块

包含计费系统的定时任务：
- 僵尸容器清理
- 孤立记录结算
- 钱包健康检查
- OOM 退款处理

包含学习中心的异步任务：
- 文献 PDF 解析（process_literature）
- DOI 导入（process_doi）
"""

from app.tasks.billing_tasks import (
    cleanup_zombie_containers,
    settle_orphan_records,
    check_wallet_health,
    process_oom_refunds,
)

# 📚 学习中心任务（shared_task 在模块导入时自动注册到 Celery）
from app.tasks.learning_tasks import (
    process_literature,
    process_doi,
    task_process_literature,
    task_process_doi,
    LEARNING_TASKS_REGISTERED,
)

__all__ = [
    "cleanup_zombie_containers",
    "settle_orphan_records",
    "check_wallet_health",
    "process_oom_refunds",
    # 学习中心任务
    "process_literature",
    "process_doi",
    "task_process_literature",
    "task_process_doi",
    "LEARNING_TASKS_REGISTERED",
]