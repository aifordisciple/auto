"""
计费系统 API 路由

设计日期: 2026-03-23

API 端点列表：
- GET  /wallet           - 获取钱包信息
- GET  /wallet/balance   - 获取余额（轻量）
- GET  /transactions     - 查询交易记录
- GET  /compute-records  - 查询计算记录
- POST /recharge/create-session - 创建充值会话
- POST /recharge/webhook - 充值回调
- POST /admin/wallets/{id}/adjust - 管理员调整余额
- POST /admin/wallets/{id}/suspend - 管理员挂起钱包
"""

try:
    import stripe
except ImportError:
    stripe = None

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi import Body
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_session
from app.core.config import settings
from app.models.domain import User
from app.models.billing import (
    Wallet,
    WalletType,
    WalletStatus,
    ComputeRecord,
    TaskType,
    TaskStatus,
    TransactionLedger,
    TransactionType,
    ResourceFlavor,
    WalletPublic,
    WalletBalance,
    TransactionPublic,
    ComputeRecordPublic,
    ResourceFlavorPublic,
    RechargeRequest,
    AdminAdjustRequest,
    BillingError,
    InsufficientBalanceError,
    WalletSuspendedError,
)
from app.api.deps import get_current_user, get_current_superuser
from app.services.billing_service import BillingService

router = APIRouter()

# Stripe 配置
if stripe and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


# ==========================================
# 请求/响应模型
# ==========================================

class CheckoutSessionResponse(BaseModel):
    """充值会话响应"""
    checkout_url: str


class TransactionListResponse(BaseModel):
    """交易记录列表响应"""
    items: List[TransactionPublic]
    total: int


class ComputeRecordListResponse(BaseModel):
    """计算记录列表响应"""
    items: List[ComputeRecordPublic]
    total: int


class FlavorListResponse(BaseModel):
    """规格列表响应"""
    items: List[ResourceFlavorPublic]


# ==========================================
# 钱包管理 API
# ==========================================

@router.get("/wallet", response_model=WalletPublic)
async def get_my_wallet(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取当前用户的钱包信息

    如果用户没有钱包，会自动创建一个初始余额为 100 CU 的钱包
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=True)

    return WalletPublic(
        id=wallet.id,
        wallet_id=wallet.wallet_id,
        wallet_type=wallet.wallet_type,
        credits_balance=wallet.credits_balance,
        credits_frozen=wallet.credits_frozen,
        credits_overdraft=wallet.credits_overdraft,
        total_consumed=wallet.total_consumed,
        status=wallet.status,
        low_balance_threshold=wallet.low_balance_threshold,
        created_at=wallet.created_at,
        updated_at=wallet.updated_at
    )


@router.get("/wallet/balance", response_model=WalletBalance)
async def get_wallet_balance(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取钱包余额（轻量接口）

    用于前端实时查询余额，返回最小数据集
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=False)

    if not wallet:
        return WalletBalance(available=0, frozen=0, overdraft=0, total=0)

    return WalletBalance(
        available=wallet.credits_balance,
        frozen=wallet.credits_frozen,
        overdraft=wallet.credits_overdraft,
        total=wallet.credits_balance + wallet.credits_frozen + wallet.credits_overdraft
    )


# ==========================================
# 充值流程 API
# ==========================================

@router.post("/recharge/create-session", response_model=CheckoutSessionResponse)
async def create_recharge_session(
    request: RechargeRequest = Body(default=RechargeRequest(amount=68)),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    创建充值会话

    生产环境：跳转到 Stripe Checkout 页面进行支付
    开发环境：直接充值（无需 Stripe 配置）
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id)

    # 生产环境：使用 Stripe 支付
    if settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID:
        try:
            # 确保 user_id 是字符串
            user_id_str = str(current_user.id)

            # 创建 Checkout Session
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": settings.STRIPE_PRICE_ID,
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=f"{settings.FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
                metadata={
                    "user_id": user_id_str
                },
                customer_email=current_user.email
            )

            return CheckoutSessionResponse(checkout_url=checkout_session.url)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"创建支付会话失败: {str(e)}"
            )

    # 开发/测试环境：直接充值（无需 Stripe）
    if settings.ENVIRONMENT == "development" or settings.DEBUG:
        # 计算充值额度：¥68 = 100 CU
        credits = request.credits if request.credits else (request.amount / 68 * 100)

        # 直接充值
        billing_service.recharge(
            wallet_id=wallet.wallet_id,
            amount=credits,
            transaction_type=TransactionType.RECHARGE_ADMIN,
            description=f"开发环境充值: ¥{request.amount} = {credits} CU",
        )

        session.commit()

        from loguru import logger
        logger.info(f"[Billing] 开发环境充值成功: user={current_user.id}, credits={credits}")

        # 返回成功页面 URL（前端刷新余额）
        return CheckoutSessionResponse(
            checkout_url=f"{settings.FRONTEND_URL}/billing/success?dev_recharge=1&credits={credits}"
        )

    # 生产环境且未配置 Stripe
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="支付系统未配置，请联系管理员"
    )


@router.post("/recharge/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_session)
):
    """
    处理 Stripe Webhook 事件

    支付成功后自动充值到用户钱包
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook 未配置"
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的请求体")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="无效的签名")

    # 处理支付成功事件
    if event["type"] == "checkout.session.completed":
        checkout_session = event["data"]["object"]
        user_id = int(checkout_session["metadata"]["user_id"])

        # 使用 BillingService 充值
        billing_service = BillingService(session)
        wallet = billing_service.get_user_wallet(user_id, create_if_not_exists=True)

        # 充值金额（从配置读取）
        credits = settings.STRIPE_CREDITS_PER_PACK if hasattr(settings, 'STRIPE_CREDITS_PER_PACK') else 100

        billing_service.recharge(
            wallet_id=wallet.wallet_id,
            amount=float(credits),
            transaction_type=TransactionType.RECHARGE_STRIPE,
            description=f"Stripe 充值: +{credits} CU",
            metadata={
                "stripe_session_id": checkout_session["id"],
                "stripe_payment_intent": checkout_session.get("payment_intent")
            }
        )

    return {"status": "success"}


# ==========================================
# 交易记录 API
# ==========================================

@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    transaction_type: Optional[TransactionType] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    查询交易记录

    支持按日期范围和交易类型筛选
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=False)

    if not wallet:
        return TransactionListResponse(items=[], total=0)

    # 构建查询
    query = select(TransactionLedger).where(
        TransactionLedger.wallet_id == wallet.wallet_id
    )

    if start_date:
        query = query.where(TransactionLedger.created_at >= start_date)
    if end_date:
        query = query.where(TransactionLedger.created_at <= end_date)
    if transaction_type:
        query = query.where(TransactionLedger.transaction_type == transaction_type)

    # 统计总数
    count_query = select(TransactionLedger).where(
        TransactionLedger.wallet_id == wallet.wallet_id
    )
    if start_date:
        count_query = count_query.where(TransactionLedger.created_at >= start_date)
    if end_date:
        count_query = count_query.where(TransactionLedger.created_at <= end_date)
    if transaction_type:
        count_query = count_query.where(TransactionLedger.transaction_type == transaction_type)

    total = len(session.exec(count_query).all())

    # 分页查询
    query = query.order_by(TransactionLedger.created_at.desc()).offset(skip).limit(limit)
    items = session.exec(query).all()

    return TransactionListResponse(
        items=[
            TransactionPublic(
                id=item.id,
                transaction_id=item.transaction_id,
                transaction_type=item.transaction_type,
                amount=item.amount,
                balance_before=item.balance_before,
                balance_after=item.balance_after,
                description=item.description,
                created_at=item.created_at
            )
            for item in items
        ],
        total=total
    )


# ==========================================
# 计算记录 API
# ==========================================

@router.get("/compute-records", response_model=ComputeRecordListResponse)
async def get_compute_records(
    project_id: Optional[str] = None,
    task_type: Optional[TaskType] = None,
    task_status: Optional[TaskStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    查询计算记录

    支持按项目、任务类型、状态筛选
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=False)

    if not wallet:
        return ComputeRecordListResponse(items=[], total=0)

    # 构建查询
    query = select(ComputeRecord).where(
        ComputeRecord.wallet_id == wallet.wallet_id
    )

    if project_id:
        query = query.where(ComputeRecord.project_id == project_id)
    if task_type:
        query = query.where(ComputeRecord.task_type == task_type)
    if task_status:
        query = query.where(ComputeRecord.task_status == task_status)

    # 统计总数
    count_query = select(ComputeRecord).where(
        ComputeRecord.wallet_id == wallet.wallet_id
    )
    if project_id:
        count_query = count_query.where(ComputeRecord.project_id == project_id)
    if task_type:
        count_query = count_query.where(ComputeRecord.task_type == task_type)
    if task_status:
        count_query = count_query.where(ComputeRecord.task_status == task_status)

    total = len(session.exec(count_query).all())

    # 分页查询
    query = query.order_by(ComputeRecord.submitted_at.desc()).offset(skip).limit(limit)
    items = session.exec(query).all()

    return ComputeRecordListResponse(
        items=[
            ComputeRecordPublic(
                id=item.id,
                record_id=item.record_id,
                task_type=item.task_type,
                task_name=item.task_name,
                task_status=item.task_status,
                estimated_cost=item.estimated_cost,
                frozen_amount=item.frozen_amount,
                actual_cost=item.actual_cost,
                refund_amount=item.refund_amount,
                duration_seconds=item.duration_seconds,
                submitted_at=item.submitted_at,
                started_at=item.started_at,
                completed_at=item.completed_at
            )
            for item in items
        ],
        total=total
    )


# ==========================================
# 资源规格 API
# ==========================================

@router.get("/flavors", response_model=FlavorListResponse)
async def get_resource_flavors(
    session: Session = Depends(get_session)
):
    """
    获取所有可用的资源规格

    公开接口，不需要登录
    """
    flavors = session.exec(
        select(ResourceFlavor).where(ResourceFlavor.is_active == True)
    ).all()

    return FlavorListResponse(
        items=[
            ResourceFlavorPublic(
                id=flavor.id,
                flavor_id=flavor.flavor_id,
                name=flavor.name,
                description=flavor.description,
                cpu_cores=flavor.cpu_cores,
                memory_gb=flavor.memory_gb,
                gpu_count=flavor.gpu_count,
                price_per_minute=flavor.price_per_minute,
                price_per_hour=flavor.price_per_hour,
                is_default=flavor.is_default
            )
            for flavor in flavors
        ]
    )


# ==========================================
# 管理员 API
# ==========================================

@router.post("/admin/wallets/{wallet_id}/adjust")
async def admin_adjust_balance(
    wallet_id: str,
    request: AdminAdjustRequest = Body(...),
    admin_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """
    管理员调整钱包余额

    正数增加余额，负数扣减余额
    """
    billing_service = BillingService(session)

    try:
        wallet = billing_service.get_wallet(wallet_id)
    except BillingError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        if request.amount >= 0:
            # 充值
            transaction = billing_service.recharge(
                wallet_id=wallet_id,
                amount=request.amount,
                transaction_type=TransactionType.ADMIN_ADJUST,
                description=f"管理员调整: {request.reason}",
                operator_id=admin_user.id
            )
        else:
            # 扣减
            transaction = billing_service.deduct_credits(
                wallet_id=wallet_id,
                amount=abs(request.amount),
                transaction_type=TransactionType.ADMIN_ADJUST,
                description=f"管理员扣减: {request.reason}"
            )

        return {
            "status": "success",
            "wallet_id": wallet_id,
            "new_balance": wallet.credits_balance,
            "transaction_id": transaction.transaction_id
        }

    except InsufficientBalanceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/wallets/{wallet_id}/suspend")
async def admin_suspend_wallet(
    wallet_id: str,
    reason: str = Body(..., embed=True),
    admin_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """
    管理员挂起钱包
    """
    billing_service = BillingService(session)

    try:
        wallet = billing_service.get_wallet(wallet_id)
    except BillingError as e:
        raise HTTPException(status_code=404, detail=str(e))

    wallet.status = WalletStatus.SUSPENDED
    wallet.suspended_at = datetime.now()
    wallet.suspended_reason = reason

    session.add(wallet)
    session.commit()

    return {
        "status": "success",
        "wallet_id": wallet_id,
        "new_status": wallet.status
    }


@router.post("/admin/wallets/{wallet_id}/resume")
async def admin_resume_wallet(
    wallet_id: str,
    admin_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """
    管理员恢复钱包
    """
    billing_service = BillingService(session)

    try:
        wallet = billing_service.get_wallet(wallet_id)
    except BillingError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not wallet:
        raise HTTPException(status_code=404, detail="钱包不存在")

    wallet.status = WalletStatus.ACTIVE
    wallet.suspended_at = None
    wallet.suspended_reason = None

    session.add(wallet)
    session.commit()

    return {
        "status": "success",
        "wallet_id": wallet_id,
        "new_status": wallet.status
    }


# ==========================================
# 兼容旧 API（逐步废弃）
# ==========================================

class CreditsResponse(BaseModel):
    """旧版余额响应（兼容）"""
    credits_balance: float


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取当前用户算力余额（旧版 API，建议使用 /wallet/balance）
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=False)

    return CreditsResponse(
        credits_balance=wallet.credits_balance if wallet else 0
    )


@router.post("/credits/deduct")
async def deduct_credits(
    amount: float = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    扣除算力（内部接口，建议使用 BillingService）

    用于 agent 直接调用扣费
    """
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=False)

    if not wallet:
        raise HTTPException(status_code=402, detail="余额不足")

    try:
        billing_service.deduct_credits(
            wallet_id=wallet.wallet_id,
            amount=amount,
            transaction_type=TransactionType.CONSUME_CHAT,
            description="对话消费"
        )

        return {"remaining": wallet.credits_balance}

    except InsufficientBalanceError as e:
        raise HTTPException(status_code=402, detail=str(e))