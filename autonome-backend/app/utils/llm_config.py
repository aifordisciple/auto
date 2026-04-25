# -*- coding: utf-8 -*-
"""
共享 LLM 配置解析工具

统一管理思考模型 / 极速模型配置的获取逻辑，消除 5+ 处重复代码。

优先级：
1. 用户级配置（User.thinking_* / User.fast_* 字段，per-user override）
2. 系统全局配置（SystemConfig id=1 的 thinking_* / fast_* 字段）
3. 环境变量（.env 中的 OPENAI_API_KEY 等）

使用方式：
    from app.utils.llm_config import get_thinking_llm_config, get_fast_llm_config
    cfg = get_thinking_llm_config(session, user_id=current_user.id)
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

def get_thinking_llm_config(session: Session, user_id: Optional[int] = None) -> LLMConfig:
    """
    解析思考模型配置：per-user override → system global → env fallback

    Args:
        session: 数据库会话
        user_id: 用户 ID（None 则跳过 per-user 查找）

    Returns:
        LLMConfig(api_key, base_url, model_name, source)
    """
    # --- 1. 尝试 per-user 配置 ---
    if user_id is not None:
        user = session.get(User, user_id)
        if user and _has_user_thinking_config(user):
            return _resolve_user_thinking_config(user, session)

    # --- 2. 回退到系统全局配置 ---
    return _resolve_system_thinking_config()


def _has_user_thinking_config(user: User) -> bool:
    """判断用户是否配置了至少一个思考模型字段"""
    return (
        user.thinking_api_key is not None
        or user.thinking_base_url is not None
        or user.thinking_model_name is not None
    )


def _resolve_user_thinking_config(user: User, session: Session) -> LLMConfig:
    """
    解析用户级思考模型配置，未设置的字段从 SystemConfig 回退

    逻辑：
    - 用户设置了 thinking_api_key → 使用用户的
    - 用户未设置 thinking_api_key → 从 SystemConfig 回退
    - base_url 和 model_name 同理
    - 对 base_url 进行 local model 检测
    """
    # 获取系统配置作为回退
    sys_config = session.get(SystemConfig, 1)
    env_api_key = os.getenv("OPENAI_API_KEY")

    # 逐字段回退
    base_url = user.thinking_base_url or (sys_config.thinking_base_url if sys_config else None) or settings.OPENAI_BASE_URL
    model_name = user.thinking_model_name or (sys_config.thinking_model if sys_config else None) or "gpt-3.5-turbo"

    # API Key 解析（含 local model 检测）
    is_local_model = _is_local_model(base_url)

    if user.thinking_api_key is not None:
        # 用户显式设置了 API Key
        if is_local_model:
            api_key = user.thinking_api_key if user.thinking_api_key else ""
        else:
            api_key = user.thinking_api_key
    else:
        # 从系统配置回退
        sys_api_key = sys_config.thinking_api_key if sys_config else None
        if is_local_model:
            api_key = sys_api_key if sys_api_key is not None else ""
        else:
            api_key = sys_api_key if sys_api_key and sys_api_key != "ollama-local" else (env_api_key or "")

    log.debug(f"🤖 [Thinking LLM Config] user={user.id}, source=user, model={model_name}, base_url={base_url}")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        source="user",
    )


def _resolve_system_thinking_config() -> LLMConfig:
    """解析系统全局思考模型配置（原有逻辑）"""
    try:
        from sqlmodel import Session as SQLModelSession
        from app.core.database import engine

        with SQLModelSession(engine) as sys_session:
            config = sys_session.get(SystemConfig, 1)
    except Exception:
        config = None

    db_api_key = config.thinking_api_key if config else None
    db_base_url = config.thinking_base_url if config else None
    db_model = config.thinking_model if config else None

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
# 极速模型配置解析
# ==========================================

def get_fast_llm_config(session: Session, user_id: Optional[int] = None) -> LLMConfig:
    """
    解析极速模型配置：per-user fast → system fast → 思考模型配置

    三级回退链路：
    1. 用户级 fast_* 字段（任一字段非 None 即视为使用用户配置）
    2. 系统级 fast_* 字段
    3. 思考模型配置（get_thinking_llm_config 的结果，保持向后兼容）

    Args:
        session: 数据库会话
        user_id: 用户 ID（None 则跳过 per-user 查找）

    Returns:
        LLMConfig(api_key, base_url, model_name, source)
    """
    # --- 1. 尝试 per-user 极速模型配置 ---
    if user_id is not None:
        user = session.get(User, user_id)
        if user and _has_user_fast_config(user):
            return _resolve_user_fast_config(user, session)

    # --- 2. 尝试系统级极速模型配置 ---
    sys_config = session.get(SystemConfig, 1)
    if sys_config and _has_system_fast_config(sys_config):
        return _resolve_system_fast_config(sys_config)

    # --- 3. 回退到思考模型配置（极速未配时复用思考模型）---
    return get_thinking_llm_config(session, user_id)


def _has_user_fast_config(user: User) -> bool:
    """判断用户是否配置了至少一个极速模型字段"""
    return (
        user.fast_api_key is not None
        or user.fast_base_url is not None
        or user.fast_model_name is not None
    )


def _has_system_fast_config(sys_config: SystemConfig) -> bool:
    """判断系统是否配置了至少一个极速模型字段"""
    return (
        sys_config.fast_api_key is not None
        or sys_config.fast_base_url is not None
        or (sys_config.fast_model is not None and sys_config.fast_model != "")
    )


def _resolve_user_fast_config(user: User, session: Session) -> LLMConfig:
    """
    解析用户级极速模型配置，未设置的字段逐级回退

    回退链路：用户 fast_* → 系统 fast_* → 思考模型配置
    """
    sys_config = session.get(SystemConfig, 1)
    env_api_key = os.getenv("OPENAI_API_KEY")

    # 逐字段回退：用户 fast → 系统 fast → 思考模型
    base_url = (
        user.fast_base_url
        or (sys_config.fast_base_url if sys_config else None)
        or user.thinking_base_url
        or (sys_config.thinking_base_url if sys_config else None)
        or settings.OPENAI_BASE_URL
    )
    model_name = (
        user.fast_model_name
        or (sys_config.fast_model if sys_config else None)
        or user.thinking_model_name
        or (sys_config.thinking_model if sys_config else None)
        or "gpt-3.5-turbo"
    )

    # API Key 解析（含 local model 检测）
    is_local_model = _is_local_model(base_url)

    # 优先使用用户 fast_api_key，然后回退到系统 fast_api_key，最后回退到思考模型
    api_key = _resolve_api_key_with_fallback(
        primary_key=user.fast_api_key,
        fallback_keys=[
            sys_config.fast_api_key if sys_config else None,
            user.thinking_api_key,
            sys_config.thinking_api_key if sys_config else None,
        ],
        env_api_key=env_api_key,
        is_local_model=is_local_model,
    )

    log.debug(
        f"🧠 [Fast LLM Config] user={user.id}, source=user_fast, "
        f"model={model_name}, base_url={base_url}"
    )

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        source="user_fast",
    )


def _resolve_system_fast_config(sys_config: SystemConfig) -> LLMConfig:
    """
    解析系统级极速模型配置，未设置的字段回退到思考模型配置

    回退链路：系统 fast_* → 思考模型配置
    """
    env_api_key = os.getenv("OPENAI_API_KEY")

    # 逐字段回退：系统 fast → 思考模型
    base_url = (
        sys_config.fast_base_url
        or sys_config.thinking_base_url
        or settings.OPENAI_BASE_URL
    )
    model_name = (
        sys_config.fast_model
        or sys_config.thinking_model
        or "gpt-3.5-turbo"
    )

    is_local_model = _is_local_model(base_url)

    api_key = _resolve_api_key_with_fallback(
        primary_key=sys_config.fast_api_key,
        fallback_keys=[
            sys_config.thinking_api_key,
        ],
        env_api_key=env_api_key,
        is_local_model=is_local_model,
    )

    log.debug(
        f"🧠 [Fast LLM Config] source=system_fast, "
        f"model={model_name}, base_url={base_url}"
    )

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        source="system_fast",
    )


def _resolve_api_key_with_fallback(
    primary_key: Optional[str],
    fallback_keys: list[Optional[str]],
    env_api_key: Optional[str],
    is_local_model: bool,
) -> str:
    """
    通用 API Key 解析：优先使用 primary_key，依次回退 fallback_keys，最后回退环境变量

    Args:
        primary_key: 首选 API Key
        fallback_keys: 回退 API Key 列表（按优先级排序）
        env_api_key: 环境变量中的 API Key
        is_local_model: 是否为本地模型

    Returns:
        解析后的 API Key 字符串
    """
    # 优先使用首选 Key
    if primary_key is not None:
        if is_local_model:
            return primary_key if primary_key else ""
        return primary_key

    # 依次尝试回退 Key
    for fallback_key in fallback_keys:
        if fallback_key is not None:
            if is_local_model:
                return fallback_key if fallback_key else ""
            if fallback_key and fallback_key != "ollama-local":
                return fallback_key

    # 最终回退到环境变量
    if is_local_model:
        return ""
    return env_api_key or ""


# ==========================================
# Celery Worker 专用（自建 Session）
# ==========================================

def get_thinking_llm_config_standalone(user_id: Optional[int] = None) -> LLMConfig:
    """
    Celery Worker 专用：自建数据库会话获取思考模型配置

    在 FastAPI 依赖注入不可用的后台任务中使用。
    """
    from sqlmodel import Session as SQLModelSession
    from app.core.database import engine

    with SQLModelSession(engine) as session:
        return get_thinking_llm_config(session, user_id=user_id)


def get_fast_llm_config_standalone(user_id: Optional[int] = None) -> LLMConfig:
    """
    Celery Worker 专用：自建数据库会话获取极速模型配置

    在 FastAPI 依赖注入不可用的后台任务中使用。
    """
    from sqlmodel import Session as SQLModelSession
    from app.core.database import engine

    with SQLModelSession(engine) as session:
        return get_fast_llm_config(session, user_id=user_id)


# ==========================================
# 辅助函数
# ==========================================

def _is_local_model(base_url: Optional[str]) -> bool:
    """检测是否为本地模型（Ollama / localhost / host.docker.internal）

    用于判断是否需要 API Key：本地部署的模型通常不需要或使用空 Key。
    注意：这不等于"是否使用 Ollama 原生客户端"，后者由 _is_ollama() 判断。
    """
    if not base_url:
        return False
    return (
        "host.docker.internal" in base_url
        or "ollama" in base_url
        or "localhost" in base_url
    )


def _is_ollama(base_url: Optional[str]) -> bool:
    """检测是否为 Ollama 原生服务（需要使用 ollama SDK 原生客户端）

    判断依据：
    - URL 中包含 "ollama" 关键字（如 http://ollama.example.com）
    - 端口为 Ollama 默认端口 11434
    - 不包含 /v1 后缀的 localhost/host.docker.internal（Ollama 不使用 /v1 路径）

    排除：
    - host.docker.internal:8008/v1 → 这是 OpenAI 兼容 API（vLLM/LiteLLM 等），不是 Ollama
    - localhost:8080/v1 → 同上
    """
    if not base_url:
        return False
    # URL 中明确包含 "ollama" 关键字
    if "ollama" in base_url.lower():
        return True
    # 解析端口判断是否为 Ollama 默认端口 11434
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        port = parsed.port
        if port == 11434:
            return True
        # 无显式端口的 localhost/host.docker.internal 默认也非 Ollama
        # （Ollama 默认 11434，不写端口时 urlparse 返回 None）
    except Exception:
        pass
    return False


def mask_api_key(api_key: Optional[str]) -> Optional[str]:
    """脱敏 API Key：使用 sk-*** 前缀 + 后 4 位，便于前端识别脱敏值"""
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "sk-***"
    return "sk-***" + api_key[-4:]
