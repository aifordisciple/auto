import json
import asyncio
import time
from typing import Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from celery.result import AsyncResult

from app.services.celery_app import TASK_REGISTRY, redis_client
from app.api.deps import get_current_user
from app.models.domain import User


# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket):
        if task_id in self.active_connections:
            self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def send_message(self, task_id: str, message: dict):
        if task_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[task_id]:
                try:
                    await websocket.send_json(message)
                except:
                    disconnected.append(websocket)
            for ws in disconnected:
                self.disconnect(task_id, ws)

manager = ConnectionManager()

router = APIRouter()

class TaskSubmitRequest(BaseModel):
    tool_id: str
    parameters: dict
    project_id: Optional[int] = None


@router.post("/submit")
async def submit_task(request: TaskSubmitRequest, current_user: User = Depends(get_current_user)):
    """提交一个异步计算任务"""
    if request.tool_id not in TASK_REGISTRY:
        return {"status": "error", "message": f"Unknown tool: {request.tool_id}"}
    
    task_func = TASK_REGISTRY[request.tool_id]
    task = task_func.delay(request.parameters)
    
    # 记录任务到用户任务列表 (Redis)
    task_info = {
        "task_id": task.id,
        "tool_id": request.tool_id,
        "project_id": request.project_id,
        "status": "PENDING",
        "created_at": time.time(),
        "name": f"{request.tool_id.replace('-', ' ').title()} Analysis"
    }
    
    # 存储任务详情
    redis_client.hset(f"task_info:{task.id}", mapping={
        "tool_id": request.tool_id,
        "project_id": str(request.project_id) if request.project_id else "",
        "name": task_info["name"],
        "created_at": str(task_info["created_at"])
    })
    redis_client.expire(f"task_info:{task.id}", 86400 * 7)  # 保留7天
    
    # 添加到用户任务列表
    redis_client.lpush(f"user_tasks:{current_user.id}", task.id)
    redis_client.ltrim(f"user_tasks:{current_user.id}", 0, 99)  # 保留最近100个任务
    
    return {"status": "submitted", "task_id": task.id, "tool_id": request.tool_id}


@router.get("/list")
async def list_user_tasks(current_user: User = Depends(get_current_user)):
    """获取用户所有任务 (看板视图)"""
    task_ids = redis_client.lrange(f"user_tasks:{current_user.id}", 0, 99)
    
    tasks = []
    for task_id in task_ids:
        task_info = redis_client.hgetall(f"task_info:{task_id}")
        if not task_info:
            continue
            
        # 获取最新状态
        try:
            task_result = AsyncResult(task_id)
            status = task_result.status
            result = task_result.result if task_result.ready() else None
        except:
            status = "UNKNOWN"
            result = None
        
        # 获取进度
        progress = None
        try:
            if hasattr(task_result, 'info') and isinstance(task_result.info, dict):
                progress = task_result.info.get('progress')
        except:
            pass
        
        tasks.append({
            "task_id": task_id,
            "name": task_info.get("name", "Unknown Task"),
            "tool_id": task_info.get("tool_id", ""),
            "project_id": task_info.get("project_id", ""),
            "status": status,
            "progress": progress,
            "result": result,
            "created_at": float(task_info.get("created_at", 0))
        })
    
    return {"tasks": tasks, "total": len(tasks)}


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


@router.websocket("/{task_id}/ws")
async def websocket_task_status(websocket: WebSocket, task_id: str):
    """WebSocket 实时获取任务状态"""
    await manager.connect(task_id, websocket)
    try:
        task_result = AsyncResult(task_id)
        last_status = None
        
        while True:
            # 检查任务状态
            current_status = task_result.status
            
            # 如果状态变化，发送更新
            if current_status != last_status:
                message = {
                    "type": "status",
                    "task_id": task_id,
                    "status": current_status,
                    "result": task_result.result if task_result.ready() else None,
                    "progress": task_result.info.get('progress') if isinstance(task_result.info, dict) else None
                }
                await manager.send_message(task_id, message)
                last_status = current_status
            
            # 如果任务完成，退出循环
            if task_result.ready():
                break
            
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(task_id, websocket)
    except Exception as e:
        await manager.send_message(task_id, {
            "type": "error",
            "task_id": task_id,
            "error": str(e)
        })
        manager.disconnect(task_id, websocket)


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
async def list_available_tasks():
    """列出所有可用任务"""
    return {"tasks": list(TASK_REGISTRY.keys())}
