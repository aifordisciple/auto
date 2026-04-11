import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import engine, create_db_and_tables
from app.core.logger import log
from app.models.domain import SystemConfig
# ✨ 导入计费模型确保表创建
from app.models.billing import Wallet, ComputeRecord, TransactionLedger, ResourceFlavor  # noqa: F401

# ✨ 导入所有路由模块
from app.api.routes import system, projects, chat, tasks, auth, billing, public, admin, skills, blueprint, templates, skills_forge, skills_market, skill_share, skill_version, ai_assistant, ai_interpret, skill_recommend, experiences, sample_sheets, packages, genomes, databases, super_executor, terminal, users, claude_executor, error_diagnostic, skill_monitor, preferences, knowledge, weights, learning, plot, dashboard, system_learning
# ✨ 导入拆分后的 chat 子模块路由
from app.api.routes import chat_session, chat_bookmark, chat_tags, chat_summary, chat_search, chat_interpret, chat_experience

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# ==========================================
# 🛡️ CORS 中间件配置 - 必须在所有路由之前注册
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # 不能与 allow_origins=["*"] 同时为 True
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🔇 访问日志过滤中间件 - 过滤掉高频轮询端点的日志
# ==========================================
# 需要过滤访问日志的路径列表（高频轮询、健康检查等）
SKIP_ACCESS_LOG_PATHS = {
    "/api/auth/me",      # 用户信息轮询（每15秒）
}


class AccessLogFilterMiddleware(BaseHTTPMiddleware):
    """
    自定义中间件：过滤特定路径的 uvicorn 访问日志
    避免高频轮询请求刷屏控制台日志
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 如果路径在跳过列表中，抑制 uvicorn 的访问日志
        if request.url.path in SKIP_ACCESS_LOG_PATHS:
            # 通过设置 uvicorn access logger 的级别来抑制此请求的日志
            # uvicorn 使用 logging 模块的 "uvicorn.access" logger
            pass  # 中间件层面无法直接控制 uvicorn 日志，需通过其他方式
        return response


# 抑制 uvicorn 对特定路径的访问日志
# 通过设置 uvicorn.access logger 的 propagate 为 False 并添加自定义 filter
class PathFilter(logging.Filter):
    """过滤特定路径的访问日志"""
    def __init__(self, paths_to_skip: set):
        super().__init__()
        self.paths_to_skip = paths_to_skip

    def filter(self, record: logging.LogRecord) -> bool:
        # 检查日志消息中是否包含需要跳过的路径
        msg = record.getMessage()
        return not any(path in msg for path in self.paths_to_skip)


# 应用过滤器到 uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(PathFilter(SKIP_ACCESS_LOG_PATHS))


# ==========================================
# 🛡️ 全局异常处理器 - 确保所有异常响应都包含 CORS 头
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器：
    捕获所有未处理的异常，返回带有 CORS 头的 JSON 响应。
    这确保了即使是认证失败等异常也能正确返回 CORS 头。
    """
    # 检查是否是 HTTPException，如果是则保留其状态码和详情
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

    # 其他异常返回 500
    log.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.on_event("startup")
def on_startup():
    # ✨ 使用 Loguru 记录启动日志
    log.info(f"🚀 正在启动 {settings.PROJECT_NAME} v{settings.VERSION}")

    # ✨ 首先创建所有数据库表
    create_db_and_tables()
    log.info("✅ 数据库表结构已创建")

    # SaaS 模式下不自动创建项目，由用户注册后自行创建
    with Session(engine) as session:
        if not session.get(SystemConfig, 1):
            env_key = os.getenv("OPENAI_API_KEY")
            session.add(SystemConfig(id=1, openai_api_key=env_key, openai_base_url="https://api.openai.com/v1", default_model="gpt-3.5-turbo", theme="dark"))
            session.commit()
            log.info("✅ 已初始化系统配置")

    # ✨ 初始化技能模板
    try:
        from app.core.init_templates import init_templates
        init_templates()
    except Exception as e:
        log.warning(f"⚠️ 技能模板初始化失败: {e}")

    # ✨ 初始化缓存服务
    try:
        from app.services.cache_service import init_cache_service, start_cache_cleanup_task
        init_cache_service()
        start_cache_cleanup_task(interval=60)  # 每分钟清理过期缓存
        log.info("✅ 缓存服务已初始化")
    except Exception as e:
        log.warning(f"⚠️ 缓存服务初始化失败: {e}")

    # ✨ 初始化容器预热池
    try:
        from app.services.container_pool_service import init_container_pool
        init_container_pool(warmup=True)  # 启动时预热容器
        log.info("✅ 容器预热池已初始化")
    except Exception as e:
        log.warning(f"⚠️ 容器预热池初始化失败: {e}")

# ==========================================
# ⚡️ 注册核心微服务路由 (代码极致解耦)
# ==========================================
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
# ✨ 拆分后的 chat 子模块路由
app.include_router(chat_session.router, prefix="/api/chat", tags=["ChatSession"])
app.include_router(chat_bookmark.router, prefix="/api/chat", tags=["ChatBookmark"])
app.include_router(chat_tags.router, prefix="/api/chat", tags=["ChatTags"])
app.include_router(chat_summary.router, prefix="/api/chat", tags=["ChatSummary"])
app.include_router(chat_search.router, prefix="/api/chat", tags=["ChatSearch"])
app.include_router(chat_interpret.router, prefix="/api/chat", tags=["ChatInterpret"])
app.include_router(chat_experience.router, prefix="/api/chat", tags=["ChatExperience"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(public.router, prefix="/api/public", tags=["Public"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(skills.router, prefix="/api/skills", tags=["Skills"])
app.include_router(skills_forge.router, prefix="/api/skills/forge", tags=["SkillForge"])
app.include_router(skills_market.router, prefix="/api/skills/market", tags=["SkillMarket"])
app.include_router(skill_share.router, prefix="/api/skills/share", tags=["SkillShare"])
app.include_router(skill_version.router, tags=["SkillVersion"])
app.include_router(ai_assistant.router, prefix="/api/ai", tags=["AIAssistant"])
app.include_router(ai_interpret.router, prefix="/api/interpret", tags=["AIInterpret"])
app.include_router(skill_recommend.router, prefix="/api/skills/recommend", tags=["SkillRecommend"])
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(blueprint.router, prefix="/api/blueprint", tags=["Blueprint"])
app.include_router(experiences.router, prefix="/api/experiences", tags=["Experiences"])
app.include_router(sample_sheets.router, tags=["SampleSheets"])
app.include_router(packages.router, prefix="/api/packages", tags=["Packages"])
app.include_router(genomes.router, prefix="/api/genomes", tags=["Genomes"])
app.include_router(databases.router, prefix="/api/databases", tags=["Databases"])
app.include_router(super_executor.router, prefix="/api/super-executor", tags=["SuperExecutor"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["Terminal"])
app.include_router(claude_executor.router, prefix="/api/claude-executor", tags=["ClaudeExecutor"])
app.include_router(error_diagnostic.router, prefix="/api/error", tags=["ErrorDiagnostic"])
app.include_router(skill_monitor.router, prefix="/api/monitor", tags=["SkillMonitor"])
# ✨ 智能学习系统路由
app.include_router(preferences.router, prefix="/api/preferences", tags=["Preferences"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(weights.router, prefix="/api/weights", tags=["Weights"])
app.include_router(learning.router, prefix="/api", tags=["Learning"])
# ✨ 系统学习层路由（隐身学习系统）
app.include_router(system_learning.router, prefix="/api", tags=["SystemLearning"])
# ✨ NL2Vis 交互式图表路由
app.include_router(plot.router, tags=["Plot"])
# ✨ Dashboard 科研项目指挥中心
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

# ✨ 挂载静态文件服务器，允许前端读取 AI 吐出的生信图表！
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    return {"status": f"{settings.PROJECT_NAME} Engine Online", "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    # 只监控 app 目录，避免 uploads 目录变化触发热重载
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs="app")
