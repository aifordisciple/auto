import docker
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func
from pydantic import BaseModel
from typing import List

from app.core.database import get_session
from app.core.logger import log
from app.models.domain import (
    User, Project, BillingAccount, ChatSession,
    SkillAsset, SkillAssetPublic, SkillStatus
)
from app.api.deps import get_current_superuser

# ✨ 引入底层任务队列引擎
try:
    from app.services.celery_app import celery_app
except ImportError:
    celery_app = None

router = APIRouter()
from sqlmodel import Session, select, func
from pydantic import BaseModel
from app.core.database import get_session
from app.core.logger import log
from app.models.domain import User, Project, BillingAccount, ChatSession
from app.api.deps import get_current_superuser

router = APIRouter()

# ==========================================
# 用户管理相关 Schema
# ==========================================
class CreditUpdate(BaseModel):
    amount: float
    reason: str = "系统管理员手动划拨"
from sqlmodel import Session, select, func
from app.core.database import get_session
from app.models.domain import User, Project, BillingAccount, ChatSession
from app.api.deps import get_current_superuser

router = APIRouter()


@router.get("/stats")
async def get_global_stats(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)  # ✨ 只有管理员能访问
):
    """
    获取全局 SaaS 运营核心数据概览
    """
    # 1. 统计用户与项目
    total_users = session.exec(select(func.count(User.id))).one()
    total_projects = session.exec(select(func.count(Project.id))).one()
    total_sessions = session.exec(select(func.count(ChatSession.id))).one()
    
    # 2. 统计财务数据 (市面上流通的总算力)
    total_credits = session.exec(select(func.sum(BillingAccount.credits_balance))).one() or 0.0
    
    # 3. 统计活跃用户
    active_users = session.exec(select(func.count(User.id)).where(User.is_active == True)).one()
    
    return {
        "status": "success",
        "data": {
            "platform_health": "Healthy",
            "users": {
                "total": total_users,
                "active": active_users
            },
            "workspaces_created": total_projects,
            "ai_sessions": total_sessions,
            "total_credits_outstanding": float(total_credits)
        }
    }



# ==========================================
# 1. 获取全站用户列表 (带分页与财务数据)
# ==========================================
@router.get("/users")
async def get_all_users(
    skip: int = 0, 
    limit: int = 50, 
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    管理员视角：查看全站所有用户及其财务状况
    """
    users = session.exec(select(User).offset(skip).limit(limit)).all()
    
    user_list = []
    for u in users:
        user_list.append({
            "id": u.id,
            "email": u.email,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "credits_balance": u.billing.credits_balance if u.billing else 0.0
        })
        
    return {"status": "success", "data": user_list}

# ==========================================
# 2. 账号封禁与解封引擎 (Ban / Unban)
# ==========================================
@router.post("/users/{target_user_id}/toggle-active")
async def toggle_user_active_status(
    target_user_id: int,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    管理员视角：一键拉黑违规用户，或者解封
    """
    target_user = session.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="未找到该用户")
        
    if target_user.is_superuser:
        raise HTTPException(status_code=403, detail="不能封禁其他超级管理员！")

    target_user.is_active = not target_user.is_active
    session.add(target_user)
    session.commit()
    
    action = "解封" if target_user.is_active else "封禁"
    log.warning(f"🚨 管理员 {admin_user.email} 执行了针对用户 {target_user.email} 的 {action} 操作。")
    
    return {"status": "success", "message": f"用户已{action}", "is_active": target_user.is_active}

# ==========================================
# 3. 财务调控引擎 (充值/扣款)
# ==========================================
@router.post("/users/{target_user_id}/credits")
async def adjust_user_credits(
    target_user_id: int,
    payload: CreditUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    管理员视角：手动为某个用户增加或扣除算力点
    """
    target_user = session.get(User, target_user_id)
    if not target_user or not target_user.billing:
        raise HTTPException(status_code=404, detail="未找到该用户或其计费账户异常")

    # 执行算力划拨
    old_balance = target_user.billing.credits_balance
    target_user.billing.credits_balance += payload.amount
    
    # 防止扣成负数
    if target_user.billing.credits_balance < 0:
         target_user.billing.credits_balance = 0
         
    session.add(target_user.billing)
    session.commit()
    
    log.info(f"💰 财务调控：管理员 {admin_user.email} 为用户 {target_user.email} 修改了算力 ({payload.amount})。原因: {payload.reason}")
    
    return {
        "status": "success", 
        "message": "算力划拨成功",
        "data": {
            "old_balance": old_balance,
            "new_balance": target_user.billing.credits_balance
        }
    }


# ==========================================
# 4. 算力集群雷达 (Cluster Status)
# ==========================================
@router.get("/cluster/status")
async def get_cluster_status(admin_user: User = Depends(get_current_superuser)):
    """
    管理员视角：扫描底层物理机，获取当前正在运行的沙箱容器和异步队列任务。
    """
    cluster_data = {
        "active_sandboxes": [],
        "active_celery_tasks": {}
    }
    
    # 📡 1. 扫描物理 Docker 容器 (寻找野生沙箱)
    try:
        client = docker.from_env()
        # 仅获取运行中的容器
        containers = client.containers.list(filters={"status": "running"})
        for c in containers:
            image_name = ", ".join(c.image.tags) if c.image.tags else c.image.short_id
            # 过滤：只看我们的生信沙箱和 pandas 临时沙箱
            if "autonome" in image_name.lower() or "pandas" in image_name.lower() or "python" in image_name.lower():
                cluster_data["active_sandboxes"].append({
                    "container_id": c.short_id,
                    "name": c.name,
                    "image": image_name,
                    "status": c.status,
                    "created": c.attrs.get('Created')
                })
    except Exception as e:
        log.error(f"Docker 引擎探针异常: {e}")
        cluster_data["active_sandboxes"] = [{"error": f"无法连接到底层 Docker 引擎: {str(e)}"}]

    # 📡 2. 扫描 Celery 任务队列 (看看有谁在排队)
    try:
        if celery_app:
            inspect = celery_app.control.inspect()
            active_tasks = inspect.active() if inspect else None
            reserved_tasks = inspect.reserved() if inspect else None
            
            cluster_data["active_celery_tasks"] = {
                "running": active_tasks or {},
                "queued": reserved_tasks or {}
            }
    except Exception as e:
        log.error(f"Celery 队列探针异常: {e}")
        cluster_data["active_celery_tasks"] = {"error": f"无法连接到 Redis/Celery: {str(e)}"}

    return {"status": "success", "data": cluster_data}

# ==========================================
# 5. 任务物理干预 - 强杀 Celery 任务
# ==========================================
@router.post("/cluster/tasks/{task_id}/revoke")
async def revoke_celery_task(
    task_id: str, 
    admin_user: User = Depends(get_current_superuser)
):
    """
    管理员视角：向 Celery Worker 发送 SIGKILL 死亡信号，强制终止某个耗时任务。
    """
    if not celery_app:
        raise HTTPException(status_code=500, detail="Celery 未配置")
    
    try:
        # terminate=True 极其暴力，直接杀进程
        celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')
        log.warning(f"⚡ 管理员 {admin_user.email} 强制终止了异步任务: {task_id}")
        return {"status": "success", "message": f"强制终止信号已发送至任务 {task_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 6. 任务物理干预 - 强杀 Docker 容器
# ==========================================
@router.post("/cluster/containers/{container_id}/kill")
async def kill_sandbox_container(
    container_id: str, 
    admin_user: User = Depends(get_current_superuser)
):
    """
    管理员视角：物理拔电源，瞬间销毁某个失控的沙箱容器。
    """
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
        # 物理销毁
        container.kill()
        log.warning(f"💥 管理员 {admin_user.email} 物理销毁了沙箱容器: {container_id}")
        return {"status": "success", "message": f"容器 {container_id} 已被物理拔电源并销毁"}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="容器不存在或已自动销毁")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# SKILL 审核相关 API
# ==========================================

class ReviewActionRequest(BaseModel):
    """审核动作请求"""
    action: str  # "APPROVE" 或 "REJECT"
    reject_reason: str = ""


@router.get("/skills/pending", response_model=List[SkillAssetPublic])
def get_pending_skills(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取所有待审核的 SKILL 列表
    """
    statement = select(SkillAsset).where(
        SkillAsset.status == SkillStatus.PENDING_REVIEW
    ).order_by(SkillAsset.updated_at.desc())

    skills = session.exec(statement).all()
    log.info(f"📋 [Admin] 管理员 {admin_user.email} 查询待审核技能，共 {len(skills)} 个")
    return skills


@router.post("/skills/{skill_id}/review")
def review_skill(
    skill_id: str,
    req: ReviewActionRequest,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】审批动作：通过或驳回

    Args:
        skill_id: 技能 ID
        req: 审核动作请求，包含 action (APPROVE/REJECT) 和 reject_reason
    """
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()

    if not skill:
        raise HTTPException(status_code=404, detail="SKILL不存在")

    if skill.status != SkillStatus.PENDING_REVIEW:
        raise HTTPException(status_code=400, detail="该技能不在待审核状态，无法执行此操作")

    if req.action == "APPROVE":
        skill.status = SkillStatus.PUBLISHED
        skill.reject_reason = None
        session.add(skill)
        session.commit()
        log.info(f"✅ 管理员 {admin_user.email} 批准了技能上架: {skill_id}")
        return {
            "status": "success",
            "message": "技能已批准上架",
            "new_status": skill.status.value
        }

    elif req.action == "REJECT":
        if not req.reject_reason:
            raise HTTPException(status_code=400, detail="驳回必须填写理由")

        skill.status = SkillStatus.REJECTED
        skill.reject_reason = req.reject_reason
        session.add(skill)
        session.commit()
        log.warning(f"❌ 管理员 {admin_user.email} 驳回了技能: {skill_id}, 理由: {req.reject_reason}")
        return {
            "status": "success",
            "message": "技能已驳回",
            "new_status": skill.status.value
        }

    else:
        raise HTTPException(status_code=400, detail="未知的审核动作，请使用 APPROVE 或 REJECT")


@router.get("/skills/all", response_model=List[SkillAssetPublic])
def get_all_skills_admin(
    status: str = None,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取所有 SKILL 列表（可按状态筛选）

    Args:
        status: 可选的状态筛选参数
    """
    if status:
        try:
            status_enum = SkillStatus(status)
            statement = select(SkillAsset).where(SkillAsset.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")
    else:
        statement = select(SkillAsset)

    statement = statement.order_by(SkillAsset.created_at.desc())
    skills = session.exec(statement).all()
    return skills


@router.post("/skills/{skill_id}/unpublish")
def unpublish_skill(
    skill_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】下架已发布的技能
    """
    skill = session.exec(select(SkillAsset).where(SkillAsset.skill_id == skill_id)).first()

    if not skill:
        raise HTTPException(status_code=404, detail="SKILL不存在")

    if skill.status != SkillStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="只能下架已发布的技能")

    skill.status = SkillStatus.PRIVATE
    session.add(skill)
    session.commit()

    log.warning(f"⬇️ 管理员 {admin_user.email} 下架了技能: {skill_id}")
    return {
        "status": "success",
        "message": "技能已下架",
        "new_status": skill.status.value
    }


log.info("🛡️ Admin API 路由已加载（含 SKILL 审核）")