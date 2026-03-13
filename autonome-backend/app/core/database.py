from sqlmodel import Session, create_engine, SQLModel, text
from app.core.config import settings

# 根据配置初始化数据库引擎
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args
)

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

    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI 依赖注入生成器：为每个请求提供独立的 Session"""
    with Session(engine) as session:
        yield session
