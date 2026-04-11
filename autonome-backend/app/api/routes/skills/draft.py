"""
技能草稿 API

包含自动生成的技能草稿管理接口：
- 获取草稿列表
- 获取草稿详情
- 更新草稿
- 发布草稿
- 忽略草稿
- 获取草稿统计
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.skill.draft import (
    DraftStatus,
    PendingSkillDraft,
    PendingSkillDraftPublic,
    PendingSkillDraftUpdate
)
from app.services.auto_skill_draft_service import AutoSkillDraftService
from app.schemas.skill import PublishDraftRequest

router = APIRouter()


# ==========================================
# GET /api/skills/drafts - 获取草稿列表
# ==========================================
@router.get("", response_model=List[PendingSkillDraftPublic])
def get_drafts(
    status: Optional[str] = Query(None, description="按状态筛选: PENDING, REVIEWED, PUBLISHED, DISMISSED"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户的技能草稿列表

    按创建时间倒序排列，支持按状态筛选。
    """
    service = AutoSkillDraftService(session)
    drafts = service.get_user_drafts(
        user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset
    )

    return drafts


# ==========================================
# GET /api/skills/drafts/stats - 获取草稿统计
# ==========================================
@router.get("/stats")
def get_draft_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户的草稿统计信息

    返回各状态的草稿数量。
    """
    service = AutoSkillDraftService(session)
    stats = service.get_draft_stats(current_user.id)

    return stats


# ==========================================
# GET /api/skills/drafts/{draft_id} - 获取草稿详情
# ==========================================
@router.get("/{draft_id}", response_model=PendingSkillDraftPublic)
def get_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取单个草稿详情
    """
    service = AutoSkillDraftService(session)
    draft = service.get_draft(draft_id, current_user.id)

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    return draft


# ==========================================
# PUT /api/skills/drafts/{draft_id} - 更新草稿
# ==========================================
@router.put("/{draft_id}", response_model=PendingSkillDraftPublic)
def update_draft(
    draft_id: int,
    update_data: PendingSkillDraftUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    更新草稿内容

    可更新字段：名称、描述、参数Schema、代码等
    """
    service = AutoSkillDraftService(session)

    # 过滤掉 None 值
    updates = update_data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的内容")

    draft = service.update_draft(draft_id, current_user.id, **updates)

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    log.info(f"📝 [Draft API] 用户 {current_user.id} 更新了草稿 {draft_id}")

    return draft


# ==========================================
# POST /api/skills/drafts/{draft_id}/publish - 发布草稿
# ==========================================
@router.post("/{draft_id}/publish")
async def publish_draft(
    draft_id: int,
    request: PublishDraftRequest = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    发布草稿为正式技能

    一键确认发布，草稿将转化为正式技能（DRAFT状态）。
    用户可在技能工厂中进一步完善。

    Args:
        draft_id: 草稿ID
        request: 可选的发布参数（名称、分类、标签）
    """
    service = AutoSkillDraftService(session)

    # 提取可选参数
    skill_name = request.skill_name if request else None
    category = request.category if request else None
    tags = request.tags if request else None

    result = await service.publish_draft(
        draft_id=draft_id,
        user_id=current_user.id,
        skill_name=skill_name,
        category=category,
        tags=tags
    )

    if not result:
        raise HTTPException(status_code=500, detail="发布失败")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    log.info(f"🚀 [Draft API] 用户 {current_user.id} 发布了草稿 {draft_id} 为技能 {result.get('skill_id')}")

    return {
        "status": "success",
        "message": result.get("message", "技能已创建"),
        "skill_id": result.get("skill_id"),
        "name": result.get("name")
    }


# ==========================================
# POST /api/skills/drafts/{draft_id}/dismiss - 忽略草稿
# ==========================================
@router.post("/{draft_id}/dismiss")
def dismiss_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    忽略草稿

    标记草稿为 DISMISSED 状态，不再显示在待处理列表中。
    """
    service = AutoSkillDraftService(session)
    success = service.dismiss_draft(draft_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="草稿不存在")

    return {
        "status": "success",
        "message": "草稿已忽略"
    }


# ==========================================
# POST /api/skills/drafts/{draft_id}/review - 标记为已查看
# ==========================================
@router.post("/{draft_id}/review")
def mark_reviewed(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    标记草稿为已查看

    用户查看草稿详情后自动调用此接口。
    """
    service = AutoSkillDraftService(session)
    draft = service.update_draft(draft_id, current_user.id, status=DraftStatus.REVIEWED)

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    return {
        "status": "success",
        "message": "已标记为已查看"
    }