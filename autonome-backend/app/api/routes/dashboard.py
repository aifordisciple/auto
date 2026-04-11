"""
Dashboard API 路由 - 科研项目指挥中心

从"系统监控大屏"重构为"科研视角"控制面板，核心解决三个问题：
1. 我的样本分析到哪一步了？
2. 我花掉的算力/费用产生了什么价值？
3. 我接下来需要确认什么操作？

模块：
- billing-analytics: 算力账单与技能雷达 ✅ 已实现
- active-workflows: 动态科研工作流大厅（本文件实现）
- action-items: 智能预警与待办中心
- recent-assets: 科研资产与洞察速递

设计日期: 2026-04-02
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, text
from sqlalchemy import and_
import json
import time

from app.core.database import get_session
from app.core.logger import log
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.domain import User
from app.models.billing import Wallet, ComputeRecord, TaskType, TaskStatus
from app.models.skill.history import SkillExecutionHistory
from app.models.task import TaskRecord


router = APIRouter()


# ==========================================
# Redis 客户端（用于读取蓝图状态）
# ==========================================

def get_redis_client():
    """获取 Redis 客户端"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=2,  # 与 celery_app 使用同一 db
        decode_responses=True
    )


# Redis 键前缀（与 blueprint.py 保持一致）
BLUEPRINT_EVENTS_PREFIX = "blueprint_events:"
BLUEPRINT_STATE_PREFIX = "blueprint_state:"
BLUEPRINT_INFO_PREFIX = "blueprint_info:"
TASK_INFO_PREFIX = "task_info:"


# ==========================================
# 辅助函数
# ==========================================

def get_utc_now():
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


def get_time_filter(time_range: str) -> datetime:
    """
    根据时间范围参数返回过滤时间点

    Args:
        time_range: "7d" | "30d" | "all"

    Returns:
        过滤起始时间点，"all" 返回最小时间
    """
    now = get_utc_now()
    if time_range == "7d":
        return now - timedelta(days=7)
    elif time_range == "30d":
        return now - timedelta(days=30)
    else:  # "all"
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


def get_task_type_display_name(task_type: str) -> str:
    """获取任务类型的中文显示名称"""
    display_names = {
        "chat": "AI 对话",
        "sandbox_python": "Python 沙箱",
        "sandbox_r": "R 沙箱",
        "blueprint": "蓝图工作流",
        "super_executor": "超级执行器",
        "skill_python": "Python 技能",
        "skill_r": "R 技能",
        "skill_nextflow": "Nextflow 流程",
        "terminal": "Web 终端",
    }
    return display_names.get(task_type, task_type)


# ==========================================
# 响应模型
# ==========================================

class WalletOverview(BaseModel):
    """钱包概览"""
    current_balance: float = Field(description="可用余额 (CU)")
    frozen_amount: float = Field(description="冻结金额 (CU)")
    total_consumed: float = Field(description="累计消费 (CU)")
    trend_last_7_days: float = Field(description="近7天消费趋势 (CU)")


class FunnelItem(BaseModel):
    """消耗漏斗单项"""
    task_type: str = Field(description="任务类型")
    task_type_display: str = Field(description="任务类型显示名称")
    count: int = Field(description="执行次数")
    total_cost: float = Field(description="总消费 (CU)")
    percentage: float = Field(description="占比 (%)")


class SkillRadarItem(BaseModel):
    """技能雷达单项"""
    skill_id: str = Field(description="技能 ID")
    skill_name: str = Field(description="技能名称")
    usage_count: int = Field(description="使用次数")
    success_rate: float = Field(description="成功率 (%)")
    avg_execution_time: float = Field(description="平均执行时间 (秒)")
    total_cost: float = Field(description="总消费 (CU)", default=0.0)


class RecommendedSkill(BaseModel):
    """推荐技能"""
    skill_id: str = Field(description="技能 ID")
    skill_name: str = Field(description="技能名称")
    reason: str = Field(description="推荐原因")
    category: str = Field(description="技能分类")


class BillingAnalyticsResponse(BaseModel):
    """账单分析响应"""
    wallet_overview: WalletOverview
    funnel_data: List[FunnelItem]
    skill_radar: List[SkillRadarItem]
    recommended_skills: List[RecommendedSkill]


class SkillRadarResponse(BaseModel):
    """技能雷达响应"""
    skills: List[SkillRadarItem]
    total_usage_count: int = Field(description="总使用次数")
    most_used_skill: Optional[str] = Field(description="最常用技能名称")


# ==========================================
# API 端点
# ==========================================

@router.get("/billing-analytics", response_model=BillingAnalyticsResponse)
async def get_billing_analytics(
    project_id: Optional[str] = Query(None, description="项目 ID（可选，用于过滤）"),
    time_range: str = Query("30d", regex="^(7d|30d|all)$", description="时间范围: 7d/30d/all"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取账单分析数据

    数据来源:
    - Wallet: 钱包余额、冻结金额、累计消费
    - ComputeRecord: 按任务类型聚合消耗
    - SkillExecutionHistory: 技能使用统计

    返回:
    - wallet_overview: 钱包概览
    - funnel_data: 算力消耗漏斗
    - skill_radar: 技能使用雷达
    - recommended_skills: 推荐技能
    """
    user_id = current_user.id
    time_filter = get_time_filter(time_range)

    log.info(f"📊 获取账单分析: user_id={user_id}, time_range={time_range}, project_id={project_id}")

    # ==========================================
    # 1. 钱包概览
    # ==========================================
    wallet = session.exec(
        select(Wallet).where(Wallet.owner_id == user_id)
    ).first()

    if not wallet:
        # 如果用户没有钱包，返回默认值
        wallet_overview = WalletOverview(
            current_balance=0.0,
            frozen_amount=0.0,
            total_consumed=0.0,
            trend_last_7_days=0.0
        )
    else:
        # 计算近7天消费
        seven_days_ago = get_utc_now() - timedelta(days=7)
        recent_consumption = session.exec(
            select(func.sum(ComputeRecord.actual_cost))
            .where(and_(
                ComputeRecord.user_id == user_id,
                ComputeRecord.submitted_at >= seven_days_ago
            ))
        ).first() or 0.0

        wallet_overview = WalletOverview(
            current_balance=wallet.credits_balance,
            frozen_amount=wallet.credits_frozen,
            total_consumed=wallet.total_consumed,
            trend_last_7_days=float(recent_consumption)
        )

    # ==========================================
    # 2. 消耗漏斗 - 按 TaskType 聚合 ComputeRecord
    # ==========================================
    # 构建基础查询条件
    base_conditions = [
        ComputeRecord.user_id == user_id,
        ComputeRecord.submitted_at >= time_filter
    ]

    if project_id:
        base_conditions.append(ComputeRecord.project_id == project_id)

    # 使用原生 SQL 进行聚合查询（更高效）
    funnel_query = text("""
        SELECT task_type, COUNT(*) as count, COALESCE(SUM(actual_cost), 0) as total_cost
        FROM computerecord
        WHERE user_id = :user_id AND submitted_at >= :time_filter
        {project_filter}
        GROUP BY task_type
        ORDER BY total_cost DESC
    """.format(
        project_filter="AND project_id = :project_id" if project_id else ""
    ))

    params = {"user_id": user_id, "time_filter": time_filter}
    if project_id:
        params["project_id"] = project_id

    # 使用 session.execute() 而非 session.exec() 来执行原生 SQL
    funnel_results = session.execute(funnel_query, params).fetchall()

    # 计算总消费
    total_cost = sum(row[2] for row in funnel_results) if funnel_results else 0.0

    funnel_data = []
    for row in funnel_results:
        task_type = row[0]
        count = row[1]
        cost = float(row[2])
        percentage = (cost / total_cost * 100) if total_cost > 0 else 0.0

        funnel_data.append(FunnelItem(
            task_type=task_type,
            task_type_display=get_task_type_display_name(task_type),
            count=count,
            total_cost=cost,
            percentage=round(percentage, 1)
        ))

    # ==========================================
    # 3. 技能雷达 - 从 SkillExecutionHistory 统计
    # ==========================================
    radar_query = text("""
        SELECT skill_id, skill_name,
               COUNT(*) as usage_count,
               COALESCE(AVG(execution_time), 0) as avg_time,
               COALESCE(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) as success_rate
        FROM skillexecutionhistory
        WHERE user_id = :user_id AND created_at >= :time_filter
        GROUP BY skill_id, skill_name
        ORDER BY usage_count DESC
        LIMIT 10
    """)

    radar_results = session.execute(radar_query, {"user_id": user_id, "time_filter": time_filter}).fetchall()

    skill_radar = []
    for row in radar_results:
        skill_id = row[0]
        skill_name = row[1] or skill_id
        usage_count = row[2]
        avg_time = float(row[3]) if row[3] else 0.0
        success_rate = float(row[4]) if row[4] else 0.0

        # 尝试获取该技能的消费数据
        skill_cost_query = text("""
            SELECT COALESCE(SUM(actual_cost), 0) as total_cost
            FROM computerecord
            WHERE user_id = :user_id AND skill_id = :skill_id AND submitted_at >= :time_filter
        """)
        skill_cost = session.execute(skill_cost_query, {
            "user_id": user_id,
            "skill_id": skill_id,
            "time_filter": time_filter
        }).first()
        total_skill_cost = float(skill_cost[0]) if skill_cost else 0.0

        skill_radar.append(SkillRadarItem(
            skill_id=skill_id,
            skill_name=skill_name,
            usage_count=usage_count,
            success_rate=round(success_rate, 1),
            avg_execution_time=round(avg_time, 1),
            total_cost=total_skill_cost
        ))

    # ==========================================
    # 4. 推荐技能 - 基于用户使用模式
    # ==========================================
    recommended_skills = []

    # 基于用户最常用的技能类别推荐相关技能
    if skill_radar:
        most_used_skill_id = skill_radar[0].skill_id

        # 尝试从技能推荐服务获取推荐
        try:
            from app.services.skill_matcher import SkillMatcher
            matcher = SkillMatcher(session)

            # 获取相似技能推荐
            similar_skills = matcher.get_similar_skills(most_used_skill_id, limit=3)

            for skill in similar_skills:
                recommended_skills.append(RecommendedSkill(
                    skill_id=skill.get("skill_id", ""),
                    skill_name=skill.get("name", ""),
                    reason=f"基于您常用的 {skill_radar[0].skill_name} 推荐",
                    category=skill.get("category_name", "")
                ))
        except Exception as e:
            log.warning(f"获取推荐技能失败: {e}")
            # 如果推荐服务不可用，返回空列表

    return BillingAnalyticsResponse(
        wallet_overview=wallet_overview,
        funnel_data=funnel_data,
        skill_radar=skill_radar,
        recommended_skills=recommended_skills
    )


@router.get("/skill-radar", response_model=SkillRadarResponse)
async def get_skill_radar(
    project_id: Optional[str] = Query(None, description="项目 ID（可选）"),
    time_range: str = Query("30d", regex="^(7d|30d|all)$", description="时间范围"),
    limit: int = Query(10, ge=1, le=20, description="返回技能数量"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取技能使用雷达数据

    维度：
    - 使用频率
    - 成功率
    - 平均执行时间
    - 成本效率
    """
    user_id = current_user.id
    time_filter = get_time_filter(time_range)

    log.info(f"📈 获取技能雷达: user_id={user_id}, time_range={time_range}")

    # 查询技能使用统计
    query = text("""
        SELECT skill_id, skill_name,
               COUNT(*) as usage_count,
               COALESCE(AVG(execution_time), 0) as avg_time,
               COALESCE(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) as success_rate
        FROM skillexecutionhistory
        WHERE user_id = :user_id AND created_at >= :time_filter
        GROUP BY skill_id, skill_name
        ORDER BY usage_count DESC
        LIMIT :limit
    """)

    results = session.execute(query, {
        "user_id": user_id,
        "time_filter": time_filter,
        "limit": limit
    }).fetchall()

    skills = []
    total_usage = 0
    most_used = None

    for row in results:
        skill_id = row[0]
        skill_name = row[1] or skill_id
        usage_count = row[2]
        avg_time = float(row[3]) if row[3] else 0.0
        success_rate = float(row[4]) if row[4] else 0.0

        total_usage += usage_count
        if most_used is None:
            most_used = skill_name

        # 获取该技能的消费
        skill_cost_query = text("""
            SELECT COALESCE(SUM(actual_cost), 0) as total_cost
            FROM computerecord
            WHERE user_id = :user_id AND skill_id = :skill_id
        """)
        skill_cost = session.execute(skill_cost_query, {
            "user_id": user_id,
            "skill_id": skill_id
        }).first()
        total_cost = float(skill_cost[0]) if skill_cost else 0.0

        skills.append(SkillRadarItem(
            skill_id=skill_id,
            skill_name=skill_name,
            usage_count=usage_count,
            success_rate=round(success_rate, 1),
            avg_execution_time=round(avg_time, 1),
            total_cost=total_cost
        ))

    return SkillRadarResponse(
        skills=skills,
        total_usage_count=total_usage,
        most_used_skill=most_used
    )


@router.get("/wallet-overview")
async def get_wallet_overview(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取钱包概览（轻量接口）

    用于 Dashboard 顶部快速展示余额信息
    """
    user_id = current_user.id

    wallet = session.exec(
        select(Wallet).where(Wallet.owner_id == user_id)
    ).first()

    if not wallet:
        return {
            "current_balance": 0.0,
            "frozen_amount": 0.0,
            "total_consumed": 0.0,
            "status": "active"
        }

    # 计算近7天消费
    seven_days_ago = get_utc_now() - timedelta(days=7)
    recent_consumption = session.exec(
        select(func.sum(ComputeRecord.actual_cost))
        .where(and_(
            ComputeRecord.user_id == user_id,
            ComputeRecord.submitted_at >= seven_days_ago
        ))
    ).first() or 0.0

    return {
        "current_balance": wallet.credits_balance,
        "frozen_amount": wallet.credits_frozen,
        "total_consumed": wallet.total_consumed,
        "trend_last_7_days": float(recent_consumption),
        "status": wallet.status.value if hasattr(wallet.status, 'value') else str(wallet.status),
        "low_balance_threshold": wallet.low_balance_threshold
    }


@router.get("/consumption-trend")
async def get_consumption_trend(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取消费趋势数据

    按天聚合消费金额，用于绘制趋势图
    """
    user_id = current_user.id

    query = text("""
        SELECT DATE(submitted_at) as date,
               SUM(actual_cost) as daily_cost,
               COUNT(*) as task_count
        FROM computerecord
        WHERE user_id = :user_id
          AND submitted_at >= NOW() - INTERVAL ':days days'
        GROUP BY DATE(submitted_at)
        ORDER BY date DESC
    """)

    results = session.execute(query, {
        "user_id": user_id,
        "days": days
    }).fetchall()

    trend_data = []
    for row in results:
        trend_data.append({
            "date": str(row[0]),
            "daily_cost": float(row[1]) if row[1] else 0.0,
            "task_count": row[2]
        })

    return {
        "days": days,
        "trend": trend_data
    }


# ==========================================
# 工作流大厅 API
# ==========================================

class MiniDAGNode(BaseModel):
    """微缩 DAG 节点"""
    task_id: str
    name: str
    status: str = "pending"  # pending, running, success, failed
    position: Dict[str, int] = Field(default_factory=lambda: {"x": 0, "y": 0})


class ActiveWorkflow(BaseModel):
    """活跃工作流"""
    task_id: str
    project_goal: str
    status: str  # running, pending, paused
    progress: float = 0.0  # 0-100
    completed_tasks: int = 0
    total_tasks: int = 0
    eta_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    mini_dag: List[MiniDAGNode] = Field(default_factory=list)


class ActiveWorkflowsResponse(BaseModel):
    """活跃工作流列表响应"""
    workflows: List[ActiveWorkflow]
    total_count: int


class ETAResponse(BaseModel):
    """ETA 响应"""
    task_id: str
    eta_seconds: Optional[int]
    confidence: float = 0.0  # 0-1, 置信度
    based_on: str = "estimate"  # historical, estimate, progress


# 任务类型基础执行时间（秒）- 用于 ETA 估算
BASE_DURATION_SECONDS = {
    "execute_python_code": 60,
    "execute_r_code": 90,
    "skill_python": 45,
    "skill_r": 60,
    "skill_nextflow": 180,
    "blueprint_dag": 180,
    "chat": 30,
}


@router.get("/active-workflows", response_model=ActiveWorkflowsResponse)
async def get_active_workflows(
    project_id: Optional[str] = Query(None, description="项目 ID（可选）"),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户正在进行的活跃工作流

    数据来源:
    - Redis task_info:* 任务详情
    - Redis blueprint_state:* DAG 节点状态
    - Celery AsyncResult 任务状态

    返回:
    - workflows: 活跃工作流列表
    - total_count: 总数
    """
    user_id = current_user.id
    redis_client = get_redis_client()

    log.info(f"🔄 获取活跃工作流: user_id={user_id}")

    workflows = []

    try:
        # 1. 从 Redis 获取用户任务列表
        user_tasks_key = f"user_tasks:{user_id}"
        task_ids = redis_client.lrange(user_tasks_key, 0, limit - 1)

        for task_id in task_ids:
            try:
                # 2. 获取任务详情
                task_info_key = f"{TASK_INFO_PREFIX}{task_id}"
                task_info = redis_client.hgetall(task_info_key)

                if not task_info:
                    continue

                tool_id = task_info.get("tool_id", "")

                # 3. 只处理蓝图类型的任务
                if tool_id != "blueprint_dag":
                    continue

                # 4. 获取 Celery 任务状态
                from celery.result import AsyncResult
                from app.services.celery_app import celery_app

                task_result = AsyncResult(task_id, app=celery_app)
                celery_status = task_result.status

                # 5. 只返回运行中或待处理的任务
                if celery_status not in ["PENDING", "STARTED", "PROGRESS", "RETRY"]:
                    continue

                # 6. 获取 DAG 节点状态
                state_key = f"{BLUEPRINT_STATE_PREFIX}{task_id}"
                node_states = redis_client.hgetall(state_key)

                # 7. 构建微缩 DAG
                mini_dag = []
                completed_count = 0
                total_count = 0

                if node_states:
                    for node_id, state_json in node_states.items():
                        try:
                            state_data = json.loads(state_json)
                            status = state_data.get("status", "pending")
                            mini_dag.append(MiniDAGNode(
                                task_id=node_id,
                                name=node_id.split("_")[0] if "_" in node_id else node_id[:8],
                                status=status
                            ))
                            total_count += 1
                            if status == "success":
                                completed_count += 1
                        except json.JSONDecodeError:
                            continue

                # 8. 计算进度
                progress = (completed_count / total_count * 100) if total_count > 0 else 0.0

                # 9. 获取蓝图信息
                info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
                blueprint_info = redis_client.hgetall(info_key)
                project_goal = blueprint_info.get("project_goal", task_info.get("name", "未命名任务"))

                # 10. 计算 ETA
                eta_seconds = None
                if total_count > 0 and completed_count < total_count:
                    remaining_tasks = total_count - completed_count
                    # 基础估算：每个剩余任务平均 60 秒
                    eta_seconds = remaining_tasks * 60

                workflows.append(ActiveWorkflow(
                    task_id=task_id,
                    project_goal=project_goal[:100] if len(project_goal) > 100 else project_goal,
                    status="running" if celery_status in ["STARTED", "PROGRESS"] else "pending",
                    progress=round(progress, 1),
                    completed_tasks=completed_count,
                    total_tasks=total_count,
                    eta_seconds=eta_seconds,
                    started_at=datetime.fromisoformat(task_info["created_at"]) if "created_at" in task_info else None,
                    mini_dag=mini_dag[:10]  # 最多返回 10 个节点
                ))

            except Exception as e:
                log.warning(f"处理任务 {task_id} 时出错: {e}")
                continue

        # 按进度排序（进度低的在前，表示刚启动）
        workflows.sort(key=lambda w: w.progress)

    except Exception as e:
        log.error(f"获取活跃工作流失败: {e}")

    return ActiveWorkflowsResponse(
        workflows=workflows[:limit],
        total_count=len(workflows)
    )


@router.get("/workflow/{task_id}/eta", response_model=ETAResponse)
async def get_workflow_eta(
    task_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取工作流 ETA 预估

    ETA 计算逻辑:
    1. 优先使用历史数据（如果有相似蓝图）
    2. 否则基于任务类型估算
    3. 考虑已完成任务的进度动态调整
    """
    redis_client = get_redis_client()

    # 1. 获取 DAG 节点状态
    state_key = f"{BLUEPRINT_STATE_PREFIX}{task_id}"
    node_states = redis_client.hgetall(state_key)

    if not node_states:
        return ETAResponse(
            task_id=task_id,
            eta_seconds=None,
            confidence=0.0,
            based_on="estimate"
        )

    # 2. 统计任务状态
    completed_count = 0
    running_count = 0
    pending_count = 0
    total_count = len(node_states)

    for node_id, state_json in node_states.items():
        try:
            state_data = json.loads(state_json)
            status = state_data.get("status", "pending")
            if status == "success":
                completed_count += 1
            elif status == "running":
                running_count += 1
            else:
                pending_count += 1
        except json.JSONDecodeError:
            pending_count += 1

    # 3. 如果全部完成
    if pending_count == 0 and running_count == 0:
        return ETAResponse(
            task_id=task_id,
            eta_seconds=0,
            confidence=1.0,
            based_on="progress"
        )

    # 4. 获取任务开始时间
    info_key = f"{BLUEPRINT_INFO_PREFIX}{task_id}"
    blueprint_info = redis_client.hgetall(info_key)
    start_time_str = blueprint_info.get("started_at")

    elapsed_seconds = 0
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str)
            elapsed_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        except:
            pass

    # 5. ETA 估算策略
    eta_seconds = None
    confidence = 0.5
    based_on = "estimate"

    if completed_count > 0 and elapsed_seconds > 0:
        # 基于已用时间推算（动态调整）
        progress_ratio = completed_count / total_count
        estimated_total = elapsed_seconds / progress_ratio
        eta_seconds = int(estimated_total - elapsed_seconds)
        confidence = min(0.8, 0.3 + progress_ratio * 0.5)  # 进度越高，置信度越高
        based_on = "progress"
    else:
        # 基础估算
        remaining_tasks = pending_count + running_count
        eta_seconds = remaining_tasks * 60  # 每个任务平均 60 秒
        based_on = "estimate"

    return ETAResponse(
        task_id=task_id,
        eta_seconds=eta_seconds,
        confidence=round(confidence, 2),
        based_on=based_on
    )


# ==========================================
# 智能预警与待办中心 API
# ==========================================

class ActionItemAction(BaseModel):
    """待办事项操作"""
    label: str
    action: str  # confirm, reject, view, retry, dismiss
    primary: bool = False


class ActionItemResponse(BaseModel):
    """待办事项响应"""
    id: str
    type: str  # strategy_confirmation, quality_alert, resource_warning, system_notice
    priority: str  # high, medium, low
    title: str
    description: str
    related_task_id: Optional[str] = None
    related_skill_id: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    actions: List[ActionItemAction] = Field(default_factory=list)


class ActionItemsListResponse(BaseModel):
    """待办事项列表响应"""
    items: List[ActionItemResponse]
    total_count: int
    high_priority_count: int


# 待办事项类型枚举
ACTION_ITEM_TYPES = {
    "strategy_confirmation": "策略确认",
    "quality_alert": "质控异常",
    "resource_warning": "资源预警",
    "system_notice": "系统通知",
}

# 优先级配置
PRIORITY_WEIGHTS = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


@router.get("/action-items", response_model=ActionItemsListResponse)
async def get_action_items(
    project_id: Optional[str] = Query(None, description="项目 ID（可选）"),
    limit: int = Query(20, ge=1, le=50, description="返回数量限制"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户待办事项

    数据来源:
    1. Strategy Card 等待确认（Redis: strategy_pending）
    2. 数据质控异常（QualityCheckResult）
    3. 资源预警（Wallet 低余额）
    4. 系统通知

    返回按优先级排序的待办事项列表
    """
    user_id = current_user.id
    items = []

    # ==========================================
    # 1. 资源预警 - 低余额检查
    # ==========================================
    wallet = session.exec(
        select(Wallet).where(Wallet.owner_id == user_id)
    ).first()

    if wallet:
        low_threshold = wallet.low_balance_threshold
        current_balance = wallet.credits_balance

        if current_balance <= low_threshold:
            items.append(ActionItemResponse(
                id=f"low_balance_{user_id}",
                type="resource_warning",
                priority="high" if current_balance <= 0 else "medium",
                title="算力余额不足",
                description=f"当前余额 {current_balance:.1f} CU，低于预警阈值 {low_threshold:.1f} CU。建议及时充值以避免任务中断。",
                created_at=get_utc_now(),
                actions=[
                    ActionItemAction(label="立即充值", action="recharge", primary=True),
                    ActionItemAction(label="稍后提醒", action="dismiss"),
                ]
            ))

    # ==========================================
    # 2. 任务失败预警 - 查询最近失败的任务
    # ==========================================
    recent_failed_query = text("""
        SELECT task_id, tool_id, created_at
        FROM taskrecord
        WHERE project_id IN (SELECT id FROM project WHERE owner_id = :user_id)
          AND status = 'FAILURE'
          AND created_at >= NOW() - INTERVAL '1 hour'
        ORDER BY created_at DESC
        LIMIT 5
    """)

    failed_tasks = session.execute(recent_failed_query, {"user_id": user_id}).fetchall()

    for task in failed_tasks:
        task_id = task[0]
        tool_id = task[1]
        created_at = task[2]

        items.append(ActionItemResponse(
            id=f"failed_task_{task_id}",
            type="quality_alert",
            priority="high",
            title="任务执行失败",
            description=f"任务 {task_id[:8]}... ({tool_id}) 执行失败，需要您关注。",
            related_task_id=task_id,
            created_at=created_at if created_at else get_utc_now(),
            actions=[
                ActionItemAction(label="查看详情", action="view", primary=True),
                ActionItemAction(label="重试任务", action="retry"),
                ActionItemAction(label="忽略", action="dismiss"),
            ]
        ))

    # ==========================================
    # 3. 技能执行成功率预警
    # ==========================================
    skill_stats_query = text("""
        SELECT skill_id, skill_name,
               COUNT(*) as total,
               SUM(CASE WHEN status='FAILURE' THEN 1 ELSE 0 END) as failures
        FROM skillexecutionhistory
        WHERE user_id = :user_id AND created_at >= NOW() - INTERVAL '7 days'
        GROUP BY skill_id, skill_name
        HAVING COUNT(*) >= 3 AND SUM(CASE WHEN status='FAILURE' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) >= 0.5
        LIMIT 3
    """)

    problematic_skills = session.execute(skill_stats_query, {"user_id": user_id}).fetchall()

    for skill in problematic_skills:
        skill_id = skill[0]
        skill_name = skill[1] or skill_id
        total = skill[2]
        failures = skill[3]

        items.append(ActionItemResponse(
            id=f"skill_issue_{skill_id}",
            type="quality_alert",
            priority="medium",
            title=f"技能执行异常：{skill_name}",
            description=f"近7天内执行 {total} 次，失败 {failures} 次。建议检查参数配置或数据质量。",
            related_skill_id=skill_id,
            created_at=get_utc_now(),
            actions=[
                ActionItemAction(label="查看技能", action="view", primary=True),
                ActionItemAction(label="忽略", action="dismiss"),
            ]
        ))

    # ==========================================
    # 4. 系统通知 - 新功能上线等
    # ==========================================
    # TODO: 可以从数据库或配置中读取系统通知
    # 这里先添加一个示例通知
    items.append(ActionItemResponse(
        id="notice_dashboard_v2",
        type="system_notice",
        priority="low",
        title="Dashboard 2.0 已上线",
        description="科研项目指挥中心全新上线，支持工作流追踪、算力分析和智能预警。",
        created_at=get_utc_now(),
        actions=[
            ActionItemAction(label="了解更多", action="view"),
            ActionItemAction(label="知道了", action="dismiss", primary=True),
        ]
    ))

    # ==========================================
    # 按优先级排序
    # ==========================================
    items.sort(key=lambda x: PRIORITY_WEIGHTS.get(x.priority, 0), reverse=True)

    # 计算高优先级数量
    high_priority_count = sum(1 for item in items if item.priority == "high")

    return ActionItemsListResponse(
        items=items[:limit],
        total_count=len(items),
        high_priority_count=high_priority_count
    )


@router.post("/action-items/{item_id}/action")
async def handle_action_item(
    item_id: str,
    action: str = Query(..., description="操作类型: confirm, reject, view, retry, dismiss"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    处理待办事项操作

    根据不同的待办事项类型和操作执行相应逻辑：
    - confirm: 确认执行
    - reject: 拒绝执行
    - view: 查看详情
    - retry: 重试任务
    - dismiss: 忽略
    """
    user_id = current_user.id

    log.info(f"处理待办事项: item_id={item_id}, action={action}, user_id={user_id}")

    # 解析 item_id 判断类型
    if item_id.startswith("low_balance_"):
        # 低余额预警
        if action == "recharge":
            return {
                "success": True,
                "message": "即将跳转到充值页面",
                "redirect": "/billing"
            }
        elif action == "dismiss":
            return {
                "success": True,
                "message": "已忽略余额预警"
            }

    elif item_id.startswith("failed_task_"):
        # 任务失败
        task_id = item_id.replace("failed_task_", "")
        if action == "view":
            return {
                "success": True,
                "message": "即将跳转到任务详情",
                "redirect": f"/chat?task={task_id}"
            }
        elif action == "retry":
            # TODO: 实现任务重试逻辑
            return {
                "success": True,
                "message": "任务已提交重试"
            }
        elif action == "dismiss":
            return {
                "success": True,
                "message": "已忽略失败任务"
            }

    elif item_id.startswith("skill_issue_"):
        # 技能问题
        skill_id = item_id.replace("skill_issue_", "")
        if action == "view":
            return {
                "success": True,
                "message": "即将跳转到技能详情",
                "redirect": f"/skills/{skill_id}"
            }
        elif action == "dismiss":
            return {
                "success": True,
                "message": "已忽略技能预警"
            }

    elif item_id.startswith("notice_"):
        # 系统通知
        if action == "dismiss":
            return {
                "success": True,
                "message": "已关闭通知"
            }
        elif action == "view":
            return {
                "success": True,
                "message": "查看详情",
                "redirect": "/dashboard"
            }

    return {
        "success": False,
        "message": f"未知的操作类型: {action}"
    }


# ==========================================
# 科研资产与洞察速递 API
# ==========================================

class RecentAsset(BaseModel):
    """科研资产"""
    id: str
    type: str  # plot, report, data, code
    title: str
    thumbnail_url: Optional[str] = None
    file_path: str
    file_size: Optional[int] = None
    created_at: datetime
    related_task_id: Optional[str] = None
    download_url: str


class RecentAssetsResponse(BaseModel):
    """科研资产列表响应"""
    assets: List[RecentAsset]
    total_count: int
    plots_count: int
    reports_count: int


# 资产类型配置
ASSET_TYPE_CONFIG = {
    "plot": {
        "extensions": [".png", ".jpg", ".jpeg", ".pdf", ".svg"],
        "icon": "📊",
    },
    "report": {
        "extensions": [".html", ".htm", ".md"],
        "icon": "📄",
    },
    "data": {
        "extensions": [".tsv", ".csv", ".xlsx", ".xls"],
        "icon": "📈",
    },
    "code": {
        "extensions": [".py", ".r", ".sh", ".nf"],
        "icon": "💻",
    },
}


@router.get("/recent-assets", response_model=RecentAssetsResponse)
async def get_recent_assets(
    project_id: Optional[str] = Query(None, description="项目 ID（可选）"),
    asset_type: Optional[str] = Query(None, description="资产类型: plot, report, data, code"),
    limit: int = Query(20, ge=1, le=50, description="返回数量限制"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取最近生成的科研资产

    数据来源:
    - TaskRecord + 文件系统扫描
    - 输出目录中的图表、报告、数据文件

    返回按时间倒序排列的资产列表
    """
    user_id = current_user.id
    assets = []
    plots_count = 0
    reports_count = 0

    # ==========================================
    # 1. 查询最近完成的任务记录
    # ==========================================
    base_query = """
        SELECT task_id, tool_id, project_id, created_at, semantic_dir_name
        FROM taskrecord
        WHERE project_id IN (SELECT id FROM project WHERE owner_id = :user_id)
          AND status = 'SUCCESS'
    """

    if project_id:
        base_query += " AND project_id = :project_id"

    base_query += " ORDER BY created_at DESC LIMIT :limit"

    params = {"user_id": user_id, "limit": limit}
    if project_id:
        params["project_id"] = project_id

    recent_tasks = session.execute(text(base_query), params).fetchall()

    # ==========================================
    # 2. 扫描任务输出目录
    # ==========================================
    for task in recent_tasks:
        task_id = task[0]
        tool_id = task[1]
        task_project_id = task[2]
        created_at = task[3]
        semantic_dir_name = task[4]

        # 构建输出目录路径
        # 参考 result_standardizer.py 的标准输出目录结构
        if semantic_dir_name:
            output_dir = f"/app/uploads/{task_project_id}/{semantic_dir_name}"
        else:
            output_dir = f"/app/uploads/{task_project_id}/results/{task_id}"

        # 检查目录是否存在
        import os
        if not os.path.exists(output_dir):
            continue

        # 扫描目录中的文件
        try:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

                    # 判断文件类型
                    asset_type_detected = None
                    for atype, config in ASSET_TYPE_CONFIG.items():
                        if file_ext in config["extensions"]:
                            asset_type_detected = atype
                            break

                    if not asset_type_detected:
                        continue

                    # 如果指定了类型，只返回该类型
                    if asset_type and asset_type != asset_type_detected:
                        continue

                    # 生成缩略图 URL（仅图片）
                    thumbnail_url = None
                    if asset_type_detected == "plot" and file_ext in [".png", ".jpg", ".jpeg"]:
                        # 生成相对 URL
                        relative_path = file_path.replace("/app/uploads/", "")
                        thumbnail_url = f"/uploads/{relative_path}"

                    # 生成下载 URL
                    relative_path = file_path.replace("/app/uploads/", "")
                    download_url = f"/uploads/{relative_path}"

                    # 统计
                    if asset_type_detected == "plot":
                        plots_count += 1
                    elif asset_type_detected == "report":
                        reports_count += 1

                    assets.append(RecentAsset(
                        id=f"asset_{task_id}_{file}",
                        type=asset_type_detected,
                        title=file,
                        thumbnail_url=thumbnail_url,
                        file_path=file_path,
                        file_size=file_size,
                        created_at=created_at if created_at else get_utc_now(),
                        related_task_id=task_id,
                        download_url=download_url
                    ))

                    # 限制每个任务最多返回 5 个文件
                    task_assets = [a for a in assets if a.related_task_id == task_id]
                    if len(task_assets) >= 5:
                        break

        except Exception as e:
            log.warning(f"扫描任务输出目录失败: {output_dir}, error: {e}")
            continue

    # ==========================================
    # 3. 按时间排序并限制数量
    # ==========================================
    assets.sort(key=lambda x: x.created_at, reverse=True)
    assets = assets[:limit]

    return RecentAssetsResponse(
        assets=assets,
        total_count=len(assets),
        plots_count=plots_count,
        reports_count=reports_count
    )


@router.get("/asset-stats")
async def get_asset_stats(
    project_id: Optional[str] = Query(None, description="项目 ID（可选）"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取资产统计信息

    用于 Dashboard 快速展示资产数量
    """
    user_id = current_user.id

    # 查询成功的任务数
    base_query = """
        SELECT COUNT(*) as total_tasks
        FROM taskrecord
        WHERE project_id IN (SELECT id FROM project WHERE owner_id = :user_id)
          AND status = 'SUCCESS'
    """

    if project_id:
        base_query += " AND project_id = :project_id"

    params = {"user_id": user_id}
    if project_id:
        params["project_id"] = project_id

    result = session.execute(text(base_query), params).first()
    total_tasks = result[0] if result else 0

    return {
        "total_tasks": total_tasks,
        "total_assets_estimate": total_tasks * 3,  # 估算平均每个任务产出 3 个文件
    }