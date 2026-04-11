from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
import bcrypt

# 生产环境请将 SECRET_KEY 移入 .env 并配置到 config.py 中
SECRET_KEY = "autonome_super_secret_key_change_me_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 默认 Token 有效期 7 天


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证用户输入的明文密码与数据库中的哈希密码是否匹配"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """将明文密码不可逆加密为哈希值"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """生成带有过期时间的 JWT 令牌"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # sub (Subject) 通常用来存放用户 ID 或 Email
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
