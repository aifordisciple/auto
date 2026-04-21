from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime

from app.core.database import get_session
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.domain import User, BillingAccount
from app.api.deps import get_current_user

router = APIRouter()

# ============================================================
# 原有 Schemas
# ============================================================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

class Token(BaseModel):
    access_token: str
    token_type: str

# ============================================================
# 新增 Schemas：手机号登录 & 会话管理（阶段1仅定义，不实现路由）
# ============================================================

class UserCreateWithPhone(BaseModel):
    """手机号 + 验证码注册/登录请求"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="中国大陆 11 位手机号")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6 位短信验证码")
    captcha_token: Optional[str] = Field(None, description="人机验证通过凭证")

class UserLoginWithPhone(BaseModel):
    """手机号登录请求：支持验证码或密码两种方式"""
    phone_number: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="中国大陆 11 位手机号")
    otp_code: Optional[str] = Field(None, min_length=6, max_length=6, description="免密登录验证码")
    password: Optional[str] = Field(None, min_length=8, description="传统密码登录")

    @field_validator('password')
    @classmethod
    def check_password_or_otp(cls, v, info):
        """必须提供验证码或密码中的至少一种"""
        if not v and not info.data.get('otp_code'):
            raise ValueError('必须提供验证码或密码')
        return v

class ActiveSessionOut(BaseModel):
    """活跃会话输出 Schema（供前端设备管理面板渲染）"""
    session_id: int
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    created_at: datetime
    last_active_at: datetime
    is_revoked: bool

    class Config:
        from_attributes = True

@router.post("/register")
async def register_user(user_in: UserCreate, session: Session = Depends(get_session)):
    # 检查邮箱是否已存在
    user = session.exec(select(User).where(User.email == user_in.email)).first()
    if user:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")
        
    # 创建新用户
    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(email=user_in.email, hashed_password=hashed_pwd, full_name=user_in.full_name)
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    # ✨ 注册时，自动为用户创建计费账户（默认送 100 点算力）
    billing = BillingAccount(user_id=new_user.id, credits_balance=100.0)
    session.add(billing)
    
    # ✨ 注册时，自动为用户创建一个默认项目
    from app.models.domain import Project
    default_project = Project(
        name="My First Project",
        description="Default workspace",
        owner_id=new_user.id
    )
    session.add(default_project)
    session.commit()
    
    return {"status": "success", "message": "注册成功", "user_id": new_user.id}

@router.post("/login", response_model=Token)
async def login_access_token(
    session: Session = Depends(get_session), 
    form_data: OAuth2PasswordRequestForm = Depends() # 接收标准的 form-data 账号密码
):
    # form_data.username 这里我们当作 email 使用
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="邮箱或密码错误")
        
    # 签发 JWT (存入 user.id)
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
async def read_users_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取当前登录用户信息及算力余额

    ⚠️ 修复：余额从 Wallet 表读取（实际扣费使用的表），
    而非旧的 BillingAccount 表，确保与用户中心、聊天扣费一致。
    """
    # 从 Wallet 表读取真实余额
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id, create_if_not_exists=True)
    credits_balance = wallet.credits_balance if wallet else 0.0

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_superuser": current_user.is_superuser,
        "credits_balance": credits_balance,
        # 阶段1新增字段：手机号、邮箱验证状态、2FA 状态
        "phone_number": getattr(current_user, 'phone_number', None),
        "is_email_verified": getattr(current_user, 'is_email_verified', False),
        "is_2fa_enabled": getattr(current_user, 'is_2fa_enabled', False),
    }
