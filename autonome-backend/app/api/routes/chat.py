import json
import os
from http import HTTPStatus
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_session, engine
from app.models.domain import ChatSession, ChatMessage, DataFile, SystemConfig, RoleEnum, Project, User
from app.agent.bot import build_bio_agent
from app.core.logger import log
from app.api.deps import get_current_user


router = APIRouter()


class ChatRequest(BaseModel):
    project_id: int
    message: str
    context_files: list[str] = []
    session_id: Optional[int] = None


@router.post("/stream")
async def chat_stream(
    request: ChatRequest, 
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    if not current_user.billing or current_user.billing.credits_balance <= 0:
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用大模型与沙箱服务。"
        )

    # 3. 会话路由与创建逻辑
    if request.session_id:
        chat_session = session.get(ChatSession, request.session_id)
        if not chat_session or chat_session.project_id != request.project_id:
            raise HTTPException(status_code=404, detail="会话不存在或已删除")
        is_new_session = False
    else:
        temp_title = request.message[:15] + "..." if len(request.message) > 15 else request.message
        chat_session = ChatSession(project_id=request.project_id, title=temp_title)
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)
        is_new_session = True
        
    user_msg = ChatMessage(session_id=chat_session.id, role=RoleEnum.user, content=request.message)
    session.add(user_msg)
    session.commit()
    session_id_for_ai = chat_session.id
    
    # 提取用户 ID
    user_id = current_user.id
    
    # 4. 解析物理文件路径
    physical_file_info = ""
    if request.context_files:
        files_in_db = session.exec(
            select(DataFile).where(
                DataFile.project_id == request.project_id, 
                DataFile.filename.in_(request.context_files)
            )
        ).all()
        for f in files_in_db:
            physical_file_info += f"- {f.filename} (物理路径: {os.path.abspath(f.file_path)})\n"

    # 5. 动态加载 LLM 配置
    config = session.get(SystemConfig, 1)
    
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None
    
    env_api_key = os.getenv("OPENAI_API_KEY")
    
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)
    
    if is_local_model:
        api_key = db_api_key if db_api_key is not None else ""
    else:
        api_key = db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key
    
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    async def event_generator():
        # 先推送 session_id 给前端
        yield {"event": "session_info", "data": json.dumps({"session_id": session_id_for_ai, "is_new": is_new_session})}
        
        if not is_local_model and not api_key:
            yield {"event": "message", "data": json.dumps({"type": "text", "content": "⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。"})}
            yield {"event": "done", "data": "[DONE]"}
            return

        ai_full_response = ""
        cost_credits = 1.0
        
        try:
            log.info(f"🔧 [Chat] 构建 Agent - base_url={base_url}, model={model_name}")
            
            agent_executor = build_bio_agent(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                physical_file_info=physical_file_info,
                user_id=user_id,
                project_id=request.project_id
            )
            
            log.info(f"💬 [Chat] 开始生成 - user_id={user_id}, message={request.message[:50]}...")
            
            messages = [{"role": "user", "content": request.message}]
            
            # ✨ 打印发送给大模型的完整消息
            log.info(f"📤 [向 AI 发送请求]: {messages}")
            log.info("📡 正在等待 Agent 流式事件响应...")

            async for event in agent_executor.astream_events({"messages": messages}, config={"recursion_limit": 20}, version="v2"):
                kind = event["event"]
                
                if kind == "on_chain_start":
                    node_name = event.get("name", "")
                    worker_names = {
                        "Advisor": "🧑‍🔬 科学顾问",
                        "Cleaner": "🧹 数据清洗专员",
                        "Analyst": "📊 生信分析师",
                        "Interpreter": "🧬 生物学解释专家",
                        "Reporter": "📝 出版撰稿人"
                    }
                    if node_name in worker_names:
                        msg = f"\n\n> *(🔄 调度中心：项目主管已将该任务划拨至 **{worker_names[node_name]}** ...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", {})
                    
                    # ✨ 拦截并打印潜在的隐藏 Tool Calls
                    if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                        log.warning(f"⚠️ [AI 生成了隐藏的工具调用]: {chunk.tool_calls}")
                        
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if isinstance(content, str) and content:
                        # ✨ 打印 AI 输出的每一个字符片段
                        log.info(f"📥 [AI 字符流]: {repr(content[:100])}")
                        ai_full_response += content
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}
                
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    if tool_name in ["execute_python_code", "rnaseq_qc"]:
                        cost_credits += 4.0
                        msg = f"\n\n*(🚀 Agent 正在调用工具: {tool_name})*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                        
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    if tool_name in ["execute_python_code", "rnaseq_qc"]:
                        msg = f"\n*(✅ 工具 {tool_name} 执行完毕)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

            # ✨ 打印 AI 的最终完整回复
            log.info(f"✅ [AI 完整输出结果]:\n{ai_full_response if ai_full_response else '<空> (AI没有返回任何文本)'}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Chat] 致命错误: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
            ai_full_response += err_msg
            yield {"event": "message", "data": json.dumps({"type": "text", "content": err_msg})}
        
        finally:
            with Session(engine) as final_db_session:
                ai_msg = ChatMessage(session_id=session_id_for_ai, role=RoleEnum.assistant, content=ai_full_response)
                final_db_session.add(ai_msg)
                
                db_user = final_db_session.get(User, user_id)
                if db_user.billing:
                    db_user.billing.credits_balance -= cost_credits
                    if db_user.billing.credits_balance < 0:
                        db_user.billing.credits_balance = 0
                
                final_db_session.commit()
                
                final_balance = db_user.billing.credits_balance if db_user.billing else 0
                yield {"event": "billing", "data": json.dumps({"cost": cost_credits, "balance": final_balance})}
            
            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())


# ==========================================
# 会话管理 API
# ==========================================

class SessionUpdate(BaseModel):
    title: str


@router.get("/projects/{project_id}/sessions")
def get_project_sessions(
    project_id: int, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """获取项目下的所有历史对话列表"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    
    sessions = session.exec(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return {"status": "success", "data": sessions}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: int, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """获取指定对话的所有聊天记录"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    
    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return {"status": "success", "data": messages}


@router.put("/sessions/{session_id}")
def rename_session(
    session_id: int, 
    req: SessionUpdate, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """手动重命名对话"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    chat_session.title = req.title[:100]
    session.add(chat_session)
    session.commit()
    return {"status": "success", "title": chat_session.title}


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """删除对话"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    session.delete(chat_session)
    session.commit()
    return {"status": "success"}


@router.post("/sessions/{session_id}/auto-name")
def auto_name_session(
    session_id: int, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """AI 自动根据第一条消息提炼标题"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    project = session.get(Project, chat_session.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    first_msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).first()
    
    if not first_msg:
        return {"title": chat_session.title}

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
                {"role": "system", "content": "你是一个标题生成器。请根据用户的提问，生成一个4到8个字的极简对话标题。不要加引号或任何标点符号。"},
                {"role": "user", "content": first_msg.content}
            ],
            max_tokens=15,
            temperature=0.3
        )
        new_title = response.choices[0].message.content.strip().replace('"', '').replace("'", '')
        chat_session.title = new_title
        session.add(chat_session)
        session.commit()
        return {"status": "success", "title": new_title}
    except Exception as e:
        log.error(f"AI 命名失败: {str(e)}")
        return {"status": "error", "title": chat_session.title}
