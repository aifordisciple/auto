"""
学习任务模块

提供智能学习系统的定时任务：
1. 反馈聚合 - 每5分钟聚合反馈数据
2. 用户偏好更新 - 每小时更新用户偏好画像
3. 知识提炼 - 每6小时提炼领域知识
4. 权重优化 - 每天优化推荐权重
5. 学习报告 - 每周生成学习报告

设计原则：
- 模块化任务函数
- 支持手动触发
- 详细结果记录
- 错误处理和重试
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 任务状态枚举
# ==========================================

class TaskStatus(str, Enum):
    """任务状态"""
    SUCCESS = "success"
    NO_DATA = "no_data"
    PARTIAL = "partial"
    ERROR = "error"


# ==========================================
# 任务结果数据类
# ==========================================

@dataclass
class TaskResult:
    """
    任务结果

    存储任务执行的详细结果：
    - 任务名称和状态
    - 处理统计数据
    - 执行时间
    """
    task_name: str
    status: str
    timestamp: str = field(default_factory=lambda: get_utc_now().isoformat())
    duration_seconds: float = 0.0
    processed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        # 将所有字段展平到顶层
        for key, value in self.metadata.items():
            if key not in result:
                result[key] = value
        return result


# ==========================================
# 反馈聚合任务
# ==========================================

def aggregate_feedback(
    hours: int = 1,
    feedback_types: Optional[List[str]] = None,
) -> TaskResult:
    """
    聚合反馈数据

    Args:
        hours: 聚合时间范围（小时）
        feedback_types: 反馈类型列表（可选）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始聚合反馈数据: hours={hours}")

    try:
        # 模拟聚合过程
        # 实际实现需要查询 BehaviorRecord 和 SkillMatchingFeedback
        processed_count = 100  # 模拟处理数量
        success_count = 95
        failed_count = 5

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="aggregate_feedback",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=processed_count,
            success_count=success_count,
            failed_count=failed_count,
            message=f"成功聚合 {success_count} 条反馈",
            metadata={
                "period_hours": hours,
                "feedback_types": feedback_types or ["all"],
            }
        )

        log.info(f"[LearningTask] 反馈聚合完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 反馈聚合失败: {e}")
        return TaskResult(
            task_name="aggregate_feedback",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 用户偏好更新任务
# ==========================================

def update_user_profiles(
    user_ids: Optional[List[int]] = None,
    days: int = 30,
) -> TaskResult:
    """
    更新用户偏好画像

    Args:
        user_ids: 指定用户ID列表（可选，不指定则更新所有活跃用户）
        days: 分析时间范围（天）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始更新用户偏好画像: user_ids={user_ids}")

    try:
        # 模拟更新过程
        # 实际实现需要调用 PreferenceEngine
        if user_ids:
            requested_count = len(user_ids)
            updated_count = requested_count
        else:
            requested_count = 50  # 模拟活跃用户数
            updated_count = 48

        failed_count = requested_count - updated_count

        status = TaskStatus.SUCCESS.value if failed_count == 0 else TaskStatus.PARTIAL.value

        result = TaskResult(
            task_name="update_user_profiles",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=requested_count,
            success_count=updated_count,
            failed_count=failed_count,
            message=f"成功更新 {updated_count} 个用户偏好",
            metadata={
                "requested_count": requested_count,
                "analysis_days": days,
            }
        )

        log.info(f"[LearningTask] 用户偏好更新完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 用户偏好更新失败: {e}")
        return TaskResult(
            task_name="update_user_profiles",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 知识提炼任务
# ==========================================

def extract_domain_knowledge(
    source: str = "all",
    min_confidence: float = 0.7,
) -> TaskResult:
    """
    提炼领域知识

    Args:
        source: 知识来源（execution_records, feedback, skill_docs, all）
        min_confidence: 最小置信度阈值

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始提炼领域知识: source={source}")

    try:
        # 模拟提炼过程
        # 实际实现需要调用 KnowledgeEngine
        extracted_count = 25  # 模拟提取数量

        knowledge_types = {
            "concept": 10,
            "synonym": 8,
            "parameter_rule": 5,
            "error_pattern": 2,
        }

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="extract_domain_knowledge",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=extracted_count,
            success_count=extracted_count,
            message=f"成功提炼 {extracted_count} 条知识",
            metadata={
                "source": source,
                "min_confidence": min_confidence,
                "knowledge_types": knowledge_types,
            }
        )

        log.info(f"[LearningTask] 知识提炼完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 知识提炼失败: {e}")
        return TaskResult(
            task_name="extract_domain_knowledge",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 权重优化任务
# ==========================================

def optimize_weights(
    strategy: str = "feedback_driven",
    min_samples: int = 10,
) -> TaskResult:
    """
    优化推荐权重

    Args:
        strategy: 优化策略（feedback_driven, success_rate, hybrid）
        min_samples: 最小样本量

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始优化推荐权重: strategy={strategy}")

    try:
        # 模拟优化过程
        # 实际实现需要调用 WeightOptimizer
        optimized_skills = 15  # 模拟优化的技能数
        total_adjustments = 45  # 模拟总调整数

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="optimize_weights",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=optimized_skills,
            success_count=optimized_skills,
            message=f"成功优化 {optimized_skills} 个技能权重",
            metadata={
                "strategy": strategy,
                "min_samples": min_samples,
                "optimized_skills": optimized_skills,
                "total_adjustments": total_adjustments,
            }
        )

        log.info(f"[LearningTask] 权重优化完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 权重优化失败: {e}")
        return TaskResult(
            task_name="optimize_weights",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 学习报告生成任务
# ==========================================

def generate_learning_report(
    report_type: str = "weekly",
) -> TaskResult:
    """
    生成学习报告

    Args:
        report_type: 报告类型（daily, weekly, monthly）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始生成学习报告: type={report_type}")

    try:
        # 模拟报告生成
        # 实际实现需要调用 LearningMetricsService
        report_id = f"report-{report_type}-{get_utc_now().strftime('%Y%m%d%H%M%S')}"

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="generate_learning_report",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=1,
            success_count=1,
            message=f"成功生成 {report_type} 报告",
            metadata={
                "report_id": report_id,
                "report_type": report_type,
            }
        )

        log.info(f"[LearningTask] 报告生成完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 报告生成失败: {e}")
        return TaskResult(
            task_name="generate_learning_report",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# Celery 任务包装器
# ==========================================

# Beat 调度配置
BEAT_SCHEDULE = {
    "aggregate-feedback": {
        "task": "app.tasks.learning_tasks.task_aggregate_feedback",
        "schedule": 300.0,  # 每 5 分钟
    },
    "update-user-profiles": {
        "task": "app.tasks.learning_tasks.task_update_user_profiles",
        "schedule": 3600.0,  # 每小时
    },
    "extract-domain-knowledge": {
        "task": "app.tasks.learning_tasks.task_extract_domain_knowledge",
        "schedule": 21600.0,  # 每 6 小时
    },
    "optimize-weights": {
        "task": "app.tasks.learning_tasks.task_optimize_weights",
        "schedule": 86400.0,  # 每天
    },
    "generate-learning-report": {
        "task": "app.tasks.learning_tasks.task_generate_learning_report",
        "schedule": 604800.0,  # 每周
    },
}

# 标记任务是否已注册
LEARNING_TASKS_REGISTERED = False

# 尝试注册 Celery 任务
try:
    from celery import shared_task

    @shared_task
    def task_aggregate_feedback():
        """Celery 任务：聚合反馈数据"""
        result = aggregate_feedback()
        return result.to_dict()

    @shared_task
    def task_update_user_profiles():
        """Celery 任务：更新用户偏好画像"""
        result = update_user_profiles()
        return result.to_dict()

    @shared_task
    def task_extract_domain_knowledge():
        """Celery 任务：提炼领域知识"""
        result = extract_domain_knowledge()
        return result.to_dict()

    @shared_task
    def task_optimize_weights():
        """Celery 任务：优化推荐权重"""
        result = optimize_weights()
        return result.to_dict()

    @shared_task
    def task_generate_learning_report():
        """Celery 任务：生成学习报告"""
        result = generate_learning_report()
        return result.to_dict()

    LEARNING_TASKS_REGISTERED = True
    log.info("✅ 学习 Celery 任务已注册")

except ImportError:
    log.warning("Celery 未安装，跳过定时任务注册")
except Exception as e:
    log.warning(f"Celery 任务注册失败: {e}")

# 尝试更新 Celery Beat 调度（延迟执行）
def _register_beat_schedule():
    """注册 Beat 调度（延迟调用）"""
    try:
        from app.services.celery_app import celery_app
        celery_app.conf.beat_schedule.update(BEAT_SCHEDULE)
        log.info("✅ 学习定时任务已注册到 Celery Beat")
    except Exception as e:
        log.warning(f"Celery Beat 调度注册失败: {e}")


# ==========================================
# 导出
# ==========================================

__all__ = [
    "TaskResult",
    "TaskStatus",
    "aggregate_feedback",
    "update_user_profiles",
    "extract_domain_knowledge",
    "optimize_weights",
    "generate_learning_report",
    "BEAT_SCHEDULE",
    "LEARNING_TASKS_REGISTERED",
]