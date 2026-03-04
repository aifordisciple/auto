import psutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional

# 引入刚刚拆分好的底层模块
from app.core.database import get_session
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
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-3.5-turbo"

@router.get("/settings")
async def get_settings(session: Session = Depends(get_session)):
    return {"status": "success", "data": session.get(SystemConfig, 1)}

@router.post("/settings")
async def update_settings(settings: SettingsUpdate, session: Session = Depends(get_session)):
    config = session.get(SystemConfig, 1)
    if config:
        # 如果不是掩码，才更新 Key
        if settings.openai_api_key and not settings.openai_api_key.startswith("sk-***"):
            config.openai_api_key = settings.openai_api_key
        config.openai_base_url = settings.openai_base_url
        config.default_model = settings.default_model
        config.updated_at = datetime.now(timezone.utc)
        
        session.add(config)
        session.commit()
        return {"status": "success", "message": "配置已保存！"}
    return {"status": "error"}
