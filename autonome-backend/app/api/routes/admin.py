import docker
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

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


# ==========================================
# Schema 定义
# ==========================================

class CreditUpdate(BaseModel):
    """算力更新请求"""
    amount: float
    reason: str = "系统管理员手动划拨"


class ExecutionModeUpdate(BaseModel):
    """执行模式更新请求"""
    execution_mode: str  # "docker" 或 "native"
    reason: str = "管理员手动调整"


class BatchExecutionModeUpdate(BaseModel):
    """批量执行模式更新请求"""
    skill_ids: List[str]
    execution_mode: str  # "docker" 或 "native"
    reason: str = "批量更新"


class SkillExecutionModeInfo(BaseModel):
    """技能执行模式信息"""
    skill_id: str
    name: str
    executor_type: str
    execution_mode: str
    status: str
    owner_id: int
    is_official: bool
    execution_mode_updated_at: Optional[datetime] = None
    execution_mode_updated_by: Optional[int] = None


# ==========================================
# 用户管理相关 API
# ==========================================
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
    管理员视角：查看全站所有用户及其财务状况，包含 Claude 权限信息
    """
    users = session.exec(select(User).offset(skip).limit(limit)).all()

    user_list = []
    for u in users:
        user_data = {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "credits_balance": u.billing.credits_balance if u.billing else 0.0
        }

        user_list.append(user_data)

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

    ⚠️ 修复：同时更新 BillingAccount（旧表）和 Wallet（新表），
    确保用户中心、聊天扣费、余额检查都读到一致的余额。
    """
    target_user = session.get(User, target_user_id)
    if not target_user or not target_user.billing:
        raise HTTPException(status_code=404, detail="未找到该用户或其计费账户异常")

    # 1. 更新旧 BillingAccount 表（保持兼容）
    old_balance = target_user.billing.credits_balance
    target_user.billing.credits_balance += payload.amount
    if target_user.billing.credits_balance < 0:
        target_user.billing.credits_balance = 0
    session.add(target_user.billing)

    # 2. 同步更新新 Wallet 表（实际扣费和用户中心读取的表）
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(target_user_id, create_if_not_exists=True)

    if payload.amount >= 0:
        # 充值：使用 recharge 记录交易流水
        billing_service.recharge(
            wallet_id=wallet.wallet_id,
            amount=payload.amount,
            transaction_type="admin_recharge",
            description=f"管理员 {admin_user.email} 充值。原因: {payload.reason}"
        )
    else:
        # 扣款：直接调整余额（不走 deduct_credits，因为可能余额不足）
        wallet.credits_balance += payload.amount
        if wallet.credits_balance < 0:
            wallet.credits_balance = 0
        session.add(wallet)

    session.commit()
    session.refresh(wallet)

    log.info(f"💰 财务调控：管理员 {admin_user.email} 为用户 {target_user.email} 修改了算力 ({payload.amount})。"
             f"BillingAccount: {old_balance}→{target_user.billing.credits_balance}, "
             f"Wallet: {wallet.credits_balance}")

    return {
        "status": "success",
        "message": "算力划拨成功",
        "data": {
            "old_balance": old_balance,
            "new_balance": wallet.credits_balance
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


# ==========================================
# 技能执行模式管理 API
# ==========================================

@router.get("/skills/execution-modes", response_model=List[SkillExecutionModeInfo])
def get_skills_execution_modes(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取所有技能的执行模式配置

    返回所有技能及其当前的执行模式（Docker 或 Native）
    数据来源：
    1. 数据库中的所有技能（包括文件系统技能的影子记录）
    2. 文件系统中的官方预置技能 (app/skills/) 作为补充

    执行模式优先级：数据库记录 > 文件系统默认值
    """
    from app.services.native_executor import is_official_skill
    from app.core.skill_parser import get_skill_parser

    result = []
    seen_skill_ids = set()

    # ==========================================
    # 1. 从数据库加载所有技能（包括影子记录）
    # ==========================================
    db_skills = session.exec(
        select(SkillAsset).order_by(SkillAsset.created_at.desc())
    ).all()

    for skill in db_skills:
        seen_skill_ids.add(skill.skill_id)
        executor_type = skill.executor_type or "Python_env"

        result.append(SkillExecutionModeInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            executor_type=executor_type,
            execution_mode=skill.execution_mode or "docker",
            status=skill.status.value if skill.status else "private",
            owner_id=skill.owner_id,
            is_official=is_official_skill(skill.skill_id, skill.owner_id),
            execution_mode_updated_at=skill.execution_mode_updated_at,
            execution_mode_updated_by=skill.execution_mode_updated_by,
        ))

    log.info(f"📋 [Admin] 从数据库加载 {len(db_skills)} 个技能")

    # ==========================================
    # 2. 从文件系统补充缺失的官方预置技能
    # ==========================================
    try:
        fs_parser = get_skill_parser()
        fs_skills = fs_parser.get_all_skills()
        added_count = 0
        for skill in fs_skills:
            metadata = skill.get("metadata", {})
            skill_id = metadata.get("skill_id")
            if skill_id and skill_id not in seen_skill_ids:
                seen_skill_ids.add(skill_id)
                result.append(SkillExecutionModeInfo(
                    skill_id=skill_id,
                    name=metadata.get("name", skill_id),
                    executor_type=metadata.get("executor_type", "Python_env"),
                    execution_mode="docker",  # 文件系统技能默认使用 docker
                    status="published",  # 官方预置技能默认已发布
                    owner_id=0,  # 官方技能
                    is_official=True,  # 文件系统技能都是官方技能
                    execution_mode_updated_at=None,
                    execution_mode_updated_by=None,
                ))
                added_count += 1
        if added_count > 0:
            log.info(f"📋 [Admin] 从文件系统补充 {added_count} 个官方技能")
    except Exception as e:
        log.warning(f"📋 [Admin] 文件系统技能加载失败: {e}")

    log.info(f"📋 [Admin] 管理员 {admin_user.email} 查询技能执行模式，共 {len(result)} 个")
    return result


@router.patch("/skills/{skill_id}/execution-mode")
def update_skill_execution_mode(
    skill_id: str,
    req: ExecutionModeUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】修改单个技能的执行模式

    Args:
        skill_id: 技能 ID
        req: 执行模式更新请求

    Note:
        只有官方技能才能切换到 Native 执行模式
        支持文件系统中的官方预置技能（会自动创建数据库影子记录）
    """
    from app.services.native_executor import is_official_skill
    from app.core.skill_parser import get_skill_parser

    # 验证执行模式值
    if req.execution_mode not in ["docker", "native"]:
        raise HTTPException(status_code=400, detail="execution_mode 必须是 'docker' 或 'native'")

    # 查询数据库中的技能
    skill = session.exec(
        select(SkillAsset).where(SkillAsset.skill_id == skill_id)
    ).first()

    # 如果数据库中没有，检查文件系统
    if not skill:
        fs_parser = get_skill_parser()
        fs_skill = fs_parser.get_skill_by_id(skill_id)

        if not fs_skill:
            raise HTTPException(status_code=404, detail="技能不存在（数据库和文件系统均未找到）")

        # 文件系统中存在，创建数据库影子记录用于存储执行模式配置
        # 使用管理员 ID 作为 owner_id（满足外键约束，同时标记为系统管理）
        metadata = fs_skill.get("metadata", {})
        skill = SkillAsset(
            skill_id=skill_id,
            name=metadata.get("name", skill_id),
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0.0"),
            executor_type=metadata.get("executor_type", "Python_env"),
            parameters_schema=fs_skill.get("parameters_schema", {}),
            expert_knowledge=fs_skill.get("expert_knowledge"),
            owner_id=admin_user.id,  # 使用当前管理员 ID（满足外键约束）
            status=SkillStatus.PUBLISHED,
            execution_mode="docker",  # 默认值
        )
        session.add(skill)
        session.flush()  # 获取 skill 对象
        log.info(f"📋 [Admin] 为文件系统技能 {skill_id} 创建数据库影子记录")

    # 如果要切换到 Native 模式，验证是否为官方技能
    if req.execution_mode == "native" and not is_official_skill(skill.skill_id, skill.owner_id):
        raise HTTPException(
            status_code=403,
            detail="只有官方技能可以使用原生执行模式。官方技能判断标准：owner_id=1 或特定前缀（fastqc_, multiqc_, singlecell_ 等）或存在于 app/skills/ 目录"
        )

    # 更新执行模式
    old_mode = skill.execution_mode or "docker"
    skill.execution_mode = req.execution_mode
    skill.execution_mode_updated_at = datetime.now(timezone.utc)
    skill.execution_mode_updated_by = admin_user.id

    session.add(skill)
    session.commit()

    log.warning(
        f"⚙️ 管理员 {admin_user.email} 将技能 {skill_id} 执行模式从 {old_mode} 切换为 {req.execution_mode}。"
        f"原因: {req.reason}"
    )

    return {
        "status": "success",
        "message": f"执行模式已更新为 {req.execution_mode}",
        "skill_id": skill_id,
        "old_mode": old_mode,
        "new_mode": req.execution_mode,
        "updated_at": skill.execution_mode_updated_at.isoformat() if skill.execution_mode_updated_at else None,
    }


@router.post("/skills/batch-execution-mode")
def batch_update_execution_mode(
    req: BatchExecutionModeUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】批量更新技能执行模式

    Args:
        req: 批量更新请求，包含 skill_ids 列表和目标执行模式

    Note:
        非官方技能会被自动跳过（不会切换到 Native 模式）
    """
    from app.services.native_executor import is_official_skill

    # 验证执行模式值
    if req.execution_mode not in ["docker", "native"]:
        raise HTTPException(status_code=400, detail="execution_mode 必须是 'docker' 或 'native'")

    updated_skills = []
    skipped_skills = []

    for skill_id in req.skill_ids:
        skill = session.exec(
            select(SkillAsset).where(SkillAsset.skill_id == skill_id)
        ).first()

        if not skill:
            skipped_skills.append({"skill_id": skill_id, "reason": "技能不存在"})
            continue

        # 如果要切换到 Native 模式，验证是否为官方技能
        if req.execution_mode == "native" and not is_official_skill(skill.skill_id, skill.owner_id):
            skipped_skills.append({
                "skill_id": skill_id,
                "reason": "非官方技能，无法使用原生执行模式"
            })
            continue

        # 更新执行模式
        old_mode = skill.execution_mode or "docker"
        skill.execution_mode = req.execution_mode
        skill.execution_mode_updated_at = datetime.now(timezone.utc)
        skill.execution_mode_updated_by = admin_user.id

        session.add(skill)
        updated_skills.append({
            "skill_id": skill_id,
            "old_mode": old_mode,
            "new_mode": req.execution_mode,
        })

    session.commit()

    log.warning(
        f"⚙️ 管理员 {admin_user.email} 批量更新执行模式: "
        f"{len(updated_skills)} 个成功, {len(skipped_skills)} 个跳过。原因: {req.reason}"
    )

    return {
        "status": "success",
        "message": f"已更新 {len(updated_skills)} 个技能",
        "updated_count": len(updated_skills),
        "skipped_count": len(skipped_skills),
        "updated_skills": updated_skills,
        "skipped_skills": skipped_skills,
    }


@router.get("/skills/{skill_id}/execution-history")
def get_skill_execution_history(
    skill_id: str,
    limit: int = 50,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取技能执行历史

    Args:
        skill_id: 技能 ID
        limit: 返回记录数量限制
    """
    from app.models.billing import ComputeRecord

    # 查询执行历史
    records = session.exec(
        select(ComputeRecord)
        .where(ComputeRecord.skill_id == skill_id)
        .order_by(ComputeRecord.created_at.desc())
        .limit(limit)
    ).all()

    result = []
    for record in records:
        result.append({
            "id": record.id,
            "user_id": record.user_id,
            "project_id": record.project_id,
            "execution_mode": record.execution_mode,
            "status": record.status,
            "duration_seconds": record.duration_seconds,
            "credits_charged": record.credits_charged,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        })

    log.info(f"📋 [Admin] 管理员 {admin_user.email} 查询技能 {skill_id} 执行历史，共 {len(result)} 条")
    return {
        "status": "success",
        "skill_id": skill_id,
        "total": len(result),
        "records": result,
    }


# ==========================================
# 缓存监控 API
# ==========================================

@router.get("/cache/stats")
def get_cache_stats(
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取缓存系统统计信息

    返回多层缓存的命中率、延迟等关键指标
    """
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()
    stats = cache.get_stats()

    log.info(f"📊 [Admin] 管理员 {admin_user.email} 查询缓存统计")

    return {
        "status": "success",
        "data": stats
    }


@router.post("/cache/clear")
def clear_cache(
    pattern: str = None,
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】清除缓存

    Args:
        pattern: 可选的缓存键模式，如 "skills:list" 或 "recommend:result"
                 如果不提供，则清除所有缓存
    """
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()

    if pattern:
        deleted = cache.invalidate_pattern(pattern)
        log.warning(f"🧹 管理员 {admin_user.email} 清除缓存模式: {pattern}, 删除 {deleted} 项")
        return {
            "status": "success",
            "message": f"已清除匹配 '{pattern}' 的缓存",
            "deleted_count": deleted
        }
    else:
        # 清除所有缓存
        cache.l2_cache.delete_pattern("*")
        for l1 in cache.l1_caches.values():
            l1.clear()

        log.warning(f"🧹 管理员 {admin_user.email} 清除所有缓存")
        return {
            "status": "success",
            "message": "已清除所有缓存"
        }


@router.post("/cache/reset-stats")
def reset_cache_stats(
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】重置缓存统计数据
    """
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()
    cache.reset_stats()

    log.info(f"📊 管理员 {admin_user.email} 重置缓存统计")

    return {
        "status": "success",
        "message": "缓存统计已重置"
    }


# ==========================================
# 容器预热池管理 API
# ==========================================

@router.get("/container-pool/status")
def get_container_pool_status(
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】获取容器预热池状态

    返回各类型容器的数量、状态、统计数据
    """
    try:
        from app.services.container_pool_service import get_container_pool

        pool = get_container_pool()
        status = pool.get_status()

        log.info(f"📊 管理员 {admin_user.email} 查询容器池状态")

        return {
            "status": "success",
            "data": status
        }
    except ImportError:
        return {
            "status": "error",
            "message": "容器池服务未加载"
        }
    except Exception as e:
        log.error(f"[Admin] 获取容器池状态失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/container-pool/warmup")
def warmup_container_pool(
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】预热容器池

    为每种类型创建最小数量的预热容器
    """
    try:
        from app.services.container_pool_service import get_container_pool

        pool = get_container_pool()
        results = pool.warmup()

        log.info(f"🔥 管理员 {admin_user.email} 预热容器池: {results}")

        return {
            "status": "success",
            "message": "容器池预热完成",
            "created": results
        }
    except ImportError:
        return {
            "status": "error",
            "message": "容器池服务未加载"
        }
    except Exception as e:
        log.error(f"[Admin] 预热容器池失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/container-pool/clear")
def clear_container_pool(
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】清空容器池

    停止并删除所有预热容器
    """
    try:
        from app.services.container_pool_service import get_container_pool

        pool = get_container_pool()
        results = pool.clear_all()

        log.warning(f"🧹 管理员 {admin_user.email} 清空容器池: {results}")

        return {
            "status": "success",
            "message": "容器池已清空",
            "removed": results
        }
    except ImportError:
        return {
            "status": "error",
            "message": "容器池服务未加载"
        }
    except Exception as e:
        log.error(f"[Admin] 清空容器池失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# ==========================================
# ✨ P1 推荐反馈闭环 - 统计监控
# ==========================================

@router.get("/feedback/overview")
def get_feedback_overview(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_superuser)
):
    """
    【管理员专供】推荐反馈闭环总览

    返回：
    - 推荐统计（过去24小时）
    - 用户行为聚合
    - 热门技能排名
    """
    try:
        from app.services.recommendation_feedback_service import RecommendationFeedbackService

        service = RecommendationFeedbackService(session)
        result = service.run_periodic_aggregation()

        log.info(f"📊 管理员 {admin_user.email} 查看反馈统计")

        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        log.error(f"[Admin] 获取反馈统计失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


log.info("🛡️ Admin API 路由已加载（含 SKILL 审核 + 执行模式管理 + 缓存监控 + 容器池管理 + 反馈统计）")