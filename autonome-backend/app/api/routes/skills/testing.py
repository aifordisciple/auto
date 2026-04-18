"""
技能测试 API

包含沙箱测试接口
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.utils.llm_config import get_llm_config
from app.services.skill_validator import validate_iron_rules
from app.schemas.skill import SkillTestRequest

router = APIRouter()


# ==========================================
# POST /api/skills/test_draft - 自动化沙箱测试
# ==========================================
@router.post("/test_draft")
async def test_skill_draft_api(
    req: SkillTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge】自动化沙箱测试接口（增强版）

    功能：
    1. 自动生成测试数据（基于参数 Schema）
    2. 多场景测试（不同参数组合）
    3. 测试失败自动修复

    前端传入生成的草稿代码和测试参数，后端扔进沙箱跑。
    如果失败自动触发 AI 修复，返回最终是否跑通，以及最终修复好的代码。
    """
    if not req.script_code:
        raise HTTPException(status_code=400, detail="缺少需要测试的代码")

    # 铁律校验
    is_valid, error_msg = validate_iron_rules(req.script_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 获取 LLM 配置（共享工具：per-user override → system global → env fallback）
    llm_cfg = get_llm_config(session, user_id=current_user.id)
    api_key, base_url, model_name = llm_cfg.api_key, llm_cfg.base_url, llm_cfg.model_name

    try:
        from app.agent.skill_tester import auto_test_and_heal_skill

        log.info(f"🧪 [Skills API] 用户 {current_user.id} 开始沙箱测试... 自动生成数据: {req.auto_generate_data}")

        test_result = await auto_test_and_heal_skill(
            script_code=req.script_code,
            test_instruction=req.test_instruction,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            parameters_schema=req.parameters_schema,
            auto_generate_data=req.auto_generate_data,
            max_test_rounds=req.max_test_rounds,
            executor_type=req.executor_type
        )

        return {"status": "success", "data": test_result}

    except Exception as e:
        log.error(f"自动化测试接口报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/test_draft_stream - 沙箱测试接口 (SSE 流式日志)
# ==========================================
@router.post("/test_draft_stream")
async def test_skill_draft_stream_api(
    req: SkillTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【SKILL Forge】自动化沙箱测试接口（SSE 流式日志版本）

    功能：
    1. 实时推送测试进度日志
    2. 多场景测试进度可视化
    3. 测试失败自动修复过程可见

    返回 SSE 流，事件格式：
    - data: {"type": "log", "message": "..."}
    - data: {"type": "status", "message": "..."}
    - data: {"type": "result", "data": {...}}
    """
    if not req.script_code:
        raise HTTPException(status_code=400, detail="缺少需要测试的代码")

    # 铁律校验
    is_valid, error_msg = validate_iron_rules(req.script_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 获取 LLM 配置（共享工具：per-user override → system global → env fallback）
    llm_cfg = get_llm_config(session, user_id=current_user.id)
    api_key, base_url, model_name = llm_cfg.api_key, llm_cfg.base_url, llm_cfg.model_name

    try:
        from app.agent.skill_tester import auto_test_and_heal_skill_stream

        log.info(f"🧪 [Skills API] 用户 {current_user.id} 开始沙箱测试 (流式模式)...")

        async def event_generator():
            async for event in auto_test_and_heal_skill_stream(
                script_code=req.script_code,
                test_instruction=req.test_instruction,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                parameters_schema=req.parameters_schema,
                auto_generate_data=req.auto_generate_data,
                max_test_rounds=req.max_test_rounds,
                executor_type=req.executor_type
            ):
                yield event

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        log.error(f"自动化测试流式接口报错: {e}")
        raise HTTPException(status_code=500, detail=str(e))