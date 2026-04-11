"""
权重调整 API 路由

提供权重管理相关接口：
1. GET /weights/{skill_id} - 获取技能权重
2. POST /weights/{skill_id}/adjust - 手动调整权重
3. POST /weights/batch-optimize - 批量优化
4. GET /weights/stats - 获取权重统计
5. GET /weights/{skill_id}/history - 获取权重历史

设计原则：
- RESTful API 设计
- 权重边界验证
- 调整原因追溯
- 批量操作支持
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.logger import log
from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.feedback_weight import (
    WeightFactorType,
    FeedbackDrivenWeight,
    WeightAdjustmentRecord,
    FeedbackWeightRecord,
)
from app.services.weight_optimizer import WeightOptimizer, WeightOptimizerConfig


# ==========================================
# 请求/响应模型
# ==========================================

class WeightFactorResponse(BaseModel):
    """权重因子响应"""
    type: str
    value: float
    weight: float
    contribution: float


class WeightDetailResponse(BaseModel):
    """权重详情响应"""
    success: bool
    data: Dict[str, Any]


class ManualAdjustmentRequest(BaseModel):
    """手动调整请求"""
    adjustment: float = Field(..., ge=-1.0, le=1.0, description="调整幅度")
    reason: str = Field(..., min_length=5, description="调整原因")


class BatchOptimizeRequest(BaseModel):
    """批量优化请求"""
    skill_ids: Optional[List[str]] = Field(default=None, description="技能列表（不指定则优化所有）")
    min_executions: int = Field(default=5, ge=1, description="最少执行次数过滤")


class BatchOptimizeResponse(BaseModel):
    """批量优化响应"""
    success: bool
    data: Dict[str, Any]


class WeightStatsResponse(BaseModel):
    """权重统计响应"""
    success: bool
    data: Dict[str, Any]


# ==========================================
# 路由定义
# ==========================================

router = APIRouter(prefix="/weights", tags=["Weights"])


@router.get("/{skill_id}", response_model=WeightDetailResponse)
async def get_skill_weight(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取技能权重详情

    Args:
        skill_id: 技能 ID

    Returns:
        权重配置详情
    """
    log.info(f"[WeightsAPI] 获取技能权重: {skill_id}")

    optimizer = WeightOptimizer(session)
    weight = optimizer.get_skill_weight(skill_id)

    # 构建因子响应
    factors = [
        WeightFactorResponse(
            type=f.factor_type.value,
            value=f.value,
            weight=f.weight,
            contribution=f.contribution,
        )
        for f in weight.factors
    ]

    return WeightDetailResponse(
        success=True,
        data={
            "skill_id": weight.skill_id,
            "skill_name": weight.skill_name,
            "category": weight.category,
            "base_weight": weight.base_weight,
            "final_weight": weight.final_weight,
            "factors": [f.model_dump() for f in factors],
            "stats": {
                "total_executions": weight.total_executions,
                "successful_executions": weight.successful_executions,
                "failed_executions": weight.failed_executions,
                "success_rate": weight.success_rate,
                "total_clicks": weight.total_clicks,
                "avg_rating": weight.avg_rating,
            },
            "time_decay": {
                "enabled": weight.time_decay.enabled,
                "half_life_days": weight.time_decay.half_life_days,
            },
            "updated_at": weight.updated_at.isoformat(),
        },
    )


@router.post("/{skill_id}/adjust", response_model=WeightDetailResponse)
async def adjust_skill_weight(
    skill_id: str,
    request: ManualAdjustmentRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    手动调整技能权重

    Args:
        skill_id: 技能 ID
        request: 调整请求

    Returns:
        调整后的权重配置
    """
    log.info(f"[WeightsAPI] 手动调整权重: {skill_id}, adjustment={request.adjustment}")

    optimizer = WeightOptimizer(session)
    config = WeightOptimizerConfig()

    # 获取当前权重
    weight = optimizer.get_skill_weight(skill_id)
    weight_before = weight.final_weight

    # 验证调整幅度
    max_adjustment = config.MAX_ADJUSTMENT_PER_DAY
    if abs(request.adjustment) > max_adjustment:
        raise HTTPException(
            status_code=400,
            detail=f"Adjustment exceeds maximum allowed ({max_adjustment})",
        )

    # 应用调整
    weight_after = max(
        config.MIN_WEIGHT,
        min(config.MAX_WEIGHT, weight_before + request.adjustment)
    )

    # 更新基础权重
    weight.base_weight = weight_after / weight.final_weight if weight.final_weight > 0 else weight_after
    weight.updated_at = get_utc_now()

    # 保存
    optimizer._save_weight(weight)

    # 记录调整
    optimizer.record_adjustment(
        skill_id=skill_id,
        weight_before=weight_before,
        weight_after=weight_after,
        reason=request.reason,
        trigger="manual",
        confidence=1.0,
    )

    return WeightDetailResponse(
        success=True,
        data={
            "skill_id": weight.skill_id,
            "weight_before": weight_before,
            "weight_after": weight_after,
            "adjustment_delta": weight_after - weight_before,
            "reason": request.reason,
            "trigger": "manual",
        },
    )


@router.post("/batch-optimize", response_model=BatchOptimizeResponse)
async def batch_optimize_weights(
    request: BatchOptimizeRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    批量优化技能权重

    Args:
        request: 批量优化请求

    Returns:
        优化结果
    """
    log.info(f"[WeightsAPI] 批量优化权重: skills={len(request.skill_ids) if request.skill_ids else 'all'}")

    optimizer = WeightOptimizer(session)

    # 执行批量优化
    results = optimizer.batch_optimize(
        skill_ids=request.skill_ids,
        min_executions=request.min_executions,
    )

    # 构建响应
    optimization_results = [
        {
            "skill_id": w.skill_id,
            "base_weight": w.base_weight,
            "final_weight": w.final_weight,
            "success_rate": w.success_rate,
        }
        for w in results
    ]

    stats = optimizer.get_stats()

    return BatchOptimizeResponse(
        success=True,
        data={
            "optimized_count": len(results),
            "stats": stats,
            "results": optimization_results,
        },
    )


@router.get("/stats/overview", response_model=WeightStatsResponse)
async def get_weight_stats(
    category: Optional[str] = Query(None, description="分类过滤"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    获取权重统计概览

    Args:
        category: 分类过滤（可选）

    Returns:
        权重统计数据
    """
    log.info(f"[WeightsAPI] 获取权重统计: category={category}")

    # 查询所有权重记录
    query = select(FeedbackWeightRecord)
    if category:
        query = query.where(FeedbackWeightRecord.category == category)

    records = session.exec(query).all()

    if not records:
        return WeightStatsResponse(
            success=True,
            data={
                "total_skills": 0,
                "weights_distribution": {"high": 0, "normal": 0, "low": 0},
                "avg_weight": 1.0,
            },
        )

    # 计算统计
    weights = [r.to_weight().final_weight for r in records]

    high_count = sum(1 for w in weights if w > 1.2)
    normal_count = sum(1 for w in weights if 0.8 <= w <= 1.2)
    low_count = sum(1 for w in weights if w < 0.8)

    avg_weight = sum(weights) / len(weights) if weights else 1.0

    # 排序获取 top/bottom
    sorted_records = sorted(records, key=lambda r: r.to_weight().final_weight, reverse=True)

    top_skills = [
        {"skill_id": r.skill_id, "weight": r.to_weight().final_weight}
        for r in sorted_records[:5]
    ]

    bottom_skills = [
        {"skill_id": r.skill_id, "weight": r.to_weight().final_weight}
        for r in sorted_records[-5:]
    ]

    return WeightStatsResponse(
        success=True,
        data={
            "total_skills": len(records),
            "weights_distribution": {
                "high": high_count,
                "normal": normal_count,
                "low": low_count,
            },
            "avg_weight": round(avg_weight, 3),
            "top_skills": top_skills,
            "bottom_skills": bottom_skills,
            "category": category,
        },
    )


@router.post("/reset/{skill_id}", response_model=WeightDetailResponse)
async def reset_skill_weight(
    skill_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    重置技能权重

    将技能权重重置为默认值（1.0）

    Args:
        skill_id: 技能 ID

    Returns:
        重置后的权重配置
    """
    log.info(f"[WeightsAPI] 重置技能权重: {skill_id}")

    optimizer = WeightOptimizer(session)
    weight = optimizer.get_skill_weight(skill_id)

    weight_before = weight.final_weight

    # 重置
    weight.base_weight = 1.0
    weight.factors = []
    weight.updated_at = get_utc_now()

    optimizer._save_weight(weight)

    return WeightDetailResponse(
        success=True,
        data={
            "skill_id": weight.skill_id,
            "weight_before": weight_before,
            "weight_after": 1.0,
            "adjustment_delta": 1.0 - weight_before,
            "reason": "权重重置为默认值",
            "trigger": "reset",
        },
    )


# ==========================================
# 导入缺失的模块
# ==========================================

from datetime import datetime, timezone
from sqlmodel import select


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


log.info("✅ 权重调整 API 路由已加载")