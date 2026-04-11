"""
Blueprint API 路由 - 提供蓝图执行和固化接口

Blueprint 是 Autonome 3.0 的核心概念，用于表示复杂的 DAG 任务流程。

架构升级 (2026-03-21):
- 蓝图执行迁移到 Celery 后台任务
- 解决长时间运行任务占用 HTTP 连接的问题
- 支持服务重启后任务恢复
- 支持水平扩展 Worker

新架构:
前端 → POST /api/blueprint/execute → 返回 { task_id }
                                     ↓
                          execute_blueprint_task.delay() → Celery Worker
                                     ↓
                          Redis 存储事件流 → 前端 SSE 订阅
"""

import json
import os
import time
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session

from app.core.database import get_session, engine
from app.core.logger import log
from app.core.config import settings
from app.api.deps import get_current_user, verify_token_and_get_user
from app.models.domain import User, Project, SystemConfig
from app.services.celery_app import redis_client


router = APIRouter()


# ==========================================
# Redis 键前缀常量（与 blueprint_runner 保持一致）
# ==========================================
BLUEPRINT_EVENTS_PREFIX = "blueprint_events:"
BLUEPRINT_STATE_PREFIX = "blueprint_state:"
BLUEPRINT_INFO_PREFIX = "blueprint_info:"


# ==========================================
# Request/Response Models
# ==========================================

class BlueprintExecuteRequest(BaseModel):
    """蓝图执行请求"""
    project_id: str
    blueprint_json: dict  # 蓝图数据
    enable_visual_review: bool = True
    max_review_attempts: int = 2


class BlueprintExecuteResponse(BaseModel):
    """蓝图执行响应"""
    task_id: str
    status: str = "submitted"
    message: str = "蓝图任务已提交到后台执行"


class BlueprintParseRequest(BaseModel):
    """蓝图解析请求（从 AI 输出中提取）"""
    ai_output: str


class BlueprintStateResponse(BaseModel):
    """蓝图状态响应"""
    task_id: str
    status: str
    project_goal: Optional[str] = None
    total_tasks: Optional[int] = None
    success_count: Optional[int] = None
    failed_count: Optional[int] = None
    nodes: Optional[dict] = None


# ==========================================
# 辅助函数：获取 Redis 客户端
# ==========================================

def get_redis_client():
    """获取 Redis 客户端"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=2,  # 与 celery_app 使用同一 db
        decode_responses=True
    )


# ==========================================
# POST /api/blueprint/execute - 执行蓝图（返回 task_id）
# ==========================================
@router.post("/execute", response_model=BlueprintExecuteResponse)
async def execute_blueprint(
    request: BlueprintExecuteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    执行 DAG 蓝图（异步 Celery 任务）

    接收蓝图 JSON，验证后提交到 Celery 后台执行。
    返回 task_id，前端通过 SSE 订阅事件流获取实时状态。

    架构优势：
    1. 不占用 HTTP 连接
    2. 服务重启后任务不丢失
    3. 支持水平扩展 Worker

    Returns:
        { task_id, status: "submitted", message }
    """
    from app.services.celery_app import execute_blueprint_task

    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    if not current_user.billing or current_user.billing.credits_balance <= 0:
        raise HTTPException(
            status_code=402,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用。"
        )

    # 3. 验证蓝图格式
    blueprint_data = request.blueprint_json
    if not blueprint_data.get("is_complex_task"):
        raise HTTPException(status_code=400, detail="蓝图格式错误：缺少 is_complex_task 标记")

    if not blueprint_data.get("tasks"):
        raise HTTPException(status_code=400, detail="蓝图格式错误：缺少任务列表")

    # 4. 获取 LLM 配置
    config = session.get(SystemConfig, 1)

    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")

    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    if is_local_model:
        api_key = db_api_key if db_api_key is not None else ""
    else:
        api_key = db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key

    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    user_id = current_user.id

    # 5. 构建 Celery 任务载荷
    payload = {
        "blueprint_json": blueprint_data,
        "project_id": request.project_id,
        "user_id": user_id,
        "api_key": api_key or "",
        "base_url": base_url,
        "model_name": model_name,
        "enable_visual_review": request.enable_visual_review,
        "max_review_attempts": request.max_review_attempts
    }

    log.info(f"🚀 [Blueprint] 提交蓝图执行任务 - project={request.project_id}, tasks={len(blueprint_data.get('tasks', []))}")

    # 6. 提交到 Celery
    task = execute_blueprint_task.delay(payload)
    task_id = str(task.id)

    log.info(f"✅ [Blueprint] 任务已提交 - task_id={task_id}")

    # 7. 注册任务到任务看板（Redis）
    #    参考 tasks.py 的 /api/tasks/submit 实现
    task_name = f"蓝图: {blueprint_data.get('project_goal', '未命名')[:50]}"

    # 存储任务详情
    redis_client.hset(f"task_info:{task_id}", mapping={
        "tool_id": "blueprint_dag",
        "project_id": str(request.project_id),
        "name": task_name,
        "created_at": str(time.time())
    })
    redis_client.expire(f"task_info:{task_id}", 86400 * 7)  # 保留 7 天

    # 添加到用户任务列表
    redis_client.lpush(f"user_tasks:{current_user.id}", task_id)
    redis_client.ltrim(f"user_tasks:{current_user.id}", 0, 99)  # 保留最近 100 个任务

    log.info(f"📋 [Blueprint] 任务已注册到看板 - user_id={current_user.id}")

    return BlueprintExecuteResponse(
        task_id=task_id,
        status="submitted",
        message="蓝图任务已提交到后台执行，请通过事件流获取实时状态"
    )


# ==========================================
# GET /api/blueprint/{task_id}/events/stream - SSE 事件流
# ==========================================
@router.get("/{task_id}/events/stream")
async def get_blueprint_events_stream(
    task_id: str,
    token: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    蓝图执行事件流（SSE）

    从 Redis 读取事件流，实时推送给前端。
    支持断点续传：客户端断开后可重新连接，从上次位置继续读取。

    注意：EventSource API 不支持自定义 header，因此通过 query parameter 传递 token。

    Args:
        task_id: Celery 任务 ID
        token: JWT 认证 token（query parameter）

    Returns:
        SSE 事件流
    """
    # 验证 token
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证 token")

    current_user = verify_token_and_get_user(token, session)
    redis_client = get_redis_client()
    event_key = f"{BLUEPRINT_EVENTS_PREFIX}{task_id}"

    async def event_generator():
        """SSE 事件生成器"""
        last_index = 0
        idle_count = 0
        max_idle = 60  # 最大空闲等待次数（60 * 5秒 = 5分钟）

        log.info(f"📡 [Blueprint SSE] 开始事件流 - task_id={task_id}")

        while True:
            # 从 Redis List 读取新事件
            events = redis_client.lrange(event_key, last_index, -1)

            if events:
                for event_str in events:
                    try:
                        event = json.loads(event_str)
                        # SSE 库只接受 event 和 data 字段，移除 timestamp 等额外字段
                        yield {
                            "event": event.get("event", "message"),
                            "data": event.get("data", "")
                        }
                        last_index += 1
                    except json.JSONDecodeError:
                        log.warning(f"⚠️ [Blueprint SSE] 无效事件: {event_str[:100]}")
                        continue

                # 检查是否收到 done 事件
                if events and json.loads(events[-1]).get("event") == "done":
                    log.info(f"🏁 [Blueprint SSE] 事件流结束 - task_id={task_id}")
                    break

                idle_count = 0  # 重置空闲计数
            else:
                # 没有新事件，等待
                idle_count += 1

                # 检查任务是否仍在运行
                info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
                status = redis_client.hget(info_key, "status")

                if status == "completed" or status == "failed":
                    # 任务已完成，推送 done 并结束
                    yield {"event": "done", "data": json.dumps({"message": "任务已完成"})}
                    break

                if idle_count >= max_idle:
                    # 超时，推送心跳保持连接
                    yield {"event": "heartbeat", "data": json.dumps({"timestamp": str(asyncio.get_event_loop().time())})}
                    idle_count = 0  # 重置计数

                await asyncio.sleep(1)  # 等待 1 秒

    return EventSourceResponse(event_generator())


# ==========================================
# GET /api/blueprint/{task_id}/state - 获取蓝图状态
# ==========================================
@router.get("/{task_id}/state", response_model=BlueprintStateResponse)
async def get_blueprint_state(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取蓝图执行状态

    返回 DAG 各节点的执行状态。

    Args:
        task_id: Celery 任务 ID

    Returns:
        蓝图状态信息
    """
    redis_client = get_redis_client()

    # 获取蓝图元数据
    info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
    info = redis_client.hgetall(info_key)

    if not info:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 获取节点状态
    state_key = f"{BLUEPRINT_STATE_PREFIX}{task_id}"
    nodes_raw = redis_client.hgetall(state_key)

    nodes = {}
    for node_id, state_str in nodes_raw.items():
        try:
            nodes[node_id] = json.loads(state_str)
        except json.JSONDecodeError:
            nodes[node_id] = {"raw": state_str}

    # 统计成功/失败数量
    success_count = sum(1 for n in nodes.values() if n.get("status") == "success")
    failed_count = sum(1 for n in nodes.values() if n.get("status") == "failed")

    return BlueprintStateResponse(
        task_id=task_id,
        status=info.get("status", "unknown"),
        project_goal=info.get("project_goal"),
        total_tasks=int(info.get("total_tasks", 0)) if info.get("total_tasks") else None,
        success_count=success_count,
        failed_count=failed_count,
        nodes=nodes
    )


# ==========================================
# POST /api/blueprint/parse - 从 AI 输出解析蓝图
# ==========================================
@router.post("/parse")
async def parse_blueprint(
    request: BlueprintParseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    从 AI 输出中解析蓝图 JSON

    支持两种格式：
    1. ```json_blueprint ... ```
    2. 直接的 JSON 对象

    Returns:
        解析后的蓝图数据
    """
    from app.services.orchestrator import extract_blueprint

    blueprint = extract_blueprint(request.ai_output)

    if not blueprint:
        return {
            "status": "error",
            "message": "未找到有效的蓝图数据"
        }

    return {
        "status": "success",
        "data": blueprint
    }


# ==========================================
# POST /api/blueprint/validate - 验证蓝图格式
# ==========================================
@router.post("/validate")
async def validate_blueprint(
    request: BlueprintExecuteRequest,
    current_user: User = Depends(get_current_user)
):
    """
    验证蓝图格式和依赖关系

    检查：
    1. 必要字段是否存在
    2. 任务 ID 是否唯一
    3. 依赖关系是否有效
    4. 是否存在循环依赖

    Returns:
        验证结果和拓扑排序后的执行顺序
    """
    from app.services.orchestrator import BlueprintOrchestrator

    blueprint_data = request.blueprint_json

    errors = []
    warnings = []

    # 1. 检查必要字段
    if not blueprint_data.get("project_goal"):
        errors.append("缺少 project_goal 字段")

    if not blueprint_data.get("is_complex_task"):
        warnings.append("is_complex_task 未设置为 true")

    tasks = blueprint_data.get("tasks", [])
    if not tasks:
        errors.append("任务列表为空")

    # 2. 检查任务 ID 唯一性
    task_ids = [t.get("task_id") for t in tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("存在重复的任务 ID")

    # 3. 尝试拓扑排序（检查依赖关系）
    execution_order = []
    try:
        orchestrator = BlueprintOrchestrator(blueprint_data)
        execution_order = orchestrator.topological_sort()
    except ValueError as e:
        errors.append(str(e))

    if errors:
        return {
            "status": "error",
            "valid": False,
            "errors": errors,
            "warnings": warnings
        }

    return {
        "status": "success",
        "valid": True,
        "execution_order": execution_order,
        "task_count": len(tasks),
        "warnings": warnings
    }


log.info("📐 Blueprint API 路由已加载（Celery 异步模式）")