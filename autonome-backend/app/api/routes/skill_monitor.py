"""
技能监控 API - 提供监控指标和告警管理

端点：
- GET /metrics: 获取所有技能的监控指标
- GET /metrics/{skill_id}: 获取特定技能的监控指标
- GET /alerts: 获取活跃告警
- POST /alerts/{alert_id}/resolve: 解决告警
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.services.skill_monitor import get_monitor, SkillMonitor


router = APIRouter()


# ==========================================
# GET /metrics - 获取所有技能监控指标
# ==========================================
@router.get("/metrics")
async def get_all_metrics(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取所有技能的监控指标

    返回：
    - 各技能的执行统计
    - 成功率、错误率、超时率
    - 平均执行时间
    """
    monitor = get_monitor()
    metrics = monitor.get_all_metrics()

    return {
        "status": "success",
        "total_skills": len(metrics),
        "metrics": metrics
    }


# ==========================================
# GET /metrics/{skill_id} - 获取特定技能监控指标
# ==========================================
@router.get("/metrics/{skill_id}")
async def get_skill_metrics(
    skill_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取特定技能的监控指标

    Args:
        skill_id: 技能ID

    Returns:
        该技能的详细监控指标
    """
    monitor = get_monitor()
    metrics = monitor.get_metrics(skill_id)

    return {
        "status": "success",
        **metrics
    }


# ==========================================
# GET /alerts - 获取活跃告警
# ==========================================
@router.get("/alerts")
async def get_active_alerts(
    skill_id: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取活跃告警列表

    Args:
        skill_id: 可选，过滤特定技能的告警
        severity: 可选，过滤特定严重程度的告警 (info/warning/critical/emergency)

    Returns:
        活跃告警列表
    """
    monitor = get_monitor()
    alerts = monitor.get_active_alerts(skill_id)

    # 过滤严重程度
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]

    # 按严重程度排序
    severity_order = {"emergency": 0, "critical": 1, "warning": 2, "info": 3}
    alerts = sorted(alerts, key=lambda a: severity_order.get(a["severity"], 99))

    return {
        "status": "success",
        "total_alerts": len(alerts),
        "alerts": alerts
    }


# ==========================================
# POST /alerts/{alert_id}/resolve - 解决告警
# ==========================================
@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    标记告警为已解决

    Args:
        alert_id: 告警ID

    Returns:
        操作结果
    """
    monitor = get_monitor()
    success = monitor.resolve_alert(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail="告警不存在或已解决")

    log.info(f"✅ [Monitor] 用户 {current_user.id} 解决了告警 {alert_id}")

    return {
        "status": "success",
        "message": f"告警 {alert_id} 已解决"
    }


# ==========================================
# GET /health - 监控系统健康检查
# ==========================================
@router.get("/health")
async def monitor_health():
    """
    监控系统健康检查（无需认证）

    Returns:
        系统健康状态
    """
    monitor = get_monitor()
    active_alerts = monitor.get_active_alerts()

    # 统计告警
    critical_count = sum(1 for a in active_alerts if a["severity"] == "critical")
    warning_count = sum(1 for a in active_alerts if a["severity"] == "warning")

    # 判断健康状态
    if critical_count > 0:
        health_status = "unhealthy"
    elif warning_count > 0:
        health_status = "degraded"
    else:
        health_status = "healthy"

    return {
        "status": health_status,
        "active_alerts": {
            "total": len(active_alerts),
            "critical": critical_count,
            "warning": warning_count
        },
        "monitored_skills": len(monitor.execution_records)
    }


log.info("✅ 技能监控 API 已加载")