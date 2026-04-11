import psutil
import time
import os
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 引入刚刚拆分好的底层模块
from app.core.database import get_session
from app.core.logger import log
from app.models.domain import SystemConfig

# 初始化路由器 (Router)
router = APIRouter()

# -----------------------------------------
# 1. 物理机系统监控接口
# -----------------------------------------
@router.get("/status")
async def get_system_status():
    return {
        "status": "success",
        "data": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": round(psutil.virtual_memory().used / (1024 ** 3), 2),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
            "disk_percent": psutil.disk_usage('/').percent
        }
    }

# -----------------------------------------
# 2. 系统偏好设置接口
# -----------------------------------------
class SettingsUpdate(BaseModel):
    """
    系统设置更新请求体

    支持三套配置：
    - 主模型配置：用于文本对话和主要推理
    - 视觉模型配置：用于图像识别（可选独立配置）
    - 嵌入模型配置：用于技能推荐向量检索
    """
    # 主模型配置
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-3.5-turbo"
    # 视觉模型配置
    vision_api_key: Optional[str] = None
    vision_base_url: Optional[str] = None
    vision_model: Optional[str] = None
    use_shared_vision_config: Optional[bool] = None
    # 嵌入模型配置
    embedding_api_base: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_dimension: Optional[int] = None

@router.get("/settings")
async def get_settings(session: Session = Depends(get_session)):
    # 尝试获取配置，如果没有则自动创建一行 ID 为 1 的默认配置 (防御性编程)
    config = session.get(SystemConfig, 1)
    if not config:
        config = SystemConfig(id=1)
        session.add(config)
        session.commit()
        session.refresh(config)
        
    return {"status": "success", "data": config}

@router.post("/settings")
async def update_settings(settings: SettingsUpdate, session: Session = Depends(get_session)):
    config = session.get(SystemConfig, 1)

    # 如果保存时发现还没配置行，也要自动创建
    if not config:
        config = SystemConfig(id=1)
        session.add(config)

    # ==========================================
    # 主模型配置更新
    # ==========================================
    # 核心修复：使用 is not None 判断，允许用户传入空字符串 "" (Ollama 必备)
    if settings.openai_api_key is not None and not settings.openai_api_key.startswith("sk-***"):
        config.openai_api_key = settings.openai_api_key

    config.openai_base_url = settings.openai_base_url
    config.default_model = settings.default_model

    # ==========================================
    # 视觉模型配置更新
    # ==========================================
    # 视觉模型 API Key（如果提供且不是掩码）
    if settings.vision_api_key is not None and not settings.vision_api_key.startswith("sk-***"):
        config.vision_api_key = settings.vision_api_key

    # 视觉模型 Base URL（如果提供）
    if settings.vision_base_url is not None:
        config.vision_base_url = settings.vision_base_url

    # 视觉模型名称
    if settings.vision_model is not None:
        config.vision_model = settings.vision_model

    # 是否使用共用配置
    if settings.use_shared_vision_config is not None:
        config.use_shared_vision_config = settings.use_shared_vision_config

    # ==========================================
    # 嵌入模型配置更新
    # ==========================================
    if settings.embedding_api_base is not None:
        config.embedding_api_base = settings.embedding_api_base

    if settings.embedding_model is not None:
        config.embedding_model = settings.embedding_model

    if settings.embedding_api_key is not None:
        config.embedding_api_key = settings.embedding_api_key

    if settings.embedding_dimension is not None:
        config.embedding_dimension = settings.embedding_dimension

    config.updated_at = datetime.now(timezone.utc)

    session.add(config)
    session.commit()

    return {"status": "success", "message": "配置已保存！"}

# ==========================================
# 3. 系统健康检查接口
# ==========================================

# 健康检查超时配置（毫秒）
HEALTH_CHECK_TIMEOUT_MS = 5000

@router.get("/health")
async def get_health():
    """
    综合健康检查接口

    检查以下服务状态：
    1. PostgreSQL 数据库连接
    2. Redis 缓存服务
    3. 本地嵌入服务 (Ollama bge-m3)
    4. Docker 容器服务

    返回状态：
    - healthy: 所有服务正常
    - degraded: 部分服务异常但核心功能可用
    - unhealthy: 核心服务不可用
    """
    start_time = time.time()

    # 并行检查所有服务（提高响应速度）
    services = await _check_all_services()

    # 计算整体状态
    overall_status = calculate_overall_status(services)

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "services": services,
    }


async def _check_all_services() -> Dict[str, Any]:
    """
    并行检查所有服务状态

    Returns:
        各服务健康状态字典
    """
    # 使用 asyncio.gather 并行检查
    results = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        check_embedding_health(),
        check_docker_health(),
        return_exceptions=True,  # 即使某个检查失败，也继续其他检查
    )

    services = {
        "database": results[0] if not isinstance(results[0], Exception) else {"status": "error", "error": str(results[0])},
        "redis": results[1] if not isinstance(results[1], Exception) else {"status": "error", "error": str(results[1])},
        "embedding": results[2] if not isinstance(results[2], Exception) else {"status": "error", "error": str(results[2])},
        "docker": results[3] if not isinstance(results[3], Exception) else {"status": "error", "error": str(results[3])},
    }

    return services


async def check_database_health() -> Dict[str, Any]:
    """
    检查 PostgreSQL 数据库连接健康状态

    Returns:
        {
            "status": "healthy" | "unhealthy",
            "latency_ms": 响应延迟毫秒,
            "error": 错误信息（如果有）
        }
    """
    start_time = time.time()

    try:
        from app.core.database import engine
        from sqlmodel import text

        # 执行简单查询测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "type": "postgresql",
        }

    except Exception as e:
        log.error(f"[HealthCheck] Database check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
            "error": str(e),
        }


async def check_redis_health() -> Dict[str, Any]:
    """
    检查 Redis 缓存服务健康状态

    Returns:
        {
            "status": "healthy" | "unhealthy" | "not_configured",
            "latency_ms": 响应延迟毫秒,
            "error": 错误信息（如果有）
        }
    """
    start_time = time.time()

    try:
        # 尝试导入 Redis 服务
        from app.services.cache_service import get_cache_service

        cache = get_cache_service()

        if cache is None:
            return {
                "status": "not_configured",
                "latency_ms": 0,
            }

        # 执行 ping 测试
        result = await cache.ping()

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "healthy" if result else "unhealthy",
            "latency_ms": latency_ms,
            "type": "redis",
        }

    except ImportError:
        return {
            "status": "not_configured",
            "latency_ms": 0,
        }

    except Exception as e:
        log.error(f"[HealthCheck] Redis check failed: {e}")
        return {
            "status": "unhealthy",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
            "error": str(e),
        }


async def check_embedding_health() -> Dict[str, Any]:
    """
    检查本地嵌入服务 (Ollama) 健康状态

    Returns:
        {
            "status": "healthy" | "unhealthy" | "not_configured",
            "model": 模型名称,
            "latency_ms": 响应延迟毫秒,
            "error": 错误信息（如果有）
        }
    """
    start_time = time.time()

    try:
        from app.services.local_embedding_service import get_local_embedding_service

        service = get_local_embedding_service()
        model_name = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")

        if service is None:
            return {
                "status": "not_configured",
                "model": model_name,
                "latency_ms": 0,
            }

        # 检查服务健康状态
        health = await service.check_health()

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": health.get("status", "unknown"),
            "model": health.get("model", model_name),
            "latency_ms": health.get("latency_ms", latency_ms),
            "type": "ollama",
        }

    except ImportError:
        return {
            "status": "not_configured",
            "model": os.getenv("OLLAMA_EMBED_MODEL", "unknown"),
            "latency_ms": 0,
        }

    except Exception as e:
        log.error(f"[HealthCheck] Embedding service check failed: {e}")
        return {
            "status": "unhealthy",
            "model": os.getenv("OLLAMA_EMBED_MODEL", "unknown"),
            "latency_ms": round((time.time() - start_time) * 1000, 2),
            "error": str(e),
        }


async def check_docker_health() -> Dict[str, Any]:
    """
    检查 Docker 服务健康状态

    Returns:
        {
            "status": "healthy" | "unhealthy" | "not_configured",
            "containers": 容器数量,
            "error": 错误信息（如果有）
        }
    """
    try:
        import docker

        client = docker.from_env()

        # 获取容器列表（测试 Docker 连接）
        containers = client.containers.list(all=False)

        return {
            "status": "healthy",
            "containers": len(containers),
            "type": "docker",
        }

    except ImportError:
        return {
            "status": "not_configured",
            "containers": 0,
        }

    except Exception as e:
        log.error(f"[HealthCheck] Docker check failed: {e}")
        return {
            "status": "unhealthy",
            "containers": 0,
            "error": str(e),
        }


def calculate_overall_status(services: Dict[str, Any]) -> str:
    """
    根据各服务状态计算整体健康状态

    逻辑：
    - healthy: 所有核心服务（database, docker）健康
    - degraded: 核心服务健康，辅助服务（redis, embedding）部分异常
    - unhealthy: 核心服务异常

    Args:
        services: 各服务状态字典

    Returns:
        整体状态字符串
    """
    # 核心服务列表
    core_services = ["database", "docker"]

    # 辅助服务列表
    auxiliary_services = ["redis", "embedding"]

    # 检查核心服务状态
    core_healthy = all(
        services.get(svc, {}).get("status") == "healthy"
        for svc in core_services
    )

    # 检查辅助服务状态
    auxiliary_healthy_count = sum(
        1 for svc in auxiliary_services
        if services.get(svc, {}).get("status") in ["healthy", "not_configured"]
    )

    if core_healthy and auxiliary_healthy_count == len(auxiliary_services):
        return "healthy"

    if core_healthy:
        # 核心服务正常，辅助服务有问题
        return "degraded"

    return "unhealthy"
