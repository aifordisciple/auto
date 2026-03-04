import json
import asyncio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from celery.result import AsyncResult

# ✨ 引入刚刚拆分的服务
from app.services.celery_app import TASK_REGISTRY, redis_client

router = APIRouter()

class TaskSubmitRequest(BaseModel):
    tool_id: str
    parameters: dict

@router.post("/submit")
async def submit_task(request: TaskSubmitRequest):
    """提交一个异步计算任务"""
    if request.tool_id not in TASK_REGISTRY:
        return {"status": "error", "message": f"Unknown tool: {request.tool_id}"}
    
    task_func = TASK_REGISTRY[request.tool_id]
    task = task_func.delay(request.parameters)
    return {"status": "submitted", "task_id": task.id, "tool_id": request.tool_id}

@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    """轮询获取任务当前状态"""
    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id, 
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None,
        "progress": task_result.info.get('progress') if isinstance(task_result.info, dict) else None
    }

@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    """获取任务日志"""
    log_key = f"task_logs:{task_id}"
    logs = redis_client.lrange(log_key, 0, -1)
    return {"task_id": task_id, "logs": logs}

@router.get("/{task_id}/logs/stream")
async def stream_task_logs(task_id: str):
    """SSE 流式读取任务终端日志"""
    log_key = f"task_logs:{task_id}"
    
    async def log_generator():
        last_index = 0
        task_result = AsyncResult(task_id)
        
        while True:
            logs = redis_client.lrange(log_key, last_index, -1)
            if logs:
                for log_line in logs: 
                    yield {"event": "log", "data": json.dumps({"text": log_line})}
                last_index += len(logs)
                
            if task_result.ready() and last_index >= redis_client.llen(log_key):
                yield {"event": "done", "data": "[DONE]"}
                break
            await asyncio.sleep(0.5)
            
    return EventSourceResponse(log_generator())

@router.get("")
async def list_tasks():
    """列出所有可用任务"""
    return {"tasks": list(TASK_REGISTRY.keys())}
