"""
技能草稿 API — 技能收割机生成的待审核草稿管理。

提供对 PendingSkillDraft 的 CRUD 操作：
- 列表查看（按状态筛选）
- 详情查看（含代码预览）
- 编辑更新
- 一键发布为 SkillAsset
- 忽略/驳回
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.skill.draft import (
    PendingSkillDraft,
    PendingSkillDraftPublic,
    PendingSkillDraftUpdate,
    DraftStatus,
)
from app.models.skill.asset import SkillAsset

router = APIRouter()


# ==========================================
# GET /api/skills/drafts - 获取草稿列表
# ==========================================
@router.get("", response_model=List[PendingSkillDraftPublic])
def get_drafts(
    status: Optional[str] = Query(None, description="按状态筛选: PENDING/REVIEWED/PUBLISHED/DISMISSED"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的技能草稿列表"""
    stmt = select(PendingSkillDraft).where(
        PendingSkillDraft.user_id == current_user.id
    )
    if status:
        stmt = stmt.where(PendingSkillDraft.status == status)
    stmt = stmt.order_by(
        PendingSkillDraft.created_at.desc()
    ).offset(offset).limit(limit)

    drafts = session.exec(stmt).all()
    return [PendingSkillDraftPublic.model_validate(d) for d in drafts]


# ==========================================
# GET /api/skills/drafts/stats - 获取草稿统计
# ==========================================
@router.get("/stats")
def get_draft_stats(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的草稿统计信息"""
    stmt = select(PendingSkillDraft).where(
        PendingSkillDraft.user_id == current_user.id
    )
    all_drafts = session.exec(stmt).all()

    stats = {"PENDING": 0, "REVIEWED": 0, "PUBLISHED": 0, "DISMISSED": 0, "total": 0}
    for d in all_drafts:
        if d.status in stats:
            stats[d.status] += 1
        stats["total"] += 1

    return stats


# ==========================================
# GET /api/skills/drafts/{draft_id} - 获取草稿详情
# ==========================================
@router.get("/{draft_id}", response_model=PendingSkillDraftPublic)
def get_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """获取单个草稿详情"""
    draft = session.exec(
        select(PendingSkillDraft).where(
            PendingSkillDraft.id == draft_id,
            PendingSkillDraft.user_id == current_user.id,
        )
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    return PendingSkillDraftPublic.model_validate(draft)


# ==========================================
# PUT /api/skills/drafts/{draft_id} - 更新草稿
# ==========================================
@router.put("/{draft_id}")
def update_draft(
    draft_id: int,
    updates: PendingSkillDraftUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """更新草稿内容（用于用户手动编辑后再发布）"""
    draft = session.exec(
        select(PendingSkillDraft).where(
            PendingSkillDraft.id == draft_id,
            PendingSkillDraft.user_id == current_user.id,
        )
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 更新字段
    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(draft, key, value)

    session.add(draft)
    session.commit()
    session.refresh(draft)

    log.info(f"[DraftAPI] 草稿已更新: id={draft_id}, fields={list(update_data.keys())}")
    return PendingSkillDraftPublic.model_validate(draft)


# ==========================================
# POST /api/skills/drafts/{draft_id}/publish - 发布草稿
# ==========================================
@router.post("/{draft_id}/publish")
async def publish_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    一键发布草稿为正式技能。

    将 PendingSkillDraft 的内容转化为 SkillAsset 并入库，
    草稿状态更新为 PUBLISHED。
    """
    draft = session.exec(
        select(PendingSkillDraft).where(
            PendingSkillDraft.id == draft_id,
            PendingSkillDraft.user_id == current_user.id,
        )
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if draft.status == DraftStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="草稿已发布")

    try:
        # 生成 skill_id
        from app.models.uuid import generate_skill_id
        skill_id = generate_skill_id()

        # 创建 SkillAsset
        skill = SkillAsset(
            skill_id=skill_id,
            name=draft.draft_name,
            description=draft.draft_description,
            version="1.0.0",
            executor_type=draft.executor_type,
            parameters_schema=draft.parameters_schema,
            expert_knowledge=draft.expert_knowledge,
            script_code=draft.script_code,
            dependencies=draft.dependencies,
            tags=draft.strategies if draft.strategies else [],
            owner_id=current_user.id,
            visibility="private",
            status="PRIVATE",
        )
        session.add(skill)

        # 更新草稿状态
        draft.status = DraftStatus.PUBLISHED
        draft.published_skill_id = skill_id
        session.add(draft)

        session.commit()
        session.refresh(skill)

        log.info(
            f"[DraftAPI] 草稿发布成功: draft_id={draft_id}, "
            f"skill_id={skill_id}, name={draft.draft_name}"
        )

        return {
            "success": True,
            "skill_id": skill_id,
            "draft_id": draft_id,
            "message": f"技能 '{draft.draft_name}' 已发布",
        }

    except Exception as e:
        log.error(f"[DraftAPI] 草稿发布失败: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=f"发布失败: {str(e)}")


# ==========================================
# POST /api/skills/drafts/{draft_id}/dismiss - 忽略草稿
# ==========================================
@router.post("/{draft_id}/dismiss")
def dismiss_draft(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """忽略/驳回草稿（不发布）"""
    draft = session.exec(
        select(PendingSkillDraft).where(
            PendingSkillDraft.id == draft_id,
            PendingSkillDraft.user_id == current_user.id,
        )
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    draft.status = DraftStatus.DISMISSED
    session.add(draft)
    session.commit()

    log.info(f"[DraftAPI] 草稿已驳回: id={draft_id}")
    return {"success": True, "message": "草稿已忽略"}


# ==========================================
# POST /api/skills/drafts/{draft_id}/review - 标记为已查看
# ==========================================
@router.post("/{draft_id}/review")
def mark_reviewed(
    draft_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """标记草稿为已查看"""
    draft = session.exec(
        select(PendingSkillDraft).where(
            PendingSkillDraft.id == draft_id,
            PendingSkillDraft.user_id == current_user.id,
        )
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    if draft.status == DraftStatus.PENDING:
        draft.status = DraftStatus.REVIEWED
        session.add(draft)
        session.commit()

    log.info(f"[DraftAPI] 草稿已标记为已查看: id={draft_id}")
    return {"success": True, "message": "草稿已标记为已查看"}
