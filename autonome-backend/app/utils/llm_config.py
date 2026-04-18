# -*- coding: utf-8 -*-
"""
共享 LLM 配置解析工具

统一管理 LLM 配置的获取逻辑，消除 5+ 处重复代码。

优先级：
1. 用户级配置（User.llm_* 字段，per-user override）
2. 系统全局配置（SystemConfig id=1）
3. 环境变量（.env 中的 OPENAI_API_KEY 等）

使用方式：
    from app.utils.llm_config import get_llm_config
    cfg = get_llm_config(session, user_id=current_user.id)
    llm = ChatOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model_name)
"""

import os
from typing import Optional, NamedTuple

from sqlmodel import Session

from app.core.config import settings
from app.core.logger import log
from app.models.config import SystemConfig
from app.models.user import User


# ==========================================
# LLM 配置数据结构
# ==========================================

class LLMConfig(NamedTuple):
    """解析后的 LLM 配置"""
    api_key: str
    base_url: str
    model_name: str
    source: str  # "user" | "system" | "env"


# ==========================================
# API Key 脱敏常量
# ==========================================

API_KEY_MASK = "sk-************************"


# ==========================================
# 核心解析函数
# ==========================================

def get_llm_config(session: Session, user_id: Optional[int] = None) -> LLMConfig:
    """
    解析 LLM 配置：per-user override → system global → env fallback

    Args:
        session: 数据库会话
        user_id: 用户 ID（None 则跳过 per-user 查找）

    Returns:
        LLMConfig(api_key, base_url, model_name, source)
    """
    # --- 1. 尝试 per-user 配置 ---
    if user_id is not None:
        user = session.get(User, user_id)
        if user and _has_user_llm_config(user):
            return _resolve_user_config(user, session)

    # --- 2. 回退到系统全局配置 ---
    return _resolve_system_config()


def _has_user_llm_config(user: User) -> bool:
    """判断用户是否配置了至少一个 LLM 字段"""
    return (
        user.llm_api_key is not None
        or user.llm_base_url is not None
        or user.llm_model_name is not None
    )


def _resolve_user_config(user: User, session: Session) -> LLMConfig:
    """
    解析用户级配置，未设置的字段从 SystemConfig 回退

    逻辑：
    - 用户设置了 llm_api_key → 使用用户的
    - 用户未设置 llm_api_key → 从 SystemConfig 回退
    - base_url 和 model_name 同理
    - 对 base_url 进行 local model 检测
    """
    # 获取系统配置作为回退
    sys_config = session.get(SystemConfig, 1)
    env_api_key = os.getenv("OPENAI_API_KEY")

    # 逐字段回退
    base_url = user.llm_base_url or (sys_config.openai_base_url if sys_config else None) or settings.OPENAI_BASE_URL
    model_name = user.llm_model_name or (sys_config.default_model if sys_config else None) or "gpt-3.5-turbo"

    # API Key 解析（含 local model 检测）
    is_local_model = _is_local_model(base_url)

    if user.llm_api_key is not None:
        # 用户显式设置了 API Key
        if is_local_model:
            api_key = user.llm_api_key if user.llm_api_key else ""
        else:
            api_key = user.llm_api_key
    else:
        # 从系统配置回退
        sys_api_key = sys_config.openai_api_key if sys_config else None
        if is_local_model:
            api_key = sys_api_key if sys_api_key is not None else ""
        else:
            api_key = sys_api_key if sys_api_key and sys_api_key != "ollama-local" else (env_api_key or "")

    log.debug(f"🤖 [LLM Config] user={user.id}, source=user, model={model_name}, base_url={base_url}")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        source="user",
    )


def _resolve_system_config() -> LLMConfig:
    """解析系统全局配置（原有逻辑）"""
    try:
        from sqlmodel import Session as SQLModelSession
        from app.core.database import engine

        with SQLModelSession(engine) as sys_session:
            config = sys_session.get(SystemConfig, 1)
    except Exception:
        config = None

    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local = _is_local_model(db_base_url)

    if is_local:
        api_key = db_api_key if db_api_key is not None else ""
    else:
        api_key = db_api_key if db_api_key and db_api_key != "ollama-local" else (env_api_key or "")

    base_url = db_base_url if db_base_url else settings.OPENAI_BASE_URL
    model_name = db_model if db_model else "gpt-3.5-turbo"

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        source="system",
    )


# ==========================================
# Celery Worker 专用（自建 Session）
# ==========================================

def get_llm_config_standalone(user_id: Optional[int] = None) -> LLMConfig:
    """
    Celery Worker 专用：自建数据库会话获取 LLM 配置

    在 FastAPI 依赖注入不可用的后台任务中使用。
    """
    from sqlmodel import Session as SQLModelSession
    from app.core.database import engine

    with SQLModelSession(engine) as session:
        return get_llm_config(session, user_id=user_id)


# ==========================================
# 辅助函数
# ==========================================

def _is_local_model(base_url: Optional[str]) -> bool:
    """检测是否为本地模型（Ollama / localhost / host.docker.internal）"""
    if not base_url:
        return False
    return (
        "host.docker.internal" in base_url
        or "ollama" in base_url
        or "localhost" in base_url
    )


def mask_api_key(api_key: Optional[str]) -> Optional[str]:
    """脱敏 API Key：使用 sk-*** 前缀 + 后 4 位，便于前端识别脱敏值"""
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "sk-***"
    return "sk-***" + api_key[-4:]
