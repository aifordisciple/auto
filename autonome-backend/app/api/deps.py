from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import SECRET_KEY, ALGORITHM
from app.models.domain import User

# FastAPI 自带的 OAuth2 密码流配置（告知 Swagger UI 登录接口在哪里）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    """
    核心安全拦截器：
    1. 提取请求头中的 Bearer Token
    2. 验证并解码 JWT
    3. 从数据库提取当前操作的用户对象
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败或 Token 已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = session.get(User, int(user_id))
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="该账户已被封禁")
        
    return user



def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    终极安全拦截器：
    不仅要求用户已登录，还必须具备超级管理员权限！
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="越权警告：您的账号级别不足以访问系统级控制台。"
        )
    return current_user