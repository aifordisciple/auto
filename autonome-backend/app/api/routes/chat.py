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


# ==========================================
# 对话上下文支持
# ==========================================

def load_conversation_history(session_id: str, db: Session, max_messages: int = 20) -> list:
    """
    加载最近 N 条历史消息，构建对话上下文

    Args:
        session_id: 会话 ID
        db: 数据库会话
        max_messages: 最大加载消息数（防止 token 超限）

    Returns:
        格式化的消息列表 [{"role": "user/assistant", "content": "..."}]
    """
    try:
        messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(max_messages)
        ).all()

        # 按时间正序排列（从旧到新）
        messages = list(reversed(messages))

        # 转换为 LangChain 消息格式
        history = []
        for msg in messages:
            if msg.role == RoleEnum.user:
                history.append({"role": "user", "content": msg.content})
            elif msg.role == RoleEnum.assistant:
                history.append({"role": "assistant", "content": msg.content})
            # 忽略 system 消息（如果有）

        log.info(f"📜 [Context] 加载了 {len(history)} 条历史消息")
        return history

    except Exception as e:
        log.error(f"❌ [Context] 加载历史消息失败: {e}")
        return []


# ==========================================
# 沙箱自动重试处理器
# ==========================================

class SandboxRetryHandler:
    """沙箱执行失败自动重试处理器"""

    MAX_RETRIES = 3  # 最大重试次数

    # 错误标记 - 用于检测执行失败
    ERROR_MARKERS = [
        'Traceback',
        'Error:',
        'Exception:',
        '❌',
        'segmentation fault',
        'Failed',
        '错误:',
    ]

    @staticmethod
    def is_execution_failed(output: str) -> bool:
        """
        检测沙箱执行是否失败

        Args:
            output: 沙箱执行输出

        Returns:
            True 表示执行失败，False 表示成功
        """
        if not output:
            return True

        output_str = str(output)

        # 检查错误标记
        for marker in SandboxRetryHandler.ERROR_MARKERS:
            if marker in output_str:
                return True

        return False

    @staticmethod
    def extract_error_message(output: str, max_lines: int = 15) -> str:
        """
        从执行输出中提取错误信息

        Args:
            output: 沙箱执行输出
            max_lines: 最大返回行数

        Returns:
            提取的错误信息
        """
        if not output:
            return "执行无输出"

        lines = output.split('\n')
        error_lines = []

        # 查找错误起始位置
        for i, line in enumerate(lines):
            for marker in SandboxRetryHandler.ERROR_MARKERS:
                if marker in line:
                    # 捕获错误及其上下文
                    start = max(0, i - 2)
                    error_lines = lines[start:i + max_lines]
                    break
            if error_lines:
                break

        if not error_lines:
            error_lines = lines[:max_lines]

        return '\n'.join(error_lines)


class ChatRequest(BaseModel):
    project_id: str
    message: str
    context_files: list[str] = []
    session_id: Optional[str] = None


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
    
    # ========================================================
    # ✨ 核心升级：基于纯物理文件系统的全景视力构建
    # ========================================================
    # 4. 扫描整个项目硬盘，构建【全景目录树】
    project_dir = os.path.join("uploads", f"project_{request.project_id}")
    global_file_tree = "当前项目文件目录树：\n"
    
    if os.path.exists(project_dir):
        for root, dirs, files in os.walk(project_dir):
            for file in files:
                if file.startswith('.'): continue
                rel_path = os.path.relpath(os.path.join(root, file), project_dir)
                global_file_tree += f"- {rel_path}\n"
    else:
        global_file_tree += "（当前项目为空）\n"

    # 5. 解析用户勾选的重点文件，提供【显微视力】（绝对路径供代码读取）
    physical_file_info = ""
    if request.context_files:
        for rel_path in request.context_files:
            if ".." not in rel_path:
                abs_path = os.path.abspath(os.path.join(project_dir, rel_path))
                sandbox_path = f"/app/uploads/project_{request.project_id}/{rel_path}"
                physical_file_info += f"- {rel_path} (沙箱绝对路径: {sandbox_path})\n"
    # ========================================================

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
                global_file_tree=global_file_tree,
                user_id=user_id,
                project_id=request.project_id
            )
            
            log.info(f"💬 [Chat] 开始生成 - user_id={user_id}, message={request.message[:50]}...")

            # ✨ Feature 1: 加载历史对话上下文
            history = load_conversation_history(session_id_for_ai, session) if not is_new_session else []
            messages = history + [{"role": "user", "content": request.message}]

            # ✨ 打印发送给大模型的完整消息
            log.info(f"📤 [向 AI 发送请求]: 历史消息 {len(history)} 条 + 当前消息 1 条")
            if history:
                log.info(f"📜 [对话上下文]: 最近 {len(history)} 条历史消息已加载")
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
                    if tool_name in ["execute_python_code"]:
                        cost_credits += 4.0
                        msg = f"\n\n> 🚀 *(启动安全沙箱，正在执行分析代码...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    elif tool_name == "peek_tabular_data":
                        msg = f"\n\n> 🟢 *(调用环境探针：正在预览表格数据结构...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    elif tool_name == "scan_workspace":
                        msg = f"\n\n> 🟢 *(调用环境探针：正在扫描工作区目录...)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    else:
                        # 其他工具的通用提示
                        msg = f"\n\n*(🔄 Agent 正在调用工具: {tool_name})*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    output = event.get("data", {}).get("output", "")

                    if tool_name in ["execute_python_code"]:
                        # ✨ Feature 2: 增强的错误检测
                        is_failed = SandboxRetryHandler.is_execution_failed(output)

                        if is_failed:
                            # 提取错误信息
                            error_msg = SandboxRetryHandler.extract_error_message(output)
                            log.warning(f"⚠️ [Sandbox] 执行失败: {error_msg[:200]}")

                            msg = f"\n\n> 🔴 *(沙箱执行失败，正在分析错误...)*\n\n"
                            ai_full_response += msg
                            yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                            # 推送错误详情事件（前端可选择性展示）
                            yield {
                                "event": "sandbox_error",
                                "data": json.dumps({
                                    "type": "execution_error",
                                    "error_preview": error_msg[:500],
                                    "retry_hint": "Agent 将自动尝试修复"
                                })
                            }
                        else:
                            msg = f"\n\n> ✅ *(沙箱代码执行成功，产物已落盘)*\n\n"
                            ai_full_response += msg
                            yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    elif tool_name == "peek_tabular_data":
                        msg = f"\n\n> ✅ *(探针返回：表格结构已解析)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    elif tool_name == "scan_workspace":
                        msg = f"\n\n> ✅ *(探针返回：目录结构已扫描)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

            # ✨ 打印 AI 的最终完整回复
            log.info(f"✅ [AI 完整输出结果]:\n{ai_full_response if ai_full_response else '<空> (AI没有返回任何文本)'}")

            # ==========================================
            # ✨ 蓝图拦截与 DAG 调度
            # ==========================================
            if "```json_blueprint" in ai_full_response or '"is_complex_task": true' in ai_full_response:
                from app.services.orchestrator import extract_blueprint, run_dag_stream

                blueprint = extract_blueprint(ai_full_response)

                if blueprint and blueprint.get("is_complex_task"):
                    log.info(f"🔄 [Chat] 检测到复杂任务蓝图，启动 DAG 调度器")

                    # 推送蓝图检测事件
                    yield {
                        "event": "blueprint_detected",
                        "data": json.dumps({
                            "project_goal": blueprint.get("project_goal", ""),
                            "task_count": len(blueprint.get("tasks", []))
                        })
                    }

                    # 启动 DAG 流式执行
                    try:
                        async for dag_event in run_dag_stream(
                            blueprint_data=blueprint,
                            api_key=api_key,
                            base_url=base_url,
                            model_name=model_name,
                            project_id=request.project_id,
                            session_id=str(session_id_for_ai)
                        ):
                            # 转发 DAG 事件到前端
                            yield dag_event

                        log.info(f"✅ [Chat] DAG 执行完成")

                    except Exception as dag_error:
                        log.error(f"❌ [Chat] DAG 执行错误: {str(dag_error)}")
                        yield {
                            "event": "blueprint_error",
                            "data": json.dumps({"error": str(dag_error)})
                        }

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
    project_id: str, 
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
    session_id: str, 
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
    session_id: str, 
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
    session_id: str, 
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
    session_id: str, 
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


# ==========================================
# 深度解读 API - 专门用于解读分析结果
# ==========================================

class InterpretRequest(BaseModel):
    project_id: str
    session_id: str
    user_message: str  # 用户的原始需求
    code: str  # 执行的代码
    files: list[str]  # 结果文件相对路径列表


@router.post("/interpret")
async def interpret_results(
    request: InterpretRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    深度解读分析结果 - 只返回解读，不生成策略卡片
    """
    # 1. 安全校验
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    if not current_user.billing or current_user.billing.credits_balance <= 0:
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用。"
        )

    user_id = current_user.id

    # 3. 读取结果文件内容
    project_dir = f"/app/uploads/project_{request.project_id}"
    file_contents = []

    for rel_path in request.files:
        # 安全检查：防止路径遍历
        if ".." in rel_path:
            continue

        full_path = os.path.join(project_dir, rel_path)
        if not os.path.exists(full_path):
            continue

        ext = os.path.splitext(rel_path)[1].lower()

        # 图片文件：只记录文件名和类型
        if ext in ['.png', '.jpg', '.jpeg', '.svg', '.pdf']:
            file_contents.append(f"\n**图片文件**: `{rel_path}`\n（AI 已生成可视化图表，请查看上方展示）\n")

        # 表格/文本文件：读取内容并截取
        elif ext in ['.csv', '.tsv', '.txt', '.xlsx']:
            try:
                if ext == '.xlsx':
                    file_contents.append(f"\n**Excel文件**: `{rel_path}`\n（二进制格式，已在前端渲染）\n")
                else:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    # 截取前 30 行
                    max_lines = 30
                    if len(lines) > max_lines:
                        content = ''.join(lines[:max_lines])
                        content += f"\n... (共 {len(lines)} 行，已截取前 {max_lines} 行)"
                    else:
                        content = ''.join(lines)

                    file_contents.append(f"\n**数据文件**: `{rel_path}`\n```\n{content}\n```\n")
            except Exception as e:
                file_contents.append(f"\n**文件**: `{rel_path}`\n（读取失败: {str(e)}）\n")

    # 4. 构造深度解读提示词
    files_info = '\n'.join(file_contents) if file_contents else "（无文件信息）"

    interpret_prompt = f"""## 任务：生成专业深度解读报告

请根据以下生物信息学分析结果，生成一份专业的深度解读报告。

---

### 用户原始需求
{request.user_message}

---

### 执行的代码
```{'python' if 'import pandas' in request.code or 'import numpy' in request.code else 'r'}
{request.code}
```

---

### 生成的结果文件
{files_info}

---

## 报告输出要求

请严格按照以下结构输出专业的深度解读报告，使用美观的 Markdown 格式：

### 📋 报告结构

**1. 主要发现（中文）**
- 用清晰的段落总结核心发现
- 列出关键数据指标

**2. Figure Legend / 图注**
```
【中文图注】
专业的图表描述（适合论文投稿格式）

【English Figure Legend】
Professional figure description in publication-ready format
```

**3. Materials and Methods / 材料与方法**
```
【中文材料方法】
简述分析流程和方法，适合论文方法部分引用

【English Materials and Methods】
Brief description of analysis pipeline for manuscript Methods section
```

**4. 生物学意义**
- 解释结果的生物学含义
- 与已知文献或知识的关联

**5. 临床/研究价值**
- 潜在应用场景
- 对后续研究的启示

**6. 局限性与注意事项**
- 分析方法的局限性
- 结果解读需注意的问题

**7. 下一步分析建议**
- 推荐 2-3 个后续分析方向
- 简要说明每个方向的价值

---

## 格式要求
- 使用适当的标题层级（##, ###）
- 关键术语加粗
- 数据用 `代码格式` 标注
- 列表使用 - 或 1. 2. 3.
- 整体风格专业、清晰、易读
- 中英文部分分开标注"""

    # 5. 获取 LLM 配置
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

    # 6. 流式生成解读结果
    async def event_generator():
        ai_full_response = ""
        cost_credits = 1.0  # 解读任务收费

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)

            log.info(f"🔍 [Interpret] 开始深度解读 - model={model_name}")

            # 专业系统提示，确保输出高质量报告
            stream = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一位资深的生物信息学分析报告撰写专家，具有丰富的学术论文写作经验。

你的专长：
- 撰写高质量的中英文图注（Figure Legend）
- 撰写标准的中英文材料方法（Materials and Methods）
- 进行深入的生物学意义解读
- 提供专业的后续分析建议

**重要规则**：
1. 不要输出任何代码
2. 不要生成策略卡片
3. 只输出纯文本的专业报告
4. 必须包含中英文图注和材料方法
5. 格式美观，适合直接用于学术报告或论文草稿"""
                    },
                    {"role": "user", "content": interpret_prompt}
                ],
                stream=True,
                temperature=0.7,
                max_tokens=4000
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    ai_full_response += content
                    yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}

            log.info(f"✅ [Interpret] 解读完成，共 {len(ai_full_response)} 字符")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Interpret] 错误: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **解读服务异常**: {str(e)}"
            ai_full_response += err_msg
            yield {"event": "message", "data": json.dumps({"type": "text", "content": err_msg})}

        finally:
            # 保存消息到数据库
            with Session(engine) as final_db_session:
                # 保存用户消息（简要提示）
                user_msg = ChatMessage(
                    session_id=request.session_id,
                    role=RoleEnum.user,
                    content="🧬 深度解读分析结果"
                )
                final_db_session.add(user_msg)

                # 保存 AI 解读结果
                ai_msg = ChatMessage(
                    session_id=request.session_id,
                    role=RoleEnum.assistant,
                    content=ai_full_response
                )
                final_db_session.add(ai_msg)

                # 扣费
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
