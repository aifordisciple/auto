"""
会话摘要 API

处理会话摘要的生成和缓存，包括：
- 获取会话摘要（从缓存）
- AI 生成会话摘要
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.domain import (
    ChatSession, ChatMessage, Project, User, RoleEnum,
    SessionSummaryCache, SystemConfig
)
from app.api.deps import get_current_user
from app.core.logger import log


router = APIRouter()


@router.get("/sessions/{session_id}/summary")
def get_session_summary(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取会话摘要（从缓存）"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    # 查找缓存
    cached = session.exec(
        select(SessionSummaryCache)
        .where(SessionSummaryCache.session_id == session_id)
    ).first()

    if cached:
        return {
            "status": "success",
            "summary": cached.summary,
            "key_points": cached.key_points,
            "generated_at": cached.generated_at,
            "cached": True
        }

    return {"status": "success", "summary": None, "cached": False}


@router.post("/sessions/{session_id}/summarize")
def generate_session_summary(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """AI 生成会话摘要"""
    from app.models.domain import get_utc_now

    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    # 获取所有消息
    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()

    if not messages:
        return {"status": "success", "summary": "暂无对话内容", "key_points": []}

    # 构建摘要提示词
    conversation_text = "\n".join([
        f"[{'用户' if msg.role == RoleEnum.user else 'AI'}]: {msg.content[:500]}"
        for msg in messages
    ])

    # 调用 LLM 生成摘要
    config = session.get(SystemConfig, 1)
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.openai_api_key or "ollama",
            base_url=config.openai_base_url or "http://localhost:11434/v1"
        )

        response = client.chat.completions.create(
            model=config.default_model or "gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个对话摘要专家。请分析对话内容，生成：
1. 一段简洁的摘要（100字以内）
2. 3-5个关键要点

请以 JSON 格式返回：
{
    "summary": "摘要内容",
    "key_points": ["要点1", "要点2", "要点3"]
}"""
                },
                {"role": "user", "content": f"请总结以下对话：\n\n{conversation_text}"}
            ],
            max_tokens=500,
            temperature=0.3
        )

        result_text = response.choices[0].message.content.strip()

        # 尝试解析 JSON
        try:
            # 提取 JSON 部分
            if "```json" in result_text:
                json_start = result_text.find("```json") + 7
                json_end = result_text.find("```", json_start)
                result_text = result_text[json_start:json_end].strip()
            elif "```" in result_text:
                json_start = result_text.find("```") + 3
                json_end = result_text.find("```", json_start)
                result_text = result_text[json_start:json_end].strip()

            result = json.loads(result_text)
            summary = result.get("summary", "摘要生成失败")
            key_points = result.get("key_points", [])
        except:
            summary = result_text[:200]
            key_points = []

        # 缓存结果
        cached_summary = session.exec(
            select(SessionSummaryCache)
            .where(SessionSummaryCache.session_id == session_id)
        ).first()

        if cached_summary:
            cached_summary.summary = summary
            cached_summary.key_points = key_points
            cached_summary.generated_at = get_utc_now()
        else:
            cached_summary = SessionSummaryCache(
                session_id=session_id,
                summary=summary,
                key_points=key_points
            )
            session.add(cached_summary)

        session.commit()

        return {
            "status": "success",
            "summary": summary,
            "key_points": key_points,
            "cached": False
        }

    except Exception as e:
        log.error(f"AI 摘要生成失败: {str(e)}")
        return {"status": "error", "message": str(e)}