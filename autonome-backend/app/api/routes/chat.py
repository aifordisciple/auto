"""
聊天 API - 核心聊天流

这是聊天模块的核心入口，处理 SSE 流式对话。

拆分说明：
- 会话管理 API → chat_session.py
- 消息收藏 API → chat_bookmark.py
- 会话标签 API → chat_tags.py
- 会话摘要 API → chat_summary.py
- 对话搜索 API → chat_search.py
- 深度解读 API → chat_interpret.py
- 经验提取 API → chat_experience.py
- 技能推荐服务 → services/chat_skill_recommendation.py
- PDF 处理服务 → services/pdf_processor.py
- 多模态消息构建 → services/multimodal_message_builder.py
- 沙箱重试处理器 → services/sandbox_retry_handler.py
- 任务复杂度分析 → services/task_complexity_analyzer.py
- 对话上下文服务 → services/conversation_context.py
- Pydantic 模型 → schemas/chat.py
"""

import os
import json
from http import HTTPStatus
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_session, engine
from app.models.domain import (
    ChatSession, ChatMessage, DataFile, SystemConfig, RoleEnum, Project, User,
    SkillAsset, SkillStatus
)
from app.agent.unified_executor import build_unified_agent
from app.agent.planning_coordinator import execute_planning
from app.core.logger import log
from app.api.deps import get_current_user
from app.services.experience_recommender import ExperienceRecommender
from app.services.intent_recognition import IntentRecognitionService, is_plotting_request, get_plotting_guidelines
from app.core.content_filter import filter_thinking_content

# ✨ 消息分类前置服务 - 判断是否需要技能推荐
from app.services.message_classifier import classify_message

# ✨ 导入拆分后的服务模块
from app.services.chat_skill_recommendation import (
    get_skill_recommendations_for_chat,
    format_skill_recommendations_for_agent
)
from app.services.conversation_context import load_conversation_history
from app.services.sandbox_retry_handler import SandboxRetryHandler
from app.services.task_complexity_analyzer import should_use_expert_committee
from app.services.pdf_processor import extract_pdf_content, build_pdf_context_message
from app.services.multimodal_message_builder import build_multimodal_message

# ✨ 导入 Pydantic 模型
from app.schemas.chat import ChatRequest


router = APIRouter()


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
    核心聊天流 - SSE 流式对话

    这是聊天模块的核心入口，处理：
    1. 安全校验和计费
    2. 会话管理
    3. 文件上下文构建
    4. 技能/经验推荐
    5. 多模态消息处理
    6. AI Agent 调用
    7. 流式响应
    """
    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截（使用 BillingService）
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)

    # 获取或创建钱包
    wallet = billing_service.get_user_wallet(current_user.id)

    # 检查余额是否充足（最低 1 CU）
    if not billing_service.check_available(wallet, min_amount=1.0):
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

    # ✨ 构建用户消息附件信息
    user_attachments = None
    if request.context_files or request.images or request.skill_id:
        user_attachments = {}
        if request.context_files:
            user_attachments["files"] = request.context_files
        if request.images:
            user_attachments["images"] = request.images
        if request.skill_id:
            skill = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == request.skill_id)
            ).first()
            if skill:
                user_attachments["skill"] = {
                    "skill_id": request.skill_id,
                    "name": skill.name
                }
            else:
                user_attachments["skill"] = {
                    "skill_id": request.skill_id,
                    "name": request.skill_id
                }

    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=RoleEnum.user,
        content=request.message,
        attachments=user_attachments
    )
    session.add(user_msg)
    session.commit()
    session_id_for_ai = chat_session.id
    user_msg_id = user_msg.id  # ✨ 保存消息 ID 避免后续访问 detached 对象

    user_id = current_user.id

    # ========================================================
    # 4. 扫描整个项目硬盘，构建【全景目录树】
    # ========================================================
    project_dir = os.path.join("uploads", f"project_{request.project_id}")
    global_file_tree = "当前项目文件目录树：\n"

    MAX_FILE_COUNT = 500
    MAX_CONTEXT_CHARS = 15000

    if os.path.exists(project_dir):
        file_count = 0
        total_chars = len(global_file_tree)
        truncated = False

        for root, dirs, files in os.walk(project_dir):
            if truncated:
                break
            for file in files:
                if file.startswith('.'):
                    continue
                if file_count >= MAX_FILE_COUNT:
                    truncated = True
                    break

                rel_path = os.path.relpath(os.path.join(root, file), project_dir)
                line = f"- {rel_path}\n"

                if total_chars + len(line) > MAX_CONTEXT_CHARS:
                    truncated = True
                    break

                global_file_tree += line
                total_chars += len(line)
                file_count += 1

        if truncated:
            total_files = sum(1 for _, _, f in os.walk(project_dir) for fi in f if not fi.startswith('.'))
            global_file_tree += f"\n... (文件列表已截断，共 {total_files} 个文件，仅显示前 {file_count} 个)\n"
            global_file_tree += "💡 提示：请使用 scan_workspace 工具查看完整目录结构\n"
    else:
        global_file_tree += "（当前项目为空）\n"

    # 5. 解析用户勾选的重点文件
    physical_file_info = ""
    pdf_results = []

    if request.context_files:
        for rel_path in request.context_files:
            if ".." not in rel_path:
                abs_path = os.path.abspath(os.path.join(project_dir, rel_path))
                sandbox_path = f"/workspace/project_{request.project_id}/{rel_path}"
                physical_file_info += f"- {rel_path} (沙箱绝对路径: {sandbox_path})\n"

                if rel_path.lower().endswith('.pdf'):
                    if os.path.exists(abs_path):
                        log.info(f"📄 [Chat] 检测到PDF文件: {rel_path}")
                        pdf_result = extract_pdf_content(abs_path)
                        pdf_results.append(pdf_result)
                    else:
                        log.warning(f"📄 [Chat] PDF文件不存在: {abs_path}")

    pdf_context = build_pdf_context_message(pdf_results) if pdf_results else ""
    if pdf_context:
        log.info(f"📄 [Chat] 已提取 {len(pdf_results)} 个PDF的内容")

    # 6. 动态加载 LLM 配置
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

        # ✨ V2: 统一单次路由 - 使用 router_node_logic 进行意图分类
        # 合并了原 IntentClassifier (3-type) 和 Router (7-type) 为单次调用
        from app.agent.nodes.router import router_node_logic

        router_messages = [{"role": "user", "content": request.message}]

        try:
            router_result = await router_node_logic(router_messages, physical_file_info)
            intent_obj = router_result.get("intent")
            intent_type = intent_obj.intent if intent_obj else "VAGUE_ANALYSIS"
            chat_subtype = getattr(intent_obj, 'chat_subtype', None) if intent_obj else None
            intent_confidence = intent_obj.confidence if intent_obj else 0.0
            intent_reason = intent_obj.reason if intent_obj else ""
        except Exception as router_err:
            log.warning(f"⚠️ [Chat] 路由器调用失败: {router_err}，默认 VAGUE_ANALYSIS")
            intent_type = "VAGUE_ANALYSIS"
            chat_subtype = None
            intent_confidence = 0.0
            intent_reason = "路由失败"
            router_result = {}

        # ✨ 发送意图检测事件
        yield {
            "event": "intent_detected",
            "data": json.dumps({
                "intent_type": intent_type,
                "confidence": intent_confidence,
                "reason": intent_reason,
                "chat_subtype": chat_subtype
            })
        }

        # ✨ CHAT 意图：根据 chat_subtype 分流
        if intent_type == "CHAT":
            # casual 子类型：硬编码快速响应
            if chat_subtype == "casual":
                casual_msg = router_result.get("messages", [])
                if casual_msg:
                    response_text = casual_msg[-1].content if hasattr(casual_msg[-1], 'content') else str(casual_msg[-1])
                else:
                    response_text = "你好！有什么我可以帮助你的吗？"
                log.info(f"💬 [Chat] 闲聊快速响应")
                yield {"event": "message", "data": json.dumps({"type": "text", "content": response_text})}
                yield {"event": "done", "data": json.dumps({})}
                yield {"event": "ai_message_content", "data": json.dumps({"content": response_text})}
                return

            # theory 子类型：轻量 LLM 流式回复
            log.info(f"💬 [Chat] 理论问答，使用主 LLM 直接回复")

            # ✨ 先发送一个提示消息
            yield {"event": "message", "data": json.dumps({"type": "text", "content": "💬 正在思考..."})}

            # 构建简单上下文（不扫描项目目录）
            theory_system_prompt = """你是一个友好的 AI 生物信息学助手。

回答原则：
1. 简洁友好，像和朋友聊天
2. 如果用户询问功能，可以简单介绍：数据分析、代码编写、SKILL 执行、可视化
3. 如果是感谢、问候等，保持轻松自然
4. 如果是理论问题（如什么是单细胞测序），用通俗易懂的方式解释

注意：不要生成任何代码或执行任何操作，只做文字回答。"""

            # ✨ 闲聊/理论使用主 LLM 直接流式回复
            from langchain_openai import ChatOpenAI
            direct_llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                temperature=0.7,
                streaming=True
            )

            try:
                log.info(f"💬 [Chat] 开始调用 LLM 生成闲聊回复...")

                # ✨ 简单直接的 thinking 标签过滤正则（兼容多种格式）
                import re
                # 匹配: <think>...</think> 或 <thinking>...</thinking> 或 <think>...</think>
                think_tag_pattern = re.compile(
                    r'<think>.*?</think>|《.*?》|<think[^>]*>.*?</think[^>]*>|<thinking>.*?</thinking>',
                    re.DOTALL | re.IGNORECASE
                )

                ai_response = ""
                async for chunk in direct_llm.astream([
                    {"role": "system", "content": theory_system_prompt},
                    {"role": "user", "content": request.message}
                ]):
                    # ✨ LangChain 的 AIMessageChunk 有 content 属性
                    raw_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    # ✨ 先用简单正则过滤 thinking 标签
                    filtered_content = think_tag_pattern.sub('', raw_content)
                    # ✨ 再用标准过滤器处理其他情况
                    content = filter_thinking_content(filtered_content, model_name=model_name, is_streaming=True)
                    if content:
                        ai_response += content
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}

                log.info(f"💬 [Chat] LLM 流式回复完成，长度: {len(ai_response)}")
                # ✨ 闲聊也需要发送 done 事件
                yield {"event": "done", "data": json.dumps({})}
                yield {"event": "ai_message_content", "data": json.dumps({"content": ai_response})}
                return

            except Exception as llm_err:
                log.warning(f"💬 [Chat] LLM 直接回复失败: {llm_err}，回退到硬编码响应")
                # ✨ 回退到硬编码响应（不需要再检查 is_casual_chat）
                casual_responses = {
                    "greeting": "你好！有什么我可以帮助你的吗？可以问我关于数据分析、代码编写、SKILL 执行等问题。",
                    "thanks": "不客气！还有什么需要帮忙的吗？",
                    "bye": "再见！有需要随时回来。",
                    "help": "我可以帮你：\n1. 分析生物数据\n2. 编写 Python/R 代码\n3. 执行 SKILL 工作流\n4. 生成可视化图表\n\n有什么具体需求吗？",
                    "default": "明白，请说。",
                }
                msg_lower = request.message.strip().lower()
                if any(kw in msg_lower for kw in ["你好", "hi", "hello", "嗨", "您好", "hey"]):
                    response_text = casual_responses["greeting"]
                elif any(kw in msg_lower for kw in ["谢谢", "thanks", "thx"]):
                    response_text = casual_responses["thanks"]
                elif any(kw in msg_lower for kw in ["再见", "bye", "拜拜"]):
                    response_text = casual_responses["bye"]
                elif any(kw in msg_lower for kw in ["帮忙", "help", "帮帮我", "请问", "question"]):
                    response_text = casual_responses["help"]
                else:
                    response_text = casual_responses["default"]

                yield {"event": "message", "data": json.dumps({"type": "text", "content": response_text})}
                yield {"event": "done", "data": json.dumps({})}
                yield {"event": "ai_message_content", "data": json.dumps({"content": response_text})}
                return

        ai_full_response = ""
        cost_credits = 1.0

        thinking_buffer = ""
        in_thinking = False

        try:
            log.info(f"🔧 [Chat] 构建 Agent - base_url={base_url}, model={model_name}")

            # 处理粘贴的图片路径
            image_abs_paths = []
            if request.images:
                docker_project_dir = f"/workspace/project_{request.project_id}"

                for img_rel_path in request.images:
                    if img_rel_path.startswith('/'):
                        img_abs_path = img_rel_path
                    elif img_rel_path.startswith('uploads/'):
                        img_abs_path = f"/app/{img_rel_path}"
                    else:
                        img_abs_path = os.path.join(docker_project_dir, img_rel_path)

                    if os.path.exists(img_abs_path):
                        image_abs_paths.append(img_abs_path)
                        log.info(f"🖼️ [Chat] 图片路径: {img_abs_path}")
                    else:
                        log.warning(f"⚠️ [Chat] 图片不存在: {img_abs_path}")

            has_images = bool(image_abs_paths)
            if has_images:
                log.info(f"🖼️ [Chat] 检测到 {len(image_abs_paths)} 张图片，使用多模态消息格式")

            # 视觉模型配置获取
            vision_config = None
            if has_images:
                use_shared = config.use_shared_vision_config if config else True

                if use_shared:
                    vision_config = {
                        "api_key": api_key,
                        "base_url": base_url,
                        "model": model_name
                    }
                    log.info(f"🖼️ [Chat] 视觉模型使用主模型配置: {model_name}")
                else:
                    vision_api_key = config.vision_api_key if config and config.vision_api_key else api_key
                    vision_base_url = config.vision_base_url if config and config.vision_base_url else base_url
                    vision_model = config.vision_model if config else "qwen3.5-plus"

                    vision_config = {
                        "api_key": vision_api_key,
                        "base_url": vision_base_url,
                        "model": vision_model
                    }
                    log.info(f"🖼️ [Chat] 使用独立视觉模型配置: {vision_model} @ {vision_base_url}")

            agent_executor = build_unified_agent(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                physical_file_info=physical_file_info,
                user_id=user_id,
                project_id=request.project_id,
                selected_skill_id=request.skill_id,
                vision_config=vision_config,
                task_mode=request.task_mode
            )

            log.info(f"💬 [Chat] 开始生成 - user_id={user_id}, message={request.message[:50]}...")

            # 加载历史对话上下文
            history = load_conversation_history(session_id_for_ai, session) if not is_new_session else []

            # 判断是否跳过推荐
            is_super_executor = request.task_mode == 'super_executor'
            is_interactive = request.task_mode == 'interactive'  # ✨ 交互式模式也跳过推荐

            # ========================================================
            # 消息分类前置判断 - 决定是否需要推荐（经验推荐 + 技能推荐）
            # ========================================================
            needs_recommendation = True  # 默认需要推荐

            if not is_super_executor and not is_interactive:
                try:
                    classification_result = await classify_message(request.message, session)
                    needs_recommendation = classification_result.get("needs_skill_recommendation", True)

                    log.info(f"📊 [Chat] 消息分类结果: needs_recommendation={needs_recommendation}, "
                            f"source={classification_result.get('classification_source')}, "
                            f"reason={classification_result.get('classification_reason')}")

                    # 如果分类确定不需要推荐，发送跳过事件
                    if not needs_recommendation:
                        yield {
                            "event": "recommendation_skipped",
                            "data": json.dumps({
                                "reason": classification_result.get("classification_reason"),
                                "classification_source": classification_result.get("classification_source")
                            })
                        }

                except Exception as class_err:
                    log.warning(f"📊 [Chat] 消息分类服务异常，默认启用推荐: {class_err}")
                    needs_recommendation = True

            # ✨ interactive 模式跳过推荐
            if is_interactive:
                log.info(f"🎨 [Chat] 交互式可视化模式，跳过消息分类和推荐")
                needs_recommendation = False

            # 智能经验推荐（只有需要推荐时才执行）
            experience_context = ""
            if not is_super_executor and not is_interactive and needs_recommendation:
                try:
                    recommender = ExperienceRecommender(session)
                    recommendations = await recommender.recommend(
                        user_query=request.message,
                        user_id=user_id,
                        top_k=3
                    )
                    if recommendations:
                        experience_context = recommender.format_for_agent(recommendations)
                        log.info(f"🧠 [Chat] 注入 {len(recommendations)} 条相关经验推荐")
                        yield {
                            "event": "experience_recommendations",
                            "data": json.dumps({
                                "count": len(recommendations),
                                "experiences": [
                                    {
                                        "title": r["title"],
                                        "similarity": r["similarity"],
                                        "category": r["category"]
                                    }
                                    for r in recommendations
                                ]
                            })
                        }
                except Exception as exp_err:
                    log.warning(f"经验推荐服务暂不可用: {exp_err}")

            # 智能技能推荐（只有需要推荐时才执行）
            skill_context = ""
            intent_result = None
            if not is_super_executor and not is_interactive and needs_recommendation:
                try:
                    intent_service = IntentRecognitionService(session)

                    llm_config_for_recommend = {
                        "api_key": api_key,
                        "base_url": base_url,
                        "model": "gpt-4o-mini"
                    } if api_key else None

                    skill_recommendations, llm_enhanced_result = await get_skill_recommendations_for_chat(
                        user_query=request.message,
                        session=session,
                        user_id=user_id,
                        limit=3,
                        llm_config=llm_config_for_recommend
                    )

                    if skill_recommendations:
                        skill_context = format_skill_recommendations_for_agent(skill_recommendations)
                        log.info(f"🎯 [Chat] 注入 {len(skill_recommendations)} 条技能推荐到 Agent 上下文")

                    # 优化：优先使用已有的 LLM 增强结果，避免重复调用
                    if llm_enhanced_result:
                        intent_result = llm_enhanced_result
                        log.info(f"🎯 [Chat] 使用已有的 LLM 增强结果: intent={intent_result.get('intent_type')}")
                    else:
                        # 仅在没有 LLM 增强结果时才调用 detect_intent
                        # 使用空列表，让 SkillMatcher 自己获取可用技能
                        intent_result = intent_service.detect_intent(request.message, [])

                    try:
                        intent_service.log_recommendation(
                            user_id=user_id,
                            session_id=session_id_for_ai,
                            query=request.message,
                            intent_result=intent_result
                        )
                    except Exception as log_err:
                        log.warning(f"记录推荐日志失败: {log_err}")

                except Exception as skill_err:
                    log.warning(f"技能推荐服务暂不可用: {skill_err}")
                    skill_recommendations = []

                # ✨ 分析任务：发送推荐选择卡片，让用户选择执行方式
                # 注意：这里不等待用户选择，继续执行 Agent（前端可以选择是否显示卡片）
                if skill_recommendations is None:
                    skill_recommendations = []

                # ✨ 发送推荐选择卡片事件
                recommendation_options = []

                # 添加技能推荐选项
                for skill_rec in skill_recommendations:
                    if hasattr(skill_rec, 'skill_id'):
                        recommendation_options.append({
                            "type": "skill",
                            "skill_id": skill_rec.skill_id,
                            "name": getattr(skill_rec, 'name', skill_rec.skill_id),
                            "description": getattr(skill_rec, 'description', ''),
                            "match_score": getattr(skill_rec, 'match_score', 0.0)
                        })
                    elif isinstance(skill_rec, dict):
                        recommendation_options.append({
                            "type": "skill",
                            "skill_id": skill_rec.get('skill_id', ''),
                            "name": skill_rec.get('name', skill_rec.get('skill_id', '')),
                            "description": skill_rec.get('description', ''),
                            "match_score": skill_rec.get('match_score', 0.0)
                        })

                # 添加 Live Coding 和直接分析选项
                recommendation_options.extend([
                    {
                        "type": "live_coding",
                        "name": "自定义代码",
                        "description": "使用 AI 生成自定义分析代码"
                    },
                    {
                        "type": "direct",
                        "name": "直接分析",
                        "description": "让 AI 直接分析，不使用预设技能"
                    }
                ])

                yield {
                    "event": "recommendation_card",
                    "data": json.dumps({
                        "message_id": str(user_msg_id) if 'user_msg_id' in dir() else "",
                        "title": "请选择执行方式",
                        "options": recommendation_options
                    })
                }

            # 出版级图表规范注入
            plotting_context = ""
            if not is_super_executor:
                try:
                    if is_plotting_request(request.message):
                        plotting_context = get_plotting_guidelines(request.message)
                        log.info(f"🎨 [Chat] 检测到画图请求，注入出版级图表规范")
                        yield {
                            "event": "plotting_guidelines",
                            "data": json.dumps({
                                "detected": True,
                                "message": "已注入出版级图表规范"
                            })
                        }
                except Exception as plot_err:
                    log.warning(f"画图规范注入失败: {plot_err}")

            # 探针预检测
            probe_context = ""
            if not is_super_executor:
                import re
                from app.tools.probe_tools import peek_tabular_data, scan_workspace

                file_pattern = r'/workspace/[^\s\]\)\}]+\.(csv|tsv|txt|h5ad|fastq|bam)'
                file_matches = re.findall(file_pattern, request.message)

                for file_path in file_matches[:2]:
                    if os.path.exists(file_path):
                        log.info(f"🔍 [Probe] 预探查文件: {file_path}")
                        try:
                            probe_result = peek_tabular_data.invoke({"file_path": file_path, "n_rows": 3})
                            probe_context += f"\n\n[文件预览: {file_path}]\n{probe_result}\n"
                        except Exception as probe_err:
                            log.warning(f"预探查文件失败: {probe_err}")

                if "扫描目录" in request.message or "查看目录" in request.message or "有哪些文件" in request.message:
                    dir_pattern = r'/workspace/[^\s\]\)\}]+'
                    dir_matches = re.findall(dir_pattern, request.message)
                    for dir_path in dir_matches[:1]:
                        if os.path.isdir(dir_path):
                            log.info(f"🔍 [Probe] 预扫描目录: {dir_path}")
                            try:
                                scan_result = scan_workspace.invoke({"directory_path": dir_path, "max_depth": 2})
                                probe_context += f"\n\n[目录结构: {dir_path}]\n{scan_result}\n"
                            except Exception as scan_err:
                                log.warning(f"预扫描目录失败: {scan_err}")

                if probe_context:
                    log.info(f"🔍 [Probe] 已注入预探查结果，跳过 Agent 工具调用")

            # 构建消息
            context_parts = []
            if plotting_context:
                context_parts.append(plotting_context)
            if skill_context:
                context_parts.append(skill_context)
            if experience_context:
                context_parts.append(experience_context)

            if probe_context:
                enhanced_message = probe_context + f"\n\n---\n\n用户问题: {request.message}"
                if has_images or pdf_context:
                    user_message = build_multimodal_message(enhanced_message, image_abs_paths, pdf_context)
                    messages = history + [user_message]
                else:
                    messages = history + [{"role": "user", "content": enhanced_message}]
            elif context_parts:
                enhanced_message = "\n\n".join(context_parts) + f"\n\n---\n\n用户问题: {request.message}"
                if has_images or pdf_context:
                    user_message = build_multimodal_message(
                        enhanced_message,
                        image_abs_paths,
                        pdf_context
                    )
                    messages = history + [user_message]
                else:
                    messages = history + [{"role": "user", "content": enhanced_message}]
            elif has_images or pdf_context:
                user_message = build_multimodal_message(
                    request.message,
                    image_abs_paths,
                    pdf_context
                )
                messages = history + [user_message]
            else:
                messages = history + [{"role": "user", "content": request.message}]

            log.info(f"📤 [向 AI 发送请求]: 历史消息 {len(history)} 条 + 当前消息 1 条")
            if history:
                log.info(f"📜 [对话上下文]: 最近 {len(history)} 条历史消息已加载")

            # ✨ 超级执行者模式已整合到 unified_executor
            # VAGUE_ANALYSIS 和 PIPELINE_BUILD 意图会自动路由到 super_executor_node

            # 专家委员会模式
            use_expert_committee_mode = should_use_expert_committee(request.message, request.task_mode)

            if use_expert_committee_mode:
                log.info(f"🧠 [Chat] 启动专家委员会模式")

                yield {
                    "event": "expert_committee_start",
                    "data": json.dumps({
                        "message": "正在启动专家委员会进行复杂任务规划...",
                        "mode": "full_parallel"
                    })
                }

                try:
                    llm_config_for_planning = {
                        "api_key": api_key,
                        "base_url": base_url,
                        "model_name": model_name
                    }

                    from app.core.skill_parser import get_combined_skills
                    available_skills = get_combined_skills(user_id)
                    skills_md = "\n".join([f"- {s.get('skill_id', s.get('name', 'unknown'))}" for s in available_skills[:10]])

                    planning_result = await execute_planning(
                        user_request=request.message,
                        llm_config=llm_config_for_planning,
                        project_id=request.project_id,
                        project_context=global_file_tree,
                        available_skills=skills_md,
                        force_mode=None
                    )

                    log.info(f"🧠 [Chat] 专家委员会规划完成: {planning_result.get('status')}")

                    yield {
                        "event": "expert_committee_result",
                        "data": json.dumps({
                            "status": planning_result.get("status"),
                            "mode": planning_result.get("metadata", {}).get("planning_mode"),
                            "expert_sources": planning_result.get("metadata", {}).get("expert_sources", []),
                            "planning_time_ms": planning_result.get("metadata", {}).get("planning_time_ms")
                        })
                    }

                    blueprint = planning_result.get("blueprint")
                    if blueprint and planning_result.get("status") in ["success", "success_with_degradation"]:
                        blueprint_md = "```json_blueprint\n" + json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n```"
                        ai_full_response = f"\n\n> 🧠 **专家委员会规划完成**\n\n{blueprint_md}"

                        yield {"event": "message", "data": json.dumps({"type": "text", "content": ai_full_response})}

                        if blueprint.get("is_complex_task") and blueprint.get("tasks"):
                            log.info(f"📋 [Chat] 专家委员会蓝图已生成，等待用户确认执行")

                            yield {
                                "event": "blueprint_detected",
                                "data": json.dumps({
                                    "project_goal": blueprint.get("project_goal", ""),
                                    "task_count": len(blueprint.get("tasks", [])),
                                    "expert_committee": True,
                                    "blueprint": blueprint
                                })
                            }

                        yield {"event": "done", "data": "[DONE]"}
                        return

                    else:
                        log.warning(f"⚠️ [Chat] 专家委员会未能生成有效蓝图，回退到单 Agent 模式")
                        yield {
                            "event": "message",
                            "data": json.dumps({"type": "text", "content": "\n\n> ⚠️ 专家委员会规划未能完成，回退到标准模式...\n\n"})
                        }

                except Exception as expert_error:
                    log.error(f"❌ [Chat] 专家委员会执行失败: {expert_error}")
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "text", "content": f"\n\n> ⚠️ 专家委员会执行失败，回退到标准模式: {str(expert_error)}\n\n"})
                    }

            log.info("📡 正在等待 Agent 流式事件响应...")

            # ✨ V2: 意图已在顶部统一路由，直接使用 intent_type 分流
            resolved_intent_type = intent_type
            log.info(f"🎯 [Chat] 最终意图: {resolved_intent_type}")

            # ✨ 根据意图类型分流处理
            # explicit_skill 意图：推荐卡片已经在前面发送了，这里只需要等待用户确认
            if resolved_intent_type == "explicit_skill":
                log.info(f"🎯 [Chat] explicit_skill 意图，推荐卡片已发送，等待用户确认")
                yield {"event": "done", "data": "[DONE]"}
                return

            # V2: PIPELINE_BUILD 已合并到 VAGUE_ANALYSIS，不再单独判断
            if resolved_intent_type == "VAGUE_ANALYSIS":
                log.info(f"🚀 [Chat] 启动超级执行者 V4，意图类型: {resolved_intent_type}")

                try:
                    from app.agent.super_executor_v4 import SuperExecutorV4
                    # 从 messages 中提取用户消息内容
                    last_msg = messages[-1] if messages else {}
                    if isinstance(last_msg, dict):
                        raw_input_text = last_msg.get("content", "")
                    else:
                        raw_input_text = getattr(last_msg, 'content', "")
                    executor = SuperExecutorV4(
                        raw_input=raw_input_text,
                        project_id=str(request.project_id),
                        user_id=user_id,
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name
                    )

                    async for event in executor.run():
                        event_type = event.get("event", "")
                        event_data = event.get("data", {})

                        if event_type == "message":
                            # event_data 可能是 dict 或 string
                            if isinstance(event_data, str):
                                content = json.loads(event_data).get("content", "")
                            else:
                                content = event_data.get("content", "")
                            if content:
                                ai_full_response += content
                                yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}
                        elif event_type == "status_update":
                            yield {"event": "status", "data": json.dumps(event_data)}
                        elif event_type == "phase_change":
                            yield {"event": "phase_change", "data": json.dumps(event_data)}
                        elif event_type == "error":
                            error_msg = event_data.get("error", "Unknown error") if isinstance(event_data, dict) else str(event_data)
                            yield {"event": "error", "data": json.dumps({"error": error_msg})}

                    yield {"event": "done", "data": "[DONE]"}
                    return

                except Exception as super_err:
                    log.error(f"❌ [Chat] 超级执行者错误: {super_err}")
                    yield {"event": "error", "data": json.dumps({"error": str(super_err)})}
                    yield {"event": "done", "data": "[DONE]"}
                    return

            # ✨ 其他意图类型走 LangGraph Agent 工作流
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

                    if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                        log.warning(f"⚠️ [AI 生成了隐藏的工具调用]: {chunk.tool_calls}")

                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if isinstance(content, str) and content:
                        # log.info(f"📥 [AI 字符流]: {repr(content[:100])}")

                        THINK_OPEN_TAG = chr(60) + "think" + chr(62)
                        THINK_CLOSE_TAG = chr(60) + "/think" + chr(62)

                        if THINK_OPEN_TAG in content or in_thinking:
                            thinking_buffer += content
                            in_thinking = True

                            if THINK_CLOSE_TAG in thinking_buffer:
                                filtered_content = filter_thinking_content(thinking_buffer, model_name=model_name, is_streaming=True)
                                if filtered_content:
                                    ai_full_response += filtered_content
                                    yield {"event": "message", "data": json.dumps({"type": "text", "content": filtered_content})}
                                thinking_buffer = ""
                                in_thinking = False
                        else:
                            filtered_content = filter_thinking_content(content, model_name=model_name, is_streaming=True)
                            if filtered_content:
                                ai_full_response += filtered_content
                                yield {"event": "message", "data": json.dumps({"type": "text", "content": filtered_content})}

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
                        msg = f"\n\n*(🔄 Agent 正在调用工具: {tool_name})*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    output_raw = event.get("data", {}).get("output", "")

                    if hasattr(output_raw, 'content'):
                        output = output_raw.content if output_raw.content else ""
                    elif isinstance(output_raw, str):
                        output = output_raw
                    else:
                        output = str(output_raw) if output_raw else ""

                    if tool_name in ["execute_python_code"]:
                        is_failed = SandboxRetryHandler.is_execution_failed(output)

                        if is_failed:
                            error_msg = SandboxRetryHandler.extract_error_message(output)
                            log.warning(f"⚠️ [Sandbox] 执行失败: {error_msg[:200]}")

                            msg = f"\n\n> 🔴 *(沙箱执行失败，Agent 正在分析错误并尝试修复...)*\n\n"
                            ai_full_response += msg
                            yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                            yield {
                                "event": "sandbox_error",
                                "data": json.dumps({
                                    "type": "execution_error",
                                    "error_preview": error_msg[:500],
                                    "retry_hint": "Agent 将自动尝试修复代码"
                                })
                            }
                        else:
                            msg = f"\n\n> ✅ *(沙箱代码执行成功，产物已落盘)*\n\n"
                            ai_full_response += msg
                            yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                            yield {
                                "event": "sandbox_success",
                                "data": json.dumps({
                                    "type": "execution_success",
                                    "output_preview": output[:200] if output else ""
                                })
                            }
                    elif tool_name == "peek_tabular_data":
                        msg = f"\n\n> ✅ *(探针返回：表格结构已解析)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}
                    elif tool_name == "scan_workspace":
                        msg = f"\n\n> ✅ *(探针返回：目录结构已扫描)*\n\n"
                        ai_full_response += msg
                        yield {"event": "message", "data": json.dumps({"type": "text", "content": msg})}

                elif kind == "on_node":
                    # ✨ 处理统一执行器节点返回的消息（如闲聊响应）
                    node_name = event.get("name", "")
                    if node_name == "unified":
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict) and "messages" in output:
                            for msg in output["messages"]:
                                if hasattr(msg, 'content') and msg.content:
                                    content = msg.content
                                    ai_full_response += content
                                    yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}

            if thinking_buffer:
                filtered_content = filter_thinking_content(thinking_buffer, is_streaming=True)
                if filtered_content:
                    ai_full_response += filtered_content
                    yield {"event": "message", "data": json.dumps({"type": "text", "content": filtered_content})}
                thinking_buffer = ""
                in_thinking = False

            log.info(f"✅ [AI 完整输出结果]:\n{ai_full_response if ai_full_response else '<空>'}")

            if "```json_blueprint" in ai_full_response or '"is_complex_task": true' in ai_full_response:
                from app.services.orchestrator import extract_blueprint

                blueprint = extract_blueprint(ai_full_response)

                if blueprint and blueprint.get("is_complex_task"):
                    log.info(f"📋 [Chat] 检测到复杂任务蓝图，等待用户确认执行")

                    yield {
                        "event": "blueprint_detected",
                        "data": json.dumps({
                            "project_goal": blueprint.get("project_goal", ""),
                            "task_count": len(blueprint.get("tasks", [])),
                            "blueprint": blueprint
                        })
                    }

        except StopAsyncIteration:
            # ✨ 异步生成器正常结束（通过 return 触发），不是错误
            raise
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Chat] 致命错误: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
            ai_full_response += err_msg
            yield {"event": "message", "data": json.dumps({"type": "text", "content": err_msg})}

        finally:
            with Session(engine) as final_db_session:
                cleaned_response = filter_thinking_content(ai_full_response, model_name=model_name)
                ai_msg = ChatMessage(session_id=session_id_for_ai, role=RoleEnum.assistant, content=cleaned_response)
                final_db_session.add(ai_msg)

                db_user = final_db_session.get(User, user_id)
                if db_user:
                    try:
                        from app.services.billing_service import BillingService
                        bs = BillingService(final_db_session)
                        bs.deduct_credits(
                            wallet_id=wallet.wallet_id,
                            amount=cost_credits,
                            transaction_type="consume_chat",
                            description=f"聊天消息消费",
                        )
                        final_db_session.refresh(wallet)
                        final_balance = wallet.credits_balance
                    except Exception as e:
                        log.warning(f"扣费失败: {e}")
                        if db_user.billing:
                            db_user.billing.credits_balance -= cost_credits
                            if db_user.billing.credits_balance < 0:
                                db_user.billing.credits_balance = 0
                        final_balance = db_user.billing.credits_balance if db_user.billing else 0
                else:
                    final_balance = 0

                final_db_session.commit()

                yield {"event": "ai_message_id", "data": json.dumps({"message_id": ai_msg.id})}

                newline_count = cleaned_response.count('\n')
                log.info(f"📤 [ai_message_content] 发送内容长度: {len(cleaned_response)}, 换行符数量: {newline_count}")
                log.info(f"📤 [ai_message_content] 内容预览:\n{repr(cleaned_response[:50000])}")
                yield {"event": "ai_message_content", "data": json.dumps({"content": cleaned_response})}

                yield {"event": "billing", "data": json.dumps({"cost": cost_credits, "balance": final_balance})}

            # ==========================================
            # 自动技能草稿生成（后台异步执行，不阻塞用户）
            # ==========================================
            try:
                import asyncio
                from app.services.auto_skill_draft_service import async_check_and_create_draft

                # 在后台触发技能草稿检查
                async def trigger_draft_check():
                    with Session(engine) as draft_session:
                        try:
                            draft = await async_check_and_create_draft(
                                db=draft_session,
                                session_id=str(session_id_for_ai),
                                user_id=user_id,
                                project_id=request.project_id,
                                execution_time=None,  # TODO: 可以从沙箱执行中获取
                                has_output_files=False  # TODO: 可以从沙箱结果中判断
                            )
                            if draft:
                                log.info(f"🎯 [AutoDraft] 已自动生成技能草稿 ID={draft.id}")
                        except Exception as draft_err:
                            log.warning(f"自动技能草稿生成失败: {draft_err}")

                # 创建后台任务（不等待完成）
                asyncio.create_task(trigger_draft_check())
                log.info(f"🔄 [AutoDraft] 已触发后台技能草稿检查: session={session_id_for_ai}")

            except Exception as bg_err:
                log.warning(f"后台任务创建失败: {bg_err}")

            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())