"""
Celery 异步任务主入口

本文件是 Celery 应用的主入口，负责：
1. 初始化 Celery 实例
2. 配置 Redis 连接
3. 注册所有任务模块

任务实现已拆分到以下模块：
- services/tasks/pipeline_tasks.py: 流水线任务
- services/tasks/sandbox_tasks.py: 沙箱执行任务
- services/tasks/skill_bundle_tasks.py: SKILL Bundle 执行任务
- services/tasks/executor_tasks.py: 高级执行器任务

辅助服务模块：
- services/task_logger.py: 任务日志工具
- services/code_fixer.py: AI 代码修复服务
- services/expert_report.py: 专家解读报告生成
- utils/command_builder.py: 命令行参数构建器
- utils/argparse_injector.py: 参数注入工具

@optimized 2026-04-08: 添加并发配置、连接池、超时设置
"""

import redis

from celery import Celery

from app.core.config import settings
from app.core.logger import log


# ==========================================
# 1. 初始化 Celery 实例
# ==========================================
celery_app = Celery(
    "bioinfo_tasks",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
)

# ==========================================
# 2. 初始化 Redis 客户端 (用于日志流)
# ==========================================
# 🚀 性能优化：添加连接池配置
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=2,
    decode_responses=True,
    max_connections=50,  # 最大连接数
    socket_timeout=5,  # Socket 超时（秒）
    socket_connect_timeout=5,  # 连接超时（秒）
    retry_on_timeout=True,  # 超时重试
    health_check_interval=30,  # 健康检查间隔（秒）
)

# ==========================================
# 3. Celery 配置（性能优化）
# ==========================================
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',

    # ==========================================
    # 🚀 性能优化配置
    # ==========================================

    # Worker 并发配置
    worker_concurrency=4,  # 并发 worker 数量（根据 CPU 核心数调整）
    worker_prefetch_multiplier=2,  # 每个 worker 预取的任务数

    # 任务执行配置
    task_acks_late=True,  # 任务完成后才确认（防止任务丢失）
    task_reject_on_worker_lost=True,  # Worker 丢失时拒绝任务
    task_track_started=True,  # 跟踪任务开始状态

    # 超时配置
    task_soft_time_limit=3600,  # 软超时（1小时，发送异常）
    task_time_limit=7200,  # 硬超时（2小时，强制终止）

    # 结果后端配置
    result_expires=86400,  # 结果过期时间（24小时）

    # Broker 连接池配置
    broker_pool_limit=10,  # Broker 连接池大小
    broker_connection_timeout=5,  # Broker 连接超时（秒）

    # 任务路由（可选）
    task_routes={
        'app.services.tasks.sandbox_tasks.*': {'queue': 'sandbox'},
        'app.services.tasks.pipeline_tasks.*': {'queue': 'pipeline'},
    },

    # 任务默认队列
    task_default_queue='default',

    # 优化：禁用结果后端的不必要功能
    result_backend_transport_options={
        'max_connections': 50,
    },
)


# ==========================================
# 4. 注册所有任务
# ==========================================
from app.services.tasks import register_all_tasks

# 注册任务并获取任务引用
_registered_tasks = register_all_tasks(celery_app)

# 导出任务函数（保持向后兼容）
run_rnaseq_qc_pipeline = _registered_tasks.get("run_rnaseq_qc_pipeline")
run_variant_calling_pipeline = _registered_tasks.get("run_variant_calling_pipeline")
run_scrna_analysis_pipeline = _registered_tasks.get("run_scrna_analysis_pipeline")
run_geo_single_cell_pipeline = _registered_tasks.get("run_geo_single_cell_pipeline")
run_custom_python_task = _registered_tasks.get("run_custom_python_task")
run_custom_r_task = _registered_tasks.get("run_custom_r_task")
execute_bundle_task = _registered_tasks.get("execute_bundle_task")
execute_blueprint_task = _registered_tasks.get("execute_blueprint_task")


# ==========================================
# 5. 任务注册表（统一管理所有 Celery 任务）
# ==========================================
TASK_REGISTRY = {
    "rnaseq-qc": run_rnaseq_qc_pipeline,
    "variant-calling": run_variant_calling_pipeline,
    "sc-rna-analysis": run_scrna_analysis_pipeline,
    "execute-python": run_custom_python_task,
    "execute-r": run_custom_r_task,
}