"""
偏好画像 API 路由

提供用户偏好画像相关接口：
1. GET /preferences/me - 获取当前用户偏好
2. POST /preferences/me/update - 手动更新偏好
3. GET /preferences/me/boost - 获取技能推荐加成
4. GET /preferences/me/skills - 获取常用技能
5. GET /preferences/me/categories - 获取分类偏好

设计原则：
- 懒加载：首次请求时计算偏好
- 缓存：偏好结果缓存 1 小时
- 实时更新：重要行为后触发更新
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.logger import log
from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.domain import User
from app.services.preference_engine import (
    PreferenceEngine,
    update_user_preference,
    get_user_preference,
)
from app.models.user_preference import (
    ExpertiseLevel,
    FrequentSkill,
    CategoryPreference,
    UserPreferenceProfile,
)


# ==========================================
# 响应模型
# ==========================================

class FrequentSkillResponse(BaseModel):
    """常用技能响应"""
    skill_id: str
    skill_name: str
    execute_count: int
    success_count: int
    success_rate: float
    last_executed_at: Optional[str] = None
    avg_execution_time: Optional[float] = None


class CategoryPreferenceResponse(BaseModel):
    """分类偏好响应"""
    category: str
    category_name: str
    weight: float
    execute_count: int


class PreferenceResponse(BaseModel):
    """偏好画像响应"""
    user_id: int
    expertise_level: str
    expertise_level_display: str
    frequent_skills: List[FrequentSkillResponse]
    preferred_categories: List[CategoryPreferenceResponse]
    total_executions: int
    total_successes: int
    total_failures: int
    overall_success_rate: float
    active_hours: List[int]
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class SkillBoostRequest(BaseModel):
    """技能加成请求"""
    skill_id: str
    category: Optional[str] = None


class SkillBoostResponse(BaseModel):
    """技能加成响应"""
    skill_id: str
    boost: float
    is_frequent: bool
    rank: Optional[int] = None
    category_weight: Optional[float] = None


class UpdatePreferenceResponse(BaseModel):
    """更新偏好响应"""
    success: bool
    message: str
    profile: Optional[PreferenceResponse] = None


# ==========================================
# 路由定义
# ==========================================

router = APIRouter(prefix="/preferences", tags=["Preferences"])


def _profile_to_response(profile: UserPreferenceProfile) -> PreferenceResponse:
    """将 Profile 转换为响应模型"""
    expertise_display = {
        ExpertiseLevel.BEGINNER: "新手",
        ExpertiseLevel.INTERMEDIATE: "中级",
        ExpertiseLevel.ADVANCED: "高级",
        ExpertiseLevel.EXPERT: "专家",
    }

    return PreferenceResponse(
        user_id=profile.user_id,
        expertise_level=profile.expertise_level.value,
        expertise_level_display=expertise_display.get(profile.expertise_level, "未知"),
        frequent_skills=[
            FrequentSkillResponse(
                skill_id=s.skill_id,
                skill_name=s.skill_name,
                execute_count=s.execute_count,
                success_count=s.success_count,
                success_rate=s.success_rate,
                last_executed_at=s.last_executed_at.isoformat() if s.last_executed_at else None,
                avg_execution_time=s.avg_execution_time,
            )
            for s in profile.frequent_skills
        ],
        preferred_categories=[
            CategoryPreferenceResponse(
                category=c.category,
                category_name=c.category_name,
                weight=c.weight,
                execute_count=c.execute_count,
            )
            for c in profile.preferred_categories
        ],
        total_executions=profile.total_executions,
        total_successes=profile.total_successes,
        total_failures=profile.total_failures,
        overall_success_rate=profile.overall_success_rate,
        active_hours=profile.active_hours,
        updated_at=profile.updated_at.isoformat() if profile.updated_at else None,
    )


@router.get("/me", response_model=PreferenceResponse)
async def get_my_preferences(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户偏好画像

    如果用户还没有偏好画像，会自动计算并返回。
    """
    engine = PreferenceEngine(session)
    profile = engine.get_user_profile(current_user.id)

    if not profile:
        # 首次请求，计算偏好
        log.info(f"[Preferences] 首次请求，计算偏好: user_id={current_user.id}")
        profile = engine.compute_user_profile(current_user.id)

    return _profile_to_response(profile)


@router.post("/me/update", response_model=UpdatePreferenceResponse)
async def update_my_preferences(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    手动更新偏好画像

    基于最近 30 天的行为数据重新计算偏好。
    """
    try:
        engine = PreferenceEngine(session)
        record = engine.update_user_profile(current_user.id)
        profile = record.to_profile()

        log.info(f"[Preferences] 偏好更新成功: user_id={current_user.id}")

        return UpdatePreferenceResponse(
            success=True,
            message="偏好画像已更新",
            profile=_profile_to_response(profile),
        )

    except Exception as e:
        log.error(f"[Preferences] 更新偏好失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.post("/me/boost", response_model=SkillBoostResponse)
async def get_skill_boost(
    request: SkillBoostRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取技能推荐加成

    用于个性化推荐时计算技能的推荐权重。
    """
    engine = PreferenceEngine(session)
    profile = engine.get_user_profile(current_user.id)

    if not profile:
        return SkillBoostResponse(
            skill_id=request.skill_id,
            boost=1.0,
            is_frequent=False,
            category_weight=None,
        )

    # 计算加成
    boost = engine.get_skill_recommendation_boost(
        user_id=current_user.id,
        skill_id=request.skill_id,
        skill_category=request.category,
    )

    # 检查是否为常用技能
    frequent_skill_ids = [s.skill_id for s in profile.frequent_skills]
    is_frequent = request.skill_id in frequent_skill_ids
    rank = None
    if is_frequent:
        rank = frequent_skill_ids.index(request.skill_id) + 1

    # 获取分类权重
    category_weight = None
    if request.category:
        for c in profile.preferred_categories:
            if c.category == request.category:
                category_weight = c.weight
                break

    return SkillBoostResponse(
        skill_id=request.skill_id,
        boost=boost,
        is_frequent=is_frequent,
        rank=rank,
        category_weight=category_weight,
    )


@router.get("/me/skills", response_model=List[FrequentSkillResponse])
async def get_my_frequent_skills(
    limit: int = 10,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取常用技能列表

    Args:
        limit: 返回数量限制（默认 10）
    """
    engine = PreferenceEngine(session)
    profile = engine.get_user_profile(current_user.id)

    if not profile:
        return []

    skills = profile.get_top_skills(limit)
    return [
        FrequentSkillResponse(
            skill_id=s.skill_id,
            skill_name=s.skill_name,
            execute_count=s.execute_count,
            success_count=s.success_count,
            success_rate=s.success_rate,
            last_executed_at=s.last_executed_at.isoformat() if s.last_executed_at else None,
            avg_execution_time=s.avg_execution_time,
        )
        for s in skills
    ]


@router.get("/me/categories", response_model=List[CategoryPreferenceResponse])
async def get_my_category_preferences(
    limit: int = 10,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取分类偏好

    Args:
        limit: 返回数量限制（默认 10）
    """
    engine = PreferenceEngine(session)
    profile = engine.get_user_profile(current_user.id)

    if not profile:
        return []

    categories = profile.get_preferred_categories(limit)
    return [
        CategoryPreferenceResponse(
            category=c.category,
            category_name=c.category_name,
            weight=c.weight,
            execute_count=c.execute_count,
        )
        for c in categories
    ]


@router.get("/me/expertise", response_model=Dict[str, Any])
async def get_my_expertise_level(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取专家水平信息
    """
    engine = PreferenceEngine(session)
    profile = engine.get_user_profile(current_user.id)

    if not profile:
        return {
            "level": "beginner",
            "display": "新手",
            "total_executions": 0,
            "success_rate": 0.0,
            "next_level": "intermediate",
            "progress_to_next": 0.0,
        }

    expertise_display = {
        ExpertiseLevel.BEGINNER: "新手",
        ExpertiseLevel.INTERMEDIATE: "中级",
        ExpertiseLevel.ADVANCED: "高级",
        ExpertiseLevel.EXPERT: "专家",
    }

    levels = [ExpertiseLevel.BEGINNER, ExpertiseLevel.INTERMEDIATE, ExpertiseLevel.ADVANCED, ExpertiseLevel.EXPERT]
    current_idx = levels.index(profile.expertise_level)
    next_level = levels[current_idx + 1].value if current_idx < len(levels) - 1 else None

    # 简单的进度计算
    progress = min(1.0, profile.total_executions / 100) if profile.expertise_level != ExpertiseLevel.EXPERT else 1.0

    return {
        "level": profile.expertise_level.value,
        "display": expertise_display.get(profile.expertise_level, "未知"),
        "total_executions": profile.total_executions,
        "success_rate": profile.overall_success_rate,
        "next_level": next_level,
        "progress_to_next": progress,
    }


log.info("✅ 偏好画像 API 路由已加载")