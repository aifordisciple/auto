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
- 必须主动调用探针工具来获取信息，不要凭猜测回答
- 工具调用后，用中文整理和解读结果，提供专业建议
- 不要在回答开头重复自己的身份，直接进入正题
- **追问场景**：当用户说"这个文件"、"这个"等指代词时，参考系统提示词中"用户当前关注的文件"来定位文件

## 可用探针工具（14个）

### 文件系统与目录
- **scan_workspace**：扫描工作区目录结构，列出文件和子目录
- **match_paired_fastq**：配对双端 FASTQ 文件（R1/R2），检测落单文件

### 表格数据探查
- **peek_tabular_data**：预览表格文件（CSV/TSV/TXT），显示表头、行列数、前几行
- **detect_na**：缺失值检测，逐列统计 NA/NaN/空值数量和占比
- **compute_summary_stats**：数值列汇总统计（count/mean/std/min/25%/50%/75%/max），推断 Log 转换状态
- **compute_set_operations**：两个文件列之间的集合运算（交集/并集/差集/重叠比例）

### 编码与格式检测
- **detect_file_encoding**：检测文件字符编码和分隔符类型（Tab/Comma/Semicolon/Pipe）
- **detect_file_type**：综合判断文件类型（基于扩展名 + magic bytes + 内容模式）

### 多组学文件探查
- **inspect_h5ad**：AnnData 对象探查（obs/var/X 层维度、obs/var 列名）
- **inspect_fastq**：FASTQ 文件质量摘要（读长分布、GC 含量、碱基质量）
- **inspect_bam**：BAM 文件比对统计 + Header 解析（@SQ 参考序列/@RG 读组/@PG 处理程序）
- **inspect_vcf**：VCF 文件变异统计（样本列表、染色体分布、变异类型）

### 矩阵文件探查
- **inspect_mtx**：MTX 矩阵维度探测（仅读文件头，不加载全量，10GB+ 秒级返回）

### 自定义探查
- **sandbox_probe**：内置工具不支持目标文件格式时，AI 自主编写 Python 脚本在 Docker 沙箱中运行探查

## 工具选择指南
| 用户需求 | 使用工具 |
|---------|---------|
| 有哪些文件 / 目录结构 | scan_workspace |
| 查看文件内容 / 表头 / 多少行列 | peek_tabular_data |
| 缺失值 / NA 比例 / 空值 | detect_na |
| 统计信息 / min/max / 均值 / 是否 Log 转换 | compute_summary_stats |
| 文件编码 / 分隔符是什么 | detect_file_encoding |
| 文件类型 / 这是什么文件 / 格式判断 | detect_file_type |
| 基因重叠 / 交集 / 并集 / Venn | compute_set_operations |
| 配对 FASTQ / 双端文件 / R1 R2 匹配 | match_paired_fastq |
| h5ad 结构 / AnnData 信息 | inspect_h5ad |
| FASTQ 质量 / GC 含量 | inspect_fastq |
| BAM 文件 / 比对信息 / 参考基因组是 hg19 还是 hg38 | inspect_bam |
| VCF 文件 / 变异样本 / 染色体分布 | inspect_vcf |
| MTX / 矩阵维度 / 稀疏矩阵 | inspect_mtx |
| 内置工具不支持的文件格式 / 自定义探查 | sandbox_probe |

⚠️ 重要：所有文件/目录操作限定在当前项目工作区内，不要扫描或访问其他项目目录。

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
# 路径安全：探针工具参数名映射
# 用于在工具调用时强制将文件/目录路径限定在当前项目工作区内
# ==========================================
PATH_SAFE_TOOL_PARAMS = {
    "scan_workspace": ["directory_path"],
    "peek_tabular_data": ["file_path"],
    "detect_na": ["file_path"],
    "compute_summary_stats": ["file_path"],
    "detect_file_encoding": ["file_path"],
    "compute_set_operations": ["file_path_1", "file_path_2"],
    "inspect_vcf": ["file_path"],
    "match_paired_fastq": ["directory_path"],
    "inspect_h5ad": ["file_path"],
    "inspect_fastq": ["file_path"],
    "inspect_bam": ["file_path"],
    "detect_file_type": ["file_path"],
    "inspect_mtx": ["file_path"],
    "sandbox_probe": ["workspace_path"],
}

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
    # ✨ 保存附件信息（图片路径、粘贴文件路径、项目文件路径），用于历史消息重建
    user_attachments = None
    if request.images or request.pasted_files or request.context_files:
        user_attachments = {}
        if request.images:
            user_attachments["images"] = request.images
        if request.pasted_files:
            user_attachments["pastedFiles"] = request.pasted_files
        if request.context_files:
            user_attachments["files"] = request.context_files
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

        # ✨ 跨轮回合文件上下文：优先使用前端传来的 context_files，
        # 若前端未传则尝试从 Redis 恢复上次的文件上下文
        _active_file = request.context_files[0] if request.context_files else None
        _context_files = request.context_files

        if not _active_file and not _context_files and request.project_id:
            try:
                from app.services.file_context_service import get_file_context_service
                restored = get_file_context_service().restore(
                    user_id=str(current_user.id),
                    project_id=request.project_id,
                )
                if restored:
                    _active_file = restored.get("active_file") or None
                    _context_files_raw = restored.get("context_files") or []
                    _context_files = [
                        f.get("name", "") if isinstance(f, dict) else str(f)
                        for f in _context_files_raw
                    ]
                    if _active_file or _context_files:
                        log.info(
                            f"[Chat] 从 Redis 恢复文件上下文: "
                            f"active_file={_active_file}, context_files={len(_context_files)}"
                        )
            except Exception as restore_err:
                log.debug(f"[Chat] Redis 文件上下文恢复跳过: {restore_err}")

        router_engine = IntentRouterEngine(session=session, user_id=current_user.id)
        route_result = await router_engine.route(
            query=request.message,
            context={
                "project_id": request.project_id,
                "skill_id": request.skill_id,
                "active_file": _active_file,
                "context_files": _context_files,
            }
        )
        intent_data = route_result.dag.model_dump()

        # ✨ 持久化文件上下文到 Redis
        # 1. 当本次请求有文件上下文时：直接保存
        # 2. 当本次请求无文件上下文但 Redis 恢复出有效 _active_file 时：刷新 TTL
        if request.project_id:
            _should_save = bool(request.context_files)
            _save_active_file = request.context_files[0] if request.context_files else ""
            _save_files = request.context_files or []
            if not _should_save and _active_file:
                # 追问场景：前端未传 context_files，但 Redis 恢复了文件上下文
                # 刷新 TTL 避免长时间对话中上下文过期
                _should_save = True
                _save_active_file = _active_file
                _save_files = _context_files if _context_files else [_active_file]
            if _should_save:
                try:
                    from app.services.file_context_service import get_file_context_service
                    get_file_context_service().save(
                        user_id=str(current_user.id),
                        project_id=request.project_id,
                        active_file=_save_active_file,
                        context_files=[
                            {"id": f.get("id", ""), "name": f.get("name", "")}
                            if isinstance(f, dict)
                            else {"id": str(f), "name": str(f)}
                            for f in _save_files
                        ],
                    )
                except Exception as save_err:
                    log.debug(f"[Chat] Redis 文件上下文保存跳过: {save_err}")
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
            # ✨ 注入文件上下文：将 active_file 和 context_files 写入系统提示词
            # 解决追问场景（如"这个文件多少行"）中 LLM 不知道"这个文件"指代哪个文件的问题
            # _active_file 来源：前端 context_files[0] > Redis 跨轮恢复 > None
            if _active_file:
                system_prompt += f"\n\n用户当前关注的文件: {_active_file}"
            if _context_files:
                _file_list = "\n".join(f"- {f}" for f in _context_files[:20])
                system_prompt += f"\n工作区可用文件列表:\n{_file_list}"
            log.info(f"[Chat] 使用数据探查模式 (intent={first_intent.value}, workspace={project_workspace}, active_file={_active_file})")
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
    # ✨ 附件文件内容合并到当前用户消息中（而不是追加额外消息对）
    # 这样 AI 能直接看到文件内容并回答，不会被 data_probe 模式的探针工具干扰
    current_user_content = request.message
    current_image_paths = request.images or []

    # ✨ 附件文件内容注入：读取 context_files 的文件内容，合并到当前用户消息
    # 当用户通过"添加附件"选择项目文件时，AI 需要看到文件内容才能回答相关问题
    # 根据文件扩展名选择不同的读取策略，直接读取文件内容（不经过 LangChain @tool 封装）
    file_context_injected = False
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
                    # 表格文件：直接用 pandas 读取表头和前几行
                    try:
                        import pandas as pd
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                            first_line = f.readline()
                        delimiter = '\t'
                        if ',' in first_line and '\t' not in first_line:
                            delimiter = ','
                        df = pd.read_csv(abs_path, sep=delimiter, nrows=10)
                        n_rows_total = sum(1 for _ in open(abs_path, 'r', encoding='utf-8', errors='ignore')) - 1
                        preview = f"文件维度: {n_rows_total} 行 × {len(df.columns)} 列\n"
                        preview += f"表头: {list(df.columns[:10])}\n"
                        preview += f"前10行:\n{df.to_string(max_cols=10, max_colwidth=12)}"
                        file_context_parts.append(f"## 文件: {file_path}\n{preview}")
                    except Exception as tbl_err:
                        log.warning(f"[Chat] 表格文件 pandas 读取失败，回退纯文本: {tbl_err}")
                        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read(50000)
                        file_context_parts.append(f"## 文件: {file_path} (纯文本预览)\n```\n{content}\n```")

                elif ext == '.h5ad':
                    try:
                        import scanpy as sc
                        adata = sc.read_h5ad(abs_path, backed='r')
                        info = f"AnnData 对象: {adata.n_obs} 观测 × {adata.n_vars} 变量\n"
                        info += f"obs 列: {list(adata.obs.columns)}\n"
                        info += f"var 列: {list(adata.var.columns)}"
                        adata.file.close()
                        file_context_parts.append(f"## 文件: {file_path}\n{info}")
                    except Exception as h5_err:
                        file_context_parts.append(f"## 文件: {file_path}\n[AnnData 读取失败: {h5_err}]")

                elif ext in ('.py', '.r', '.sh', '.json', '.yaml', '.yml', '.md',
                             '.log', '.nf', '.conf', '.cfg', '.ini', '.toml',
                             '.tex', '.html', '.css', '.js', '.ts', '.sql'):
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
                    from app.services.pdf_processor import extract_pdf_content
                    result = extract_pdf_content(abs_path)
                    text = result.get('text', '[PDF 内容提取失败]')[:5000]
                    file_context_parts.append(f"## 文件: {file_path}\n{text}")

                elif ext in ('.fastq', '.fq'):
                    try:
                        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                            lines = [f.readline() for _ in range(8)]
                        preview = ''.join(lines)
                        file_context_parts.append(f"## 文件: {file_path}\n```\n{preview}\n... (更多记录省略)\n```")
                    except Exception as fq_err:
                        file_context_parts.append(f"## 文件: {file_path}\n[FASTQ 读取失败: {fq_err}]")

                elif ext in ('.bam', '.sam'):
                    try:
                        import pysam
                        if ext == '.bam':
                            sf = pysam.AlignmentFile(abs_path, 'rb')
                        else:
                            sf = pysam.AlignmentFile(abs_path, 'r')
                        info = f"BAM/SAM 文件: {sf.header}\n参考序列: {list(sf.references)[:10]}"
                        sf.close()
                        file_context_parts.append(f"## 文件: {file_path}\n{info}")
                    except Exception as bam_err:
                        file_context_parts.append(f"## 文件: {file_path}\n[BAM/SAM 读取失败: {bam_err}]")

                else:
                    file_size = os.path.getsize(abs_path)
                    file_context_parts.append(
                        f"## 文件: {file_path} (类型: {ext}, 大小: {file_size} 字节)\n[此文件类型暂不支持内容预览]"
                    )

            # ✨ 合并文件内容到当前用户消息中（而不是追加额外消息对）
            # 这样 AI 直接在用户消息中看到文件内容，不会被 data_probe 模式的探针工具干扰
            if file_context_parts:
                file_context_text = "\n\n".join(file_context_parts)
                current_user_content += f"\n\n[用户附加的文件内容]\n{file_context_text}"
                file_context_injected = True
                log.info(f"[Chat] 合并 {len(file_context_parts)} 个附件文件内容到当前用户消息")

        except Exception as e:
            log.warning(f"[Chat] 附件文件内容注入失败: {e}")

    current_user_msg = {"role": "user", "content": current_user_content}
    lc_messages.append(current_user_msg)

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
        _should_probe = (route_result and route_result.probing and route_result.probing.is_missing)
        if _should_probe:
            # ✨ DATA_PROBE 追问场景：对话历史中已包含文件数据内容时跳过探查
            # 典型场景：用户上一轮已查看文件内容，追问"列名叫什么"等细节问题时，
            # L2 在当前消息中找不到 input_file 会触发 probing，但 AI 可以直接
            # 从对话历史中的文件内容回答，无需重新探查
            if (route_result.dag.nodes
                and route_result.dag.nodes[0].intent == NewIntentType.DATA_PROBE):
                for msg in reversed(lc_messages):
                    if msg["role"] == "assistant" and msg.get("content"):
                        # 助手消息中包含数据探查标记，说明之前已探查过文件内容
                        # 使用探针工具输出中的专用 emoji 和关键词，避免宽泛匹配
                        _data_markers = [
                            "📊", "表头", "数据维度",
                            "📋", "🔍", "🧬", "探测完成", "预览报告",
                        ]
                        if any(marker in msg["content"] for marker in _data_markers):
                            _should_probe = False
                            log.info("[Chat] DATA_PROBE 追问场景，对话历史已含数据内容，跳过 Active Probing")
                            break
        if _should_probe:
            # 发送 request_parameters ToolCall（通过 data-tool_call 自定义事件）
            tool_call_event = {
                "type": "data-tool-call",
                "toolCallId": "call_probe_0",
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
            # ✨ 即席交互式分析拦截：生成策略包并发送生成式 UI 卡片
            # 设计文档: docs/modules/意图升级.md — 意图 13: 即席交互式分析
            #
            # 这是 ADHOC 的主执行路径（SSE 流式场景）。
            # chat.py 直接生成策略包 → 存入 Redis → 发送 render_adhoc_card ToolCall → 挂起。
            # 图节点 adhoc_analysis_node 是备用路径（队列驱动 / 非流式场景），
            # 两者共享 _generate_strategy_pack() 和 ProbingRequest 协议。
            #
            # 当 L1+L2 判定为 ADHOC 且文件已指定时，不直接进入 LLM 流式，
            # 而是调用 adhoc_analysis_node 生成策略包，通过 render_adhoc_card
            # ToolCall 向前端推送交互式分析策略卡片，挂起等待用户确认参数后执行。
            is_adhoc_intent = (
                intent_data.get("nodes")
                and len(intent_data["nodes"]) > 0
                and intent_data["nodes"][0].get("intent") == "INTENT_ADHOC_INTERACTIVE_ANALYSIS"
            )
            if is_adhoc_intent:
                log.info("[Chat] 检测到即席交互式分析意图，生成策略包并发送策略卡片")
                try:
                    from app.agent.nodes.adhoc_analysis_node import _generate_strategy_pack_streaming

                    dag_node = intent_data["nodes"][0]
                    raw_instruction = dag_node.get("raw_instruction", request.message)
                    resolved_assets = dag_node.get("resolved_assets", [])
                    file_id = resolved_assets[0] if resolved_assets else "unknown"

                    # 收集用户实际提供的文件路径，填充到参数 Schema 默认值中
                    # 注意：沙箱容器现在按项目挂载（project_{id} → /workspace），
                    # 所以文件路径只需补全 /workspace/ 前缀，无需 project_{id} 中间层
                    context_file_paths = request.context_files or []
                    full_file_paths = [
                        f"/workspace/{f}" if not f.startswith("/") else f
                        for f in context_file_paths
                    ]
                    file_paths_str = "\n  - ".join(full_file_paths)
                    if file_paths_str:
                        file_paths_str = f"  - {file_paths_str}"

                    # 流式生成策略包（分阶段进度事件 + 内容块）
                    # 替代原来的阻塞式骨架屏方案，前端渐进式渲染策略卡片
                    # 先探查输入文件结构，注入 LLM prompt 以提升代码和参数准确性
                    file_profiles_text = ""
                    if full_file_paths:
                        try:
                            from app.services.file_profiler import profile_files, format_profiles_for_prompt
                            profiles = profile_files(full_file_paths)
                            file_profiles_text = format_profiles_for_prompt(profiles)
                            log.info(f"[Chat] 文件探查完成: {len(profiles)} 个文件")
                        except Exception as prof_err:
                            log.warning(f"[Chat] 文件探查失败（非致命）: {prof_err}")

                    strategy_pack = None
                    async for event in _generate_strategy_pack_streaming(
                        file_id=file_id,
                        instruction=raw_instruction,
                        session=session,
                        user_id=current_user.id,
                        file_paths=file_paths_str,
                        enable_think=request.enable_think,
                        file_profiles_text=file_profiles_text,
                    ):
                        if event["type"] == "stage":
                            # 推送阶段变更事件 → 前端更新进度指示器
                            yield encoder.data_event(
                                {
                                    "status": "generating_strategy",
                                    "stage": event["stage"],
                                    "message": event["message"],
                                },
                                event_name="adhoc_status",
                            )
                        elif event["type"] == "chunk":
                            # 推送流式内容块 → 前端渐进式填充卡片内容
                            yield encoder.data_event(
                                {
                                    "status": "streaming_chunk",
                                    "stage": event["stage"],
                                    "content": event["content"],
                                },
                                event_name="adhoc_chunk",
                            )
                        elif event["type"] == "complete":
                            # 策略包生成完成
                            strategy_pack = event["data"]
                        elif event["type"] == "error":
                            # 策略包生成失败，抛出异常进入降级处理
                            raise Exception(event["message"])

                    if strategy_pack is None:
                        raise Exception("策略包流式生成未返回完整数据")

                    # 策略包存入 Redis，通过 Chat/Graph 共享函数统一存储
                    from app.agent.nodes.adhoc_analysis_node import _store_strategy_pack_to_redis
                    _store_strategy_pack_to_redis(
                        strategy_pack=strategy_pack,
                        message_id=user_msg.id,
                        project_id=request.project_id,
                    )

                    # 发送 render_adhoc_card ToolCall（通过 data-tool_call 自定义事件流向 Vercel AI SDK）
                    # message_id 传递给前端，执行时前端回传用于 Redis 查找策略包
                    tool_call_event = {
                        "type": "data-tool-call",
                        "toolCallId": f"call_adhoc_{user_msg.id}",
                        "toolName": "render_adhoc_card",
                        "args": {
                            "strategy": strategy_pack.get("strategy", ""),
                            "code": strategy_pack.get("code", ""),
                            "code_language": strategy_pack.get("code_language", "python"),
                            "parameter_schema": strategy_pack.get("parameter_schema", {}),
                            "input_mapping": strategy_pack.get("input_mapping", {}),
                            "message": "即席分析策略已生成，请在卡片上确认参数后执行",
                            "message_id": user_msg.id,
                            "_validation": strategy_pack.get("_validation"),
                        },
                    }
                    yield encoder.from_custom_event("tool_call", tool_call_event)
                    yield encoder.finish()
                    return
                except Exception as adhoc_err:
                    log.error(f"[Chat] 即席分析策略包生成失败，降级为 Skill Forge: {adhoc_err}")
                    # 降级：修改意图为 SKILL_FORGE，使用代码生成模式
                    intent_data["nodes"][0]["intent"] = "INTENT_SKILL_FORGE"
                    first_intent = NewIntentType.SKILL_FORGE
                    system_prompt = SYSTEM_PROMPT_CODE
                    lc_messages[0] = {"role": "system", "content": system_prompt}
                    # 不 return，继续走 LLM 流式（代码生成模式）

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
                # ✨ 当附件文件内容已注入用户消息时，选择性保留计算类探针工具
                # 查看类工具（peek/scan/inspect）可跳过（文件内容已在消息中），
                # 但计算类工具（detect_na/compute_summary_stats/detect_file_encoding/
                # compute_set_operations/match_paired_fastq）仍需保留，支持深度分析
                # _active_probe_tools: None=使用完整工具列表, list=使用过滤后的列表
                _active_probe_tools = None
                if is_data_probe and file_context_injected:
                    from app.tools.probe_tools import probe_tools_list, COMPUTE_TOOLS
                    _active_probe_tools = [t for t in probe_tools_list if t.name in COMPUTE_TOOLS]
                    log.info(
                        f"[Chat] 附件文件内容已注入，保留计算类探针工具: "
                        f"{[t.name for t in _active_probe_tools]}"
                    )
                    # 追加提示到系统消息：告知 AI 文件内容已注入但计算工具可用
                    lc_messages[0]["content"] += (
                        "\n\n## 附件文件已注入\n"
                        "用户消息中已包含附件文件的内容，你可以直接基于内容回答关于文件基本信息的问题"
                        "（如有哪些列、数据长什么样、前几行等）。"
                        "如需深度分析（缺失值检测、统计汇总、编码检测等），可使用计算类探针工具。"
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
                        # 使用过滤后的工具列表（附件注入场景仅保留计算类工具）
                        _tools = _active_probe_tools if _active_probe_tools is not None else probe_tools_list
                        # Ollama 原生客户端支持 tools 参数
                        # 将 LangChain @tool 装饰器定义的工具转为 Ollama 格式
                        ollama_tools = []
                        for t in _tools:
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
                                # 对所有文件/目录路径参数进行安全校验
                                if data_probe_project_dir and tool_name in PATH_SAFE_TOOL_PARAMS:
                                    for path_key in PATH_SAFE_TOOL_PARAMS[tool_name]:
                                        if path_key in tool_args:
                                            requested_path = tool_args[path_key]
                                            # 相对路径 → 拼接到项目目录下，而非替换
                                            if not requested_path.startswith("/"):
                                                corrected_path = os.path.join(data_probe_project_dir, requested_path)
                                                log.info(f"[Chat] data_probe 路径拼接: {requested_path} → {corrected_path}")
                                                tool_args[path_key] = corrected_path
                                            # 绝对路径但不在项目目录下 → 限制在项目目录内
                                            elif not requested_path.startswith(data_probe_project_dir):
                                                log.warning(f"[Chat] data_probe 路径限制: {requested_path} 不在项目目录内，替换为 {data_probe_project_dir}")
                                                tool_args[path_key] = data_probe_project_dir
                                tool_result = ""
                                try:
                                    for t in _tools:
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
                        # 使用过滤后的工具列表（附件注入场景仅保留计算类工具）
                        _tools_lc = _active_probe_tools if _active_probe_tools is not None else probe_tools_list
                        llm_with_tools = direct_llm.bind_tools(_tools_lc)
                        log.info(f"[Chat] data_probe: 绑定 {len(_tools_lc)} 个探针工具到 LangChain LLM")

                        # 工具调用循环：LLM 可能多次调用工具
                        # V2.3 升级：使用 astream_events 流式输出，消除 ainvoke 导致的空白等待
                        max_tool_rounds = 5
                        current_messages = list(lc_messages)  # 复制消息列表
                        from langchain_core.messages import AIMessage, ToolMessage

                        for round_idx in range(max_tool_rounds):
                            # 流式调用 LLM，边生成文本边输出，同时收集 tool_call_chunks
                            full_content = ""
                            tool_call_chunks_by_idx: dict = {}
                            has_any_stream_output = False

                            try:
                                async for event in llm_with_tools.astream_events(
                                    current_messages,
                                    version="v2",
                                ):
                                    kind = event["event"]
                                    if kind == "on_chat_model_stream":
                                        chunk = event["data"]["chunk"]
                                        # 流式输出文本内容
                                        if chunk.content:
                                            has_any_stream_output = True
                                            filtered_content, content_type = content_filter.filter_chunk(chunk.content)
                                            if filtered_content:
                                                if content_type == "thinking":
                                                    yield encoder.from_thinking(filtered_content)
                                                else:
                                                    start = ensure_text_started()
                                                    if start:
                                                        yield start
                                                    full_content += filtered_content
                                                    ai_full_response += filtered_content
                                                    yield encoder.text_chunk(filtered_content)
                                        # 收集 tool_call_chunks（按 index 聚合，流式模式下分片到达）
                                        if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                                            for tc_chunk in chunk.tool_call_chunks:
                                                idx = tc_chunk.get('index', 0)
                                                if idx not in tool_call_chunks_by_idx:
                                                    tool_call_chunks_by_idx[idx] = {
                                                        'name': '',
                                                        'args': '',
                                                        'id': tc_chunk.get('id') or '',
                                                    }
                                                if tc_chunk.get('name'):
                                                    tool_call_chunks_by_idx[idx]['name'] += tc_chunk['name']
                                                if tc_chunk.get('args'):
                                                    tool_call_chunks_by_idx[idx]['args'] += tc_chunk['args']
                                                if tc_chunk.get('id') and not tool_call_chunks_by_idx[idx]['id']:
                                                    tool_call_chunks_by_idx[idx]['id'] = tc_chunk['id']
                            except Exception as stream_err:
                                log.warning(
                                    f"[Chat] astream_events 失败，回退到 ainvoke: {stream_err}"
                                )
                                # 回退到非流式调用
                                response = await llm_with_tools.ainvoke(current_messages)
                                if response.content:
                                    filtered_content, content_type = content_filter.filter_chunk(response.content)
                                    if filtered_content:
                                        start = ensure_text_started()
                                        if start:
                                            yield start
                                        full_content = filtered_content
                                        ai_full_response += filtered_content
                                        yield encoder.text_chunk(filtered_content)
                                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                                    break
                                # 从 ainvoke 响应构建 tool_call_chunks_by_idx
                                for i, tc in enumerate(response.tool_calls):
                                    tool_call_chunks_by_idx[i] = {
                                        'name': tc['name'],
                                        'args': json.dumps(tc.get('args', {}), ensure_ascii=False),
                                        'id': tc.get('id', ''),
                                    }

                            # 如果没有工具调用，退出循环
                            if not tool_call_chunks_by_idx:
                                break

                            # 构建 AMessage 追加到对话历史（LLM 需要知道它调用过什么工具）
                            tool_calls_for_history = []
                            for idx in sorted(tool_call_chunks_by_idx.keys()):
                                tc_data = tool_call_chunks_by_idx[idx]
                                try:
                                    tc_args = json.loads(tc_data['args']) if tc_data['args'] else {}
                                except json.JSONDecodeError:
                                    tc_args = {}
                                tool_calls_for_history.append({
                                    "id": tc_data['id'] or f"call_{round_idx}_{idx}",
                                    "name": tc_data['name'],
                                    "args": tc_args,
                                })
                            current_messages.append(AIMessage(
                                content=full_content,
                                tool_calls=tool_calls_for_history,
                            ))

                            # 执行每个工具调用
                            for tc in tool_calls_for_history:
                                tool_name = tc['name']
                                tool_args = tc['args']
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
                                if data_probe_project_dir and tool_name in PATH_SAFE_TOOL_PARAMS:
                                    for path_key in PATH_SAFE_TOOL_PARAMS[tool_name]:
                                        if path_key in tool_args:
                                            requested_path = tool_args[path_key]
                                            if not requested_path.startswith("/"):
                                                corrected_path = os.path.join(data_probe_project_dir, requested_path)
                                                log.info(f"[Chat] data_probe 路径拼接: {requested_path} → {corrected_path}")
                                                tool_args[path_key] = corrected_path
                                            elif not requested_path.startswith(data_probe_project_dir):
                                                log.warning(f"[Chat] data_probe 路径限制: {requested_path} 不在项目目录内，替换为 {data_probe_project_dir}")
                                                tool_args[path_key] = data_probe_project_dir
                                tool_result = ""
                                try:
                                    for t in _tools_lc:
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

                                # 追加工具结果到消息列表
                                current_messages.append(ToolMessage(
                                    content=tool_result,
                                    tool_call_id=tc['id'],
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
                # 发送降级提示消息给用户，避免前端显示空白流
                fallback_msg = "抱歉，我暂时无法处理您的请求，请尝试重新描述您的问题。"
                start = ensure_text_started()
                if start:
                    yield start
                yield encoder.text_chunk(fallback_msg)
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
# 即席交互式分析执行端点
# ==========================================


def _derive_short_name(strategy_text: str, max_len: int = 20) -> str:
    """
    从即席分析策略描述中提取简短英文标识，用于输出目录命名。

    程序说明：
    - 优先从描述中提取英文关键词（PCA、Heatmap、Volcano 等）
    - 若描述不含英文，使用 "analysis" 作为默认值
    - 结果转为小写、空格替换为下划线

    Args:
        strategy_text: LLM 生成的策略描述文本
        max_len: 最大长度限制

    Returns:
        简短英文标识字符串（如 "pca_analysis"）
    """
    import re
    # 常见生信分析方法关键词
    known_keywords = [
        "PCA", "Heatmap", "Volcano", "MA", "UMAP", "t-SNE", "tSNE",
        "DEG", "GO", "KEGG", "GSEA", "Boxplot", "Violin", "Barplot",
        "Scatter", "Correlation", "Clustering", "QC", "Normalization",
        "DESeq2", "edgeR", "limma", "Seurat", "Scanpy",
    ]
    # 提取策略文本中的英文单词
    english_words = re.findall(r'[A-Za-z][A-Za-z0-9_-]*', strategy_text)
    # 优先匹配已知关键词
    for word in english_words:
        if word in known_keywords:
            return word.lower().replace("-", "_")
    # 回退：使用前几个英文单词
    if english_words:
        name = "_".join(english_words[:3]).lower()
        return name[:max_len]
    # 无英文时使用默认值
    return "analysis"


class AdhocExecuteRequest(BaseModel):
    """即席分析执行请求 —— 用户在前端策略卡片点击"执行"后提交"""
    message_id: str = Field(..., description="关联的 render_adhoc_card tool_call 的 message_id")
    payload: Dict[str, Any] = Field(default_factory=dict, description="执行参数载荷")


@router.post("/adhoc/execute")
async def adhoc_execute(
    request: AdhocExecuteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    SSE 流式端点：接收前端 AdhocAnalysisCard 的执行请求，实时推送 Docker 沙箱日志。

    程序说明：
    1. 从 Redis 读取策略包
    2. 写入脚本文件、构建命令行
    3. 通过 SSE 流式推送 Docker 容器实时日志
    4. 执行完成后推送最终结果（含输出文件树）
    """
    import redis
    from concurrent.futures import ThreadPoolExecutor
    from app.core.config import settings
    from app.tools.bio_tools import run_container

    # 从 Redis 读取策略包
    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        strategy_key = f"adhoc:{request.message_id}"
        strategy_json = r.get(strategy_key)
        if not strategy_json:
            raise HTTPException(
                status_code=404,
                detail="策略包已过期或不存在（有效期 10 分钟），请重新发起即席分析请求",
            )
        strategy_pack = json.loads(strategy_json)
        log.info(f"[adhoc_execute] 从 Redis 读取策略包: key={strategy_key}")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[adhoc_execute] Redis 读取失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取策略包失败: {str(e)}")

    # 提取执行参数和项目信息
    payload = request.payload or {}
    parameters = payload.get("parameters", {})
    code_snapshot = payload.get("code_snapshot", "")
    code_language = strategy_pack.get("code_language", "python")
    project_id = strategy_pack.get("project_id", "default")

    if not code_snapshot:
        raise HTTPException(status_code=400, detail="缺少代码快照，无法执行")

    log.info(
        f"[adhoc_execute] 开始执行: language={code_language}, "
        f"project_id={project_id}, params={list(parameters.keys())}"
    )

    # 准备执行环境：按项目隔离挂载 + 时间戳命名输出目录
    # 沙箱容器挂载: uploads/project_{id} → /workspace（只挂当前项目，非整个 uploads）
    # 注意：需要两条路径 — 后端容器内路径用于文件操作，Mac宿主机路径用于 Docker bind mount
    from datetime import datetime
    project_host_dir = os.path.join(settings.UPLOAD_DIR, f"project_{project_id}")
    os.makedirs(project_host_dir, exist_ok=True)

    # Docker 守护进程运行在 Mac 宿主机上，bind mount 必须使用 Mac 宿主机路径
    # HOST_UPLOAD_DIR 指向 Mac 宿主机的 uploads 目录（如 /opt/data1/.../uploads）
    host_upload_base = os.environ.get("HOST_UPLOAD_DIR", settings.UPLOAD_DIR)
    docker_host_upload_dir = os.path.join(host_upload_base, f"project_{project_id}")

    # 生成输出目录名: 时间戳_分析简称_短ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 从策略描述中提取简短英文标识，或使用默认值
    strategy_text = strategy_pack.get("strategy", "analysis")
    short_name = _derive_short_name(strategy_text)
    short_id = request.message_id.replace("/", "_").replace("..", "_")[:8]
    output_dir_name = f"{timestamp}_{short_name}_{short_id}"

    # 容器内路径：项目目录是 /workspace 根
    container_out_dir = f"/workspace/results/{output_dir_name}"
    # 宿主机路径：在项目目录下的 results 子目录
    host_out_dir = os.path.join(project_host_dir, "results", output_dir_name)
    os.makedirs(host_out_dir, exist_ok=True)

    log.info(
        f"[adhoc_execute] 输出目录: host={host_out_dir}, container={container_out_dir}"
    )

    # 写入脚本文件到输出目录
    script_name = "latest_script.py" if code_language == "python" else "latest_script.R"
    script_path = os.path.join(host_out_dir, script_name)
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(code_snapshot)

    # 构建执行命令：必须使用沙箱容器内可见路径
    # 沙箱挂载 project_proj_{id} → /workspace，因此容器内路径为 /workspace/results/{name}/{script}
    container_script_path = f"{container_out_dir}/{script_name}"
    if code_language == "python":
        cmd = ["python", container_script_path]
    else:
        cmd = ["Rscript", container_script_path]

    # 追加命令行参数
    for key, value in parameters.items():
        if key.startswith("_") or key in ("code_snapshot", "code_language", "skill_id"):
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{key}")
        else:
            str_value = str(value)
            str_value = str_value.replace("${TASK_OUT_DIR}", container_out_dir)
            # 相对文件路径转绝对路径：项目目录即 /workspace 根，补全 /workspace/ 即可
            if (
                not str_value.startswith("/")
                and not str_value.startswith("$")
                and ("file" in key.lower() or "input" in key.lower())
            ):
                str_value = f"/workspace/{str_value}"
            cmd.append(f"--{key}")
            cmd.append(str_value)

    log.info(f"[adhoc_execute] 执行命令: {' '.join(cmd)}")

    # SSE 事件生成器：桥接同步 Docker 轮询与异步 SSE 流
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def log_callback(line: str):
            """同步回调：将日志行推入异步队列"""
            try:
                loop.call_soon_threadsafe(queue.put_nowait, ("log", line))
            except Exception:
                pass  # 队列满时丢弃日志，不影响主流程

        def run_docker():
            """在独立线程中执行 Docker 容器，通过回调推送日志"""
            try:
                log.info(f"[adhoc_execute] Docker 执行开始, cmd: {' '.join(cmd)}")
                output, exit_code, _ = run_container(
                    image='autonome-tool-env',
                    command=cmd,
                    language=code_language,
                    environment={"TASK_OUT_DIR": container_out_dir},
                    timeout=3600,
                    cli_mode=True,
                    user_id=user.id,
                    log_callback=log_callback,
                    # 按项目隔离挂载：使用 Mac 宿主机路径，Docker 守护进程才能解析
                    host_upload_dir=docker_host_upload_dir,
                    # 宿主机输出目录（用于 os.makedirs）
                    host_output_dir=host_out_dir,
                )
                log.info(
                    f"[adhoc_execute] Docker 执行结束: exit_code={exit_code}, "
                    f"output_len={len(output)}, output_head={output[:300]}"
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    ("done", {"output": output, "exit_code": exit_code}),
                )
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    ("error", str(e)),
                )

        # 发送初始化事件
        yield f"data: {json.dumps({'type': 'init', 'message': '沙箱启动中...', 'language': code_language})}\n\n"

        # 在独立线程中启动 Docker 执行
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_docker)

        try:
            while True:
                msg_type, data = await asyncio.wait_for(queue.get(), timeout=3600)
                if msg_type == "log":
                    yield f"data: {json.dumps({'type': 'log', 'line': data})}\n\n"
                elif msg_type == "done":
                    docker_output = data["output"]
                    exit_code = data["exit_code"]
                    success = exit_code == 0

                    log.info(
                        f"[adhoc_execute] 执行完成: exit_code={exit_code}, "
                        f"success={success}"
                    )

                    # 扫描输出目录，构建文件树
                    output_files = []
                    if host_out_dir and os.path.isdir(host_out_dir):
                        try:
                            for root, dirs, files in os.walk(host_out_dir):
                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    rel_path = os.path.relpath(fpath, host_out_dir)
                                    ext = os.path.splitext(fname)[1].lower()
                                    fsize = os.path.getsize(fpath)
                                    output_files.append({
                                        "path": rel_path,
                                        "name": fname,
                                        "ext": ext,
                                        "size": fsize,
                                        "preview": ext in (".png", ".jpg", ".jpeg", ".svg", ".pdf", ".html"),
                                    })
                        except Exception as scan_err:
                            log.warning(f"[adhoc_execute] 输出文件扫描失败: {scan_err}")

                    # 清理 Redis 中的策略包
                    try:
                        r.delete(strategy_key)
                    except Exception:
                        pass

                    # 推送最终结果（包含 project_id 用于前端文件预览）
                    yield f"data: {json.dumps({'type': 'result', 'status': 'success' if success else 'failed', 'output': docker_output[:5000] if success else None, 'error': docker_output[:2000] if not success else None, 'exit_code': exit_code, 'output_files': output_files, 'project_id': project_id, 'output_dir_name': output_dir_name})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                elif msg_type == "error":
                    log.error(f"[adhoc_execute] 执行异常: {data}")
                    yield f"data: {json.dumps({'type': 'result', 'status': 'failed', 'error': str(data), 'exit_code': -1, 'output_files': []})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
        finally:
            executor.shutdown(wait=False)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


class AdhocSaveSkillRequest(BaseModel):
    """即席分析固化技能请求"""
    message_id: str = Field(..., description="关联的 render_adhoc_card tool_call 的 message_id")
    skill_name: str = Field(..., description="用户指定的技能名称")
    description: str = Field(default="", description="技能描述")
    visibility: str = Field(default="private", description="可见性: private | team | public")
    category_name: str = Field(default="即席分析", description="分类名称")


@router.post("/adhoc/save-skill")
async def adhoc_save_skill(
    request: AdhocSaveSkillRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    将即席分析策略包固化为平台技能。

    程序说明：
    1. 从 Redis 读取策略包
    2. 调用 write_script_skill 创建技能目录和 SKILL.md
    3. 返回新技能 ID
    """
    import redis
    import hashlib

    # 从 Redis 读取策略包
    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        strategy_key = f"adhoc:{request.message_id}"
        strategy_json = r.get(strategy_key)
        if not strategy_json:
            raise HTTPException(status_code=404, detail="策略包已过期，请重新发起即席分析")
        strategy_pack = json.loads(strategy_json)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[adhoc_save_skill] Redis 读取失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取策略包失败: {str(e)}")

    code = strategy_pack.get("code", "")
    code_language = strategy_pack.get("code_language", "python")
    parameter_schema = strategy_pack.get("parameter_schema", {})

    # 生成 skill_id
    skill_id = f"adhoc_{hashlib.md5(code.encode()).hexdigest()[:12]}"

    # 确定 executor_type
    from app.models.skill_bundle import ExecutorType
    executor_type = ExecutorType.PYTHON_ENV if code_language == "python" else ExecutorType.R_ENV

    # 调用 skill_bundle_writer 写入文件系统
    from app.services.skill_bundle_writer import write_script_skill
    try:
        result = write_script_skill(
            skill_id=skill_id,
            name=request.skill_name,
            description=request.description or strategy_pack.get("strategy", ""),
            parameters_schema=parameter_schema,
            script_code=code,
            executor_type=executor_type,
            skills_dir="/app/skills",
            category="adhoc",
            category_name=request.category_name,
            tags=["adhoc", "generated"],
        )
        log.info(f"[adhoc_save_skill] 技能已固化: skill_id={skill_id}, files={result.get('files_created', [])}")
    except Exception as e:
        log.error(f"[adhoc_save_skill] 写入技能失败: {e}")
        raise HTTPException(status_code=500, detail=f"写入技能失败: {str(e)}")

    return {
        "status": "ok",
        "skill_id": skill_id,
        "skill_name": request.skill_name,
    }


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
