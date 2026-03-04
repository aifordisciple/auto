try:
    import stripe
except ImportError:
    stripe = None
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.core.config import settings
from app.models.domain import User, BillingAccount
from app.api.deps import get_current_user

router = APIRouter()

# Stripe configuration
if stripe and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.core.config import settings
from app.models.domain import User, BillingAccount
from app.api.deps import get_current_user

router = APIRouter()

# Stripe configuration
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class CreditsResponse(BaseModel):
    credits_balance: float


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """创建 Stripe Checkout Session，让用户跳转支付"""
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system not configured"
        )
    
    try:
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
                "user_id": str(current_user.id)
            },
            customer_email=current_user.email
        )
        
        return CheckoutSessionResponse(checkout_url=checkout_session.url)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}"
        )


@router.post("/webhook")
async def stripe_webhook(request: Request, session: Session = Depends(get_session)):
    """处理 Stripe Webhook 事件"""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured"
        )
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # 处理支付成功事件
    if event["type"] == "checkout.session.completed":
        checkout_session = event["data"]["object"]
        user_id = checkout_session["metadata"]["user_id"]
        
        # 查找用户并充值
        user = session.get(User, user_id)
        if user and user.billing:
            user.billing.credits_balance += settings.STRIPE_CREDITS_PER_PACK
            session.add(user.billing)
            session.commit()
    
    return {"status": "success"}


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(current_user: User = Depends(get_current_user)):
    """获取当前用户算力余额"""
    return CreditsResponse(
        credits_balance=current_user.billing.credits_balance if current_user.billing else 0
    )


@router.post("/credits/deduct")
async def deduct_credits(
    amount: float,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """扣除算力（内部接口，用于 agent 调用）"""
    if not current_user.billing:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    if current_user.billing.credits_balance < amount:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    current_user.billing.credits_balance -= amount
    session.add(current_user.billing)
    session.commit()
    
    return {"remaining": current_user.billing.credits_balance}
