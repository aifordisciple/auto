"""
超级执行者 API 路由 - 外部 AI 代码的执行入口

提供两个核心接口：
1. POST /api/super-executor/execute - 提交执行任务
2. GET /api/super-executor/{task_id}/events/stream - SSE 事件流

架构设计：
- 前端通过 POST 提交任务，获得 task_id
- 后端将任务存入 Redis，通过 Celery 异步执行
- 前端通过 SSE 订阅事件流，实时获取执行状态
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

from app.core.database import get_session
from app.core.logger import log
from app.core.config import settings
from app.api.deps import get_current_user, verify_token_and_get_user
from app.models.domain import User, Project, SystemConfig
from app.services.celery_app import redis_client


router = APIRouter()


# ==========================================
# Redis 键前缀常量
# ==========================================
SUPER_EXECUTOR_EVENTS_PREFIX = "super_executor_events:"
SUPER_EXECUTOR_STATE_PREFIX = "super_executor_state:"
SUPER_EXECUTOR_INFO_PREFIX = "super_executor_info:"

# 事件流保留时间（秒）
EVENT_TTL = 86400  # 24 小时


# ==========================================
# Request/Response Models
# ==========================================

class SuperExecutorRequest(BaseModel):
    """超级执行请求"""
    project_id: str
    raw_input: str  # 用户粘贴的外部 AI 输出
    version: str = "v4"  # 执行器版本: "v3" 或 "v4"，默认使用 V4（三步执行流程）


class SuperExecutorResponse(BaseModel):
    """超级执行响应"""
    task_id: str
    status: str = "submitted"
    message: str = "超级执行任务已提交"


# ==========================================
# 辅助函数
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


def push_event_to_redis(
    redis_client,
    task_id: str,
    event_type: str,
    data: dict
) -> None:
    """
    将事件推送到 Redis 事件流

    Args:
        redis_client: Redis 客户端
        task_id: 任务 ID
        event_type: 事件类型
        data: 事件数据
    """
    event_key = f"{SUPER_EXECUTOR_EVENTS_PREFIX}{task_id}"

    event = {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False),
        "timestamp": time.time()
    }

    # 推送到 List（右进）
    redis_client.rpush(event_key, json.dumps(event, ensure_ascii=False))

    # 设置过期时间
    redis_client.expire(event_key, EVENT_TTL)

    log.debug(f"📤 [SuperExecutor] 推送事件: {event_type} -> {task_id}")


def set_task_info(
    redis_client,
    task_id: str,
    project_id: str,
    user_id: int,
    raw_input_preview: str
) -> None:
    """
    设置任务元数据

    Args:
        redis_client: Redis 客户端
        task_id: 任务 ID
        project_id: 项目 ID
        user_id: 用户 ID
        raw_input_preview: 输入预览
    """
    info_key = f"{SUPER_EXECUTOR_INFO_PREFIX}{task_id}"

    info_data = {
        "project_id": project_id,
        "user_id": user_id,
        "raw_input_preview": raw_input_preview[:500],
        "status": "running",
        "created_at": str(time.time())
    }

    redis_client.hset(info_key, mapping=info_data)
    redis_client.expire(info_key, EVENT_TTL)


# ==========================================
# POST /api/super-executor/execute
# ==========================================
@router.post("/execute", response_model=SuperExecutorResponse)
async def execute_super_executor(
    request: SuperExecutorRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    提交超级执行任务

    接收用户粘贴的外部 AI 输出，解析代码并执行。
    返回 task_id，前端通过 SSE 订阅事件流获取实时状态。

    Returns:
        { task_id, status: "submitted", message }
    """
    from app.services.celery_app import execute_super_executor_task

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

    # 3. 验证输入
    if not request.raw_input or len(request.raw_input.strip()) < 10:
        raise HTTPException(status_code=400, detail="输入内容过短，请粘贴完整的外部 AI 输出")

    # 4. 获取 LLM 配置（用于代码修复）
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
    # 根据版本选择执行器
    version = getattr(request, 'version', 'v4')
    log.info(f"🚀 [SuperExecutor] 提交执行任务 - project={request.project_id}, user={user_id}, version={version}")

    payload = {
        "raw_input": request.raw_input,
        "project_id": request.project_id,
        "user_id": user_id,
        "api_key": api_key or "",
        "base_url": base_url,
        "model_name": model_name,
        "version": version  # 传递版本参数
    }

    # 6. 提交到 Celery
    task = execute_super_executor_task.delay(payload)
    task_id = str(task.id)

    log.info(f"✅ [SuperExecutor] 任务已提交 - task_id={task_id}, version={version}")

    # 7. 注册任务到任务看板
    task_name = f"超级执行: {request.raw_input[:50]}..."

    redis_client.hset(f"task_info:{task_id}", mapping={
        "tool_id": "super_executor",
        "project_id": str(request.project_id),
        "name": task_name,
        "created_at": str(time.time())
    })
    redis_client.expire(f"task_info:{task_id}", 86400 * 7)  # 保留 7 天

    # 添加到用户任务列表
    redis_client.lpush(f"user_tasks:{current_user.id}", task_id)
    redis_client.ltrim(f"user_tasks:{current_user.id}", 0, 99)  # 保留最近 100 个任务

    log.info(f"📋 [SuperExecutor] 任务已注册到看板 - user_id={current_user.id}")

    return SuperExecutorResponse(
        task_id=task_id,
        status="submitted",
        message="超级执行任务已提交，请通过事件流获取实时状态"
    )


# ==========================================
# GET /api/super-executor/{task_id}/events/stream
# ==========================================
@router.get("/{task_id}/events/stream")
async def get_super_executor_events_stream(
    task_id: str,
    token: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    超级执行事件流（SSE）

    从 Redis 读取事件流，实时推送给前端。
    支持断点续传：客户端断开后可重新连接，从上次位置继续读取。

    注意：EventSource API 不支持自定义 header，因此通过 query parameter 传递 token。

    Args:
        task_id: 任务 ID
        token: JWT 认证 token（query parameter）

    Returns:
        SSE 事件流
    """
    # 验证 token
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证 token")

    current_user = verify_token_and_get_user(token, session)
    redis_client = get_redis_client()
    event_key = f"{SUPER_EXECUTOR_EVENTS_PREFIX}{task_id}"

    async def event_generator():
        """SSE 事件生成器"""
        last_index = 0
        idle_count = 0
        max_idle = 300  # 最大空闲等待次数（300 * 1秒 = 5分钟）

        log.info(f"📡 [SuperExecutor SSE] 开始事件流 - task_id={task_id}")

        while True:
            # 从 Redis List 读取新事件
            events = redis_client.lrange(event_key, last_index, -1)

            if events:
                for event_str in events:
                    try:
                        event = json.loads(event_str)
                        # SSE 库只接受 event 和 data 字段
                        yield {
                            "event": event.get("event", "message"),
                            "data": event.get("data", "")
                        }
                        last_index += 1
                    except json.JSONDecodeError:
                        log.warning(f"⚠️ [SuperExecutor SSE] 无效事件: {event_str[:100]}")
                        continue

                # 检查是否收到 done 事件
                if events and json.loads(events[-1]).get("event") == "done":
                    log.info(f"🏁 [SuperExecutor SSE] 事件流结束 - task_id={task_id}")
                    break

                idle_count = 0  # 重置空闲计数
            else:
                # 没有新事件，等待
                idle_count += 1

                # 检查任务是否仍在运行
                info_key = f"{SUPER_EXECUTOR_INFO_PREFIX}{task_id}"
                status = redis_client.hget(info_key, "status")

                if status == "completed" or status == "failed":
                    # 任务已完成，推送 done 并结束
                    yield {"event": "done", "data": json.dumps({"message": "任务已完成"})}
                    break

                if idle_count >= max_idle:
                    # 超时，推送心跳保持连接
                    yield {"event": "heartbeat", "data": json.dumps({"timestamp": str(time.time())})}
                    idle_count = 0  # 重置计数

                await asyncio.sleep(1)  # 等待 1 秒

    return EventSourceResponse(event_generator())


# ==========================================
# GET /api/super-executor/{task_id}/state
# ==========================================
@router.get("/{task_id}/state")
async def get_super_executor_state(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取超级执行状态

    返回任务执行状态和结果摘要。

    Args:
        task_id: 任务 ID

    Returns:
        任务状态信息
    """
    redis_client = get_redis_client()

    # 获取任务元数据
    info_key = f"{SUPER_EXECUTOR_INFO_PREFIX}{task_id}"
    info = redis_client.hgetall(info_key)

    if not info:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 获取节点状态
    state_key = f"{SUPER_EXECUTOR_STATE_PREFIX}{task_id}"
    state = redis_client.hgetall(state_key)

    return {
        "task_id": task_id,
        "status": info.get("status", "unknown"),
        "project_id": info.get("project_id"),
        "user_id": info.get("user_id"),
        "created_at": info.get("created_at"),
        "state": state
    }


# ==========================================
# GET /api/super-executor/files/download
# ==========================================
@router.get("/files/download")
async def download_file(
    path: str,
    token: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    下载文件

    Args:
        path: 文件绝对路径
        token: JWT 认证 token

    Returns:
        文件内容（下载）
    """
    from fastapi.responses import FileResponse
    import mimetypes

    # 验证 token
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证 token")

    current_user = verify_token_and_get_user(token, session)

    # 安全检查：路径必须在 uploads 目录下
    if not path.startswith("/workspace/"):
        raise HTTPException(status_code=403, detail="无权访问此路径")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")

    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="路径不是文件")

    # 获取文件名和 MIME 类型
    filename = os.path.basename(path)
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "application/octet-stream"

    log.info(f"📥 [SuperExecutor] 下载文件: {path}")

    return FileResponse(
        path=path,
        filename=filename,
        media_type=mime_type
    )


# ==========================================
# GET /api/super-executor/files/preview
# ==========================================
@router.get("/files/preview")
async def preview_file(
    path: str,
    token: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    预览文件

    Args:
        path: 文件绝对路径
        token: JWT 认证 token

    Returns:
        文件内容（预览）
    """
    from fastapi.responses import FileResponse, PlainTextResponse
    import mimetypes

    # 验证 token
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证 token")

    current_user = verify_token_and_get_user(token, session)

    # 安全检查：路径必须在 uploads 目录下
    if not path.startswith("/workspace/"):
        raise HTTPException(status_code=403, detail="无权访问此路径")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")

    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="路径不是文件")

    # 获取文件扩展名
    ext = os.path.splitext(path)[1].lower()

    # 图片文件直接返回
    image_exts = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
    if ext in image_exts:
        mime_type, _ = mimetypes.guess_type(path)
        log.info(f"👁️ [SuperExecutor] 预览图片: {path}")
        return FileResponse(path=path, media_type=mime_type or "image/png")

    # PDF 文件直接返回
    if ext == ".pdf":
        log.info(f"👁️ [SuperExecutor] 预览 PDF: {path}")
        return FileResponse(path=path, media_type="application/pdf")

    # 文本文件返回内容
    text_exts = [".txt", ".csv", ".tsv", ".json", ".md", ".log", ".py", ".r", ".sh"]
    if ext in text_exts:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(100000)  # 最多读取 100KB
            log.info(f"👁️ [SuperExecutor] 预览文本: {path}")
            return PlainTextResponse(content=content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")

    # 其他文件类型返回下载
    filename = os.path.basename(path)
    mime_type, _ = mimetypes.guess_type(path)
    log.info(f"👁️ [SuperExecutor] 预览文件(下载模式): {path}")
    return FileResponse(
        path=path,
        filename=filename,
        media_type=mime_type or "application/octet-stream"
    )


log.info("🦾 超级执行者 API 路由已加载")