"""
技能锻造会话 API - 提供对话式技能锻造功能

核心端点:
- POST /session: 创建锻造会话
- GET /session/{id}: 获取会话详情
- POST /session/{id}/chat: 对话锻造 (SSE流式)
- PUT /session/{id}/draft: 手动更新草稿
- POST /session/{id}/commit: 确认保存技能
"""

import os
import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, get_utc_now
from app.models.forge_session import (
    ForgeSession, ForgeSessionCreate, ForgeSessionUpdate, ForgeSessionPublic,
    ForgeMessage, ForgeMessagePublic,
    ForgeStatus, ForgeChatRequest, SkillDraftUpdate
)
from app.agent.forge_agent import build_forge_agent
from app.core.config import settings
from app.services.code_reviewer import review_skill_code, CodeReviewResult


router = APIRouter()


# ==========================================
# 辅助函数
# ==========================================
def get_api_config(session: Session) -> tuple:
    """获取 API 配置"""
    from app.models.domain import SystemConfig
    config = session.get(SystemConfig, 1)
    if not config:
        raise HTTPException(status_code=500, detail="系统配置未初始化")

    api_key = config.openai_api_key or settings.OPENAI_API_KEY
    base_url = config.openai_base_url or settings.OPENAI_BASE_URL
    model_name = config.default_model or settings.DEFAULT_MODEL

    return api_key, base_url, model_name


def session_to_public(session: ForgeSession, messages: List[ForgeMessage] = None) -> dict:
    """将会话转换为公开格式"""
    return {
        "id": session.id,
        "user_id": session.user_id,
        "title": session.title,
        "status": session.status,
        "skill_draft": session.skill_draft,
        "skill_id": session.skill_id,
        "executor_type": session.executor_type,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "messages": [
            {
                "id": msg.id,
                "session_id": msg.session_id,
                "role": msg.role,
                "content": msg.content,
                "attachments": msg.attachments,
                "created_at": msg.created_at.isoformat()
            }
            for msg in (messages or [])
        ]
    }


# ==========================================
# POST /session - 创建锻造会话
# ==========================================
@router.post("/session")
async def create_forge_session(
    request: ForgeSessionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    创建新的锻造会话

    Returns:
        {"session_id": str, "title": str}
    """
    forge_session = ForgeSession(
        user_id=current_user.id,
        title=request.title or "新技能锻造",
        executor_type=request.executor_type,
        skill_draft={
            "name": "",
            "description": "",
            "executor_type": request.executor_type,
            "script_code": "",
            "parameters_schema": {},
            "expert_knowledge": "",
            "dependencies": []
        }
    )

    session.add(forge_session)
    session.commit()
    session.refresh(forge_session)

    log.info(f"✅ [Forge] 创建新会话: {forge_session.id}, 用户: {current_user.id}")

    return {
        "session_id": forge_session.id,
        "title": forge_session.title
    }


# ==========================================
# GET /sessions - 获取用户的锻造会话列表
# ==========================================
@router.get("/sessions")
async def list_forge_sessions(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的锻造会话列表
    """
    statement = select(ForgeSession).where(
        ForgeSession.user_id == current_user.id
    ).order_by(ForgeSession.updated_at.desc()).offset(offset).limit(limit)

    sessions = session.exec(statement).all()

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "executor_type": s.executor_type,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "has_draft": bool(s.skill_draft.get("script_code"))
            }
            for s in sessions
        ]
    }


# ==========================================
# GET /session/{session_id} - 获取会话详情
# ==========================================
@router.get("/session/{session_id}")
async def get_forge_session(
    session_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    获取锻造会话详情（包含消息历史）
    """
    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    # 获取消息
    messages = db.exec(
        select(ForgeMessage).where(
            ForgeMessage.session_id == session_id
        ).order_by(ForgeMessage.created_at)
    ).all()

    return session_to_public(forge_session, messages)


# ==========================================
# DELETE /session/{session_id} - 删除会话
# ==========================================
@router.delete("/session/{session_id}")
async def delete_forge_session(
    session_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    删除锻造会话
    """
    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除此会话")

    db.delete(forge_session)
    db.commit()

    return {"status": "success", "message": "会话已删除"}


# ==========================================
# POST /session/{session_id}/chat - 对话锻造 (SSE)
# ==========================================
@router.post("/session/{session_id}/chat")
async def forge_chat_stream(
    session_id: str,
    request: ForgeChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    对话式锻造 - SSE流式响应

    核心逻辑：
    1. 保存用户消息
    2. 加载历史上下文
    3. 调用锻造Agent
    4. 流式返回文本 + 技能更新事件
    5. 保存AI消息
    """

    # 验证会话
    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    # 获取API配置
    api_key, base_url, model_name = get_api_config(db)

    async def event_generator():
        try:
            # 1. 保存用户消息
            user_msg = ForgeMessage(
                session_id=session_id,
                role="user",
                content=request.message,
                attachments=request.attachments
            )
            db.add(user_msg)
            db.commit()
            db.refresh(user_msg)

            log.info(f"💬 [Forge] 用户消息已保存: {user_msg.id}")

            # 2. 加载历史消息
            history_msgs = db.exec(
                select(ForgeMessage).where(
                    ForgeMessage.session_id == session_id
                ).order_by(ForgeMessage.created_at)
            ).all()

            # 排除刚保存的用户消息
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in history_msgs[:-1]  # 排除最后一条（刚保存的）
            ]

            # 3. 构建锻造Agent
            agent = build_forge_agent(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                executor_type=forge_session.executor_type,
                skill_draft=forge_session.skill_draft
            )

            # 4. 流式处理
            ai_response = ""
            skill_update_data = None

            async for event in agent.chat_stream(
                message=request.message,
                history=history,
                attachments=request.attachments
            ):
                if event["type"] == "text":
                    ai_response += event["content"]
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "text",
                            "content": event["content"]
                        }, ensure_ascii=False)
                    }

                elif event["type"] == "skill_update":
                    skill_update_data = event["data"]
                    log.info(f"📤 [Forge] 发送 skill_update 事件: {json.dumps(event['data'], ensure_ascii=False)[:500]}")
                    yield {
                        "event": "skill_update",
                        "data": json.dumps({
                            "type": "draft",
                            "data": event["data"]
                        }, ensure_ascii=False)
                    }

                elif event["type"] == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "type": "error",
                            "content": event["content"]
                        }, ensure_ascii=False)
                    }

            # 5. 保存AI消息
            ai_msg = ForgeMessage(
                session_id=session_id,
                role="assistant",
                content=ai_response
            )
            db.add(ai_msg)

            # 6. 更新会话草稿（如果有技能更新）
            if skill_update_data:
                forge_session.skill_draft.update(skill_update_data)
                forge_session.updated_at = get_utc_now()

            forge_session.updated_at = get_utc_now()
            db.add(forge_session)
            db.commit()

            log.info(f"💬 [Forge] AI 消息已保存, 会话已更新")

            # 7. 发送完成事件
            yield {
                "event": "done",
                "data": json.dumps({"type": "done"}, ensure_ascii=False)
            }

        except Exception as e:
            log.error(f"🔥 [Forge] 对话处理失败: {e}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "type": "error",
                    "content": str(e)
                }, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())


# ==========================================
# PUT /session/{session_id}/draft - 手动更新草稿
# ==========================================
@router.put("/session/{session_id}/draft")
async def update_skill_draft(
    session_id: str,
    draft_update: SkillDraftUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    手动更新技能草稿
    """
    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    # 更新草稿
    update_data = draft_update.model_dump(exclude_unset=True)
    log.info(f"[Forge Draft Update] 会话 {session_id} 更新字段: {list(update_data.keys())}")
    if 'script_code' in update_data:
        log.info(f"[Forge Draft Update] script_code 长度: {len(update_data.get('script_code', '') or '')}")

    # 创建新的字典对象以确保 SQLAlchemy 检测到变更
    new_draft = dict(forge_session.skill_draft)
    new_draft.update(update_data)
    forge_session.skill_draft = new_draft

    # ==========================================
    # 关键修复：同步更新会话表的 executor_type 字段
    # 如果草稿中包含 executor_type，需要同步到会话表的独立字段
    # 这样加载会话时前端才能正确获取执行器类型
    # ==========================================
    if 'executor_type' in update_data:
        forge_session.executor_type = update_data['executor_type']
        log.info(f"[Forge Draft Update] 同步更新会话 executor_type: {update_data['executor_type']}")

    forge_session.updated_at = get_utc_now()

    db.add(forge_session)
    db.commit()
    db.refresh(forge_session)

    return {
        "status": "success",
        "skill_draft": forge_session.skill_draft
    }


# ==========================================
# POST /session/{session_id}/commit - 确认保存技能
# ==========================================
@router.post("/session/{session_id}/commit")
async def commit_skill(
    session_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    确认并保存技能到技能库

    幂等性保证：
    - 如果会话已有 skill_id，则更新现有的 SkillAsset 记录
    - 如果没有 skill_id，则创建新的 SkillAsset 记录
    """
    from app.models.domain import SkillAsset, SkillStatus, generate_skill_id

    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    draft = forge_session.skill_draft
    log.info(f"[Forge Commit] 会话 {session_id} 草稿内容: name={draft.get('name')}, executor_type={draft.get('executor_type')}, script_code_len={len(draft.get('script_code', '') or '')}, nextflow_code_len={len(draft.get('nextflow_code', '') or '')}")

    # 检查是否有有效代码（根据执行器类型检查不同字段）
    executor_type = draft.get("executor_type", "Python_env")
    has_code = False
    if executor_type == "Logical_Blueprint":
        has_code = bool(draft.get("nextflow_code"))
    else:
        has_code = bool(draft.get("script_code"))

    if not has_code:
        log.warning(f"[Forge Commit] 代码检查失败: executor_type={executor_type}, has_code={has_code}")
        raise HTTPException(status_code=400, detail="技能草稿中没有可执行代码")

    # ==========================================
    # 幂等性检查：如果已有 skill_id，更新现有记录而非创建新记录
    # ==========================================
    skill = None
    if forge_session.skill_id:
        # 查找现有的 SkillAsset 记录
        existing_skill = db.exec(
            select(SkillAsset).where(SkillAsset.skill_id == forge_session.skill_id)
        ).first()

        if existing_skill:
            log.info(f"📝 [Forge] 更新现有技能: {forge_session.skill_id}")
            # 更新现有记录
            existing_skill.name = draft.get("name") or existing_skill.name
            existing_skill.description = draft.get("description") or existing_skill.description
            existing_skill.executor_type = draft.get("executor_type") or existing_skill.executor_type
            existing_skill.parameters_schema = draft.get("parameters_schema") or existing_skill.parameters_schema
            existing_skill.script_code = draft.get("script_code")
            existing_skill.expert_knowledge = draft.get("expert_knowledge") or ""
            existing_skill.dependencies = draft.get("dependencies") or []
            existing_skill.updated_at = get_utc_now()
            skill = existing_skill
        else:
            # skill_id 存在但记录不存在（可能是被删除了），创建新记录
            log.warning(f"⚠️ [Forge] skill_id {forge_session.skill_id} 不存在，创建新记录")
            skill = SkillAsset(
                skill_id=forge_session.skill_id,
                name=draft.get("name") or "未命名技能",
                description=draft.get("description") or "",
                executor_type=draft.get("executor_type") or "Python_env",
                parameters_schema=draft.get("parameters_schema") or {},
                script_code=draft.get("script_code"),
                expert_knowledge=draft.get("expert_knowledge") or "",
                dependencies=draft.get("dependencies") or [],
                status=SkillStatus.DRAFT,
                owner_id=current_user.id
            )
            db.add(skill)
    else:
        # 创建新的技能记录
        new_skill_id = generate_skill_id()
        log.info(f"✨ [Forge] 创建新技能: {new_skill_id}")
        skill = SkillAsset(
            skill_id=new_skill_id,
            name=draft.get("name") or "未命名技能",
            description=draft.get("description") or "",
            executor_type=draft.get("executor_type") or "Python_env",
            parameters_schema=draft.get("parameters_schema") or {},
            script_code=draft.get("script_code"),
            expert_knowledge=draft.get("expert_knowledge") or "",
            dependencies=draft.get("dependencies") or [],
            status=SkillStatus.DRAFT,
            owner_id=current_user.id
        )
        db.add(skill)
        # 更新会话的 skill_id
        forge_session.skill_id = skill.skill_id

    # 更新会话状态
    forge_session.status = ForgeStatus.SAVED
    forge_session.updated_at = get_utc_now()

    db.commit()
    db.refresh(skill)

    log.info(f"✅ [Forge] 技能已保存: {skill.skill_id}, 会话: {session_id}")

    # ==========================================
    # 自动代码审查（后台执行，不阻塞保存）
    # ==========================================
    code_review_result = None
    try:
        # 获取要审查的代码
        code_to_review = draft.get("script_code") if executor_type != "Logical_Blueprint" else draft.get("nextflow_code")
        if code_to_review:
            language = "r" if executor_type == "R_env" else "python"
            review_result = review_skill_code(code_to_review, language)
            code_review_result = {
                "passed": review_result.passed,
                "score": review_result.score,
                "summary": review_result.summary,
                "issues_count": len(review_result.issues),
                "critical_count": sum(1 for i in review_result.issues if i.severity.value == "critical"),
                "suggestions": review_result.suggestions[:3]  # 只返回前3条建议
            }
            log.info(f"📊 [Forge] 代码审查完成: 分数={review_result.score}, 问题={len(review_result.issues)}")
    except Exception as e:
        log.warning(f"⚠️ [Forge] 代码审查失败（不影响保存）: {e}")

    return {
        "status": "success",
        "skill_id": skill.skill_id,
        "name": skill.name,
        "code_review": code_review_result
    }


# ==========================================
# POST /session/{session_id}/submit - 提交审核
# ==========================================
@router.post("/session/{session_id}/submit")
async def submit_forge_skill(
    session_id: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    保存技能并提交审核

    幂等性保证：
    - 如果会话已有 skill_id，则更新现有的 SkillAsset 记录
    - 如果没有 skill_id，则创建新的 SkillAsset 记录
    """
    from app.models.domain import SkillAsset, SkillStatus, generate_skill_id

    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    draft = forge_session.skill_draft
    log.info(f"[Forge Commit] 会话 {session_id} 草稿内容: name={draft.get('name')}, executor_type={draft.get('executor_type')}, script_code_len={len(draft.get('script_code', '') or '')}, nextflow_code_len={len(draft.get('nextflow_code', '') or '')}")

    # 检查是否有有效代码（根据执行器类型检查不同字段）
    executor_type = draft.get("executor_type", "Python_env")
    has_code = False
    if executor_type == "Logical_Blueprint":
        has_code = bool(draft.get("nextflow_code"))
    else:
        has_code = bool(draft.get("script_code"))

    if not has_code:
        log.warning(f"[Forge Commit] 代码检查失败: executor_type={executor_type}, has_code={has_code}")
        raise HTTPException(status_code=400, detail="技能草稿中没有可执行代码")

    # ==========================================
    # 提交审核前进行代码审查（强制检查）
    # 如果发现严重安全问题（hardcoded secrets, SQL injection等），阻止提交
    # ==========================================
    code_to_review = draft.get("script_code") if executor_type != "Logical_Blueprint" else draft.get("nextflow_code")
    if code_to_review and executor_type != "Logical_Blueprint":
        try:
            language = "r" if executor_type == "R_env" else "python"
            review_result = review_skill_code(code_to_review, language)

            # 检查是否有严重安全问题
            critical_issues = [i for i in review_result.issues if i.severity.value == "critical"]

            if critical_issues:
                # 发现严重安全问题，阻止提交
                error_messages = [f"行 {i.line}: {i.message}" for i in critical_issues[:3]]
                log.warning(f"🚨 [Forge] 代码审查发现严重安全问题，阻止提交: {error_messages}")

                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "代码存在严重安全问题，请修复后再提交审核",
                        "issues": error_messages,
                        "score": review_result.score,
                        "suggestions": review_result.suggestions[:3]
                    }
                )

            log.info(f"✅ [Forge] 代码审查通过: 分数={review_result.score}, 问题={len(review_result.issues)}")

        except HTTPException:
            # 重新抛出 HTTPException（阻止提交）
            raise
        except Exception as e:
            # 其他错误不阻止提交，但记录警告
            log.warning(f"⚠️ [Forge] 代码审查失败（允许提交）: {e}")

    # ==========================================
    # 幂等性检查：如果已有 skill_id，更新现有记录而非创建新记录
    # ==========================================
    skill = None
    if forge_session.skill_id:
        # 查找现有的 SkillAsset 记录
        existing_skill = db.exec(
            select(SkillAsset).where(SkillAsset.skill_id == forge_session.skill_id)
        ).first()

        if existing_skill:
            log.info(f"📝 [Forge] 更新现有技能并提交审核: {forge_session.skill_id}")
            # 更新现有记录
            existing_skill.name = draft.get("name") or existing_skill.name
            existing_skill.description = draft.get("description") or existing_skill.description
            existing_skill.executor_type = draft.get("executor_type") or existing_skill.executor_type
            existing_skill.parameters_schema = draft.get("parameters_schema") or existing_skill.parameters_schema
            existing_skill.script_code = draft.get("script_code")
            existing_skill.expert_knowledge = draft.get("expert_knowledge") or ""
            existing_skill.dependencies = draft.get("dependencies") or []
            existing_skill.status = SkillStatus.PENDING_REVIEW  # 更新为待审核状态
            existing_skill.updated_at = get_utc_now()
            skill = existing_skill
        else:
            # skill_id 存在但记录不存在（可能是被删除了），创建新记录
            log.warning(f"⚠️ [Forge] skill_id {forge_session.skill_id} 不存在，创建新记录")
            skill = SkillAsset(
                skill_id=forge_session.skill_id,
                name=draft.get("name") or "未命名技能",
                description=draft.get("description") or "",
                executor_type=draft.get("executor_type") or "Python_env",
                parameters_schema=draft.get("parameters_schema") or {},
                script_code=draft.get("script_code"),
                expert_knowledge=draft.get("expert_knowledge") or "",
                dependencies=draft.get("dependencies") or [],
                status=SkillStatus.PENDING_REVIEW,
                owner_id=current_user.id
            )
            db.add(skill)
    else:
        # 创建新的技能记录
        new_skill_id = generate_skill_id()
        log.info(f"✨ [Forge] 创建新技能并提交审核: {new_skill_id}")
        skill = SkillAsset(
            skill_id=new_skill_id,
            name=draft.get("name") or "未命名技能",
            description=draft.get("description") or "",
            executor_type=draft.get("executor_type") or "Python_env",
            parameters_schema=draft.get("parameters_schema") or {},
            script_code=draft.get("script_code"),
            expert_knowledge=draft.get("expert_knowledge") or "",
            dependencies=draft.get("dependencies") or [],
            status=SkillStatus.PENDING_REVIEW,
            owner_id=current_user.id
        )
        db.add(skill)
        # 更新会话的 skill_id
        forge_session.skill_id = skill.skill_id

    # 更新会话状态
    forge_session.status = ForgeStatus.SAVED
    forge_session.updated_at = get_utc_now()

    db.commit()
    db.refresh(skill)

    log.info(f"✅ [Forge] 技能已提交审核: {skill.skill_id}")

    return {
        "status": "success",
        "skill_id": skill.skill_id,
        "name": skill.name,
        "skill_status": "PENDING_REVIEW"
    }


# ==========================================
# POST /infer_parameters - AI 参数推断
# ==========================================
class InferParametersRequest(BaseModel):
    """参数推断请求"""
    code: str
    executor_type: str = "Python_env"
    force_llm: bool = False  # 强制使用 LLM（跳过快速提取）


def _extract_python_argparse_params(code: str) -> Optional[Dict]:
    """
    快速提取 Python argparse 参数（基于规则，无需 LLM）

    解析 argparse.add_argument 调用，提取参数名、类型、默认值、帮助信息

    Returns:
        JSON Schema 格式的参数定义，如果未找到 argparse 则返回 None
    """
    import re

    # 检查是否使用 argparse
    if 'argparse' not in code and 'ArgumentParser' not in code:
        return None

    properties = {}
    required = []

    # 匹配 add_argument 调用
    # 模式1: parser.add_argument('--name', type=str, default='value', help='desc')
    # 模式2: parser.add_argument('-n', '--name', type=int, default=10)
    pattern = r'''add_argument\s*\(\s*
        (?:['"](-\w)['"],\s*)?  # 短参数名（可选）
        ['"]--(\w+)['"]\s*       # 长参数名
        (?:,\s*type\s*=\s*(\w+))?  # 类型
        (?:,\s*default\s*=\s*([^,\)]+))?  # 默认值
        (?:,\s*help\s*=\s*['"]([^'"]*)['"])?  # 帮助信息
    '''

    # 更宽松的正则
    arg_pattern = r"add_argument\s*\([^)]+\)"

    matches = re.findall(arg_pattern, code, re.VERBOSE | re.IGNORECASE)

    if not matches:
        return None

    for match in matches:
        try:
            arg_str = match

            # 提取参数名 (--xxx 或 -xxx)
            name_match = re.search(r"['\"]--(\w+)['\"]", arg_str)
            if not name_match:
                name_match = re.search(r"['\"]-(\w+)['\"]", arg_str)
            if not name_match:
                continue

            param_name = name_match.group(1)

            # 提取类型
            type_match = re.search(r"type\s*=\s*(\w+)", arg_str)
            param_type = "string"
            json_type = "string"
            if type_match:
                type_val = type_match.group(1).lower()
                if type_val in ['int']:
                    json_type = "integer"
                    param_type = "int"
                elif type_val in ['float', 'double']:
                    json_type = "number"
                    param_type = "float"
                elif type_val in ['bool', 'boolean']:
                    json_type = "boolean"
                    param_type = "bool"

            # 提取默认值
            default_val = ""
            default_match = re.search(r"default\s*=\s*([^,\)]+)", arg_str)
            if default_match:
                default_raw = default_match.group(1).strip()
                # 处理不同类型的默认值
                if default_raw in ['None', 'none', 'null']:
                    default_val = ""
                elif default_raw.startswith(("'", '"')):
                    default_val = default_raw.strip("'\"")
                elif default_raw.lower() in ['true', 'false']:
                    default_val = default_raw.lower() == 'true'
                else:
                    try:
                        default_val = float(default_raw) if '.' in default_raw else int(default_raw)
                    except:
                        default_val = default_raw

            # 提取帮助信息
            help_match = re.search(r"help\s*=\s*['\"]([^'\"]*)['\"]", arg_str)
            description = help_match.group(1) if help_match else f"参数: {param_name}"

            # 检查是否必填 (没有 default 的位置参数)
            if 'default' not in arg_str and not re.search(r"['\"]--", arg_str):
                required.append(param_name)

            # 检测是否为文件路径参数
            format_type = None
            if any(kw in param_name.lower() or kw in description.lower() for kw in ['file', 'input', 'output', 'path', '文件']):
                format_type = "filepath"
            elif any(kw in param_name.lower() or kw in description.lower() for kw in ['dir', 'directory', 'folder', '目录']):
                format_type = "directorypath"

            prop_def = {
                "type": json_type,
                "description": description,
                "default": default_val
            }
            if format_type:
                prop_def["format"] = format_type

            properties[param_name] = prop_def

        except Exception as e:
            log.warning(f"[快速提取] 解析参数失败: {e}")
            continue

    if not properties:
        return None

    log.info(f"⚡ [快速提取] 成功提取 {len(properties)} 个 Python argparse 参数")

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


def _extract_r_optparse_params(code: str) -> Optional[Dict]:
    """
    快速提取 R optparse 参数（基于规则，无需 LLM）

    Returns:
        JSON Schema 格式的参数定义，如果未找到 optparse 则返回 None
    """
    import re

    # 检查是否使用 optparse
    if 'optparse' not in code.lower() and 'make_option' not in code.lower():
        return None

    properties = {}
    required = []

    # 匹配 make_option 调用
    # make_option(c("--input", "-i"), type="character", default=NULL, help="Input file")
    pattern = r"make_option\s*\(\s*c?\s*\(\s*['\"]--?(\w+)['\"]"

    matches = re.findall(pattern, code, re.IGNORECASE)

    if not matches:
        return None

    # 更完整的提取
    arg_pattern = r"make_option\s*\([^)]+\)"
    arg_matches = re.findall(arg_pattern, code)

    for arg_str in arg_matches:
        try:
            # 提取参数名
            name_match = re.search(r"['\"]--?(\w+)['\"]", arg_str)
            if not name_match:
                continue

            param_name = name_match.group(1)

            # 提取类型
            type_match = re.search(r"type\s*=\s*['\"](\w+)['\"]", arg_str)
            json_type = "string"
            if type_match:
                type_val = type_match.group(1).lower()
                if type_val in ['integer', 'numeric']:
                    json_type = "integer" if type_val == 'integer' else "number"
                elif type_val == 'logical':
                    json_type = "boolean"

            # 提取默认值
            default_val = ""
            default_match = re.search(r"default\s*=\s*([^,\)]+)", arg_str)
            if default_match:
                default_raw = default_match.group(1).strip()
                if default_raw.upper() in ['NULL', 'NA']:
                    default_val = ""
                elif default_raw.startswith('"') or default_raw.startswith("'"):
                    default_val = default_raw.strip("\"'")
                elif default_raw.upper() in ['TRUE', 'FALSE']:
                    default_val = default_raw.upper() == 'TRUE'
                else:
                    try:
                        default_val = float(default_raw) if '.' in default_raw else int(default_raw)
                    except:
                        default_val = default_raw

            # 提取帮助信息
            help_match = re.search(r"help\s*=\s*['\"]([^'\"]*)['\"]", arg_str)
            description = help_match.group(1) if help_match else f"参数: {param_name}"

            properties[param_name] = {
                "type": json_type,
                "description": description,
                "default": default_val
            }

        except Exception as e:
            log.warning(f"[快速提取] 解析 R 参数失败: {e}")
            continue

    if not properties:
        return None

    log.info(f"⚡ [快速提取] 成功提取 {len(properties)} 个 R optparse 参数")

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


@router.post("/infer_parameters")
async def infer_parameters(
    request: InferParametersRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    从代码推断参数定义

    优化策略：
    1. 快速提取：优先使用正则规则提取 argparse/optparse 参数（毫秒级）
    2. LLM 推断：快速提取失败时才调用 LLM（秒级）

    分析 Python argparse 或 R commandArgs 代码，返回 JSON Schema

    增强的错误反馈：
    - 返回具体的错误类型（json_parse_error / llm_error / validation_error）
    - 返回原始响应内容（前500字符）
    - 返回用户友好的建议
    """
    import re
    import json

    code = request.code
    executor_type = request.executor_type
    force_llm = request.force_llm

    # 前置检查：代码是否有效
    if not code or len(code.strip()) < 10:
        return {
            "status": "error",
            "error_type": "validation_error",
            "parameters_schema": {"type": "object", "properties": {}, "required": []},
            "message": "代码内容过短或为空，无法推断参数",
            "suggestion": "请提供包含参数定义的完整代码，例如使用 argparse (Python) 或 optparse (R) 的代码"
        }

    # ==========================================
    # 策略1: 快速提取（基于规则，毫秒级）
    # ==========================================
    if not force_llm:
        quick_result = None

        if executor_type == "Python_env":
            quick_result = _extract_python_argparse_params(code)
        elif executor_type == "R_env":
            quick_result = _extract_r_optparse_params(code)

        if quick_result and quick_result.get("properties"):
            log.info(f"✅ [Forge] 快速提取成功，跳过 LLM 调用")
            return {
                "status": "success",
                "parameters_schema": quick_result,
                "extraction_method": "quick_regex"
            }

    # ==========================================
    # 策略2: LLM 智能推断（秒级）
    # ==========================================
    log.info(f"🤖 [Forge] 快速提取未成功，启动 LLM 智能推断...")

    # 使用 LLM 进行智能推断
    api_key, base_url, model_name = get_api_config(session)

    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1
    )

    prompt = f"""分析以下{'Python' if executor_type == 'Python_env' else 'R' if executor_type == 'R_env' else 'Nextflow'}代码，提取所有参数定义，返回 JSON Schema 格式。

代码:
```
{code}
```

请返回符合以下格式的 JSON Schema:
{{
  "type": "object",
  "properties": {{
    "param_name": {{
      "type": "string|number|integer|boolean",
      "description": "参数描述",
      "default": "默认值"
    }}
  }},
  "required": ["必填参数列表"]
}}

注意:
1. type 必须是 string, number, integer, boolean 之一
2. 对于文件路径参数，添加 "format": "filepath"
3. 对于目录路径参数，添加 "format": "directorypath"
4. 必须包含 description 字段
5. 只返回 JSON，不要有其他内容"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content

        # ==========================================
        # 增强的 JSON 提取逻辑 - 多策略容错
        # ==========================================
        json_str = None
        extraction_method = None

        # 策略1: 匹配 ```json ... ``` 代码块
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1).strip()
            extraction_method = "json_code_block"
            log.info(f"[Forge] 使用策略1 (json_code_block) 提取 JSON")

        # 策略2: 匹配 ``` ... ``` 代码块（无语言标记）
        if not json_str:
            code_match = re.search(r'```\s*([\s\S]*?)\s*```', content)
            if code_match:
                extracted = code_match.group(1).strip()
                # 检查是否以 { 开头（可能是 JSON）
                if extracted.startswith('{'):
                    json_str = extracted
                    extraction_method = "generic_code_block"
                    log.info(f"[Forge] 使用策略2 (generic_code_block) 提取 JSON")

        # 策略3: 查找第一个 { 到最后一个 } 之间的内容
        if not json_str:
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx + 1].strip()
                extraction_method = "bracket_extraction"
                log.info(f"[Forge] 使用策略3 (bracket_extraction) 提取 JSON")

        # 如果所有策略都失败
        if not json_str:
            log.error(f"🔥 [Forge] JSON 提取失败，LLM 返回内容不包含有效 JSON 结构")
            return {
                "status": "error",
                "error_type": "json_parse_error",
                "parameters_schema": {"type": "object", "properties": {}, "required": []},
                "message": "AI 返回的内容不包含有效的 JSON 结构",
                "raw_response": content[:500],
                "suggestion": "请检查代码是否包含清晰的参数定义（如 argparse 参数），或手动在下方参数面板中添加参数"
            }

        # 解析 JSON
        try:
            parameters_schema = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error(f"🔥 [Forge] JSON 解析失败: {e}, 提取方法: {extraction_method}")
            return {
                "status": "error",
                "error_type": "json_parse_error",
                "parameters_schema": {"type": "object", "properties": {}, "required": []},
                "message": f"JSON 解析失败: {str(e)}",
                "raw_response": content[:500],
                "extracted_json": json_str[:300] if len(json_str) > 300 else json_str,
                "suggestion": "AI 返回的 JSON 格式不正确，请手动在下方参数面板中添加参数"
            }

        # 验证 JSON Schema 结构
        if not isinstance(parameters_schema, dict):
            return {
                "status": "error",
                "error_type": "validation_error",
                "parameters_schema": {"type": "object", "properties": {}, "required": []},
                "message": "解析结果不是有效的 JSON Schema 对象",
                "raw_response": content[:500],
                "suggestion": "请检查代码格式，或手动添加参数"
            }

        # 确保 properties 字段存在
        if "properties" not in parameters_schema:
            parameters_schema["properties"] = {}
        if "type" not in parameters_schema:
            parameters_schema["type"] = "object"
        if "required" not in parameters_schema:
            parameters_schema["required"] = []

        log.info(f"✅ [Forge] 参数推断完成，发现 {len(parameters_schema.get('properties', {}))} 个参数")

        return {
            "status": "success",
            "parameters_schema": parameters_schema,
            "extraction_method": extraction_method
        }

    except json.JSONDecodeError as e:
        log.error(f"🔥 [Forge] JSON 解析失败: {e}")
        return {
            "status": "error",
            "error_type": "json_parse_error",
            "parameters_schema": {"type": "object", "properties": {}, "required": []},
            "message": f"参数推断失败：JSON 解析错误 - {str(e)}",
            "suggestion": "请检查代码是否包含 argparse 参数定义，或手动填写参数"
        }
    except Exception as e:
        log.error(f"🔥 [Forge] 参数推断失败: {e}")
        return {
            "status": "error",
            "error_type": "llm_error",
            "parameters_schema": {"type": "object", "properties": {}, "required": []},
            "message": f"LLM 调用失败: {str(e)}",
            "suggestion": "请检查网络连接和 API 配置，或手动填写参数"
        }


log.info("✅ 技能锻造会话 API 已加载")


# ==========================================
# GET /test_file - 读取测试输出文件
# ==========================================
@router.get("/test_file")
async def read_test_file(
    path: str,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    读取测试输出文件内容

    支持图片、PDF、文本等文件的读取和下载
    """
    from fastapi.responses import Response, FileResponse
    import base64
    import mimetypes

    # 安全检查：路径必须在 /workspace/skill_test_ 下
    if not path.startswith('/workspace/skill_test_'):
        raise HTTPException(status_code=403, detail="无权访问此文件")

    # 检查文件是否存在
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")

    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="路径不是文件")

    # 获取文件扩展名和 MIME 类型
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.pdf': 'application/pdf',
        '.csv': 'text/csv',
        '.tsv': 'text/tab-separated-values',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.md': 'text/markdown',
        '.html': 'text/html',
        '.xml': 'application/xml',
    }

    mime_type = mime_types.get(ext, 'application/octet-stream')

    # 读取文件内容
    try:
        # 对于图片和PDF，返回 base64 编码
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf']:
            with open(path, 'rb') as f:
                content = f.read()
            base64_content = base64.b64encode(content).decode('utf-8')

            return {
                "status": "success",
                "type": "binary",
                "mime_type": mime_type,
                "filename": os.path.basename(path),
                "size": os.path.getsize(path),
                "data": base64_content
            }
        else:
            # 对于文本文件，返回文本内容
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            return {
                "status": "success",
                "type": "text",
                "mime_type": mime_type,
                "filename": os.path.basename(path),
                "size": os.path.getsize(path),
                "data": content
            }
    except Exception as e:
        log.error(f"[Forge] 读取文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")


# ==========================================
# POST /review_code - 代码审查
# ==========================================
class CodeReviewRequest(BaseModel):
    """代码审查请求"""
    code: str
    executor_type: str = "Python_env"


@router.post("/review_code")
async def review_code(
    request: CodeReviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    代码质量和安全审查

    提供以下检查：
    1. 语法检查（Python AST）
    2. 安全漏洞扫描（硬编码密钥、SQL注入、命令注入等）
    3. 最佳实践检查（裸except、print语句等）
    4. 代码风格建议

    返回：
    - passed: 是否通过审查（分数>=60且无严重问题）
    - score: 代码质量分数（0-100）
    - issues: 问题列表
    - summary: 审查摘要
    - suggestions: 改进建议
    """
    code = request.code
    executor_type = request.executor_type

    # 前置检查：代码是否有效
    if not code or len(code.strip()) < 10:
        return {
            "status": "error",
            "message": "代码内容过短或为空，无法进行审查",
            "passed": True,
            "score": 100,
            "issues": [],
            "summary": "代码过短，跳过审查",
            "suggestions": []
        }

    # 确定语言
    language = "python"
    if executor_type == "R_env":
        language = "r"
    elif executor_type == "Logical_Blueprint":
        # Nextflow 基于 Groovy，暂不支持深度分析
        return {
            "status": "success",
            "passed": True,
            "score": 80,
            "issues": [],
            "summary": "Nextflow 工作流代码，暂不支持自动审查",
            "suggestions": ["请确保流程遵循 nf-core 规范"]
        }

    try:
        # 执行代码审查
        result: CodeReviewResult = review_skill_code(code, language)

        log.info(f"✅ [Forge] 代码审查完成: 分数={result.score}, 通过={result.passed}, 问题数={len(result.issues)}")

        return {
            "status": "success",
            "passed": result.passed,
            "score": result.score,
            "issues": [
                {
                    "line": issue.line,
                    "column": issue.column,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "rule_id": issue.rule_id,
                    "suggestion": issue.suggestion
                }
                for issue in result.issues
            ],
            "summary": result.summary,
            "suggestions": result.suggestions
        }

    except Exception as e:
        log.error(f"🔥 [Forge] 代码审查失败: {e}")
        return {
            "status": "error",
            "message": f"代码审查失败: {str(e)}",
            "passed": True,
            "score": 50,
            "issues": [],
            "summary": "代码审查服务异常，默认通过",
            "suggestions": ["请稍后重试或手动检查代码"]
        }


log.info("✅ 技能锻造会话 API 已加载")