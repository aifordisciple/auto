import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 基础信息
    PROJECT_NAME: str = "Autonome Studio"
    VERSION: str = "2.0.0 (Enterprise)"
    
    # 数据库配置 (默认使用 SQLite，未来如果要换 PostgreSQL，只需在 .env 里改这个值)
    DATABASE_URL: str = "sqlite:///autonome.db"
    
    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # 文件存储配置
    UPLOAD_DIR: str = "uploads"
    
    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Stripe 支付配置
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""  # Credits pack price ID
    STRIPE_CREDITS_PER_PACK: int = 100
    
    # 前端 URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # 读取 .env 文件，忽略额外的环境变量
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# 实例化全局单例配置对象
settings = Settings()

# 确保上传目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
