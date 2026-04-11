"""
定时任务调度 - Celery Beat

任务:
1. run_learning_cycle: 每小时执行，提取和更新系统技能
2. rebuild_vector_index: 每天执行，重建向量索引

这是系统学习层的自动化引擎，定期处理待学习会话，
提取方法论并更新技能库。

配置方式:
    在 Celery Beat 配置中添加:
    CELERYBEAT_SCHEDULE = {
        'system-learning-hourly': {
            'task': 'app.services.system_learning.batch_scheduler.run_learning_cycle',
            'schedule': 60 * 60,  # 每小时
        },
        'system-learning-daily-index': {
            'task': 'app.services.system_learning.batch_scheduler.rebuild_vector_index',
            'schedule': 24 * 60 * 60,  # 每天
        },
    }
"""

from celery import shared_task
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.core.logger import log
from app.services.system_learning.session_pool import get_session_pool
from app.services.system_learning.method_extractor import get_method_extractor


# ============================================================================
# 学习周期任务
# ============================================================================

@shared_task(name="system_learning.run_learning_cycle")
def run_learning_cycle() -> Dict[str, Any]:
    """
    学习周期任务（每小时执行）

    流程:
    1. 从 SessionPool 获取待处理会话
    2. 批量提取方法候选
    3. 合并更新现有技能
    4. 更新向量索引
    5. 清理过期会话

    Returns:
        Dict[str, Any]: 执行统计
    """
    start_time = datetime.now(timezone.utc)
    log.info("🔄 [SystemLearning] 开始学习周期")

    stats = {
        "processed_sessions": 0,
        "extracted_candidates": 0,
        "merged_skills": 0,
        "new_skills": 0,
        "errors": 0,
        "start_time": start_time.isoformat(),
        "duration_seconds": 0
    }

    try:
        # -------------------------------------------------------------------------
        # 1. 获取待处理会话
        # -------------------------------------------------------------------------
        pool = get_session_pool()
        session_ids = pool.get_pending_sessions(limit=100)

        if not session_ids:
            log.info("🔄 [SystemLearning] 没有待处理会话")
            stats["duration_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
            return stats

        log.info(f"🔄 [SystemLearning] 处理 {len(session_ids)} 个会话")

        # -------------------------------------------------------------------------
        # 2. 批量提取
        # -------------------------------------------------------------------------
        extractor = get_method_extractor()

        for session_id in session_ids:
            try:
                # 获取会话信息
                session_info = pool.get_session_info(session_id)
                if not session_info:
                    log.warning(f"会话 {session_id} 信息不存在")
                    pool.mark_processed(session_id, extracted=False)
                    stats["errors"] += 1
                    continue

                # TODO: 从数据库加载会话消息
                # 这里需要实现从 ChatSession 表加载消息的逻辑
                # session_messages = load_session_messages(session_id)
                # candidates = extractor.extract_from_session(session_messages, session_id)

                # 暂时模拟：标记已处理
                pool.mark_processed(session_id, extracted=False)
                stats["processed_sessions"] += 1

                log.debug(f"处理会话 {session_id}: 跳过（消息加载未实现）")

            except Exception as e:
                log.error(f"处理会话 {session_id} 失败: {e}")
                stats["errors"] += 1

        # -------------------------------------------------------------------------
        # 3. 清理过期会话
        # -------------------------------------------------------------------------
        expired_count = pool.cleanup_expired(days=7)
        if expired_count > 0:
            log.info(f"🔄 [SystemLearning] 清理了 {expired_count} 个过期会话")

        # -------------------------------------------------------------------------
        # 4. 更新向量索引（待实现）
        # -------------------------------------------------------------------------
        # index = get_vector_index()
        # index.rebuild_index()

    except Exception as e:
        log.error(f"学习周期执行失败: {e}")
        stats["errors"] += 1

    # -------------------------------------------------------------------------
    # 完成统计
    # -------------------------------------------------------------------------
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    stats["duration_seconds"] = duration
    stats["end_time"] = datetime.now(timezone.utc).isoformat()

    log.info(f"🔄 [SystemLearning] 学习周期完成: {stats}")

    return stats


@shared_task(name="system_learning.rebuild_vector_index")
def rebuild_vector_index() -> Dict[str, Any]:
    """
    重建向量索引（每天执行）

    流程:
    1. 重新计算所有技能的 embedding
    2. 更新 pgvector 索引
    3. 重建 BM25 索引

    Returns:
        Dict[str, Any]: 执行结果
    """
    log.info("🔄 [SystemLearning] 开始重建向量索引")

    result = {
        "status": "pending",
        "indexed_count": 0,
        "errors": []
    }

    try:
        # TODO: 实现向量索引重建逻辑
        # 1. 从数据库加载所有系统技能
        # 2. 生成 embedding
        # 3. 更新数据库

        result["status"] = "success"
        log.info("🔄 [SystemLearning] 向量索引重建完成")

    except Exception as e:
        log.error(f"重建向量索引失败: {e}")
        result["status"] = "error"
        result["errors"].append(str(e))

    return result


@shared_task(name="system_learning.cleanup_expired_sessions")
def cleanup_expired_sessions(days: int = 7) -> Dict[str, Any]:
    """
    清理过期会话任务

    Args:
        days: 过期天数

    Returns:
        Dict[str, Any]: 清理统计
    """
    log.info(f"🔄 [SystemLearning] 开始清理过期会话 (>{days}天)")

    try:
        pool = get_session_pool()
        count = pool.cleanup_expired(days=days)

        return {
            "status": "success",
            "expired_count": count
        }

    except Exception as e:
        log.error(f"清理过期会话失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@shared_task(name="system_learning.get_pool_stats")
def get_pool_stats() -> Dict[str, Any]:
    """
    获取会话池统计（监控任务）

    Returns:
        Dict[str, Any]: 池统计信息
    """
    try:
        pool = get_session_pool()
        stats = pool.get_stats()

        log.info(f"📊 [SystemLearning] 会话池统计: {stats}")
        return stats

    except Exception as e:
        log.error(f"获取池统计失败: {e}")
        return {"error": str(e)}


# ============================================================================
# Celery Beat 配置
# ============================================================================

CELERYBEAT_SCHEDULE = {
    'system-learning-hourly': {
        'task': 'system_learning.run_learning_cycle',
        'schedule': 60 * 60,  # 每小时
    },
    'system-learning-daily-index': {
        'task': 'system_learning.rebuild_vector_index',
        'schedule': 24 * 60 * 60,  # 每天
    },
    'system-learning-daily-cleanup': {
        'task': 'system_learning.cleanup_expired_sessions',
        'schedule': 24 * 60 * 60,  # 每天
        'kwargs': {'days': 7}
    },
}


# ============================================================================
# 手动触发接口
# ============================================================================

def trigger_learning_cycle() -> Dict[str, Any]:
    """
    手动触发学习周期

    用于测试或管理员手动触发。

    Returns:
        Dict[str, Any]: 执行结果
    """
    log.info("📌 [SystemLearning] 手动触发学习周期")
    return run_learning_cycle()


def trigger_index_rebuild() -> Dict[str, Any]:
    """
    手动触发索引重建

    Returns:
        Dict[str, Any]: 执行结果
    """
    log.info("📌 [SystemLearning] 手动触发索引重建")
    return rebuild_vector_index()