"""
技能草稿 API（已简化 - 自动草稿服务已移除）

保留接口兼容性，返回空结果。
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.skill.draft import (
    PendingSkillDraftPublic,
)

router = APIRouter()


# ==========================================
# GET /api/skills/drafts - 获取草稿列表
# ==========================================
@router.get("", response_model=List[PendingSkillDraftPublic])
def get_drafts(
    status: Optional[str] = Query(None, description="按状态筛选"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取用户的技能草稿列表（自动草稿服务已移除，返回空列表）"""
    return []


# ==========================================
# GET /api/skills/drafts/stats - 获取草稿统计
# ==========================================
@router.get("/stats")
def get_draft_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取用户的草稿统计信息（自动草稿服务已移除）"""
    return {"PENDING": 0, "REVIEWED": 0, "PUBLISHED": 0, "DISMISSED": 0}


# ==========================================
# GET /api/skills/drafts/{draft_id} - 获取草稿详情
# ==========================================
@router.get("/{draft_id}", response_model=PendingSkillDraftPublic)
def get_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取单个草稿详情（自动草稿服务已移除）"""
    raise HTTPException(status_code=404, detail="草稿不存在")


# ==========================================
# PUT /api/skills/drafts/{draft_id} - 更新草稿
# ==========================================
@router.put("/{draft_id}")
def update_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """更新草稿内容（自动草稿服务已移除）"""
    raise HTTPException(status_code=404, detail="草稿不存在")


# ==========================================
# POST /api/skills/drafts/{draft_id}/publish - 发布草稿
# ==========================================
@router.post("/{draft_id}/publish")
async def publish_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """发布草稿为正式技能（自动草稿服务已移除）"""
    raise HTTPException(status_code=404, detail="草稿不存在")


# ==========================================
# POST /api/skills/drafts/{draft_id}/dismiss - 忽略草稿
# ==========================================
@router.post("/{draft_id}/dismiss")
def dismiss_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """忽略草稿（自动草稿服务已移除）"""
    raise HTTPException(status_code=404, detail="草稿不存在")


# ==========================================
# POST /api/skills/drafts/{draft_id}/review - 标记为已查看
# ==========================================
@router.post("/{draft_id}/review")
def mark_reviewed(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """标记草稿为已查看（自动草稿服务已移除）"""
    raise HTTPException(status_code=404, detail="草稿不存在")
