"""
会话关闭与经验提取 API

处理会话关闭时的经验资产提取，包括：
- 关闭会话并提取经验
- 评估会话成功度
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel

from app.core.database import get_session
from app.models.domain import ChatSession, Project, User
from app.api.deps import get_current_user
from app.services.success_evaluator import SuccessEvaluator
from app.services.knowledge_extractor import KnowledgeExtractor
from app.core.logger import log


router = APIRouter()


class CloseSessionRequest(BaseModel):
    """关闭会话请求"""
    extract_experience: bool = True  # 是否尝试提取经验


@router.post("/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    request: CloseSessionRequest = CloseSessionRequest(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    关闭会话并尝试提取经验资产

    当用户关闭会话时：
    1. 评估会话成功度
    2. 如果成功且置信度足够高，自动提取知识资产
    3. 存储为私有经验，用户可选择公开
    """
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    result = {
        "session_id": session_id,
        "session_title": chat_session.title,
        "closed_at": datetime.now().isoformat(),
        "experience_extracted": False,
        "evaluation": None,
        "experience": None
    }

    if not request.extract_experience:
        return {"status": "success", **result}

    try:
        # 1. 评估会话成功度
        evaluator = SuccessEvaluator(session)
        evaluation = evaluator.evaluate_session(session_id)
        result["evaluation"] = evaluation

        log.info(
            f"📊 [CloseSession] 会话 {session_id} 评估: "
            f"成功={evaluation['is_successful']}, 置信度={evaluation['confidence']:.2f}"
        )

        # 2. 如果成功且置信度足够高，提取经验
        if evaluation["is_successful"] and evaluation["confidence"] >= 0.7:
            extractor = KnowledgeExtractor(session)
            experience = await extractor.extract_from_session(
                session_id=session_id,
                user_id=current_user.id,
                project_id=chat_session.project_id
            )

            if experience:
                result["experience_extracted"] = True
                result["experience"] = {
                    "experience_id": experience.experience_id,
                    "title": experience.title,
                    "summary": experience.summary[:100] + "...",
                    "category": experience.category
                }
                log.info(f"✅ [CloseSession] 成功提取经验: {experience.experience_id}")

    except Exception as e:
        log.error(f"❌ [CloseSession] 经验提取失败: {e}")
        result["error"] = str(e)

    return {"status": "success", **result}


@router.get("/sessions/{session_id}/evaluate")
async def evaluate_session_success(
    session_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    评估会话成功度（不关闭会话）

    返回会话成功度评估详情，供前端展示
    """
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    try:
        evaluator = SuccessEvaluator(session)
        evaluation = evaluator.evaluate_session(session_id)

        return {
            "status": "success",
            "session_id": session_id,
            "evaluation": evaluation
        }

    except Exception as e:
        log.error(f"评估会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))