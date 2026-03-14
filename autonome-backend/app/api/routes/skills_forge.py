"""
技能锻造会话 API - 提供对话式技能锻造功能

核心端点:
- POST /session: 创建锻造会话
- GET /session/{id}: 获取会话详情
- POST /session/{id}/chat: 对话锻造 (SSE流式)
- PUT /session/{id}/draft: 手动更新草稿
- POST /session/{id}/commit: 确认保存技能
"""

import json
from typing import List, Optional
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
    forge_session.skill_draft.update(update_data)
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
    """
    from app.models.domain import SkillAsset, SkillStatus, generate_skill_id

    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    draft = forge_session.skill_draft

    if not draft.get("script_code"):
        raise HTTPException(status_code=400, detail="技能草稿中没有可执行代码")

    # 创建正式技能
    skill = SkillAsset(
        skill_id=generate_skill_id(),
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

    # 更新会话状态
    forge_session.skill_id = skill.skill_id
    forge_session.status = ForgeStatus.SAVED
    forge_session.updated_at = get_utc_now()

    db.commit()
    db.refresh(skill)

    log.info(f"✅ [Forge] 技能已保存: {skill.skill_id}, 会话: {session_id}")

    return {
        "status": "success",
        "skill_id": skill.skill_id,
        "name": skill.name
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
    """
    from app.models.domain import SkillAsset, SkillStatus, generate_skill_id

    forge_session = db.get(ForgeSession, session_id)
    if not forge_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if forge_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    draft = forge_session.skill_draft

    if not draft.get("script_code"):
        raise HTTPException(status_code=400, detail="技能草稿中没有可执行代码")

    # 创建正式技能
    skill = SkillAsset(
        skill_id=generate_skill_id(),
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

    # 更新会话状态
    forge_session.skill_id = skill.skill_id
    forge_session.status = ForgeStatus.SAVED

    db.commit()
    db.refresh(skill)

    log.info(f"✅ [Forge] 技能已提交审核: {skill.skill_id}")

    return {
        "status": "success",
        "skill_id": skill.skill_id,
        "name": skill.name,
        "status": "PENDING_REVIEW"
    }


# ==========================================
# POST /infer_parameters - AI 参数推断
# ==========================================
class InferParametersRequest(BaseModel):
    """参数推断请求"""
    code: str
    executor_type: str = "Python_env"


@router.post("/infer_parameters")
async def infer_parameters(
    request: InferParametersRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    从代码推断参数定义

    分析 Python argparse 或 R commandArgs 代码，返回 JSON Schema
    """
    import re
    import json

    code = request.code
    executor_type = request.executor_type

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
2. 对于文件路径参数，添加 "format": "file-path"
3. 对于目录路径参数，添加 "format": "directory-path"
4. 必须包含 description 字段
5. 只返回 JSON，不要有其他内容"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content

        # 提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = content.strip()

        parameters_schema = json.loads(json_str)

        log.info(f"✅ [Forge] 参数推断完成，发现 {len(parameters_schema.get('properties', {}))} 个参数")

        return {
            "status": "success",
            "parameters_schema": parameters_schema
        }

    except json.JSONDecodeError as e:
        log.error(f"🔥 [Forge] JSON 解析失败: {e}")
        return {
            "status": "error",
            "parameters_schema": {"type": "object", "properties": {}, "required": []},
            "message": "参数推断失败，请手动定义参数"
        }
    except Exception as e:
        log.error(f"🔥 [Forge] 参数推断失败: {e}")
        return {
            "status": "error",
            "parameters_schema": {"type": "object", "properties": {}, "required": []},
            "message": str(e)
        }


log.info("✅ 技能锻造会话 API 已加载")