"""
聊天 API - 核心聊天流（意图感知模式）

处理流程：
1. 安全校验和计费检查
2. 会话创建/恢复
3. 意图分类（代码生成 / 技能匹配 / 一般问答）
4. 根据意图选择系统提示词
5. LLM 流式调用
6. 持久化助手消息 + 扣费

拆分说明：
- 会话管理 API → chat_session.py
- 消息收藏 API → chat_bookmark.py
- 会话标签 API → chat_tags.py
- 对话搜索 API → chat_search.py
- Pydantic 模型 → schemas/chat.py
"""

import json
import asyncio
from http import HTTPStatus
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from fastapi.responses import StreamingResponse

from app.core.database import get_session, engine
from app.models.domain import (
    ChatSession, ChatMessage, RoleEnum, Project, User,
)
from app.core.logger import log
from app.api.deps import get_current_user
from app.core.content_filter import filter_thinking_content, StreamContentFilter
from app.core.vercel_stream import VercelDataStreamEncoder

from app.schemas.chat import ChatRequest


router = APIRouter()


# ==========================================
# 系统提示词
# ==========================================

# 一般问答模式：知识解答
SYSTEM_PROMPT_CHAT = """你是一个专业的生物信息学AI助手，名为 Autonome。你可以帮助用户解答生物信息学相关的问题，包括数据分析方法、工具使用、实验设计等。

核心原则：
- 用中文回答问题
- 回答要准确、专业
- 如果不确定，请诚实说明
- 对于用户的提问，始终直接给出专业、详细的回答，这是最重要的规则

【严禁事项 - 最高优先级】：
- 绝对不要在回答开头重复自己的身份（如"我是 Autonome AI助手"、"我是 Autonome"等）
- 绝对不要在回答开头做自我介绍
- 绝对不要说"你好！我是..."之类的话
- 直接回答用户的问题，不要任何前缀或寒暄

身份相关：
- 不要提及你的训练来源、模型身份或开发机构（如 Google、OpenAI 等）
- 当且仅当用户明确询问"你是谁"或"你是什么"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接回答用户的问题"""

# 代码生成模式：编写可执行代码
SYSTEM_PROMPT_CODE = """你是一个专业的生物信息学编程助手，名为 Autonome。你的核心职责是为用户编写可执行的数据分析代码。

核心原则：
- 用中文解释思路，但代码本身使用英文变量名和注释
- 始终直接输出可执行的代码，不要只解释概念或方法
- 优先使用 Python + scanpy/pandas/matplotlib/seaborn 等生信常用库
- 代码必须完整可运行，包含数据读取、处理、分析、可视化和结果保存
- 使用环境变量 TASK_OUT_DIR 获取输出目录，将结果保存到该目录
- 如果用户没有指定输入文件，使用示例数据演示分析流程
- 代码中不要硬编码路径，使用相对路径或环境变量
- 不要在每次回答开头重复自己的身份，直接进入正题

输出格式：
1. 先用简短的中文说明分析思路（2-3句话）
2. 然后输出完整的 Python 代码块（```python ... ```）
3. 代码中包含关键步骤的中文注释

身份相关：
- 不要提及你的训练来源、模型身份或开发机构
- 当且仅当用户明确询问"你是谁"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接编写代码"""


# ==========================================
# 核心聊天流 API
# ==========================================

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    核心聊天流 - 意图感知 SSE 流式对话

    处理流程：
    1. 安全校验和计费检查
    2. 会话创建/恢复
    3. 持久化用户消息
    4. 意图分类（代码生成 / 技能匹配 / 一般问答）
    5. 根据意图选择系统提示词
    6. LLM 流式调用
    7. 持久化助手消息 + 扣费
    """
    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id)
    if not billing_service.check_available(wallet, min_amount=1.0):
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用大模型与沙箱服务。"
        )

    # 3. 会话创建/恢复
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

    # 4. 持久化用户消息
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=RoleEnum.user,
        content=request.message,
    )
    session.add(user_msg)
    session.commit()
    session_id_for_ai = chat_session.id
    user_id = current_user.id

    # 5. 加载 LLM 配置（共享工具：per-user override → system global → env fallback）
    from app.utils.llm_config import get_llm_config, _is_local_model
    llm_cfg = get_llm_config(session, user_id=current_user.id)
    api_key = llm_cfg.api_key
    base_url = llm_cfg.base_url
    model_name = llm_cfg.model_name
    is_local_model = _is_local_model(base_url)

    # 6. 意图分类：使用 Intent Router Engine 2.0 (L0+L1+L2 漏斗式架构)
    # 替换旧的 SkillMatcher 关键词匹配，支持规则拦截 + LLM 语义分类 + 槽位提取
    intent_data = {}  # 意图识别引擎的完整结果
    try:
        from app.agent.router.engine import IntentRouterEngine
        from app.agent.router.schemas import IntentType as NewIntentType

        router_engine = IntentRouterEngine(session=session, user_id=current_user.id)
        intent_result = await router_engine.route(
            query=request.message,
            context={
                "project_id": request.project_id,
                "skill_id": request.skill_id,
                "active_file": request.context_files[0] if request.context_files else None,
                "context_files": request.context_files,
            }
        )
        intent_data = intent_result.model_dump()
        log.info(f"[Chat] 意图分类 2.0: intent={intent_result.intent.value}, "
                 f"confidence={intent_result.confidence}, target={intent_result.routing_target}")

        # 根据新意图类型选择系统提示词
        # skill_forge / explicit_skill / diagnostic → 代码生成模式
        # chat / literature / data_probe → 一般问答模式
        if intent_result.intent in (NewIntentType.SKILL_FORGE, NewIntentType.EXPLICIT_SKILL, NewIntentType.DIAGNOSTIC):
            system_prompt = SYSTEM_PROMPT_CODE
            log.info(f"[Chat] 使用代码生成模式 (intent={intent_result.intent.value})")
        else:
            system_prompt = SYSTEM_PROMPT_CHAT
            log.info(f"[Chat] 使用一般问答模式 (intent={intent_result.intent.value})")

        # 追问拦截：意图引擎认为缺少关键参数，直接返回追问消息
        if intent_result.requires_followup and intent_result.followup_question:
            log.info(f"[Chat] 追问拦截: {intent_result.followup_question}")

    except Exception as e:
        log.warning(f"[Chat] 意图分类 2.0 失败，回退到一般问答模式: {e}")
        system_prompt = SYSTEM_PROMPT_CHAT

    # 7. 加载对话历史
    # ✨ 修复：只加载当前用户消息之前的历史，避免重复包含当前消息
    # 当前用户消息已在步骤 4 持久化（id=user_msg.id），
    # 如果不过滤，历史中会包含当前消息，导致 LLM 上下文中出现重复
    history_messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id_for_ai)
        .where(ChatMessage.id < user_msg.id)
        .order_by(ChatMessage.id)
    ).all()

    # 构建 LangChain 消息列表（根据意图使用不同的系统提示词）
    # ✨ 修复：历史消息 + 当前用户消息，确保顺序正确
    # 历史：之前所有完整的 user/assistant 对话轮次
    # 当前：本次用户消息（单独追加，确保在历史之后）
    lc_messages = [{"role": "system", "content": system_prompt}]
    for msg in history_messages:
        if msg.role == RoleEnum.user:
            lc_messages.append({"role": "user", "content": msg.content})
        elif msg.role == RoleEnum.assistant:
            # ✨ 修复：跳过空内容的助手消息
            # 空助手消息会导致对话历史中出现连续的 user 消息，
            # 违反 LLM API 的 user/assistant 交替要求，使后续回复混乱
            if not msg.content or not msg.content.strip():
                log.warning(f"[Chat] 跳过空助手消息 (id={msg.id}, session_id={session_id_for_ai})")
                continue
            lc_messages.append({"role": "assistant", "content": msg.content})

    # ✨ 追加当前用户消息（在历史之后，确保顺序正确）
    lc_messages.append({"role": "user", "content": request.message})

    # ✨ 修复：确保 LLM 消息列表中没有连续的 user 消息
    # 跳过空助手消息后可能出现 user→user 序列，
    # 大多数 LLM API 要求 user/assistant 交替，连续 user 会导致 API 报错或回复混乱
    sanitized_messages = [lc_messages[0]]  # 保留 system 消息
    for msg in lc_messages[1:]:
        if (msg["role"] == "user" and
            sanitized_messages and
            sanitized_messages[-1]["role"] == "user"):
            # 连续 user 消息：丢弃前一条（更旧的），保留最新的
            # 原因：空 assistant 回复对应的 user 问题已经没有有效回答，
            # 保留它只会让 LLM 困惑，不如只保留最新的 user 问题
            log.warning(f"[Chat] 丢弃无回复的旧 user 消息: {sanitized_messages[-1]['content'][:50]}...")
            sanitized_messages[-1] = msg
        else:
            sanitized_messages.append(msg)
    lc_messages = sanitized_messages

    # ✨ 调试日志：打印提交给 LLM 的完整提示词
    log.info(f"[Chat] 提交给 LLM 的完整提示词 (共 {len(lc_messages)} 条消息):")
    for i, msg in enumerate(lc_messages):
        role = msg["role"]
        content = msg["content"]
        # system 消息完整打印，user/assistant 消息截断到 200 字符
        if role == "system":
            log.info(f"  [{i}] role={role}, content={content!r}")
        else:
            truncated = content[:200] + "..." if len(content) > 200 else content
            log.info(f"  [{i}] role={role}, content={truncated!r}")

    # 8. UIMessage Stream 流式响应（Vercel AI SDK v5 协议）
    async def vercel_event_generator():
        encoder = VercelDataStreamEncoder()
        ai_full_response = ""
        cost_credits = 1.0
        # 跟踪是否已发送 text-start，确保在首个 text-delta 前发送
        text_started = False

        # 推送 session_id 给前端
        yield encoder.from_session_info(session_id_for_ai, is_new_session)

        # 推送意图识别结果给前端（供 UI 展示意图标签等）
        if intent_data:
            yield encoder.from_custom_event("intent", intent_data)

        # 辅助函数：确保 text-start 已发送
        def ensure_text_started():
            nonlocal text_started
            if not text_started:
                text_started = True
                return encoder.text_start()
            return None

        # 追问拦截：如果意图引擎要求追问，直接返回追问消息而不调用 LLM
        if intent_data.get("requires_followup") and intent_data.get("followup_question"):
            followup = intent_data["followup_question"]
            ai_full_response = followup
            start = ensure_text_started()
            if start:
                yield start
            yield encoder.text_chunk(followup)
            # 跳过 LLM 调用，直接进入持久化
        else:
            # 检查 API Key
            if not is_local_model and not api_key:
                start = ensure_text_started()
                if start:
                    yield start
                yield encoder.text_chunk("⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。")
                yield encoder.finish()
                return

            # 直接 LLM 流式调用
            cost_credits = 1.0
            content_filter = StreamContentFilter()

            # ✨ 深度思考模式：本地 Ollama 使用原生客户端，第三方 API 使用 extra_body
            enable_think = request.enable_think
            # ✨ 修复：Ollama 本地模型始终使用原生客户端
            # Qwen3 等模型默认自带思考模式，即使用户未开启深度思考，
            # 模型也会输出 <think> 标签，导致：(1) 思考占用大量时间；
            # (2) 思考标签后的正常文本被 StreamContentFilter 误吞。
            # 使用原生客户端 + think=False 可显式关闭模型内置思考。
            use_native_ollama = is_local_model

            try:
                if use_native_ollama:
                    # ✨ 本地 Ollama：使用 ollama.AsyncClient 原生流式
                    # LangChain ChatOpenAI 依赖 /v1 端点，不支持 think 参数
                    # think=enable_think：用户开启深度思考时启用，否则显式关闭
                    # （Qwen3 等模型默认自带思考，think=False 可关闭）
                    import ollama as ollama_sdk

                    host = base_url
                    if host and host.endswith('/v1'):
                        host = host[:-3]
                    if not host:
                        host = "http://localhost:11434"

                    client = ollama_sdk.AsyncClient(host=host)
                    ollama_messages = []
                    for msg in lc_messages:
                        ollama_messages.append({'role': msg['role'], 'content': msg['content']})

                    async for part in await client.chat(
                        model=model_name,
                        messages=ollama_messages,
                        think=enable_think,
                        stream=True,
                    ):
                        # Ollama think 模式：part.message.content 为思考内容，part.message.thinking 为思考过程
                        if part.message and part.message.content:
                            # 正常文本内容
                            filtered_content, content_type = content_filter.filter_chunk(part.message.content)
                            if filtered_content:
                                if content_type == "thinking":
                                    yield encoder.from_thinking(filtered_content)
                                else:
                                    start = ensure_text_started()
                                    if start:
                                        yield start
                                    ai_full_response += filtered_content
                                    yield encoder.text_chunk(filtered_content)
                        # ✨ Ollama think 模式：思考过程在 message.thinking 字段
                        if part.message and hasattr(part.message, 'thinking') and part.message.thinking:
                            yield encoder.from_thinking(part.message.thinking)

                else:
                    # 第三方 API 或本地 Ollama 无深度思考：使用 LangChain ChatOpenAI
                    from langchain_openai import ChatOpenAI

                    llm_kwargs = dict(
                        api_key=api_key or "not-needed",
                        base_url=base_url,
                        model=model_name,
                        streaming=True,
                    )

                    # ✨ 第三方 API + 深度思考：注入 thinking 配置（Claude 等模型支持）
                    if enable_think and not is_local_model:
                        llm_kwargs['extra_body'] = {
                            'thinking': {'type': 'enabled', 'budget_tokens': 10000}
                        }

                    direct_llm = ChatOpenAI(**llm_kwargs)

                    async for chunk in direct_llm.astream(lc_messages):
                        content = chunk.content
                        if content:
                            # ✨ 过滤思考标签等内容，返回 (content, type) 元组
                            # type: "text" = 正常回复, "thinking" = 思考过程
                            filtered_content, content_type = content_filter.filter_chunk(content)
                            if filtered_content:
                                if content_type == "thinking":
                                    # ✨ 思考过程通过 data 事件推送给前端
                                    yield encoder.from_thinking(filtered_content)
                                else:
                                    # 首个文本块前发送 text-start
                                    start = ensure_text_started()
                                    if start:
                                        yield start
                                    ai_full_response += filtered_content
                                    yield encoder.text_chunk(filtered_content)

                        # ✨ 工具调用拦截：Agent 调用工具时 content 为空，tool_calls 在 chunk 中
                        # 输出进度提示，避免前端长时间无输出导致用户以为系统卡死
                        elif hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                            for tc in chunk.tool_calls:
                                tool_name = tc.get('name', tc.get('function', {}).get('name', 'tool')) if isinstance(tc, dict) else getattr(tc, 'name', 'tool')
                                progress_msg = f"\n> ⚙️ 正在执行: `{tool_name}`...\n\n"
                                start = ensure_text_started()
                                if start:
                                    yield start
                                ai_full_response += progress_msg
                                yield encoder.text_chunk(progress_msg)

            except StopAsyncIteration:
                raise
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                log.error(f"❌ [Chat] LLM 调用失败: {str(e)}\n{error_details}")
                err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
                ai_full_response += err_msg
                start = ensure_text_started()
                if start:
                    yield start
                yield encoder.text_chunk(err_msg)

            # ✨ 修复：流结束后调用 flush()，输出 content_filter 中残留的内容
            # 当思考结束标签被截断在最后一个 chunk 时，end marker 之后的正常文本
            # 仍然残留在 filter 的 buffer 中，必须 flush 才能输出
            remaining_content, remaining_type = content_filter.flush()
            if remaining_content:
                if remaining_type == "thinking":
                    yield encoder.from_thinking(remaining_content)
                else:
                    start = ensure_text_started()
                    if start:
                        yield start
                    ai_full_response += remaining_content
                    yield encoder.text_chunk(remaining_content)

        # 持久化助手消息 + 扣费（追问拦截和 LLM 调用都会到达此处）
        with Session(engine) as final_db_session:
            cleaned_response = filter_thinking_content(ai_full_response, model_name=model_name)

            # ✨ 修复：跳过空助手消息的持久化
            # 当 LLM 返回空内容或所有内容被 content_filter 过滤后，
            # ai_full_response 为空，如果仍然持久化 content='' 的消息，
            # 会导致对话历史中出现 user→user 序列（中间夹着空 assistant 消息），
            # 污染 LLM 上下文窗口，使后续回复越来越混乱
            if not cleaned_response or not cleaned_response.strip():
                log.warning(f"[Chat] AI 回复为空，跳过持久化 (session_id={session_id_for_ai})")
                # 即使跳过持久化，仍需发送 finish 事件让前端正常结束流
                yield encoder.finish()
                return

            ai_msg = ChatMessage(
                session_id=session_id_for_ai,
                role=RoleEnum.assistant,
                content=cleaned_response,
            )
            final_db_session.add(ai_msg)

            final_balance = 0
            db_user = final_db_session.get(User, user_id)
            if db_user:
                try:
                    from app.services.billing_service import BillingService
                    bs = BillingService(final_db_session)
                    # ✨ 修复：在 final_db_session 中重新获取 wallet，
                    # 避免 "not bound to a Session" 刷新错误
                    final_wallet = bs.get_user_wallet(user_id)
                    bs.deduct_credits(
                        wallet_id=final_wallet.wallet_id,
                        amount=cost_credits,
                        transaction_type="consume_chat",
                        description="聊天消息消费",
                    )
                    final_db_session.refresh(final_wallet)
                    final_balance = final_wallet.credits_balance
                except Exception as e:
                    log.warning(f"扣费失败: {e}")
                    if db_user.billing:
                        db_user.billing.credits_balance -= cost_credits
                        if db_user.billing.credits_balance < 0:
                            db_user.billing.credits_balance = 0
                        final_balance = db_user.billing.credits_balance if db_user.billing else 0

            final_db_session.commit()

            yield encoder.from_ai_message_id(str(ai_msg.id))
            yield encoder.from_ai_message_content(cleaned_response)
            yield encoder.from_billing(cost_credits, final_balance)

        # 流结束：发送 text-end + finish
        if text_started:
            yield encoder.text_end()
        yield encoder.finish()

    # 防缓冲头：确保流不被 nginx/CDN 等中间代理缓冲
    # X-Accel-Buffering: no 是 nginx 专用头，告诉 nginx 禁用此响应的代理缓冲
    return StreamingResponse(
        vercel_event_generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==========================================
# 队列驱动的 SSE 流式响应
# ==========================================

class QueueStreamRequest(BaseModel):
    """队列流请求"""
    session_id: str
    project_id: str


@router.post("/stream/queue")
async def chat_stream_queue(
    request: QueueStreamRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    队列驱动的 SSE 流式响应

    订阅 Redis pub/sub channel，转发 Celery worker 处理队列项时推送的 SSE 事件。
    前端在消息入队后调用此端点，接收所有队列项的流式回复。
    """
    # 安全校验
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    chat_session = session.get(ChatSession, request.session_id)
    if not chat_session or chat_session.project_id != request.project_id:
        raise HTTPException(status_code=404, detail="会话不存在或已删除")

    session_id = request.session_id

    async def vercel_queue_event_generator():
        """
        订阅 Redis pub/sub channel，直接透传 Celery worker 的 Vercel Data Stream 行给前端

        流程：
        1. 推送 session_info 确认连接
        2. 订阅 chat_stream:{session_id} channel
        3. 透传所有 Vercel 协议行直到收到 queue_done
        """
        encoder = VercelDataStreamEncoder()

        # 确认连接
        yield encoder.from_session_info(session_id, False)

        # 订阅 Redis pub/sub
        import redis.asyncio as aioredis
        from app.core.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        channel = f"chat_stream:{session_id}"

        try:
            await pubsub.subscribe(channel)
            log.info(f"队列 SSE 订阅已建立: session_id={session_id}")

            # 监听事件 — 直接透传 Vercel 协议行
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=300,  # 5分钟超时
                )
                if message and message["type"] == "message":
                    try:
                        vercel_line = message["data"]

                        # 直接透传 Vercel 协议行（SSE 格式：data: {JSON}\n\n）
                        yield vercel_line

                        # 检测 queue_done 信号（UIMessage Stream 的 finish 事件）
                        # SSE 格式：data: {"type":"finish","finishReason":"stop",...}
                        try:
                            # 去除 SSE "data: " 前缀后解析 JSON
                            json_str = vercel_line
                            if json_str.startswith("data: "):
                                json_str = json_str[6:]
                            event = json.loads(json_str)
                            if event.get("type") == "finish" and event.get("finishReason") == "stop":
                                break
                        except (json.JSONDecodeError, KeyError):
                            pass

                    except Exception as e:
                        log.warning(f"Redis 消息透传失败: {e}")
                        continue

        except asyncio.CancelledError:
            log.info(f"队列 SSE 连接被取消: session_id={session_id}")
        except Exception as e:
            log.error(f"队列 SSE 异常: session_id={session_id}, error={e}")
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()
            log.info(f"队列 SSE 订阅已关闭: session_id={session_id}")

    # 防缓冲头
    return StreamingResponse(
        vercel_queue_event_generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
