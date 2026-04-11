"""
Claude Code 执行器 API 路由

提供 Claude Code 执行功能的 HTTP 和 WebSocket 端点。

API 端点：
- POST /start: 启动执行
- GET /ws/{session_id}: WebSocket 实时流
- POST /stop/{session_id}: 停止执行
- GET /config: 获取配置
- PUT /config: 更新配置
- GET /check-permission: 检查用户权限
- GET /permissions: 获取授权列表（管理员）
- POST /permissions/grant: 授权用户（管理员）
- DELETE /permissions/{user_id}: 撤销授权（管理员）
"""

import json
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import engine
from app.api.deps import get_current_user, get_current_superuser
from app.models.domain import User, ClaudeExecutorPermission, ClaudeExecutorPermissionCreate, ClaudeExecutorPermissionUpdate, ClaudeExecutorPermissionPublic
from app.services.claude_config_service import claude_config_service
from app.services.claude_executor_service import claude_executor_service, ClaudeSession
from app.core.logger import log


router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

class StartExecutionRequest(BaseModel):
    """启动执行请求"""
    project_id: str
    prompt: str
    mode: str = "host"  # "host" or "container"


class StartExecutionResponse(BaseModel):
    """启动执行响应"""
    session_id: str
    websocket_url: str


class PermissionCheckResponse(BaseModel):
    """权限检查响应"""
    allowed: bool
    modes: List[str] = []
    message: str = ""


class ConfigResponse(BaseModel):
    """配置响应"""
    api_config: dict
    settings_path: str


class UpdateConfigRequest(BaseModel):
    """更新配置请求"""
    settings: dict


class ValidateResponse(BaseModel):
    """验证响应"""
    success: bool
    message: str


# ==========================================
# 权限检查工具函数
# ==========================================

def get_db_session():
    """获取数据库会话"""
    return Session(engine)


def check_user_permission(user_id: int, mode: str) -> tuple[bool, List[str]]:
    """
    检查用户是否有执行权限

    Args:
        user_id: 用户 ID
        mode: 请求的执行模式

    Returns:
        (是否允许, 允许的模式列表)
    """
    session = get_db_session()
    try:
        permission = session.exec(
            select(ClaudeExecutorPermission).where(ClaudeExecutorPermission.user_id == user_id)
        ).first()

        if not permission:
            return False, []

        # 检查是否过期
        if permission.expires_at and permission.expires_at < datetime.utcnow():
            return False, []

        allowed_modes = permission.allowed_modes or ["container"]

        if mode in allowed_modes:
            return True, allowed_modes

        return False, allowed_modes

    finally:
        session.close()


# ==========================================
# API 端点
# ==========================================

@router.post("/start", response_model=StartExecutionResponse)
async def start_execution(
    request: StartExecutionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    启动 Claude Code 执行

    流程：
    1. 检查用户权限
    2. 创建执行会话
    3. 返回 WebSocket URL
    """
    # 检查权限
    allowed, allowed_modes = check_user_permission(current_user.id, request.mode)

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"您没有使用 Claude Code ({request.mode}模式) 的权限。请联系管理员申请。"
        )

    # 创建会话
    session = claude_executor_service.create_session(
        project_id=request.project_id,
        user_id=current_user.id,
        mode=request.mode
    )

    # 构建 WebSocket URL
    websocket_url = f"/api/claude-executor/ws/{session.session_id}"

    log.info(f"[ClaudeAPI] 启动执行: session={session.session_id}, user={current_user.id}, mode={request.mode}")

    return StartExecutionResponse(
        session_id=session.session_id,
        websocket_url=websocket_url
    )


@router.websocket("/ws/{session_id}")
async def websocket_execution(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="JWT 认证 token"),
    prompt: str = Query(..., description="执行提示")
):
    """
    WebSocket 执行端点

    实时流输出 Claude Code 执行过程
    """
    from app.api.deps import verify_token_and_get_user

    session = get_db_session()
    claude_session = None

    try:
        # 验证用户
        user = verify_token_and_get_user(token, session)
        if not user:
            await websocket.close(code=4001, reason="认证失败")
            return

        # 获取执行会话
        claude_session = claude_executor_service.get_session(session_id)
        if not claude_session:
            await websocket.close(code=4004, reason="会话不存在")
            return

        if claude_session.user_id != user.id:
            await websocket.close(code=4003, reason="无权访问此会话")
            return

        # 接受 WebSocket 连接
        await websocket.accept()

        log.info(f"[ClaudeWS] WebSocket 连接建立: session={session_id}")

        # 发送欢迎消息
        await websocket.send_json({
            "type": "status",
            "status": "starting",
            "message": f"正在启动 Claude Code ({claude_session.mode}模式)...",
            "timestamp": datetime.utcnow().isoformat()
        })

        # 输出回调
        async def output_callback(line: str):
            try:
                # 尝试解析 JSON 行
                if line.startswith('{'):
                    data = json.loads(line)
                    await websocket.send_json({
                        "type": "output",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    await websocket.send_json({
                        "type": "output",
                        "content": line,
                        "timestamp": datetime.utcnow().isoformat()
                    })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "output",
                    "content": line,
                    "timestamp": datetime.utcnow().isoformat()
                })

        # 执行
        result = await claude_executor_service.execute(
            session=claude_session,
            prompt=prompt,
            output_callback=output_callback
        )

        # 发送完成状态
        await websocket.send_json({
            "type": "status",
            "status": "completed" if result.success else "error",
            "exit_code": result.exit_code,
            "execution_time": result.execution_time_seconds,
            "timestamp": datetime.utcnow().isoformat()
        })

        # 发送战报
        await websocket.send_json({
            "type": "battle_report",
            "data": result.battle_report,
            "timestamp": datetime.utcnow().isoformat()
        })

        log.info(f"[ClaudeWS] 执行完成: session={session_id}, success={result.success}")

    except WebSocketDisconnect:
        log.info(f"[ClaudeWS] WebSocket 断开: session={session_id}")
    except Exception as e:
        log.error(f"[ClaudeWS] WebSocket 错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass
    finally:
        session.close()
        if claude_session:
            claude_executor_service.cleanup_session(session_id)


@router.post("/stop/{session_id}")
async def stop_execution(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """停止执行"""
    claude_session = claude_executor_service.get_session(session_id)

    if not claude_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if claude_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此会话")

    success = await claude_executor_service.stop_session(session_id)

    return {"success": success, "session_id": session_id}


@router.get("/check-permission", response_model=PermissionCheckResponse)
async def check_permission(current_user: User = Depends(get_current_user)):
    """检查当前用户的 Claude Code 执行权限"""
    session = get_db_session()
    try:
        permission = session.exec(
            select(ClaudeExecutorPermission).where(ClaudeExecutorPermission.user_id == current_user.id)
        ).first()

        if not permission:
            return PermissionCheckResponse(
                allowed=False,
                modes=[],
                message="您没有 Claude Code 执行权限，请联系管理员申请"
            )

        # 检查是否过期
        if permission.expires_at and permission.expires_at < datetime.utcnow():
            return PermissionCheckResponse(
                allowed=False,
                modes=[],
                message="您的授权已过期，请联系管理员续期"
            )

        return PermissionCheckResponse(
            allowed=True,
            modes=permission.allowed_modes or ["container"],
            message=""
        )

    finally:
        session.close()


@router.get("/config", response_model=ConfigResponse)
async def get_config(current_user: User = Depends(get_current_user)):
    """获取 Claude API 配置（仅管理员）"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    api_config = claude_config_service.get_api_config()
    settings_path = str(claude_config_service.get_settings_file_path())

    return ConfigResponse(
        api_config=api_config,
        settings_path=settings_path
    )


@router.put("/config")
async def update_config(
    request: UpdateConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """更新配置（仅管理员）"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    success = claude_config_service.update_settings(request.settings)

    if not success:
        raise HTTPException(status_code=500, detail="更新配置失败")

    return {"success": True, "message": "配置已更新"}


@router.post("/validate", response_model=ValidateResponse)
async def validate_connection(current_user: User = Depends(get_current_user)):
    """验证 API 连接（仅管理员）"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    result = await claude_config_service.validate_connection()

    return ValidateResponse(
        success=result["success"],
        message=result["message"]
    )


# ==========================================
# 管理员授权管理端点
# ==========================================

@router.get("/permissions", response_model=List[ClaudeExecutorPermissionPublic])
async def list_permissions(
    current_user: User = Depends(get_current_superuser)
):
    """获取所有授权用户列表（仅超级管理员）"""
    session = get_db_session()
    try:
        permissions = session.exec(select(ClaudeExecutorPermission)).all()
        return permissions
    finally:
        session.close()


@router.post("/permissions/grant", response_model=ClaudeExecutorPermissionPublic)
async def grant_permission(
    request: ClaudeExecutorPermissionCreate,
    current_user: User = Depends(get_current_superuser)
):
    """授权用户使用 Claude Code（仅超级管理员）"""
    session = get_db_session()
    try:
        # 检查用户是否存在
        target_user = session.get(User, request.user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 检查是否已有权限
        existing = session.exec(
            select(ClaudeExecutorPermission).where(ClaudeExecutorPermission.user_id == request.user_id)
        ).first()

        if existing:
            # 更新现有权限
            existing.allowed_modes = request.allowed_modes
            existing.expires_at = request.expires_at
            existing.notes = request.notes
            existing.granted_by = current_user.id
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        # 创建新权限
        permission = ClaudeExecutorPermission(
            user_id=request.user_id,
            allowed_modes=request.allowed_modes,
            granted_by=current_user.id,
            expires_at=request.expires_at,
            notes=request.notes
        )
        session.add(permission)
        session.commit()
        session.refresh(permission)

        log.info(f"[ClaudeAPI] 授权用户: user={request.user_id}, modes={request.allowed_modes}, by={current_user.id}")

        return permission

    finally:
        session.close()


@router.delete("/permissions/{user_id}")
async def revoke_permission(
    user_id: int,
    current_user: User = Depends(get_current_superuser)
):
    """撤销用户授权（仅超级管理员）"""
    session = get_db_session()
    try:
        permission = session.exec(
            select(ClaudeExecutorPermission).where(ClaudeExecutorPermission.user_id == user_id)
        ).first()

        if not permission:
            raise HTTPException(status_code=404, detail="授权记录不存在")

        session.delete(permission)
        session.commit()

        log.info(f"[ClaudeAPI] 撤销授权: user={user_id}, by={current_user.id}")

        return {"success": True, "message": "授权已撤销"}

    finally:
        session.close()


@router.patch("/permissions/{user_id}", response_model=ClaudeExecutorPermissionPublic)
async def update_permission(
    user_id: int,
    request: ClaudeExecutorPermissionUpdate,
    current_user: User = Depends(get_current_superuser)
):
    """更新用户授权（仅超级管理员）"""
    session = get_db_session()
    try:
        permission = session.exec(
            select(ClaudeExecutorPermission).where(ClaudeExecutorPermission.user_id == user_id)
        ).first()

        if not permission:
            raise HTTPException(status_code=404, detail="授权记录不存在")

        if request.allowed_modes is not None:
            permission.allowed_modes = request.allowed_modes
        if request.expires_at is not None:
            permission.expires_at = request.expires_at
        if request.notes is not None:
            permission.notes = request.notes

        permission.updated_at = datetime.utcnow()
        session.add(permission)
        session.commit()
        session.refresh(permission)

        return permission

    finally:
        session.close()