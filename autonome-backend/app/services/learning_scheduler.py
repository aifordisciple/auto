"""
学习调度器服务

提供学习任务的管理和调度：
1. 任务状态查询
2. 手动触发任务
3. 调度配置管理
4. 任务历史记录

设计原则：
- 统一任务管理接口
- 支持手动触发和定时调度
- 任务执行历史追踪
- 错误处理和重试
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 调度任务信息
# ==========================================

@dataclass
class ScheduledTask:
    """调度任务信息"""
    task_name: str
    interval_seconds: float
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: str = "idle"
    last_result: Optional[Dict[str, Any]] = None


# ==========================================
# 默认调度配置
# ==========================================

DEFAULT_BEAT_SCHEDULE = {
    "aggregate-feedback": {"schedule": 300.0},
    "update-user-profiles": {"schedule": 3600.0},
    "extract-domain-knowledge": {"schedule": 21600.0},
    "optimize-weights": {"schedule": 86400.0},
    "generate-learning-report": {"schedule": 604800.0},
}


# ==========================================
# 学习调度器
# ==========================================

class LearningScheduler:
    """
    学习调度器

    管理学习任务的执行和状态：
    - 查询任务状态
    - 手动触发任务
    - 获取调度配置
    """

    def __init__(self):
        """初始化调度器"""
        self._task_states: Dict[str, ScheduledTask] = {}
        self._task_functions: Dict[str, callable] = {}
        self._init_task_states()
        self._init_task_functions()

    def _init_task_states(self):
        """初始化任务状态"""
        now = get_utc_now()

        for task_name, config in DEFAULT_BEAT_SCHEDULE.items():
            interval = config["schedule"]

            self._task_states[task_name] = ScheduledTask(
                task_name=task_name,
                interval_seconds=interval,
                last_run=None,
                next_run=now + timedelta(seconds=interval),
                status="idle",
            )

    def _init_task_functions(self):
        """初始化任务函数映射"""
        # 延迟导入任务函数
        try:
            # 使用 importlib 直接加载模块避免导入链
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "learning_tasks",
                "app/tasks/learning_tasks.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            self._task_functions = {
                "aggregate_feedback": module.aggregate_feedback,
                "update_user_profiles": module.update_user_profiles,
                "extract_domain_knowledge": module.extract_domain_knowledge,
                "optimize_weights": module.optimize_weights,
                "generate_learning_report": module.generate_learning_report,
            }
        except Exception as e:
            log.warning(f"学习任务模块导入失败，调度器功能受限: {e}")
            self._task_functions = {}

    def get_task_status(self, task_name: str) -> Dict[str, Any]:
        """
        获取任务状态

        Args:
            task_name: 任务名称

        Returns:
            任务状态信息
        """
        # 处理下划线和连字符两种格式
        normalized_name = task_name.replace("-", "_")
        schedule_name = task_name.replace("_", "-")

        if normalized_name not in self._task_functions:
            return {
                "task_name": task_name,
                "last_run": None,
                "next_run": None,
                "status": "not_found",
            }

        task = self._task_states.get(schedule_name)

        if not task:
            return {
                "task_name": task_name,
                "last_run": None,
                "next_run": None,
                "status": "not_configured",
            }

        return {
            "task_name": task.task_name,
            "interval_seconds": task.interval_seconds,
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "next_run": task.next_run.isoformat() if task.next_run else None,
            "status": task.status,
            "last_result": task.last_result,
        }

    def run_task(self, task_name: str, **kwargs) -> Dict[str, Any]:
        """
        手动运行任务

        Args:
            task_name: 任务名称
            **kwargs: 任务参数

        Returns:
            执行结果
        """
        # 处理下划线和连字符两种格式
        normalized_name = task_name.replace("-", "_")
        schedule_name = task_name.replace("_", "-")

        if normalized_name not in self._task_functions:
            return {
                "success": False,
                "error": f"Task '{task_name}' not found",
            }

        task_func = self._task_functions[normalized_name]
        task_state = self._task_states.get(schedule_name)

        try:
            # 更新状态为运行中
            if task_state:
                task_state.status = "running"

            # 执行任务
            log.info(f"[LearningScheduler] 手动运行任务: {task_name}")
            result = task_func(**kwargs)

            # 更新任务状态
            if task_state:
                task_state.last_run = get_utc_now()
                task_state.next_run = get_utc_now() + timedelta(seconds=task_state.interval_seconds)
                task_state.status = "completed"
                task_state.last_result = result.to_dict() if hasattr(result, 'to_dict') else result

            return {
                "success": True,
                "result": result.to_dict() if hasattr(result, 'to_dict') else result,
            }

        except Exception as e:
            log.error(f"[LearningScheduler] 任务执行失败: {e}")

            if task_state:
                task_state.status = "failed"
                task_state.last_result = {"error": str(e)}

            return {
                "success": False,
                "error": str(e),
            }

    def get_schedule(self) -> List[Dict[str, Any]]:
        """
        获取所有调度配置

        Returns:
            调度配置列表
        """
        schedules = []

        for task_name, task_state in self._task_states.items():
            schedules.append({
                "task_name": task_name,
                "interval_seconds": task_state.interval_seconds,
                "last_run": task_state.last_run.isoformat() if task_state.last_run else None,
                "next_run": task_state.next_run.isoformat() if task_state.next_run else None,
                "status": task_state.status,
            })

        return schedules

    def get_available_tasks(self) -> List[str]:
        """
        获取所有可用任务名称

        Returns:
            任务名称列表
        """
        return list(self._task_functions.keys())


# ==========================================
# 导出
# ==========================================

__all__ = ["LearningScheduler"]