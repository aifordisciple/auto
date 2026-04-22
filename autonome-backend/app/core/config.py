import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 基础信息
    PROJECT_NAME: str = "Autonome Studio"
    VERSION: str = "2.0.0 (Enterprise)"

    # 环境配置
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = False

    # 数据库配置 (默认使用 SQLite，未来如果要换 PostgreSQL，只需在 .env 里改这个值)
    DATABASE_URL: str = "sqlite:///autonome.db"
    
    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        """Redis 连接 URL（从 REDIS_HOST 和 REDIS_PORT 派生）"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/2"
    
    # 文件存储配置
    UPLOAD_DIR: str = "uploads"
    
    # JWT 配置
    SECRET_KEY: str = ""  # 必须在 .env 中设置，启动时校验非空
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days（旧端点兼容）
    # 新端点使用短命 AT + 长命 RT
    ACCESS_TOKEN_SHORT_EXPIRE_MINUTES: int = 15  # 15 分钟（新认证端点）
    # Refresh Token 有效期（天），用于长效会话保持
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Cookie 安全配置：生产环境必须设为 True（要求 HTTPS）
    SECURE_COOKIES: bool = False

    # 阿里云短信服务配置
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = "Autonome"
    ALIYUN_SMS_TEMPLATE_CODE: str = ""

    # SMTP 邮件服务配置（安全邮箱绑定）
    SMTP_HOST: str = ""          # SMTP 服务器地址，如 smtp.gmail.com
    SMTP_PORT: int = 587         # SMTP 端口
    SMTP_USER: str = ""          # SMTP 用户名
    SMTP_PASSWORD: str = ""      # SMTP 密码或应用专用密码
    SMTP_FROM: str = ""          # 发件人地址（默认与 SMTP_USER 相同）
    SMTP_TLS: bool = True        # 是否使用 TLS

    # OAuth 第三方登录配置
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # OpenAI 默认 Base URL（作为数据库中未配置时的回退值）
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Ollama MLX 加速配置（Apple Silicon Mac 上启用 MLX 后端提升推理速度）
    OLLAMA_MLX: int = 0  # 设置为 1 启用 MLX 加速
    
    # Stripe 支付配置
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""  # Credits pack price ID
    STRIPE_CREDITS_PER_PACK: int = 100
    
    # 前端 URL
    FRONTEND_URL: str = "http://localhost:3000"

    # 后端 API Base URL（OAuth 回调地址构造使用）
    BASE_URL: str = "http://localhost:8000"
    
    # 读取 .env 文件，忽略额外的环境变量
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# 实例化全局单例配置对象
settings = Settings()

# 校验 SECRET_KEY 非空，防止生产环境使用空密钥
if not settings.SECRET_KEY:
    raise ValueError("SECRET_KEY 必须在 .env 文件中设置，不能为空")

# 确保上传目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# ✨ 设置 OLLAMA_MLX 环境变量（供 Ollama 进程读取）
# 当 .env 中 OLLAMA_MLX=1 时，将环境变量传递给子进程（如 Ollama）
if settings.OLLAMA_MLX:
    os.environ["OLLAMA_MLX"] = "1"
