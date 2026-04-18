"""
消息队列 API 路由

提供消息队列的 CRUD 端点：
- POST /api/chat/queue: 提交消息到队列
- GET /api/chat/queue/{session_id}: 获取队列状态
- PATCH /api/chat/queue/{item_id}: 编辑队列项
- DELETE /api/chat/queue/{item_id}: 删除队列项
- DELETE /api/chat/queue/session/{session_id}: 清空队列
- PATCH /api/chat/queue/reorder: 调整顺序
- POST /api/chat/queue/{session_id}/recover: 恢复中断的队列
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.database import get_session
from app.models.domain import User
from app.api.deps import get_current_user
from app.core.logger import log
from app.services import chat_queue_service

router = APIRouter()


# ==========================================
# Pydantic 请求模型
# ==========================================

class QueueAddRequest(BaseModel):
    """提交消息到队列"""
    session_id: str
    project_id: str
    message: str
    attachments: Optional[dict] = None


class QueueUpdateRequest(BaseModel):
    """编辑队列项"""
    message: Optional[str] = None
    attachments: Optional[dict] = None


class QueueReorderRequest(BaseModel):
    """调整队列顺序"""
    session_id: str
    item_ids: List[str]  # 按新顺序排列的 ID 列表


# ==========================================
# Pydantic 响应模型
# ==========================================

class QueueItemResponse(BaseModel):
    """队列项响应"""
    id: str
    session_id: str
    project_id: str
    status: str
    message: str
    attachments: Optional[dict] = None
    position: int
    result_message_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


def _item_to_response(item) -> QueueItemResponse:
    """将 ChatQueueItem 转换为响应模型"""
    return QueueItemResponse(
        id=item.id,
        session_id=item.session_id,
        project_id=item.project_id,
        status=item.status,
        message=item.message,
        attachments=item.attachments,
        position=item.position,
        result_message_id=item.result_message_id,
        error=item.error,
        created_at=item.created_at.isoformat() if item.created_at else "",
        started_at=item.started_at.isoformat() if item.started_at else None,
        completed_at=item.completed_at.isoformat() if item.completed_at else None,
    )


# ==========================================
# API 端点
# ==========================================

@router.post("/queue", response_model=QueueItemResponse)
async def add_to_queue(
    request: QueueAddRequest,
    current_user: User = Depends(get_current_user),
):
    """提交消息到队列"""
    try:
        item = await chat_queue_service.add_to_queue(
            session_id=request.session_id,
            project_id=request.project_id,
            user_id=current_user.id,
            message=request.message,
            attachments=request.attachments,
        )
        return _item_to_response(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/queue/{session_id}", response_model=List[QueueItemResponse])
async def get_queue_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取队列状态"""
    items = chat_queue_service.get_queue_status(session_id)
    return [_item_to_response(item) for item in items]


@router.patch("/queue/{item_id}", response_model=QueueItemResponse)
async def update_queue_item(
    item_id: str,
    request: QueueUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """编辑队列项（仅 pending 状态可编辑）"""
    try:
        item = chat_queue_service.update_queue_item(
            item_id=item_id,
            user_id=current_user.id,
            message=request.message,
            attachments=request.attachments,
        )
        if not item:
            raise HTTPException(status_code=404, detail="队列项不存在")
        return _item_to_response(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/queue/{item_id}")
async def delete_queue_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    """删除队列项"""
    try:
        success = chat_queue_service.delete_queue_item(
            item_id=item_id,
            user_id=current_user.id,
        )
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/queue/session/{session_id}")
async def clear_queue(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """清空会话的所有 pending 队列项"""
    count = chat_queue_service.clear_queue(
        session_id=session_id,
        user_id=current_user.id,
    )
    return {"cleared": count}


@router.patch("/queue/reorder", response_model=List[QueueItemResponse])
async def reorder_queue(
    request: QueueReorderRequest,
    current_user: User = Depends(get_current_user),
):
    """调整队列中消息的顺序"""
    try:
        items = chat_queue_service.reorder_queue(
            session_id=request.session_id,
            user_id=current_user.id,
            item_ids=request.item_ids,
        )
        return [_item_to_response(item) for item in items]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/queue/{session_id}/recover")
async def recover_queue(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """恢复中断的队列（SSE 重连后调用）"""
    await chat_queue_service.recover_queue(session_id)
    return {"success": True}