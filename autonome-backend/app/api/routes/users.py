"""
用户中心 API 路由

设计日期: 2026-03-22

## API 端点列表
- GET    /api/users/me              - 获取当前用户完整资料
- PUT    /api/users/me              - 更新用户资料
- POST   /api/users/me/password     - 修改密码
- GET    /api/users/me/llm-config   - 获取用户 AI 模型配置
- PUT    /api/users/me/llm-config   - 更新用户 AI 模型配置
- POST   /api/users/me/llm-config/test - 测试 AI 模型连接
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import hashlib

from app.core.database import get_session
from app.core.security import verify_password, get_password_hash
from app.models.domain import User, SystemConfig
from app.api.deps import get_current_user

router = APIRouter()


# ==========================================
# 请求/响应模型
# ==========================================

class UserProfileResponse(BaseModel):
    """用户资料响应"""
    id: int
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    organization: Optional[str]
    phone_number: Optional[str]
    bio: Optional[str]
    is_superuser: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 计算字段
    role: str  # "admin" | "user"
    gravatar_url: str  # Gravatar 备用头像


class UserProfileUpdate(BaseModel):
    """用户资料更新请求"""
    full_name: Optional[str] = None
    organization: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    """密码修改请求"""
    current_password: str
    new_password: str  # 前端需验证密码强度


# ==========================================
# API 端点实现
# ==========================================

@router.get("/me", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户完整资料

    包含：
    - 基础信息
    - 计算字段（role, gravatar_url）
    """
    # 生成 Gravatar URL（邮箱哈希）
    email_hash = hashlib.md5(current_user.email.lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon&s=200"

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        organization=current_user.organization,
        phone_number=current_user.phone_number,
        bio=current_user.bio,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        role="admin" if current_user.is_superuser else "user",
        gravatar_url=gravatar_url
    )


@router.put("/me")
async def update_user_profile(
    profile: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    更新用户资料

    可更新字段：
    - full_name: 昵称/全名
    - organization: 组织/机构
    - phone: 手机号
    - bio: 个人简介

    注意：邮箱修改需要单独的验证流程（MVP 阶段暂不支持）
    """
    from app.core.logger import log

    # 更新字段（仅更新非 None 的字段）
    update_data = profile.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.now(timezone.utc)

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    log.info(f"用户 {current_user.id} 更新资料成功: {list(update_data.keys())}")

    return {"status": "success", "message": "资料更新成功"}



# ==========================================
# 🤖 用户级 AI 模型配置
# ==========================================

class UserLLMConfigResponse(BaseModel):
    """用户 LLM 配置响应（API Key 脱敏）"""
    # 思考模型配置
    thinking_api_key: Optional[str] = None
    thinking_base_url: Optional[str] = None
    thinking_model_name: Optional[str] = None
    is_using_user_thinking_config: bool
    # 系统回退信息（供前端展示）
    system_thinking_base_url: Optional[str] = None
    system_thinking_model_name: Optional[str] = None

    # 极速模型配置
    fast_api_key: Optional[str] = None
    fast_base_url: Optional[str] = None
    fast_model_name: Optional[str] = None
    is_using_user_fast_config: bool
    # 系统极速模型回退信息
    system_fast_base_url: Optional[str] = None
    system_fast_model_name: Optional[str] = None

    # ✨ 嵌入模型配置（用于语义检索、经验向量化）
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_model_name: Optional[str] = None
    is_using_user_embedding_config: bool
    # 系统嵌入模型回退信息
    system_embedding_base_url: Optional[str] = None
    system_embedding_model_name: Optional[str] = None


class UserLLMConfigUpdate(BaseModel):
    """用户 LLM 配置更新请求"""
    # 思考模型配置
    thinking_api_key: Optional[str] = None
    thinking_base_url: Optional[str] = None
    thinking_model_name: Optional[str] = None

    # 极速模型配置
    fast_api_key: Optional[str] = None
    fast_base_url: Optional[str] = None
    fast_model_name: Optional[str] = None

    # ✨ 嵌入模型配置
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_model_name: Optional[str] = None


@router.get("/me/llm-config", response_model=UserLLMConfigResponse)
async def get_user_llm_config(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    获取当前用户 LLM 配置

    返回用户配置（API Key 脱敏）+ 系统回退信息，
    前端据此判断当前使用的是个人配置还是系统全局配置。
    """
    from app.utils.llm_config import mask_api_key, is_masked_api_key

    config = session.get(SystemConfig, 1)

    is_using_user_thinking_config = (
        current_user.thinking_api_key is not None
        or current_user.thinking_base_url is not None
        or current_user.thinking_model_name is not None
    )

    is_using_user_fast_config = (
        current_user.fast_api_key is not None
        or current_user.fast_base_url is not None
        or current_user.fast_model_name is not None
    )

    is_using_user_embedding_config = (
        current_user.embedding_api_key is not None
        or current_user.embedding_base_url is not None
        or current_user.embedding_model_name is not None
    )

    return UserLLMConfigResponse(
        # 思考模型配置
        thinking_api_key=mask_api_key(current_user.thinking_api_key),
        thinking_base_url=current_user.thinking_base_url,
        thinking_model_name=current_user.thinking_model_name,
        is_using_user_thinking_config=is_using_user_thinking_config,
        system_thinking_base_url=config.thinking_base_url if config else None,
        system_thinking_model_name=config.thinking_model if config else None,
        # 极速模型配置
        fast_api_key=mask_api_key(current_user.fast_api_key),
        fast_base_url=current_user.fast_base_url,
        fast_model_name=current_user.fast_model_name,
        is_using_user_fast_config=is_using_user_fast_config,
        system_fast_base_url=config.fast_base_url if config else None,
        system_fast_model_name=config.fast_model if config else None,
        # ✨ 嵌入模型配置
        embedding_api_key=mask_api_key(current_user.embedding_api_key),
        embedding_base_url=current_user.embedding_base_url,
        embedding_model_name=current_user.embedding_model_name,
        is_using_user_embedding_config=is_using_user_embedding_config,
        system_embedding_base_url=config.embedding_api_base if config else None,
        system_embedding_model_name=config.embedding_model if config else None,
    )


@router.put("/me/llm-config")
async def update_user_llm_config(
    config_update: UserLLMConfigUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    更新用户 LLM 配置

    - 发送实际值：更新对应字段
    - 发送 null：清除字段（回退到系统配置）
    - 发送脱敏值 sk-***：跳过该字段（前端未修改）
    """
    from app.core.logger import log
    from app.utils.llm_config import is_masked_api_key

    update_data = config_update.model_dump(exclude_unset=True)

    # 脱敏值跳过：前端未修改 API Key 时会发回脱敏值
    if "thinking_api_key" in update_data:
        val = update_data["thinking_api_key"]
        if is_masked_api_key(val):
            del update_data["thinking_api_key"]

    if "fast_api_key" in update_data:
        val = update_data["fast_api_key"]
        if is_masked_api_key(val):
            del update_data["fast_api_key"]

    if "embedding_api_key" in update_data:
        val = update_data["embedding_api_key"]
        if is_masked_api_key(val):
            del update_data["embedding_api_key"]

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.now(timezone.utc)

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    log.info(f"🤖 用户 {current_user.id} 更新 LLM 配置: {list(update_data.keys())}")

    return {"status": "success", "message": "AI 模型配置已更新"}


@router.post("/me/llm-config/test")
async def test_user_llm_config(
    config_update: UserLLMConfigUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    测试 LLM 连接（不保存）

    使用提供的配置值（合并现有用户配置和系统回退），
    发送一个简单的 OpenAI API 请求验证连通性。
    """
    import time
    import openai

    # 合并配置：测试值 → 现有用户值 → 系统回退
    from app.utils.llm_config import get_thinking_llm_config, get_fast_llm_config, _is_local_model

    # 判断测试的是极速模型还是思考模型
    # 前端发送 fast 字段时，测试极速模型；否则测试思考模型
    is_fast_test = (
        config_update.fast_api_key is not None
        or config_update.fast_base_url is not None
        or config_update.fast_model_name is not None
    )

    if is_fast_test:
        # 测试极速模型
        test_api_key = config_update.fast_api_key
        test_base_url = config_update.fast_base_url
        test_model_name = config_update.fast_model_name

        # 如果测试值中某些字段为 None，回退到用户现有配置
        if test_api_key is None and current_user.fast_api_key is not None:
            test_api_key = current_user.fast_api_key
        if test_base_url is None and current_user.fast_base_url is not None:
            test_base_url = current_user.fast_base_url
        if test_model_name is None and current_user.fast_model_name is not None:
            test_model_name = current_user.fast_model_name

        # 如果仍为 None，回退到极速模型系统配置，再回退到思考模型
        if test_api_key is None or test_base_url is None or test_model_name is None:
            fast_cfg = get_fast_llm_config(session, user_id=None)
            test_api_key = test_api_key or fast_cfg.api_key
            test_base_url = test_base_url or fast_cfg.base_url
            test_model_name = test_model_name or fast_cfg.model_name
    else:
        # 测试思考模型（原有逻辑）
        test_api_key = config_update.thinking_api_key
        test_base_url = config_update.thinking_base_url
        test_model_name = config_update.thinking_model_name

        # 如果测试值中某些字段为 None，回退到用户现有配置
        if test_api_key is None and current_user.thinking_api_key is not None:
            test_api_key = current_user.thinking_api_key
        if test_base_url is None and current_user.thinking_base_url is not None:
            test_base_url = current_user.thinking_base_url
        if test_model_name is None and current_user.thinking_model_name is not None:
            test_model_name = current_user.thinking_model_name

        # 如果仍为 None，回退到系统配置
        if test_api_key is None or test_base_url is None or test_model_name is None:
            sys_cfg = get_thinking_llm_config(session, user_id=None)
            test_api_key = test_api_key or sys_cfg.api_key
            test_base_url = test_base_url or sys_cfg.base_url
            test_model_name = test_model_name or sys_cfg.model_name

    is_local = _is_local_model(test_base_url)

    try:
        start_time = time.time()

        client = openai.OpenAI(
            api_key=test_api_key or ("not-needed" if is_local else ""),
            base_url=test_base_url,
        )

        # 🤖 真正验证模型可用性：发送最小 completion 请求
        # 仅 models.list() 无法验证模型名称是否真实存在
        response = client.chat.completions.create(
            model=test_model_name,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            stream=False,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # 验证响应中包含有效内容
        model_used = response.model if response else test_model_name

        return {
            "status": "success",
            "message": f"连接成功（{latency_ms}ms），模型: {model_used}",
            "latency_ms": latency_ms,
            "model_name": test_model_name,
            "base_url": test_base_url,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"连接失败: {str(e)[:200]}",
            "latency_ms": None,
            "model_name": test_model_name,
            "base_url": test_base_url,
        }