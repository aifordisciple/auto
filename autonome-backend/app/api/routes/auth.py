from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr

from app.core.database import get_session
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.domain import User, BillingAccount
from app.api.deps import get_current_user

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

class Token(BaseModel):
    access_token: str
    token_type: str

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
async def read_users_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息及算力余额"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_superuser": current_user.is_superuser,
        "credits_balance": current_user.billing.credits_balance if current_user.billing else 0
    }
