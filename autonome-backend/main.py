import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import engine
from app.core.logger import log
from app.models.domain import SystemConfig

# ✨ 导入所有路由模块
from app.api.routes import system, projects, chat, tasks, auth, billing, public, admin

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # ✨ 使用 Loguru 记录启动日志
    log.info(f"🚀 正在启动 {settings.PROJECT_NAME} v{settings.VERSION}")
    
    # SaaS 模式下不自动创建项目，由用户注册后自行创建
    with Session(engine) as session:
        if not session.get(SystemConfig, 1):
            env_key = os.getenv("OPENAI_API_KEY")
            session.add(SystemConfig(id=1, openai_api_key=env_key, openai_base_url="https://api.openai.com/v1", default_model="gpt-3.5-turbo", theme="dark"))
            session.commit()
            log.info("✅ 已初始化系统配置")

# ==========================================
# ⚡️ 注册核心微服务路由 (代码极致解耦)
# ==========================================
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(public.router, prefix="/api/public", tags=["Public"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(public.router, prefix="/api/public", tags=["Public"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])

# ✨ 挂载静态文件服务器，允许前端读取 AI 吐出的生信图表！
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    return {"status": f"{settings.PROJECT_NAME} Engine Online", "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
