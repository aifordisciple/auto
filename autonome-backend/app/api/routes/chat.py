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
import os
import asyncio
from pathlib import Path
from http import HTTPStatus
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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

# 数据探查模式：使用探针工具感知数据环境
# ✨ 使用模板格式，运行时注入项目工作区路径，确保 scan_workspace 只扫描当前项目目录
SYSTEM_PROMPT_DATA_PROBE_TEMPLATE = """你是一个专业的生物信息学数据探查助手，名为 Autonome。你的核心职责是帮助用户了解数据环境和文件结构。

核心原则：
- 用中文回答问题
- 你拥有探针工具（scan_workspace, peek_tabular_data, inspect_h5ad, inspect_fastq, inspect_bam），必须主动调用这些工具来获取信息，而不是凭猜测回答
- 当用户询问"有哪些文件"、"目录结构"时，调用 scan_workspace 扫描工作区
- ⚠️ 重要：scan_workspace 的 directory_path 参数必须使用当前项目的工作区路径，不要扫描其他项目或根目录
- 当用户询问数据结构、预览数据时，调用对应的探针工具
- 工具调用后，用中文整理和解读结果，提供专业建议
- 不要在回答开头重复自己的身份，直接进入正题

当前项目工作区路径：{workspace_path}

身份相关：
- 不要提及你的训练来源、模型身份或开发机构
- 当且仅当用户明确询问"你是谁"时，简洁回答"我是 Autonome 生物信息学AI助手"
- 其他任何情况下，不要提及身份，直接使用工具回答用户的问题"""

# 视觉微调模式：SCI 级图表输出约束
SYSTEM_PROMPT_VISUAL = """你是一个专业的生物信息学可视化助手，名为 Autonome。你的核心职责是帮助用户调整和优化科研图表。

核心输出协议 (SCI Protocol)：
1. 【视觉专业性】：应用专业配色方案（如 ggsci 的 npg/jco/lancet），分辨率至少 300 DPI
2. 【双格式输出】：同步生成 .pdf（矢量编辑）和 .png（网页预览）
3. 【数据对称性（最高红线）】：严禁仅输出图像！必须同步产出底层坐标/阈值 .tsv 数据文件

核心原则：
- 用中文回答问题
- 不启动全量计算型沙箱，仅重载视图配置或执行轻量级绘图环境
- 直接进入正题，不要自我介绍"""

# 工作流编排模式：Nextflow 流程设计
SYSTEM_PROMPT_ORCHESTRATE = """你是一个专业的生物信息学流程编排助手，名为 Autonome。你的核心职责是帮助用户设计和生成 Nextflow 分析流程。

核心原则：
- 用中文解释设计思路
- 生成的 Nextflow 代码必须包含完整的 processes、channels 和 workflow 定义
- 通过多轮对话确认通道（Channels）和进程（Processes）
- 仅负责"调度"和"串联"，不负责单一脚本的具体实现
- 直接进入正题，不要自我介绍"""


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
    # DEBUG: 临时排查 403 问题
    from loguru import logger
    logger.warning(f"[DEBUG 403] project_id={request.project_id}, user_id={current_user.id}")
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        logger.error(f"[DEBUG 403] project={'None' if not project else project.id}, owner_id={'None' if not project else project.owner_id}, user_id={current_user.id}")
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
    # ✨ 保存附件信息（图片路径、粘贴文件路径），用于历史消息重建
    user_attachments = None
    if request.images or request.pasted_files:
        user_attachments = {}
        if request.images:
            user_attachments["images"] = request.images
        if request.pasted_files:
            user_attachments["pastedFiles"] = request.pasted_files
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=RoleEnum.user,
        content=request.message,
        attachments=user_attachments,
    )
    session.add(user_msg)
    session.commit()
    session_id_for_ai = chat_session.id
    user_id = current_user.id

    # 5. 加载 LLM 配置（共享工具：per-user override → system global → env fallback）
    # 根据深度思考模式选择模型：开启思考 → 思考模型；关闭思考 → 极速模型
    from app.utils.llm_config import get_thinking_llm_config, get_fast_llm_config, _is_local_model, _is_ollama
    if request.enable_think:
        llm_cfg = get_thinking_llm_config(session, user_id=current_user.id)
    else:
        llm_cfg = get_fast_llm_config(session, user_id=current_user.id)
    api_key = llm_cfg.api_key
    base_url = llm_cfg.base_url
    model_name = llm_cfg.model_name
    is_local_model = _is_local_model(base_url)
    is_ollama_service = _is_ollama(base_url)

    # 6. 意图分类：使用 Intent Router Engine 2.0 (L0+L1+L2 漏斗式架构)
    # 替换旧的 SkillMatcher 关键词匹配，支持规则拦截 + LLM 语义分类 + 槽位提取
    # V2.0 升级：route() 返回 RouteResult(dag=TaskDAG, probing=Optional[ProbingRequest])
    intent_data = {}  # 意图识别引擎的完整结果（序列化后的 DAG + probing）
    route_result = None  # RouteResult 原始对象，供后续 Active Probing 逻辑使用
    try:
        from app.agent.router.engine import IntentRouterEngine
        from app.agent.router.schemas import IntentType as NewIntentType

        router_engine = IntentRouterEngine(session=session, user_id=current_user.id)
        route_result = await router_engine.route(
            query=request.message,
            context={
                "project_id": request.project_id,
                "skill_id": request.skill_id,
                "active_file": request.context_files[0] if request.context_files else None,
                "context_files": request.context_files,
            }
        )
        intent_data = route_result.dag.model_dump()
        # 提取首个任务的意图信息（兼容下游 SSE 流逻辑）
        first_intent = route_result.dag.nodes[0].intent if route_result.dag.nodes else NewIntentType.GENERAL_CHAT
        log.info(f"[Chat] 意图分类 2.0: intent={first_intent.value}, "
                 f"nodes={len(route_result.dag.nodes)}, probing={route_result.probing is not None}")

        # 根据新意图类型选择系统提示词 (V2.0 12 原子意图映射)
        # skill_forge / explicit_exec / diagnostic_recovery → 代码生成模式
        # data_probe → 数据探查模式（绑定探针工具）
        # visual_perception_and_tweak → 视觉微调模式
        # workflow_orchestrate → 工作流编排模式
        # chat / literature_mining / 其他 → 一般问答模式
        if first_intent in (
            NewIntentType.SKILL_FORGE,
            NewIntentType.EXPLICIT_EXEC,
            NewIntentType.DIAGNOSTIC_RECOVERY,
        ):
            system_prompt = SYSTEM_PROMPT_CODE
            log.info(f"[Chat] 使用代码生成模式 (intent={first_intent.value})")
        elif first_intent == NewIntentType.DATA_PROBE:
            # ✨ 注入当前项目的工作区路径，确保 scan_workspace 只扫描当前项目
            from app.core.config import settings
            project_workspace = str(Path(settings.UPLOAD_DIR) / f"project_{request.project_id}")
            system_prompt = SYSTEM_PROMPT_DATA_PROBE_TEMPLATE.format(workspace_path=project_workspace)
            log.info(f"[Chat] 使用数据探查模式 (intent={first_intent.value}, workspace={project_workspace})")
        elif first_intent == NewIntentType.VISUAL_PERCEPTION_AND_TWEAK:
            system_prompt = SYSTEM_PROMPT_VISUAL
            log.info(f"[Chat] 使用视觉微调模式 (intent={first_intent.value})")
        elif first_intent == NewIntentType.WORKFLOW_ORCHESTRATE:
            system_prompt = SYSTEM_PROMPT_ORCHESTRATE
            log.info(f"[Chat] 使用工作流编排模式 (intent={first_intent.value})")
        else:
            system_prompt = SYSTEM_PROMPT_CHAT
            log.info(f"[Chat] 使用一般问答模式 (intent={first_intent.value})")

        # Active Probing：参数缺失时通过 SSE 流发送 ToolCall 事件
        # 实际发送逻辑在 vercel_event_generator() 中，此处仅做标记
        if route_result.probing and route_result.probing.is_missing:
            log.info(f"[Chat] Active Probing: 缺失参数={route_result.probing.missing_params}, "
                     f"追问={route_result.probing.message_to_user}")

    except Exception as e:
        log.warning(f"[Chat] 意图分类 2.0 失败，回退到一般问答模式: {e}")
        system_prompt = SYSTEM_PROMPT_CHAT

    # 7. 加载对话历史
    # ✨ 修复：使用 created_at 而非 id 做过滤和排序
    # 消息 ID 格式为 msg_{uuid}，UUID 的字典序与时间序无关，
    # 字符串比较会导致大量历史消息被错误排除
    # 使用 created_at 时间戳确保按真实时间顺序加载历史
    history_messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id_for_ai)
        .where(ChatMessage.created_at < user_msg.created_at)
        .order_by(ChatMessage.created_at)
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
            # ✨ 修复：空助手消息不跳过，而是插入占位消息
            # 跳过会导致连续 user 消息，LLM API 要求 user/assistant 交替
            # 插入占位消息保持交替结构，确保追问场景中每条 user 消息独立
            # 新消息作为 current message，历史消息明确作为上下文供 AI 理解
            if not msg.content or not msg.content.strip():
                log.warning(f"[Chat] 空助手消息插入占位 (id={msg.id}, session_id={session_id_for_ai})")
                lc_messages.append({"role": "assistant", "content": "（此回复为空）"})
            else:
                lc_messages.append({"role": "assistant", "content": msg.content})

    # ✨ 追加当前用户消息（在历史之后，确保顺序正确）
    # ✨ 支持多模态：图片消息包含 images 字段（Ollama）或 image_url blocks（LangChain）
    current_user_msg = {"role": "user", "content": request.message}
    # 图片路径列表（服务器路径，如 raw_data/.pasted/image.png）
    # 这些路径会在 Ollama 消息构建时转为 images 字段
    current_image_paths = request.images or []
    lc_messages.append(current_user_msg)

    # ✨ PDF 内容注入：提取粘贴的 PDF 文件文本，追加到用户消息后
    pdf_context_text = ""
    if request.pasted_files:
        try:
            from app.services.pdf_processor import extract_pdf_content, build_pdf_context_message
            pdf_results = []
            for pdf_path in request.pasted_files:
                # 将相对路径转为绝对路径（项目工作区路径）
                abs_path = pdf_path
                if not os.path.isabs(pdf_path):
                    # 项目目录格式：UPLOAD_DIR/project_{project_id}
                    from app.core.config import settings as pdf_settings
                    project_dir = str(Path(pdf_settings.UPLOAD_DIR) / f"project_{request.project_id}")
                    abs_path = f"{project_dir}/{pdf_path}"
                result = extract_pdf_content(abs_path)
                pdf_results.append(result)
                log.info(f"[Chat] PDF 提取完成: {abs_path}, {result['char_count']} 字符")
            pdf_context_text = build_pdf_context_message(pdf_results)
        except Exception as e:
            log.warning(f"[Chat] PDF 内容提取失败: {e}")
    # 如果有 PDF 上下文，作为额外的 user 消息注入
    if pdf_context_text:
        lc_messages.append({"role": "user", "content": pdf_context_text})
        lc_messages.append({"role": "assistant", "content": "好的，我已经阅读了您上传的PDF文档内容，请继续提问。"})

    # ✨ 附件文件内容注入：读取 context_files 的文件内容，追加到用户消息后
    # 当用户通过"添加附件"选择项目文件时，AI 需要看到文件内容才能回答相关问题
    # 根据文件扩展名选择不同的读取策略，复用已有的探针工具和处理器
    if request.context_files:
        try:
            from app.core.config import settings as cf_settings
            project_dir = str(Path(cf_settings.UPLOAD_DIR) / f"project_{request.project_id}")
            file_context_parts = []
            for file_path in request.context_files:
                # 将相对路径转为绝对路径（项目工作区路径）
                abs_path = file_path if os.path.isabs(file_path) else f"{project_dir}/{file_path}"
                if not os.path.exists(abs_path):
                    file_context_parts.append(f"## 文件: {file_path}\n[文件不存在]")
                    continue

                # 根据文件扩展名选择读取策略
                ext = os.path.splitext(abs_path)[1].lower()

                if ext in ('.csv', '.tsv', '.txt', '.tab'):
                    # 表格文件：使用探针工具预览表头和前几行
                    from app.tools.probe_tools import peek_tabular_data
                    preview = peek_tabular_data(abs_path, n_rows=5)
                    file_context_parts.append(f"## 文件: {file_path}\n{preview}")

                elif ext == '.h5ad':
                    # AnnData 文件：使用探针工具读取结构信息
                    from app.tools.probe_tools import inspect_h5ad
                    info = inspect_h5ad(abs_path)
                    file_context_parts.append(f"## 文件: {file_path}\n{info}")

                elif ext in ('.py', '.r', '.sh', '.json', '.yaml', '.yml', '.md',
                             '.log', '.nf', '.conf', '.cfg', '.ini', '.toml',
                             '.tex', '.html', '.css', '.js', '.ts', '.sql'):
                    # 文本文件：直接读取内容（限制 100KB 避免过长）
                    max_size = 100 * 1024  # 100KB
                    file_size = os.path.getsize(abs_path)
                    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(max_size)
                    if file_size > max_size:
                        file_context_parts.append(
                            f"## 文件: {file_path} ({file_size} 字节，截断显示前 100KB)\n```\n{content}\n... (截断)\n```"
                        )
                    else:
                        file_context_parts.append(f"## 文件: {file_path}\n```\n{content}\n```")

                elif ext == '.pdf':
                    # PDF 文件：使用已有的 PDF 处理器提取文本
                    from app.services.pdf_processor import extract_pdf_content
                    result = extract_pdf_content(abs_path)
                    text = result.get('text', '[PDF 内容提取失败]')[:5000]
                    file_context_parts.append(f"## 文件: {file_path}\n{text}")

                elif ext in ('.fastq', '.fq'):
                    # FASTQ 文件：使用探针工具预览
                    from app.tools.probe_tools import inspect_fastq
                    info = inspect_fastq(abs_path)
                    file_context_parts.append(f"## 文件: {file_path}\n{info}")

                elif ext in ('.bam', '.sam'):
                    # BAM/SAM 文件：使用探针工具预览
                    from app.tools.probe_tools import inspect_bam
                    info = inspect_bam(abs_path)
                    file_context_parts.append(f"## 文件: {file_path}\n{info}")

                else:
                    # 其他文件类型：仅告知文件存在和大小
                    file_size = os.path.getsize(abs_path)
                    file_context_parts.append(
                        f"## 文件: {file_path} (类型: {ext}, 大小: {file_size} 字节)\n[此文件类型暂不支持内容预览]"
                    )

            # 将所有文件内容作为额外的 user 消息注入
            if file_context_parts:
                file_context_text = "\n\n".join(file_context_parts)
                lc_messages.append({"role": "user", "content": f"以下是我附加的文件内容：\n\n{file_context_text}"})
                lc_messages.append({"role": "assistant", "content": "好的，我已经阅读了您附加的文件内容，请继续提问。"})
                log.info(f"[Chat] 注入 {len(file_context_parts)} 个附件文件内容到 LLM 消息")

        except Exception as e:
            log.warning(f"[Chat] 附件文件内容注入失败: {e}")

    # ✨ 消息列表完整性校验：确保 user/assistant 交替
    # 根因修复：空助手消息已在上游插入占位，正常情况下不会出现连续 user 消息
    # 此处仅做防御性检查，如发现异常则插入占位 assistant 消息
    for i in range(1, len(lc_messages)):
        if (lc_messages[i]["role"] == "user" and lc_messages[i - 1]["role"] == "user"):
            log.warning(f"[Chat] 防御性修复：在消息 [{i-1}] 和 [{i}] 之间插入占位 assistant 消息")
            lc_messages.insert(i, {"role": "assistant", "content": "（此回复为空）"})
            break  # 一次修复一轮，下轮循环继续检查

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

        # Active Probing: 参数缺失时发送 ToolCall 事件（V2.0 升级）
        # 替代旧的追问拦截逻辑，改用 Vercel AI SDK 兼容的 ToolCall 格式，
        # 前端 ParameterProbingCard 组件接收后渲染动态表单
        if route_result and route_result.probing and route_result.probing.is_missing:
            # 发送 request_parameters ToolCall（Vercel AI SDK 兼容格式）
            tool_call_event = {
                "type": "data-tool-call",
                "toolCallId": f"call_probe_0",
                "toolName": "request_parameters",
                "args": {
                    "message": route_result.probing.message_to_user,
                    "schema": route_result.probing.ui_schema,
                },
            }
            yield encoder.from_custom_event("tool_call", tool_call_event)
            # 参数缺失时不调用 LLM，直接结束流
            yield encoder.finish()
            return
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
            # ✨ 修复：仅 Ollama 原生服务使用 ollama SDK 客户端
            # host.docker.internal:8008/v1 等本地 OpenAI 兼容 API（vLLM/LiteLLM）
            # 不应走 ollama 原生客户端，否则会请求 /api/chat 端点导致 404
            # Ollama 原生客户端支持 think 参数控制 Qwen3 等模型的内置思考
            use_native_ollama = is_ollama_service

            try:
                # ✨ 判断是否为 data_probe 意图（需要绑定探针工具）
                # V2.0 升级：intent_data 结构为 TaskDAG.model_dump()，意图在 nodes[0].intent 中
                is_data_probe = (
                    intent_data.get("nodes")
                    and len(intent_data["nodes"]) > 0
                    and intent_data["nodes"][0].get("intent") == "INTENT_DATA_PROBE"
                )
                # ✨ data_probe 项目路径：工具执行时强制限定在此目录内，防止扫描其他项目
                data_probe_project_dir = ""
                if is_data_probe:
                    from app.core.config import settings as app_settings
                    data_probe_project_dir = str(Path(app_settings.UPLOAD_DIR) / f"project_{request.project_id}")
                    log.info(f"[Chat] data_probe 项目目录: {data_probe_project_dir}")

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
                    for i, msg in enumerate(lc_messages):
                        ollama_msg = {'role': msg['role'], 'content': msg['content']}
                        # ✨ 图片消息：为当前用户消息添加 images 字段
                        # Ollama SDK 支持在消息中传递图片路径，自动 base64 编码
                        if msg['role'] == 'user' and i == len(lc_messages) - 1 and current_image_paths:
                            # 将服务器相对路径转为绝对路径
                            # 项目目录格式：UPLOAD_DIR/project_{project_id}
                            from app.core.config import settings as img_settings
                            abs_image_paths = []
                            for img_path in current_image_paths:
                                if os.path.isabs(img_path):
                                    abs_image_paths.append(img_path)
                                else:
                                    project_dir = str(Path(img_settings.UPLOAD_DIR) / f"project_{request.project_id}")
                                    abs_image_paths.append(f"{project_dir}/{img_path}")
                            ollama_msg['images'] = abs_image_paths
                            log.info(f"[Chat] Ollama 消息包含 {len(abs_image_paths)} 张图片: {abs_image_paths}")
                        ollama_messages.append(ollama_msg)

                    # ✨ data_probe 意图：绑定探针工具
                    if is_data_probe:
                        from app.tools.probe_tools import probe_tools_list
                        # Ollama 原生客户端支持 tools 参数
                        # 将 LangChain @tool 装饰器定义的工具转为 Ollama 格式
                        ollama_tools = []
                        for t in probe_tools_list:
                            tool_schema = {
                                "type": "function",
                                "function": {
                                    "name": t.name,
                                    "description": t.description,
                                    "parameters": t.args_schema.schema() if hasattr(t, 'args_schema') and t.args_schema else {},
                                }
                            }
                            ollama_tools.append(tool_schema)
                        log.info(f"[Chat] data_probe: 绑定 {len(ollama_tools)} 个探针工具")

                        # ✨ Ollama 工具调用循环：LLM 可能多次调用工具
                        # 每次工具调用后，将结果追加到消息列表，继续调用 LLM
                        max_tool_rounds = 5  # 最多 5 轮工具调用
                        for round_idx in range(max_tool_rounds):
                            stream_response = await client.chat(
                                model=model_name,
                                messages=ollama_messages,
                                tools=ollama_tools,
                                think=enable_think,
                                stream=True,
                            )
                            has_tool_call = False
                            tool_calls_in_round = []

                            async for part in stream_response:
                                # 处理文本内容
                                if part.message and part.message.content:
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
                                # 处理思考内容
                                if part.message and hasattr(part.message, 'thinking') and part.message.thinking:
                                    yield encoder.from_thinking(part.message.thinking)
                                # ✨ 收集工具调用
                                if part.message and hasattr(part.message, 'tool_calls') and part.message.tool_calls:
                                    for tc in part.message.tool_calls:
                                        tool_calls_in_round.append(tc)
                                        has_tool_call = True

                            # 如果没有工具调用，退出循环
                            if not has_tool_call:
                                break

                            # 执行工具调用并将结果追加到消息列表
                            for tc in tool_calls_in_round:
                                tool_name = tc.function.name
                                tool_args = tc.function.arguments if isinstance(tc.function.arguments, dict) else json.loads(tc.function.arguments or '{}')
                                log.info(f"[Chat] data_probe 工具调用: {tool_name}({tool_args})")

                                # 输出工具调用进度
                                progress_msg = f"\n> ⚙️ 正在执行: `{tool_name}`...\n\n"
                                start = ensure_text_started()
                                if start:
                                    yield start
                                ai_full_response += progress_msg
                                yield encoder.text_chunk(progress_msg)

                                # 执行工具
                                # ✨ 路径安全修正：强制限定在当前项目目录内
                                if data_probe_project_dir and tool_name in ("scan_workspace", "peek_tabular_data"):
                                    path_key = "directory_path" if tool_name == "scan_workspace" else "file_path"
                                    if path_key in tool_args:
                                        requested_path = tool_args[path_key]
                                        # 如果请求路径不在项目目录下，强制替换
                                        if not requested_path.startswith(data_probe_project_dir):
                                            log.warning(f"[Chat] data_probe 路径修正: {requested_path} → {data_probe_project_dir}")
                                            tool_args[path_key] = data_probe_project_dir
                                tool_result = ""
                                try:
                                    for t in probe_tools_list:
                                        if t.name == tool_name:
                                            tool_result = t.invoke(tool_args)
                                            break
                                except Exception as te:
                                    tool_result = f"工具执行失败: {str(te)}"
                                    log.error(f"[Chat] 工具执行失败: {tool_name}, error={te}")

                                # 输出工具结果
                                start = ensure_text_started()
                                if start:
                                    yield start
                                ai_full_response += tool_result
                                yield encoder.text_chunk(tool_result)

                                # 将工具调用和结果追加到消息列表
                                ollama_messages.append({
                                    'role': 'assistant',
                                    'content': '',
                                    'tool_calls': [{'function': {'name': tool_name, 'arguments': tool_args}}],
                                })
                                ollama_messages.append({
                                    'role': 'tool',
                                    'content': tool_result,
                                })

                        log.info(f"[Chat] data_probe 工具调用完成，共 {round_idx + 1} 轮")

                    else:
                        # 普通聊天（无工具绑定）
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

                    # ✨ 图片消息：构建多模态 content（image_url blocks）
                    # OpenAI/Claude 等模型支持 content 为列表，包含 text 和 image_url
                    if current_image_paths:
                        # 将图片注入到当前用户消息中
                        # 找到 lc_messages 中最后一个 user 消息，替换为多模态格式
                        for i in range(len(lc_messages) - 1, -1, -1):
                            if lc_messages[i]["role"] == "user":
                                multimodal_content = [{"type": "text", "text": lc_messages[i]["content"]}]
                                for img_path in current_image_paths:
                                    abs_img = img_path
                                    if not os.path.isabs(img_path):
                                        from app.core.config import settings as lc_img_settings
                                        project_dir = str(Path(lc_img_settings.UPLOAD_DIR) / f"project_{request.project_id}")
                                        abs_img = f"{project_dir}/{img_path}"
                                    # 读取图片并 base64 编码
                                    try:
                                        import base64
                                        with open(abs_img, 'rb') as f:
                                            img_data = base64.b64encode(f.read()).decode('utf-8')
                                        ext = os.path.splitext(abs_img)[1].lower()
                                        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
                                        mime_type = mime_map.get(ext, 'image/png')
                                        multimodal_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:{mime_type};base64,{img_data}"}
                                        })
                                    except Exception as img_err:
                                        log.warning(f"[Chat] 图片读取失败: {abs_img}, error={img_err}")
                                lc_messages[i] = {"role": "user", "content": multimodal_content}
                                log.info(f"[Chat] LangChain 消息包含 {len(current_image_paths)} 张图片")
                                break

                    llm_kwargs = dict(
                        api_key=api_key or "not-needed",
                        base_url=base_url,
                        model=model_name,
                        streaming=True,
                    )

                    # ✨ 第三方 API + 深度思考：注入 thinking 配置（Claude 等模型支持）
                    # ✨ 本地 OpenAI 兼容 API（vLLM/OMLX 等）也支持 extra_body 传递思考参数
                    if enable_think:
                        if not is_local_model:
                            # Claude 等第三方 API 的 thinking 配置
                            llm_kwargs['extra_body'] = {
                                'thinking': {'type': 'enabled', 'budget_tokens': 10000}
                            }
                        else:
                            # 本地 OpenAI 兼容 API（vLLM/OMLX/Qwen3 等）的思考配置
                            # Qwen3 等模型通过 chat_template 中的 enable_thinking 参数控制
                            llm_kwargs['extra_body'] = {
                                'enable_thinking': True
                            }

                    direct_llm = ChatOpenAI(**llm_kwargs)

                    # ✨ data_probe 意图：绑定探针工具并执行工具调用循环
                    if is_data_probe:
                        from app.tools.probe_tools import probe_tools_list
                        llm_with_tools = direct_llm.bind_tools(probe_tools_list)
                        log.info(f"[Chat] data_probe: 绑定 {len(probe_tools_list)} 个探针工具到 LangChain LLM")

                        # 工具调用循环：LLM 可能多次调用工具
                        max_tool_rounds = 5
                        current_messages = list(lc_messages)  # 复制消息列表

                        for round_idx in range(max_tool_rounds):
                            # 非流式调用以获取完整的 tool_calls
                            response = await llm_with_tools.ainvoke(current_messages)

                            # 如果有文本内容，流式输出
                            if response.content:
                                filtered_content, content_type = content_filter.filter_chunk(response.content)
                                if filtered_content:
                                    start = ensure_text_started()
                                    if start:
                                        yield start
                                    ai_full_response += filtered_content
                                    yield encoder.text_chunk(filtered_content)

                            # 如果没有工具调用，退出循环
                            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                                break

                            # 执行每个工具调用
                            for tc in response.tool_calls:
                                tool_name = tc['name']
                                tool_args = tc.get('args', {})
                                log.info(f"[Chat] data_probe 工具调用: {tool_name}({tool_args})")

                                # 输出工具调用进度
                                progress_msg = f"\n> ⚙️ 正在执行: `{tool_name}`...\n\n"
                                start = ensure_text_started()
                                if start:
                                    yield start
                                ai_full_response += progress_msg
                                yield encoder.text_chunk(progress_msg)

                                # 执行工具
                                # ✨ 路径安全修正：强制限定在当前项目目录内
                                if data_probe_project_dir and tool_name in ("scan_workspace", "peek_tabular_data"):
                                    path_key = "directory_path" if tool_name == "scan_workspace" else "file_path"
                                    if path_key in tool_args:
                                        requested_path = tool_args[path_key]
                                        if not requested_path.startswith(data_probe_project_dir):
                                            log.warning(f"[Chat] data_probe 路径修正: {requested_path} → {data_probe_project_dir}")
                                            tool_args[path_key] = data_probe_project_dir
                                tool_result = ""
                                try:
                                    for t in probe_tools_list:
                                        if t.name == tool_name:
                                            tool_result = t.invoke(tool_args)
                                            break
                                except Exception as te:
                                    tool_result = f"工具执行失败: {str(te)}"
                                    log.error(f"[Chat] 工具执行失败: {tool_name}, error={te}")

                                # 输出工具结果
                                start = ensure_text_started()
                                if start:
                                    yield start
                                ai_full_response += tool_result
                                yield encoder.text_chunk(tool_result)

                                # 追加工具调用和结果到消息列表
                                from langchain_core.messages import AIMessage, ToolMessage
                                current_messages.append(AIMessage(
                                    content="",
                                    tool_calls=[{"id": tc.get('id', ''), "name": tool_name, "args": tool_args}]
                                ))
                                current_messages.append(ToolMessage(
                                    content=tool_result,
                                    tool_call_id=tc.get('id', ''),
                                ))

                        log.info(f"[Chat] data_probe 工具调用完成，共 {round_idx + 1} 轮")

                    else:
                        # 普通聊天（无工具绑定）
                        async for chunk in direct_llm.astream(lc_messages):
                            content = chunk.content
                            if content:
                                # ✨ 过滤思考标签等内容，返回 (content, type) 元组
                                # type: "text" = 正常回复, "thinking" = 思考过程
                                filtered_content, content_type = content_filter.filter_chunk(content)
                                if filtered_content:
                                    if content_type == "thinking":
                                        # ✨ 思考过程通过 data 事件推送给前端
                                        log.info(f"[Chat] DEBUG thinking: len={len(filtered_content)}, preview={filtered_content[:80]}")
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

        # 持久化助手消息 + 扣费（Active Probing 提前 return，此处仅 LLM 正常回复到达）
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


# ==========================================
# Active Probing 参数提交端点
# ==========================================

class ProbingSubmitRequest(BaseModel):
    """Active Probing 参数提交请求"""
    message_id: str = Field(..., description="ProbingRequest 的 message_id")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="用户填写的参数")


@router.post("/probing/submit")
async def probing_submit(
    request: ProbingSubmitRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    接收前端 Active Probing 表单提交的参数。

    程序说明：
    将用户提交的参数写入 Redis，key 为 probing:{message_id}，
    TTL 10 分钟。LangGraph 的 probing_response_node 从 Redis 读取。
    """
    import redis
    from app.core.config import settings

    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        key = f"probing:{request.message_id}"
        r.setex(key, 600, json.dumps(request.parameters))  # TTL 10 分钟
        log.info(f"[probing_submit] 参数已写入 Redis: key={key}")
        return {"status": "ok", "message_id": request.message_id}
    except Exception as e:
        log.error(f"[probing_submit] Redis 写入失败: {e}")
        raise HTTPException(status_code=500, detail=f"参数提交失败: {str(e)}")


# ==========================================
# DAG 节点重试端点
# ==========================================

@router.post("/dag/retry/{task_id}")
async def dag_retry_task(
    task_id: str,
    session_id: str = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    重试 DAG 中失败的节点。

    程序说明：
    重置指定 task_id 的执行状态为 READY，
    清除其 task_results 记录，
    使其可被 DAG 调度器重新拾取执行。
    通过 Redis 通知正在运行的 graph 重试该节点。
    """
    try:
        import redis
        from app.core.config import settings

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        key = f"dag_retry:{task_id}"
        r.setex(key, 300, json.dumps({"task_id": task_id, "action": "retry"}))
        log.info(f"[dag_retry] 重试请求已写入 Redis: task_id={task_id}")
        return {"status": "ok", "task_id": task_id, "action": "retry"}
    except Exception as e:
        log.error(f"[dag_retry] Redis 写入失败: {e}")
        raise HTTPException(status_code=500, detail=f"重试请求失败: {str(e)}")
