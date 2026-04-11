"""
埋点 API 路由

提供用户行为埋点上报接口：
1. POST /events - 批量上报事件
2. POST /event - 单个事件上报
3. GET /stats - 获取统计信息

设计原则：
- 支持批量上报提高效率
- 异步处理避免阻塞
- 返回简要统计信息
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.logger import log
from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.domain import User
from app.services.behavior_tracker import (
    BehaviorTracker,
    BehaviorType,
    BehaviorEvent,
)


# ==========================================
# 请求模型
# ==========================================

class EventRequest(BaseModel):
    """单个事件请求"""

    user_id: int = Field(description="用户 ID")
    session_id: str = Field(description="会话 ID")
    event_type: str = Field(description="事件类型")

    # 可选字段
    skill_id: Optional[str] = Field(default=None, description="技能 ID")
    skill_name: Optional[str] = Field(default=None, description="技能名称")
    query: Optional[str] = Field(default=None, description="用户查询")
    match_source: Optional[str] = Field(default=None, description="匹配来源")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="执行参数")
    execution_time: Optional[float] = Field(default=None, description="执行耗时")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")


class BatchEventsRequest(BaseModel):
    """批量事件请求"""

    events: List[EventRequest] = Field(description="事件列表")


# ==========================================
# 响应模型
# ==========================================

class EventResponse(BaseModel):
    """事件响应"""

    success: bool = Field(description="是否成功")
    message: str = Field(description="消息")
    events_processed: int = Field(description="处理的事件数")


class StatsResponse(BaseModel):
    """统计响应"""

    total_events: int = Field(description="总事件数")
    events_today: int = Field(description="今日事件数")
    top_event_types: List[Dict[str, Any]] = Field(description="热门事件类型")


# ==========================================
# 路由定义
# ==========================================

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/events", response_model=EventResponse)
async def batch_events(
    request: BatchEventsRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    批量上报事件

    用于前端批量上报埋点事件，支持页面卸载时的 sendBeacon 调用。

    Args:
        request: 批量事件请求
        background_tasks: 后台任务
        session: 数据库会话
        current_user: 当前用户

    Returns:
        上报结果
    """
    try:
        tracker = BehaviorTracker(session)
        events = []

        for event_req in request.events:
            # 验证事件类型
            try:
                event_type = BehaviorType(event_req.event_type)
            except ValueError:
                log.warning(f"[Analytics] 未知事件类型: {event_req.event_type}")
                continue

            event = BehaviorEvent(
                user_id=event_req.user_id,
                session_id=event_req.session_id,
                event_type=event_type,
                skill_id=event_req.skill_id,
                skill_name=event_req.skill_name,
                query=event_req.query,
                match_source=event_req.match_source,
                confidence=event_req.confidence,
                parameters=event_req.parameters,
                execution_time=event_req.execution_time,
                error_message=event_req.error_message,
                metadata=event_req.metadata,
            )
            events.append(event)

        # 批量记录
        results = tracker.batch_track(events)
        success_count = sum(1 for r in results if r)

        log.info(f"[Analytics] 批量上报: {success_count}/{len(events)} 成功")

        return EventResponse(
            success=True,
            message=f"成功处理 {success_count} 个事件",
            events_processed=success_count,
        )

    except Exception as e:
        log.error(f"[Analytics] 批量上报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/event", response_model=EventResponse)
async def single_event(
    request: EventRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    单个事件上报

    用于实时上报单个埋点事件。

    Args:
        request: 事件请求
        session: 数据库会话
        current_user: 当前用户

    Returns:
        上报结果
    """
    try:
        # 验证事件类型
        try:
            event_type = BehaviorType(request.event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"未知事件类型: {request.event_type}")

        tracker = BehaviorTracker(session)
        event = BehaviorEvent(
            user_id=request.user_id,
            session_id=request.session_id,
            event_type=event_type,
            skill_id=request.skill_id,
            skill_name=request.skill_name,
            query=request.query,
            match_source=request.match_source,
            confidence=request.confidence,
            parameters=request.parameters,
            execution_time=request.execution_time,
            error_message=request.error_message,
            metadata=request.metadata,
        )

        result = tracker.track(event)

        return EventResponse(
            success=result,
            message="事件已记录" if result else "事件记录失败",
            events_processed=1 if result else 0,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[Analytics] 单事件上报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取埋点统计信息

    返回系统埋点统计概览。

    Args:
        session: 数据库会话
        current_user: 当前用户

    Returns:
        统计信息
    """
    try:
        from app.services.behavior_tracker import BehaviorRecord
        from datetime import timedelta
        from sqlmodel import select, func

        # 总事件数
        total = session.exec(
            select(func.count(BehaviorRecord.id))
        ).one()

        # 今日事件数
        today_start = datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_count = session.exec(
            select(func.count(BehaviorRecord.id))
            .where(BehaviorRecord.created_at >= today_start)
        ).one()

        # 按事件类型统计
        type_counts = session.exec(
            select(
                BehaviorRecord.event_type,
                func.count(BehaviorRecord.id).label("count")
            )
            .group_by(BehaviorRecord.event_type)
            .order_by(func.count(BehaviorRecord.id).desc())
            .limit(5)
        ).all()

        top_types = [
            {"event_type": row[0], "count": row[1]}
            for row in type_counts
        ]

        return StatsResponse(
            total_events=total or 0,
            events_today=today_count or 0,
            top_event_types=top_types,
        )

    except Exception as e:
        log.error(f"[Analytics] 获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 公开端点（不需要认证）
# ==========================================

@router.post("/public/events")
async def public_batch_events(
    request: BatchEventsRequest,
    session: Session = Depends(get_session),
):
    """
    公开的批量上报端点

    用于不需要用户认证的场景（如页面卸载时的 sendBeacon）。
    注意：生产环境应考虑添加 API Key 或其他验证方式。
    """
    try:
        tracker = BehaviorTracker(session)
        events = []

        for event_req in request.events:
            try:
                event_type = BehaviorType(event_req.event_type)
            except ValueError:
                continue

            event = BehaviorEvent(
                user_id=event_req.user_id,
                session_id=event_req.session_id,
                event_type=event_type,
                skill_id=event_req.skill_id,
                skill_name=event_req.skill_name,
                query=event_req.query,
                match_source=event_req.match_source,
                confidence=event_req.confidence,
                parameters=event_req.parameters,
                execution_time=event_req.execution_time,
                error_message=event_req.error_message,
                metadata=event_req.metadata,
            )
            events.append(event)

        results = tracker.batch_track(events)
        success_count = sum(1 for r in results if r)

        return EventResponse(
            success=True,
            message=f"成功处理 {success_count} 个事件",
            events_processed=success_count,
        )

    except Exception as e:
        log.error(f"[Analytics] 公开批量上报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


log.info("✅ 埋点 API 路由已加载")