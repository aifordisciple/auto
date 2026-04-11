from sqlmodel import Session, create_engine, SQLModel, text
from app.core.config import settings

# 根据配置初始化数据库引擎
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

# PostgreSQL 连接池配置
engine_kwargs = {
    "echo": False,
    "connect_args": connect_args,
}

# 仅对 PostgreSQL 添加连接池配置（SQLite 不支持）
if "postgresql" in settings.DATABASE_URL:
    engine_kwargs.update({
        "pool_size": 10,           # 基础连接池大小
        "max_overflow": 20,        # 额外连接数上限
        "pool_pre_ping": True,     # 使用前验证连接有效性
        "pool_recycle": 3600,      # 1小时后回收连接
        "pool_timeout": 30,        # 获取连接超时时间
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

def create_db_and_tables():
    """建表函数，稍后在 main.py 启动时调用"""
    # ✨ 如果是 PostgreSQL，先创建 pgvector 扩展
    if "postgresql" in settings.DATABASE_URL:
        with engine.connect() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            except Exception as e:
                print(f"Warning: Could not create pgvector extension: {e}")

            # ✨ 确保 skillstatus 枚举包含所有必需的值
            # 这是为了处理已有数据库中枚举值不完整的情况
            try:
                # 检查并添加 DEPRECATED 值（如果不存在）
                result = conn.execute(text(
                    "SELECT 1 FROM pg_enum WHERE enumtypid = 'skillstatus'::regclass AND enumlabel = 'DEPRECATED'"
                ))
                if not result.fetchone():
                    conn.execute(text("ALTER TYPE skillstatus ADD VALUE IF NOT EXISTS 'DEPRECATED'"))
                    conn.commit()
                    print("Added 'DEPRECATED' to skillstatus enum")
            except Exception as e:
                print(f"Warning: Could not update skillstatus enum: {e}")

    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI 依赖注入生成器：为每个请求提供独立的 Session"""
    with Session(engine) as session:
        yield session
