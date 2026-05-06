"""
技能创建 Agent API — SSE 流式端点。

提供 generate、iterate、supplement 三个端点，
通过 Server-Sent Events 将 Agent 各阶段输出实时推送到前端。

SSE 事件类型:
  event: phase → data: {"phase": "...", "status": "running|done|error", "result": {...}}
  event: done  → data: {"session_id": "...", "forge_url": "..."}
  event: error → data: {"error": "..."}
"""

import asyncio
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.logger import log

router = APIRouter(prefix="/api/forge/agent", tags=["skill-forge-agent"])


# ==========================================
# Request Models
# ==========================================

class GenerateRequest(BaseModel):
    """首次生成技能请求"""
    user_input: str = Field(..., description="用户自然语言描述")
    chat_context: Optional[List[Dict[str, Any]]] = Field(None, description="聊天上下文")
    base_skill_id: Optional[str] = Field(None, description="基于已有技能创建")
    executor_type: Optional[str] = Field("Python_env", description="执行器类型偏好")


class IterateRequest(BaseModel):
    """迭代修改请求"""
    session_id: str = Field(..., description="ForgeSession ID")
    instruction: str = Field(..., description="修改指令，如 '参数加一个 pvalue 阈值'")
    scope: str = Field("code", description="修改范围: code|params|docs|all")


class SupplementRequest(BaseModel):
    """按需补全请求"""
    session_id: str = Field(..., description="ForgeSession ID")
    supplement_type: str = Field(..., description="补全类型: docs|tags|metadata|dependencies")


# ==========================================
# SSE Helpers
# ==========================================

async def _sse_event(event: str, data: dict) -> str:
    """生成 SSE 格式的事件字符串（与 claude.py 保持一致的命名事件格式）"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_error(message: str) -> str:
    """生成 SSE 错误事件"""
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"


# ==========================================
# POST /generate — 首次生成技能（SSE 流式）
# ==========================================

@router.post("/generate")
async def generate_skill(request: GenerateRequest):
    """首次生成技能 — SSE 流式返回 Agent 各阶段进度。

    依赖 SkillCreatorAgent（app.agent.skill_creator），
    通过 phase_callback 将 Agent 内部阶段事件推送到 SSE。

    SSE 事件类型:
      event: phase → data: {"phase": "intent_parse", "status": "running|done|error", "result": {...}}
      event: done  → data: {"session_id": "...", "forge_url": "..."}
      event: error → data: {"error": "..."}
    """
    log.info(f"[ForgeAgent] generate: {request.user_input[:50]}...")

    async def event_generator():
        event_queue: asyncio.Queue = asyncio.Queue()

        async def phase_callback(phase: str, event_data: dict):
            """Agent 各阶段回调：将事件放入队列供 SSE 消费"""
            await event_queue.put(("phase", event_data))

        # 尝试导入 SkillCreatorAgent（依赖 Tasks 3-7 的实现）
        try:
            from app.agent.skill_creator import SkillCreatorAgent
            AGENT_AVAILABLE = True
        except ImportError:
            AGENT_AVAILABLE = False
            log.warning("[ForgeAgent] SkillCreatorAgent 未实现，generate 端点降级运行")

        if not AGENT_AVAILABLE:
            yield await _sse_event("phase", {
                "phase": "init",
                "status": "error",
                "result": {"message": "SkillCreatorAgent 尚未实现，请先完成 Tasks 3-7"}
            })
            yield await _sse_error("SkillCreatorAgent 模块不存在，generate 端点暂不可用")
            return

        try:
            from app.utils.llm_config import get_thinking_llm_config_standalone
            from langchain_openai import ChatOpenAI

            # 使用项目统一的 LLM 配置解析（支持 per-user / system / env 三级回退）
            llm_config = get_thinking_llm_config_standalone()
            llm = ChatOpenAI(
                model=llm_config.model_name,
                temperature=0.3,
                api_key=llm_config.api_key,
                base_url=llm_config.base_url,
            )

            agent = SkillCreatorAgent(llm=llm, callback=phase_callback)

            # 启动 Agent（后台任务）
            agent_task = asyncio.create_task(
                agent.run(
                    user_input=request.user_input,
                    chat_context=request.chat_context,
                    base_skill_id=request.base_skill_id,
                )
            )

            # 从队列读取 SSE 事件并推送到前端
            while True:
                try:
                    event_type, event_data = await asyncio.wait_for(
                        event_queue.get(), timeout=5.0
                    )
                    yield await _sse_event(event_type, event_data)
                except asyncio.TimeoutError:
                    # 检查 Agent 是否已完成
                    if agent_task.done():
                        break
                    continue

            # Agent 完成，推送最终状态
            try:
                final_state = agent_task.result()
                if final_state.get("error"):
                    yield await _sse_event("error", {"error": final_state["error"]})
                else:
                    yield await _sse_event("done", {
                        "session_id": final_state.get("session_id"),
                        "forge_url": final_state.get("forge_url"),
                    })
            except Exception as e:
                log.error(f"[ForgeAgent] Agent 执行异常: {e}")
                yield await _sse_event("error", {"error": str(e)})

        except Exception as e:
            log.error(f"[ForgeAgent] generate 初始化失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲，确保 SSE 实时推送
        },
    )


# ==========================================
# POST /iterate — 迭代修改技能
# ==========================================

@router.post("/iterate")
async def iterate_skill(request: IterateRequest):
    """迭代修改技能 — 针对已创建的 ForgeSession 进行局部修改。

    使用 LLM 根据用户指令修改技能代码/参数/文档，
    修改结果写回 ForgeSession.skill_draft。
    """

    async def event_generator():
        from app.models.forge_session import ForgeSession
        from app.core.database import get_session

        # 从 ForgeSession 加载当前草稿内容
        db = next(get_session())
        try:
            forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
            if not forge_session:
                yield await _sse_error(f"Session not found: {request.session_id}")
                return
            draft = forge_session.skill_draft or {}
            existing_code = draft.get("script_code", "")
            existing_params = draft.get("parameters_schema", {})
            existing_name = draft.get("name", "")
            existing_desc = draft.get("description", "")
        finally:
            db.close()

        from app.utils.llm_config import get_thinking_llm_config_standalone
        from langchain_openai import ChatOpenAI

        llm_config = get_thinking_llm_config_standalone()
        llm = ChatOpenAI(
            model=llm_config.model_name,
            temperature=0.3,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
        )

        # 根据 scope 生成对应的修改提示词
        scope_map = {
            "code": "只修改脚本代码",
            "params": "只修改参数 schema",
            "docs": "只修改文档/专家知识",
            "all": "可以修改所有内容",
        }
        scope_desc = scope_map.get(request.scope, "修改代码和参数")

        iterate_prompt = f"""根据用户指令修改技能内容。

当前技能:
- 名称: {existing_name}
- 描述: {existing_desc}
- 代码:
```python
{existing_code[:3000]}
```
- 参数: {json.dumps(existing_params, ensure_ascii=False, indent=2)}

用户指令: {request.instruction}
修改范围: {scope_desc}

请返回 JSON 格式的修改后内容，只包含被修改的字段:
{{"script_code": "修改后的完整代码（如未修改则省略此字段）", "parameters_schema": {{修改后的参数（如未修改则省略此字段）}}}}"""

        try:
            yield await _sse_event("phase", {"phase": "iterate", "status": "running"})
            response = await llm.ainvoke(iterate_prompt)

            # 解析 LLM 返回的 JSON
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            result = json.loads(json_str)

            # 更新 ForgeSession 草稿
            db = next(get_session())
            try:
                forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
                # 创建新的字典对象以确保 SQLAlchemy 检测到变更（不可变模式）
                draft = dict(forge_session.skill_draft or {})
                if result.get("script_code"):
                    draft["script_code"] = result["script_code"]
                if result.get("parameters_schema"):
                    draft["parameters_schema"] = result["parameters_schema"]
                # 记录 Agent 历史
                draft["agent_history"] = draft.get("agent_history", []) + [
                    {"phase": "iterate", "instruction": request.instruction, "scope": request.scope}
                ]
                forge_session.skill_draft = draft
                db.commit()
                log.info(f"[ForgeAgent] iterate 完成: session={request.session_id}, scope={request.scope}")
            finally:
                db.close()

            yield await _sse_event("phase", {"phase": "iterate", "status": "done", "result": result})
            yield await _sse_event("done", {"session_id": request.session_id})
        except Exception as e:
            log.error(f"[ForgeAgent] iterate 失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ==========================================
# POST /supplement — 按需补全技能
# ==========================================

@router.post("/supplement")
async def supplement_skill(request: SupplementRequest):
    """按需补全技能 — 生成文档、标签、元数据或依赖。

    支持四种补全类型，每种使用不同的提示词模板，
    补全结果写回 ForgeSession.skill_draft。
    """

    supplement_prompts = {
        "docs": "为以下技能生成专业知识和操作指南文档（300字以内，中文）：",
        "tags": "为以下技能推荐 3-6 个标签（小写英文，逗号分隔）：",
        "metadata": "为以下技能推荐分类和子分类（JSON格式 {'category': '', 'subcategory': ''}）：",
        "dependencies": "为以下技能列出所需的依赖包（JSON 字符串数组）：",
    }

    async def event_generator():
        from app.models.forge_session import ForgeSession
        from app.core.database import get_session

        # 从 ForgeSession 加载当前技能上下文
        db = next(get_session())
        try:
            forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
            if not forge_session:
                yield await _sse_error(f"Session not found: {request.session_id}")
                return
            draft = forge_session.skill_draft or {}
            skill_context = f"""
名称: {draft.get('name', '')}
描述: {draft.get('description', '')}
执行器: {draft.get('executor_type', 'Python_env')}
参数: {json.dumps(draft.get('parameters_schema', {}), ensure_ascii=False)}
代码摘要: {draft.get('script_code', '')[:1000]}
"""
        finally:
            db.close()

        prompt = supplement_prompts.get(request.supplement_type)
        if not prompt:
            yield await _sse_error(f"Unknown supplement_type: {request.supplement_type}")
            return

        from app.utils.llm_config import get_thinking_llm_config_standalone
        from langchain_openai import ChatOpenAI

        llm_config = get_thinking_llm_config_standalone()
        llm = ChatOpenAI(
            model=llm_config.model_name,
            temperature=0.5,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
        )

        try:
            yield await _sse_event("phase", {"phase": "supplement", "status": "running"})
            response = await llm.ainvoke(prompt + "\n\n" + skill_context)
            content = response.content.strip()

            # 根据补全类型写入 ForgeSession 草稿的不同字段
            db = next(get_session())
            try:
                forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
                # 创建新的字典对象以确保 SQLAlchemy 检测到变更（不可变模式）
                draft = dict(forge_session.skill_draft or {})
                if request.supplement_type == "docs":
                    draft["expert_knowledge"] = content
                elif request.supplement_type == "tags":
                    draft["tags"] = [t.strip() for t in content.split(",")]
                elif request.supplement_type == "metadata":
                    # 尝试解析 JSON，失败则保持原文
                    try:
                        meta = json.loads(content)
                    except json.JSONDecodeError:
                        meta = {}
                    draft["category"] = meta.get("category", draft.get("category"))
                    draft["subcategory"] = meta.get("subcategory", draft.get("subcategory"))
                elif request.supplement_type == "dependencies":
                    # 尝试解析 JSON 数组，失败则按逗号分割
                    try:
                        deps = json.loads(content) if content.startswith("[") else [d.strip() for d in content.split(",")]
                    except json.JSONDecodeError:
                        deps = [d.strip() for d in content.split(",")]
                    draft["dependencies"] = deps
                forge_session.skill_draft = draft
                db.commit()
                log.info(f"[ForgeAgent] supplement 完成: session={request.session_id}, type={request.supplement_type}")
            finally:
                db.close()

            yield await _sse_event("phase", {
                "phase": "supplement",
                "status": "done",
                "result": {"type": request.supplement_type, "content": content}
            })
            yield await _sse_event("done", {"session_id": request.session_id})
        except Exception as e:
            log.error(f"[ForgeAgent] supplement 失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ==========================================
# GET /session/{session_id}/state — Agent 状态恢复
# ==========================================

@router.get("/session/{session_id}/state")
async def get_agent_state(session_id: str):
    """获取 Agent 当前状态（用于 SSE 断连后恢复）。

    返回 ForgeSession 中记录的 Agent 阶段、历史、检查结果等信息，
    前端可根据状态决定是否重新连接 SSE 或展示已有结果。
    """
    from app.models.forge_session import ForgeSession
    from app.core.database import get_session

    db = next(get_session())
    try:
        forge_session = db.query(ForgeSession).filter(ForgeSession.id == session_id).first()
        if not forge_session:
            raise HTTPException(status_code=404, detail="Session not found")
        draft = forge_session.skill_draft or {}
        return {
            "session_id": session_id,
            "agent_phase": draft.get("agent_phase"),
            "agent_history": draft.get("agent_history", []),
            "static_check_result": draft.get("static_check_result"),
            "auto_test_result": draft.get("auto_test_result"),
            "has_code": bool(draft.get("script_code")),
            "has_params": bool(draft.get("parameters_schema")),
        }
    finally:
        db.close()


log.info("✅ 技能创建 Agent API 已加载")
