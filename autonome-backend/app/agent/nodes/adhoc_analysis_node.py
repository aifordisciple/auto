"""
即席交互式分析 Agent 节点 - 零样本即席分析策略包生成。

当用户指定数据文件并要求进行系统无预设技能的分析时路由到此节点。
调用 LLM 生成"策略包"（策略描述 + 代码 + 参数 Schema + 输入映射），
通过 Active Probing 挂起机制向前端推送分析策略卡片，
用户确认参数后恢复执行。

核心红线：
1. 代码与 Schema 同步锻造：绝不单纯抛出代码文本
2. 生成式 UI 拦截：系统拦截直接执行，向前端推送策略卡片
3. 异步沙箱触达：用户确认后唤醒 Docker 暖池执行
"""
import json
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from json_repair import repair_json

from app.agent.router.schemas import AgentState, ProbingRequest
from app.core.logger import log


# 即席分析策略包生成的系统提示词
ADHOC_SYSTEM_PROMPT = """你是一个生物信息学即席分析专家，擅长使用 R/Bioconductor 和 Python 生态进行数据分析和可视化。
用户希望对以下文件进行分析：{file_paths}
分析需求：{instruction}

你的任务是生成一份"分析策略包"，必须输出严格 JSON 格式，包含以下字段：

1. **strategy**: 简洁的文字描述分析逻辑（1-2 句话）
2. **code**: 完整的、带参数系统的 Python 或 R 代码
3. **code_language**: "python" 或 "r"
4. **parameter_schema**: 符合 JSON Schema 规范的参数定义，用于前端渲染表单。必须包含 default 值。
   **关键要求**：文件输入参数（如 expression_file、group_file 等）的 default 值必须使用上面列出的实际文件路径！
5. **input_mapping**: 将用户提供的文件路径映射到代码的输入参数名

⚠️ 代码语言选择规则（极其重要，必须严格遵守）：
- **涉及数据可视化必须使用 R 语言**：热图(heatmap)、火山图(volcano)、散点图(scatter)、箱线图(boxplot)、PCA 图、小提琴图(violin)、气泡图(dotplot/bubble)、韦恩图(Venn)、GO/KEGG 富集气泡图、染色体分布图等
- R 语言默认使用领域标准包：ggplot2（通用绑图，优先）、ComplexHeatmap（热图/聚类热图）、EnhancedVolcano（火山图）、pheatmap（简洁热图）、ggpubr（拼图/统计检验图）、ggrepel（标签避让）、ggsci（期刊色板）、RColorBrewer（色板）、patchwork/cowplot（拼图）
- 仅当分析需求完全不涉及可视化（如纯统计检验、数据清洗、格式转换）时，才使用 Python
- Python 可视化仅用于交互式图表（plotly）

⚠️ CNS 级出图规范（当 code_language 为 r 且涉及可视化时强制执行）：
- **双格式输出**：每张图必须同时保存 PDF 矢量图和 PNG 位图
  ```r
  ggsave(file.path(output_dir, "figure_name.pdf"), p, width=8, height=6, device="pdf")
  ggsave(file.path(output_dir, "figure_name.png"), p, width=8, height=6, dpi=300)
  ```
- **期刊级配色**：使用 ggsci::scale_color_npg() / scale_fill_npg() 或 scale_color_nejm() / scale_fill_lancet()（Nature/NEJM/Lancet 色板）
- **字体规范**：theme_minimal()/theme_bw() 基础 + 统一 Arial/Helvetica family（theme(text=element_text(family="Arial"))) + 字号 7-10pt
- **高分辨率**：PNG 至少 300 dpi，PDF 为矢量格式（无限分辨率）
- **完整注释**：轴标签含单位，图注清晰，必要时添加统计显著性标注（如 p 值星号）
- **尺寸合理**：宽 6-10 inches，高 4-8 inches，适合双栏/单栏排版

参数智能推断要求（重要）：
- 仔细分析用户需求中的关键词，自动推断参数默认值
- 常见模式识别：
  * 提到"红色"/"蓝色"/"绿色"等 → color_palette 或 color_scheme 参数
  * 提到"log2"/"log10"/"标准化"/"归一化" → transform 或 normalization 参数
  * 提到"p值"/"显著性"/"阈值" → p_value 或 threshold 参数（默认应匹配用户要求）
  * 提到"聚类"/"分组"/"分类" → cluster 或 group 参数
  * 提到具体数值（如"前100个"、"top 50"）→ top_n 或 n_genes 参数
  * 提到"热图"/"散点图"/"箱线图"/"火山图"等 → plot_type 参数
- 如果有文件探查结果，严格使用探查出的列名来生成参数和代码，不要编造列名

⚠️ 输入文件路径识别（极其重要，必须严格遵守）：
- 文件列表中的每个文件路径（如 /workspace/expression.csv、/workspace/project_xxx/sample.fastq.gz）就是沙箱容器内真实可访问的文件路径
- 代码中读取输入文件时，必须使用 argparse/optparse 接收的参数值，直接传递给 pd.read_csv() 等读取函数
- 绝对不要编造、简化或修改文件路径！如果文件列表显示路径是 "/workspace/project_abc123/sample.csv"，代码中就必须使用这个完整路径
- parameter_schema 中 file 类型参数的 default 值必须是文件列表中的完整路径（如 "/workspace/expression.csv"），不要使用相对路径或文件名
- input_mapping 必须将文件路径正确映射到代码参数名，例如：{{ "/workspace/expression.csv": "expression_file", "/workspace/group.csv": "group_file" }}

⚠️ 输出目录规则（极其重要，必须严格遵守）：
- 所有输出文件（图表、结果表格等）必须写入 TASK_OUT_DIR 环境变量指定的目录
- Python: output_dir = os.environ["TASK_OUT_DIR"]
- R: output_dir <- Sys.getenv("TASK_OUT_DIR")
- 绝对不要将输出写入当前工作目录、硬编码路径（如 /tmp、/output）或其他位置
- 代码示例 Python: plt.savefig(os.path.join(os.environ["TASK_OUT_DIR"], "heatmap.png"))
- 代码示例 R: ggsave(file.path(Sys.getenv("TASK_OUT_DIR"), "heatmap.png"))

代码要求：
- Python 必须使用 argparse，R 必须使用 optparse 或 commandArgs
- 必须为所有参数设定符合生信经验的默认值（如 p-value 默认 0.05，聚类默认开启）
- 输出目录使用 TASK_OUT_DIR 环境变量（见上方输出目录规则）
- 代码必须完整可执行，不能有省略或占位符
- 文件输入参数的默认值必须使用用户实际提供的文件路径（见上方输入文件路径识别）

参数 Schema 要求：
- 每个参数必须有 type、title、default
- file 类型参数的 default 必须是用户实际提供的文件路径，不能是占位路径
- 可选参数使用 enum 提供选项列表
- 数值参数可提供 minimum、maximum、step
- 参数 title 应使用中文，简洁易懂

进度报告要求：
- autonome_progress 函数已由系统预先注入到执行环境中，你只需要直接调用它，绝对不要在代码中重复定义
- 不要生成 def autonome_progress 或 autonome_progress <- function 等函数定义语句
- 在代码的关键步骤调用进度报告函数：
  * Python: autonome_progress(step, total, message)
  * R:      autonome_progress(step, total, message)
- 将分析流程分解为 3-6 个关键步骤，如：加载数据、数据预处理、执行分析、生成图表、保存结果
- 每个步骤调用一次 autonome_progress，step 从 1 递增，total 为总步骤数
- 进度消息使用中文，简洁描述当前步骤（不超过 15 字）

输出示例：
```json
{{
  "strategy": "使用 ComplexHeatmap 对表达矩阵进行行标准化并绘制聚类热图",
  "code": "library(optparse)\\n...",
  "code_language": "r",
  "parameter_schema": {{
    "type": "object",
    "properties": {{
      "cluster_rows": {{ "type": "boolean", "title": "行聚类", "default": true }},
      "color_palette": {{ "type": "string", "title": "配色方案", "enum": ["npg", "jco", "lancet"], "default": "npg" }}
    }}
  }},
  "input_mapping": {{ "input_file_param": "input", "file_id": "{{file_id}}" }}
}}
```

请严格按照上述 JSON 格式输出，不要输出任何其他内容。"""


async def adhoc_analysis_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    即席交互式分析 Agent 节点。

    程序说明：
    1. 从 AgentState 中获取当前 TaskNode 的指令和文件信息
    2. 调用 LLM（thinking 模型）生成策略包
    3. 将策略包存入 TaskNode.adhoc_metadata
    4. 生成 ProbingRequest(render_type="adhoc_card") 触发前端渲染
    5. 不推进 current_task_idx，等待用户确认

    降级策略：
    - LLM 调用失败 → 降级为 Skill Forge 意图，返回 skill_forge_node 路由
    - JSON 解析失败 → 使用 json_repair 修复，修复失败则降级
    """
    intent_data = state.get("intent_data", {})
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])

    # 获取当前 TaskNode 的指令和文件信息
    current_task = nodes[idx] if idx < len(nodes) else {}
    raw_instruction = current_task.get("raw_instruction", "")
    resolved_assets = current_task.get("resolved_assets", [])
    file_id = resolved_assets[0] if resolved_assets else "unknown"

    log.info(f"[adhoc_analysis_node] 生成策略包: file_id={file_id}, instruction='{raw_instruction[:50]}...'")

    # 调用 LLM 生成策略包
    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    try:
        # 将 resolved_assets 拼接为 file_paths 字符串，填入参数默认值
        assets_paths = "\n  - ".join(resolved_assets) if resolved_assets else ""
        if assets_paths:
            assets_paths = f"  - {assets_paths}"

        # 探查输入文件结构，注入 LLM prompt 以提升代码和参数准确性
        # resolved_assets 是沙箱路径（如 /workspace/expression.csv），需转换为宿主机路径
        file_profiles_text = ""
        if resolved_assets:
            try:
                from pathlib import Path
                from app.core.config import settings as prof_settings
                from app.services.file_profiler import profile_files, format_profiles_for_prompt

                context = state.get("context", {})
                project_id = context.get("project_id")
                if project_id:
                    project_host_dir = str(Path(prof_settings.UPLOAD_DIR) / f"project_{project_id}")
                    # 将沙箱路径 /workspace/filename 转换为宿主机路径
                    host_file_paths = []
                    for asset in resolved_assets:
                        # 提取文件名（去掉 /workspace/ 前缀）
                        filename = asset.replace("/workspace/", "") if asset.startswith("/workspace/") else asset
                        host_file_paths.append(f"{project_host_dir}/{filename}")
                    profiles = profile_files(host_file_paths)
                    file_profiles_text = format_profiles_for_prompt(profiles)
                    log.info(f"[adhoc_analysis_node] 文件探查完成: {len(profiles)} 个文件")
            except Exception as prof_err:
                log.warning(f"[adhoc_analysis_node] 文件探查失败（非致命）: {prof_err}")

        strategy_pack = await _generate_strategy_pack(
            file_id=file_id,
            instruction=raw_instruction,
            session=session,
            user_id=user_id,
            file_paths=assets_paths,
            file_profiles_text=file_profiles_text,
        )
    except Exception as e:
        log.error(f"[adhoc_analysis_node] 策略包生成失败，降级为 Skill Forge: {e}")
        # 降级：修改当前 TaskNode 的意图为 SKILL_FORGE
        nodes[idx]["intent"] = "INTENT_SKILL_FORGE"
        return {
            "intent_data": {**intent_data, "node": "skill_forge_node", "system_prompt_key": "forge"},
            "dag": dag,
        }

    # 将策略包存入 TaskNode.adhoc_metadata
    nodes[idx]["adhoc_metadata"] = strategy_pack

    # 策略包同时存入 Redis，供前端 /api/chat/adhoc/execute 端点读取
    # 使用 UUID 生成唯一 message_id，通过共享函数 _store_strategy_pack_to_redis 存储
    import uuid

    message_id = str(uuid.uuid4())
    strategy_pack["message_id"] = message_id
    _store_strategy_pack_to_redis(strategy_pack, message_id)

    # 生成 ProbingRequest 触发前端渲染即席分析卡片
    probing_request = ProbingRequest(
        is_missing=True,
        missing_params=["adhoc_confirmation"],
        render_type="adhoc_card",
        adhoc_card_data=strategy_pack,
        message_to_user="即席分析策略已生成，请在卡片上确认参数后执行",
    )

    log.info("[adhoc_analysis_node] 策略包生成成功，挂起等待用户确认")

    return {
        "intent_data": {**intent_data, "node": "adhoc_analysis_node"},
        "dag": dag,
        "active_probing": probing_request.model_dump(),
        # 不推进 current_task_idx，等待用户确认
    }


async def _generate_strategy_pack(
    file_id: str,
    instruction: str,
    session: Any,
    user_id: Any,
    file_paths: str = "",
    enable_think: bool = False,
    file_profiles_text: str = "",
) -> Dict[str, Any]:
    """
    调用 LLM 生成即席分析策略包。

    程序说明：
    默认使用 fast 模型（非 thinking），因为策略包生成是纯 JSON 输出任务，
    不需要深度推理，且 thinking 模型耗时过长（>3 分钟）。
    仅当用户在前端开启深度思考模式（enable_think=True）时使用 thinking 模型。

    Args:
        file_id: 用户指定的文件 ID
        instruction: 用户的分析需求描述
        session: 数据库会话
        user_id: 用户 ID
        file_paths: 用户实际提供的文件路径（换行分隔），用于填充参数默认值
        enable_think: 深度思考模式开关（由前端传递，默认关闭）
        file_profiles_text: 文件探查结果文本，注入 LLM prompt 以提升代码和参数准确性

    Returns:
        策略包字典，包含 strategy、code、code_language、parameter_schema、input_mapping
    """
    from app.utils.llm_config import get_fast_llm_config, get_thinking_llm_config

    # 根据用户是否开启深度思考模式选择模型：开启 → thinking，关闭 → fast
    if enable_think:
        llm_config = get_thinking_llm_config(session, user_id)
    else:
        llm_config = get_fast_llm_config(session, user_id)
    api_key = llm_config.api_key or "not-needed"
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
        model=llm_config.model_name,
        temperature=0.0,
    )

    # 构造 system prompt，注入文件探查结果以提升参数准确性
    system_prompt = ADHOC_SYSTEM_PROMPT
    if file_profiles_text:
        system_prompt += (
            "\n\n**输入文件自动探查结果**（请严格根据以下列名和数据类型生成代码和参数）：\n"
            f"{file_profiles_text}\n"
        )

    # 构造提示词（必须包含 user 消息，否则部分 LLM 提供商会报错 "No user query found in messages"）
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "请根据以上要求生成即席分析策略包，输出严格 JSON 格式。"),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "file_paths": file_paths or file_id,
        "instruction": instruction,
    })

    # 解析 LLM 输出为 JSON
    raw_content = response.content.strip()
    # 移除可能的 markdown 代码块标记
    if raw_content.startswith("```"):
        lines = raw_content.split("\n")
        # 去掉首行 ```json 和末行 ```
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_content = "\n".join(lines)

    repaired = repair_json(raw_content)
    strategy_pack = json.loads(repaired)

    # 验证策略包必需字段
    required_keys = ["strategy", "code", "code_language", "parameter_schema", "input_mapping"]
    for key in required_keys:
        if key not in strategy_pack:
            raise ValueError(f"策略包缺少必需字段: {key}")

    log.info(
        f"[adhoc_analysis_node] 策略包验证通过: "
        f"language={strategy_pack.get('code_language')}, "
        f"params={list(strategy_pack.get('parameter_schema', {}).get('properties', {}).keys())}"
    )

    return strategy_pack


async def _generate_strategy_pack_streaming(
    file_id: str,
    instruction: str,
    session: Any,
    user_id: Any,
    file_paths: str = "",
    enable_think: bool = False,
    file_profiles_text: str = "",
):
    """
    流式生成即席分析策略包，通过异步生成器推送各阶段进度事件。

    程序说明：
    使用 ChatOpenAI streaming=True + chain.astream() 实现 token 级流式输出。
    通过检测 JSON 顶层字段边界来识别当前生成阶段，向前端推送分阶段进度事件。
    前端消费这些事件实现渐进式卡片渲染，消除 10-30s 的骨架屏空等。

    生成阶段：
    1. understanding → L1 分类完成，开始理解需求
    2. planning → 正在输出 strategy 字段
    3. coding → 正在输出 code 字段
    4. params → 正在输出 parameter_schema 字段
    5. validating → 解析 JSON + 字段校验

    Yields:
        {"type": "stage", "stage": str, "message": str}  — 阶段变更事件
        {"type": "chunk", "stage": str, "content": str}   — 流式内容块
        {"type": "complete", "data": dict}                — 完整策略包
        {"type": "error", "message": str}                 — 生成失败
    """
    import re
    from app.utils.llm_config import get_fast_llm_config, get_thinking_llm_config

    # Stage 1: 理解需求（L1+L2 分类已完成，直接通知前端开始生成）
    yield {
        "type": "stage",
        "stage": "understanding",
        "message": "正在理解您的分析需求...",
    }

    # 根据深度思考模式选择模型
    if enable_think:
        llm_config = get_thinking_llm_config(session, user_id)
    else:
        llm_config = get_fast_llm_config(session, user_id)

    api_key = llm_config.api_key or "not-needed"
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
        model=llm_config.model_name,
        temperature=0.0,
        streaming=True,
    )

    # 构建 system prompt，注入文件探查结果以提升参数准确性
    system_prompt = ADHOC_SYSTEM_PROMPT
    if file_profiles_text:
        system_prompt += (
            "\n\n**输入文件自动探查结果**（请严格根据以下列名和数据类型生成代码和参数）：\n"
            f"{file_profiles_text}\n"
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "请根据以上要求生成即席分析策略包，输出严格 JSON 格式。"),
    ])

    # Stage 2: 设计策略（LLM 开始输出 strategy 字段）
    yield {
        "type": "stage",
        "stage": "planning",
        "message": "正在设计分析策略...",
    }

    chain = prompt | llm
    full_content = ""
    current_stage = "planning"

    try:
        async for chunk in chain.astream({
            "file_paths": file_paths or file_id,
            "instruction": instruction,
        }):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_content += content

            # 检测 JSON 顶层字段边界，切换阶段
            # 字段生成顺序固定: strategy → code → code_language → parameter_schema → input_mapping
            if current_stage == "planning" and re.search(r'"code"\s*:\s*"', full_content):
                current_stage = "coding"
                yield {
                    "type": "stage",
                    "stage": "coding",
                    "message": "正在生成分析代码...",
                }
            elif current_stage == "coding" and re.search(r'"parameter_schema"\s*:\s*\{', full_content):
                current_stage = "params"
                yield {
                    "type": "stage",
                    "stage": "params",
                    "message": "正在构建参数表单...",
                }

            # 推送流式内容块
            yield {"type": "chunk", "stage": current_stage, "content": content}

    except Exception as stream_err:
        log.error(f"[adhoc_analysis_node] 流式生成失败: {stream_err}")
        yield {
            "type": "error",
            "message": f"策略包生成失败: {stream_err}",
        }
        return

    # Stage 5: 解析和校验
    yield {
        "type": "stage",
        "stage": "validating",
        "message": "正在校验策略包...",
    }

    # 解析 JSON
    raw_content = full_content.strip()
    if raw_content.startswith("```"):
        lines = raw_content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_content = "\n".join(lines)

    try:
        repaired = repair_json(raw_content)
        strategy_pack = json.loads(repaired)

        # 验证策略包必需字段
        required_keys = ["strategy", "code", "code_language", "parameter_schema", "input_mapping"]
        for key in required_keys:
            if key not in strategy_pack:
                raise ValueError(f"策略包缺少必需字段: {key}")

        log.info(
            f"[adhoc_analysis_node] 流式策略包验证通过: "
            f"language={strategy_pack.get('code_language')}, "
            f"params={list(strategy_pack.get('parameter_schema', {}).get('properties', {}).keys())}"
        )

        # 代码语法校验（非阻塞，校验结果附加到策略包中供前端展示）
        try:
            from app.services.code_validator import validate_generated_code, auto_fix_generated_code
            validation = validate_generated_code(
                code=strategy_pack.get("code", ""),
                language=strategy_pack.get("code_language", "python"),
            )
            strategy_pack["_validation"] = {
                "is_valid": validation.is_valid,
                "status_text": validation.status_text,
                "status_icon": validation.status_icon,
                "issues": [
                    {"severity": i.severity, "message": i.message, "suggestion": i.suggestion}
                    for i in validation.issues
                ],
            }

            # 若校验发现错误，自动拉起 LLM Agent 修复代码
            if validation.error_count > 0:
                log.info(
                    f"[adhoc_analysis_node] 代码校验发现 {validation.error_count} 个错误，"
                    f"启动 LLM Agent 自动修复..."
                )
                fix_result = await auto_fix_generated_code(
                    code=strategy_pack.get("code", ""),
                    language=strategy_pack.get("code_language", "python"),
                    instruction=instruction,
                    issues=validation.issues,
                    session=session,
                    user_id=user_id,
                )
                strategy_pack["_auto_fix"] = {
                    "fixed_code": fix_result.get("fixed_code"),
                    "changes_description": fix_result.get("changes_description"),
                    "success": fix_result.get("success"),
                    "re_validation": fix_result.get("re_validation"),
                }
                if fix_result.get("success") and fix_result.get("fixed_code"):
                    log.info("[adhoc_analysis_node] LLM Agent 自动修复成功，已附加到策略包")
                else:
                    log.warning("[adhoc_analysis_node] LLM Agent 自动修复未完全解决问题")
        except Exception as val_err:
            log.warning(f"[adhoc_analysis_node] 代码校验/修复失败（非致命）: {val_err}")

        yield {"type": "complete", "data": strategy_pack}
    except Exception as parse_err:
        log.error(f"[adhoc_analysis_node] 策略包 JSON 解析失败: {parse_err}")
        # 尝试 json_repair 修复后再试
        try:
            repaired_again = repair_json(raw_content, skip_json_loads=True)
            strategy_pack = json.loads(repaired_again)
            required_keys = ["strategy", "code", "code_language", "parameter_schema", "input_mapping"]
            for key in required_keys:
                if key not in strategy_pack:
                    raise ValueError(f"策略包缺少必需字段: {key}")
            # 重试路径也做代码校验 + 自动修复
            try:
                from app.services.code_validator import validate_generated_code, auto_fix_generated_code
                validation = validate_generated_code(
                    code=strategy_pack.get("code", ""),
                    language=strategy_pack.get("code_language", "python"),
                )
                strategy_pack["_validation"] = {
                    "is_valid": validation.is_valid,
                    "status_text": validation.status_text,
                    "status_icon": validation.status_icon,
                    "issues": [
                        {"severity": i.severity, "message": i.message, "suggestion": i.suggestion}
                        for i in validation.issues
                    ],
                }
                if validation.error_count > 0:
                    fix_result = await auto_fix_generated_code(
                        code=strategy_pack.get("code", ""),
                        language=strategy_pack.get("code_language", "python"),
                        instruction=instruction,
                        issues=validation.issues,
                        session=session,
                        user_id=user_id,
                    )
                    strategy_pack["_auto_fix"] = {
                        "fixed_code": fix_result.get("fixed_code"),
                        "changes_description": fix_result.get("changes_description"),
                        "success": fix_result.get("success"),
                        "re_validation": fix_result.get("re_validation"),
                    }
            except Exception as val_err:
                log.warning(f"[adhoc_analysis_node] 代码校验失败（非致命）: {val_err}")
            yield {"type": "complete", "data": strategy_pack}
        except Exception:
            yield {
                "type": "error",
                "message": f"策略包解析失败: {parse_err}",
            }


def _store_strategy_pack_to_redis(
    strategy_pack: Dict[str, Any],
    message_id: str,
    project_id: str | None = None,
) -> bool:
    """
    将策略包存入 Redis，供 /api/chat/adhoc/execute 端点读取。

    这是 Chat 路径和 Graph 路径的共享函数，统一 key 格式为 adhoc:{message_id}。

    Args:
        strategy_pack: LLM 生成的策略包字典
        message_id: 消息唯一标识符（Chat 路径用 user_msg.id，Graph 路径用 UUID）
        project_id: 项目 ID（可选，Chat 路径传入用于 execute 时确定文件系统范围）

    Returns:
        True 表示存储成功，False 表示存储失败（非致命错误）
    """
    import redis as redis_client
    from app.core.config import settings as app_settings

    redis_data = {**strategy_pack}
    if project_id:
        redis_data["project_id"] = project_id

    try:
        r = redis_client.Redis(
            host=app_settings.REDIS_HOST,
            port=app_settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        r.setex(f"adhoc:{message_id}", 3600, json.dumps(redis_data, ensure_ascii=False))
        log.info(f"[adhoc] 策略包已存入 Redis: key=adhoc:{message_id}")
        return True
    except Exception as redis_err:
        log.warning(f"[adhoc] Redis 存储失败（非致命）: {redis_err}")
        return False
