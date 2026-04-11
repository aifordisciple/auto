"""
蓝图同步执行器 - 为 Celery 任务提供同步执行包装

核心职责：
1. 封装 BlueprintOrchestrator 的异步执行
2. 将事件推送到 Redis（供 SSE 流消费）
3. 使用 asyncio.run() 在同步上下文中执行异步 DAG
4. 处理计费逻辑
5. 创建语义化蓝图根目录
"""

import os
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Callable, Optional

import redis
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.logger import log
from app.models.domain import User

# 语义化目录命名
from app.utils.semantic_naming import generate_blueprint_root_name


# ==========================================
# Redis 键前缀常量
# ==========================================
BLUEPRINT_EVENTS_PREFIX = "blueprint_events:"  # DAG 事件流 (List)
BLUEPRINT_STATE_PREFIX = "blueprint_state:"    # DAG 节点状态 (Hash)
BLUEPRINT_INFO_PREFIX = "blueprint_info:"      # 任务元数据 (Hash)

# 事件流保留时间（秒）
EVENT_TTL = 86400  # 24 小时


def get_redis_client() -> redis.Redis:
    """获取 Redis 客户端"""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=2,  # 与 celery_app 使用同一 db
        decode_responses=True
    )


def push_event_to_redis(
    redis_client: redis.Redis,
    task_id: str,
    event_type: str,
    data: Dict[str, Any]
) -> None:
    """
    将事件推送到 Redis 事件流

    Args:
        redis_client: Redis 客户端
        task_id: Celery 任务 ID
        event_type: 事件类型（如 task_start, task_complete 等）
        data: 事件数据
    """
    event_key = f"{BLUEPRINT_EVENTS_PREFIX}{task_id}"

    event = {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False),
        "timestamp": time.time()
    }

    # 推送到 List（右进）
    redis_client.rpush(event_key, json.dumps(event, ensure_ascii=False))

    # 设置过期时间
    redis_client.expire(event_key, EVENT_TTL)

    log.debug(f"📤 [BlueprintRunner] 推送事件: {event_type} -> {task_id}")


def update_task_state(
    redis_client: redis.Redis,
    task_id: str,
    node_id: str,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None
) -> None:
    """
    更新 DAG 节点状态到 Redis Hash

    Args:
        redis_client: Redis 客户端
        task_id: Celery 任务 ID
        node_id: DAG 节点 ID
        status: 节点状态（pending, running, success, failed）
        result: 执行结果（可选）
        error: 错误信息（可选）
    """
    state_key = f"{BLUEPRINT_STATE_PREFIX}{task_id}"

    state_data = {
        "status": status,
        "updated_at": str(time.time())
    }
    if result:
        state_data["result"] = result[:1000]  # 截断防止过大
    if error:
        state_data["error"] = error[:500]

    # 使用 Hash 存储每个节点的状态
    redis_client.hset(state_key, node_id, json.dumps(state_data, ensure_ascii=False))
    redis_client.expire(state_key, EVENT_TTL)


def set_blueprint_info(
    redis_client: redis.Redis,
    task_id: str,
    project_id: str,
    user_id: int,
    project_goal: str,
    total_tasks: int
) -> None:
    """
    设置蓝图元数据

    Args:
        redis_client: Redis 客户端
        task_id: Celery 任务 ID
        project_id: 项目 ID
        user_id: 用户 ID
        project_goal: 项目目标
        total_tasks: 任务总数
    """
    info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"

    info_data = {
        "project_id": project_id,
        "user_id": user_id,
        "project_goal": project_goal,
        "total_tasks": total_tasks,
        "status": "running",
        "created_at": str(time.time())
    }

    redis_client.hset(info_key, mapping=info_data)
    redis_client.expire(info_key, EVENT_TTL)


def run_blueprint_sync(
    task_id: str,
    blueprint_data: Dict[str, Any],
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str,
    user_id: int,
    enable_visual_review: bool = True,
    max_review_attempts: int = 2
) -> Dict[str, Any]:
    """
    同步执行蓝图（用于 Celery 任务）

    这是核心函数，封装了异步执行逻辑：
    1. 创建 Redis 客户端
    2. 设置蓝图元数据
    3. 使用 asyncio.run() 执行异步 DAG
    4. 推送事件到 Redis
    5. 更新节点状态
    6. 处理计费

    Args:
        task_id: Celery 任务 ID
        blueprint_data: 蓝图 JSON 数据
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称
        project_id: 项目 ID
        user_id: 用户 ID
        enable_visual_review: 是否启用视觉审稿
        max_review_attempts: 最大审稿重试次数

    Returns:
        执行结果字典，包含 success, message, stats 等字段
    """
    redis_client = get_redis_client()

    # 设置蓝图元数据
    set_blueprint_info(
        redis_client=redis_client,
        task_id=task_id,
        project_id=project_id,
        user_id=user_id,
        project_goal=blueprint_data.get("project_goal", "未命名任务"),
        total_tasks=len(blueprint_data.get("tasks", []))
    )

    # 计费累计
    cost_credits = 2.0  # 蓝图执行基础费用

    try:
        # 使用 asyncio.run() 执行异步 DAG
        result = asyncio.run(
            _run_blueprint_async(
                task_id=task_id,
                blueprint_data=blueprint_data,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                project_id=project_id,
                redis_client=redis_client,
                enable_visual_review=enable_visual_review,
                max_review_attempts=max_review_attempts
            )
        )

        # 计算最终费用
        cost_credits += result.get("cost_credits", 0)

        # 更新蓝图状态
        info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
        redis_client.hset(info_key, "status", "completed")

        return {
            "success": True,
            "message": "蓝图执行完成",
            "stats": result.get("stats", {}),
            "cost_credits": cost_credits
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        log.error(f"❌ [BlueprintRunner] 执行失败: {str(e)}\n{error_trace}")

        # 推送错误事件
        push_event_to_redis(
            redis_client=redis_client,
            task_id=task_id,
            event_type="blueprint_error",
            data={"error": str(e), "trace": error_trace[:1000]}
        )

        # 更新蓝图状态
        info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
        redis_client.hset(info_key, "status", "failed")

        return {
            "success": False,
            "message": f"蓝图执行失败: {str(e)}",
            "cost_credits": cost_credits
        }

    finally:
        # 推送完成事件
        push_event_to_redis(
            redis_client=redis_client,
            task_id=task_id,
            event_type="done",
            data={"message": "[DONE]", "cost_credits": cost_credits}
        )

        # 扣费
        _deduct_credits(user_id, cost_credits)


async def _run_blueprint_async(
    task_id: str,
    blueprint_data: Dict[str, Any],
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str,
    redis_client: redis.Redis,
    enable_visual_review: bool = True,
    max_review_attempts: int = 2
) -> Dict[str, Any]:
    """
    异步执行蓝图核心逻辑

    内部函数，由 run_blueprint_sync 通过 asyncio.run() 调用

    Args:
        task_id: Celery 任务 ID
        blueprint_data: 蓝图 JSON 数据
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称
        project_id: 项目 ID
        redis_client: Redis 客户端
        enable_visual_review: 是否启用视觉审稿
        max_review_attempts: 最大审稿重试次数

    Returns:
        执行统计信息
    """
    from app.services.orchestrator import BlueprintOrchestrator

    # ==========================================
    # 创建语义化蓝图根目录 (Semantic Blueprint Root Directory)
    # ==========================================
    # 格式: YYYYMMDD_HHMMSS_BLUEPRINT_ALIAS_SHORTID

    # ✨ 优先使用 AI 生成的语义名
    ai_semantic_name = blueprint_data.get("semantic_folder_name")
    blueprint_alias = blueprint_data.get("project_goal", "Analysis_Pipeline")

    if ai_semantic_name:
        # 清理语义名（确保只包含合法字符）
        import re
        ai_semantic_name = re.sub(r"[^a-z0-9_]", "", ai_semantic_name.lower())[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = str(task_id)[:6]
        blueprint_root_name = f"{timestamp}_{ai_semantic_name}_{short_id}"
        log.info(f"🎯 [BlueprintRunner] 使用 AI 生成的语义名: {ai_semantic_name}")
    else:
        # Fallback: 使用原有的 project_goal 生成
        blueprint_root_name = generate_blueprint_root_name(
            blueprint_alias=blueprint_alias,
            blueprint_id=task_id,
            timestamp=datetime.now(),
        )

    blueprint_root_dir = f"/workspace/project_{project_id}/results/{blueprint_root_name}"
    os.makedirs(blueprint_root_dir, exist_ok=True)

    log.info(f"📁 [BlueprintRunner] 创建蓝图根目录: {blueprint_root_name}")

    # 创建调度器
    orchestrator = BlueprintOrchestrator(
        blueprint_data=blueprint_data,
        blueprint_root_dir=blueprint_root_dir,  # 传递蓝图根目录
        blueprint_id=task_id,  # 传递蓝图 ID 用于步骤命名
    )

    # 费用累计
    cost_credits = 0.0

    # 统计信息
    stats = {
        "success_count": 0,
        "failed_count": 0,
        "review_failed_count": 0
    }

    log.info(f"🚀 [BlueprintRunner] 开始执行蓝图 - task_id={task_id}")

    # 推送开始事件
    push_event_to_redis(
        redis_client=redis_client,
        task_id=task_id,
        event_type="blueprint_start",
        data={
            "project_goal": blueprint_data.get("project_goal", ""),
            "total_tasks": len(blueprint_data.get("tasks", []))
        }
    )

    # 流式执行 DAG
    async for event in orchestrator.run_dag_stream(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        project_id=project_id,
        session_id=f"blueprint_{task_id}",
        enable_visual_review=enable_visual_review,
        max_review_attempts=max_review_attempts
    ):
        event_type = event.get("event", "unknown")
        event_data_raw = event.get("data", "{}")

        # 解析 data（可能是字符串或 dict）
        if isinstance(event_data_raw, str):
            try:
                event_data = json.loads(event_data_raw)
            except json.JSONDecodeError:
                event_data = {"raw": event_data_raw}
        else:
            event_data = event_data_raw

        # 推送事件到 Redis
        push_event_to_redis(
            redis_client=redis_client,
            task_id=task_id,
            event_type=event_type,
            data=event_data
        )

        # 更新节点状态
        node_id = event_data.get("task_id")
        if node_id and event_type in ["task_start", "task_complete", "task_failed"]:
            status_map = {
                "task_start": "running",
                "task_complete": event_data.get("status", "success"),
                "task_failed": "failed"
            }
            update_task_state(
                redis_client=redis_client,
                task_id=task_id,
                node_id=node_id,
                status=status_map.get(event_type, "pending"),
                result=event_data.get("result"),
                error=event_data.get("error")
            )

        # 累计费用
        if event_type == "task_complete":
            cost_credits += 1.0
            stats["success_count"] += 1
        elif event_type == "task_failed":
            stats["failed_count"] += 1
        elif event_type == "visual_review_pass":
            cost_credits += 0.5
        elif event_type == "visual_review_reject":
            pass  # 审稿打回不额外收费
        elif event_type == "blueprint_complete":
            stats["success_count"] = event_data.get("success_count", 0)
            stats["failed_count"] = event_data.get("failed_count", 0)
            stats["review_failed_count"] = event_data.get("review_failed_count", 0)

    log.info(f"✅ [BlueprintRunner] 蓝图执行完成 - task_id={task_id}")

    return {
        "cost_credits": cost_credits,
        "stats": stats
    }


def _deduct_credits(user_id: int, cost_credits: float, wallet_id: str = None) -> None:
    """
    扣除用户积分（使用 BillingService）

    Args:
        user_id: 用户 ID
        cost_credits: 扣除金额
        wallet_id: 钱包 ID（可选，不传则自动获取）
    """
    if cost_credits <= 0:
        return

    try:
        with Session(engine) as session:
            # 使用 BillingService 扣费
            try:
                from app.services.billing_service import BillingService
                billing_service = BillingService(session)

                if not wallet_id:
                    wallet = billing_service.get_user_wallet(user_id)
                    wallet_id = wallet.wallet_id

                billing_service.deduct_credits(
                    wallet_id=wallet_id,
                    amount=cost_credits,
                    transaction_type="consume_blueprint",
                    description=f"蓝图执行消费",
                )

                # 刷新获取最新余额
                wallet = billing_service.get_wallet(wallet_id)
                log.info(f"💰 [BlueprintRunner] 扣费成功: user={user_id}, cost={cost_credits}, balance={wallet.credits_balance}")

            except Exception as e:
                log.warning(f"[BlueprintRunner] BillingService 扣费失败，回退到旧逻辑: {e}")
                # 回退到旧逻辑
                db_user = session.get(User, user_id)
                if db_user and db_user.billing:
                    db_user.billing.credits_balance -= cost_credits
                    if db_user.billing.credits_balance < 0:
                        db_user.billing.credits_balance = 0
                    session.commit()
                    log.info(f"💰 [BlueprintRunner] 扣费成功(旧逻辑): user={user_id}, cost={cost_credits}, balance={db_user.billing.credits_balance}")

    except Exception as e:
        log.error(f"❌ [BlueprintRunner] 扣费失败: user={user_id}, error={str(e)}")


log.info("🔄 蓝图同步执行器模块已加载")