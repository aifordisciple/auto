import json
import os
from http import HTTPStatus
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

    # 3. 记录用户消息
    chat_session = session.exec(
        select(ChatSession).where(ChatSession.project_id == request.project_id)
    ).first()
    if not chat_session:
        chat_session = ChatSession(project_id=request.project_id)
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)
        
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
        if not is_local_model and not api_key:
            yield {"event": "message", "data": json.dumps({"type": "text", "content": "⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。"})}
            yield {"event": "done", "data": "[DONE]"}
            return

        ai_full_response = ""
        cost_credits = 1.0
        
        try:
            agent_executor = build_bio_agent(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                physical_file_info=physical_file_info,
                user_id=user_id,
                project_id=request.project_id
            )
            
            log.info(f"💬 [Chat] 开始生成 - user_id={user_id}, base_url={base_url}, model={model_name}")
            
            messages = [{"role": "user", "content": request.message}]

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
                    content = event["data"]["chunk"].content
                    if isinstance(content, str) and content:
                        ai_full_response += content
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}
                
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    if tool_name == "execute_python_code":
                        cost_credits += 4.0
                        msg = "\n\n*(🚀 Agent 决策：正在安全沙箱中编写并执行 Python 脚本...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                        
                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    if tool_name == "execute_python_code":
                        msg = "\n*(✅ 沙箱执行完毕，正在将运行结果反馈给 AI 大脑...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

        except Exception as e:
            log.error(f"❌ [Chat] 错误: {str(e)}")
            err_msg = f"\n\n❌ **AI 引擎连接或图执行异常**: {str(e)}\n请检查网络或日志。"
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
