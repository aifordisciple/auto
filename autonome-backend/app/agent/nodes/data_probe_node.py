"""
Data Probe Agent 节点 - 数据预览与探查。

当用户需要查看数据结构、预览数据内容时路由到此节点。
使用 LLM 工具调用循环（tool-calling loop）主动调用 probe_tools.py 中的探针工具，
将探查结果写入 task_results 并推进 DAG 指针。

升级要点：
- 从空壳升级为完整的 LLM 工具调用执行器
- 支持 Ollama 原生客户端和 ChatOpenAI 双路径
- 路径安全：所有文件/目录操作限定在项目工作区内
- 工具调用循环：最多 5 轮，自动收集结果
- DAG 指针推进：记录结果后推进到下一个任务
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from app.agent.router.schemas import AgentState
from app.core.config import settings
from app.core.logger import log
from app.tools.probe_tools import probe_tools_list
from app.utils.llm_config import get_fast_llm_config, _is_local_model, _is_ollama


# 数据探查节点的系统提示词
DATA_PROBE_SYSTEM_PROMPT = """你是一个专业的生物信息学数据探查助手。你的核心职责是使用探针工具帮助用户了解数据。

核心原则：
- 用中文回答问题
- 必须主动调用探针工具来获取信息，不要凭猜测回答
- 工具调用后，用中文整理和解读结果，提供专业建议
- 不要在回答开头重复自己的身份，直接进入正题

## 可用探针工具（11个）

### 文件系统与目录
- **scan_workspace**: 扫描工作区目录结构，列出文件和子目录
- **match_paired_fastq**: 配对双端 FASTQ 文件（R1/R2），检测落单文件

### 表格数据探查
- **peek_tabular_data**: 预览表格文件（CSV/TSV/TXT），显示表头、行列数
- **detect_na**: 缺失值检测，逐列统计 NA/NaN/空值数量和占比
- **compute_summary_stats**: 数值列汇总统计（min/max/mean/quartiles），推断 Log 转换状态
- **compute_set_operations**: 两个文件列之间的集合运算（交集/并集/差集）

### 编码与格式检测
- **detect_file_encoding**: 检测文件字符编码和分隔符类型

### 多组学文件探查
- **inspect_h5ad**: AnnData 对象探查（obs/var/X 层维度）
- **inspect_fastq**: FASTQ 文件质量摘要（读长分布、碱基质量）
- **inspect_bam**: BAM 文件比对统计 + Header 解析（@SQ/@RG/@PG）
- **inspect_vcf**: VCF 文件变异统计（样本列表、染色体分布、变异类型）

## 工具选择指南
- "有哪些文件" / "目录结构" → scan_workspace
- "查看文件内容" / "表头" → peek_tabular_data
- "缺失值" / "NA 比例" → detect_na
- "统计" / "min/max" / "分布" → compute_summary_stats
- "编码" / "分隔符" → detect_file_encoding
- "重叠" / "交集" / "Venn" → compute_set_operations
- "配对 FASTQ" / "R1 R2" → match_paired_fastq
- "h5ad" / "AnnData" → inspect_h5ad
- "FASTQ 质量" → inspect_fastq
- "BAM" / "比对" / "参考基因组" → inspect_bam
- "VCF" / "变异" / "样本" → inspect_vcf

当前项目工作区路径：{workspace_path}
所有文件操作限定在此目录内。"""


# 路径参数名映射：工具名 → 需要安全校验的参数名列表
PATH_PARAM_MAP: Dict[str, list] = {
    "scan_workspace": ["directory_path"],
    "peek_tabular_data": ["file_path"],
    "detect_na": ["file_path"],
    "compute_summary_stats": ["file_path"],
    "detect_file_encoding": ["file_path"],
    "compute_set_operations": ["file_path_1", "file_path_2"],
    "inspect_vcf": ["file_path"],
    "match_paired_fastq": ["directory_path"],
}


def _apply_path_safety(
    tool_name: str,
    tool_args: Dict[str, Any],
    project_dir: str,
) -> Dict[str, Any]:
    """
    对工具参数中的文件/目录路径进行安全修正，强制限定在项目目录内。

    处理策略：
    - 相对路径 → 拼接到项目目录下
    - 绝对路径但不在项目目录内 → 替换为项目目录
    - 已在项目目录内的绝对路径 → 保持不变
    """
    path_keys = PATH_PARAM_MAP.get(tool_name, [])
    for path_key in path_keys:
        if path_key not in tool_args:
            continue
        requested_path = tool_args[path_key]
        if not requested_path.startswith("/"):
            # 相对路径 → 拼接
            corrected = os.path.join(project_dir, requested_path)
            log.info(f"[data_probe_node] 路径拼接: {requested_path} → {corrected}")
            tool_args[path_key] = corrected
        elif not requested_path.startswith(project_dir):
            # 绝对路径但不在项目目录内 → 限制在项目目录
            log.warning(
                f"[data_probe_node] 路径限制: {requested_path} 不在项目目录内，"
                f"替换为 {project_dir}"
            )
            tool_args[path_key] = project_dir
    return tool_args


async def data_probe_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Data Probe Agent 节点 —— LLM 工具调用执行器。

    从 DAG 中提取当前任务参数，使用 LLM + 绑定的探针工具执行数据探查，
    将探查结果写入 task_results 并推进 DAG 指针。

    执行流程：
    1. 提取当前 TaskNode 和用户查询
    2. 解析 LLM 配置（通过 configurable 获取 session/user_id）
    3. 构建系统提示词 + 绑定 11 个探针工具
    4. 运行工具调用循环（最多 5 轮，兼容 Ollama / ChatOpenAI 双路径）
    5. 路径安全校验：所有文件操作限定在项目目录内
    6. 将最终 AI 回复写入 task_results[task_id]，推进 current_task_idx
    """
    # 1. 提取当前任务信息
    messages = state.get("messages", [])
    context = state.get("context", {})
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    idx = state.get("current_task_idx", 0)

    # 获取当前任务节点
    if idx < len(nodes):
        current_task = nodes[idx]
    else:
        log.warning("[data_probe_node] current_task_idx 超出 DAG 范围，降级为空结果")
        return {
            "intent_data": state.get("intent_data", {}),
            "current_task_idx": idx + 1,
            "task_results": {**state.get("task_results", {}), "unknown": {"status": "error", "reason": "index_out_of_range"}},
        }

    task_id = current_task.get("task_id", f"task_{idx}")
    task_params = current_task.get("parameters", {})
    raw_instruction = current_task.get("raw_instruction", "")
    # 优先使用 task 的 resolved_assets 中的文件，其次使用 context 中的 active_file
    resolved_assets = current_task.get("resolved_assets", [])
    active_file = (
        resolved_assets[0] if resolved_assets
        else context.get("active_file", "")
    )

    # 用户查询：优先使用 raw_instruction，其次使用最后一条消息
    user_query = raw_instruction or (messages[-1].content if messages else "")
    if not user_query:
        log.warning("[data_probe_node] 用户查询为空，降级为空结果")
        task_results = state.get("task_results", {})
        task_results[task_id] = {"status": "error", "reason": "empty_query"}
        return {
            "intent_data": state.get("intent_data", {}),
            "current_task_idx": idx + 1,
            "task_results": task_results,
        }

    log.info(
        f"[data_probe_node] 处理任务: task_id={task_id}, query='{user_query[:80]}...', "
        f"active_file={active_file}"
    )

    # 2. 解析 LLM 配置
    configurable = config.get("configurable", {})
    session = configurable.get("session")
    user_id = configurable.get("user_id")

    if not session or not user_id:
        log.warning("[data_probe_node] 缺少 session/user_id，降级为空结果")
        task_results = state.get("task_results", {})
        task_results[task_id] = {"status": "error", "reason": "missing_config"}
        return {
            "intent_data": state.get("intent_data", {}),
            "current_task_idx": idx + 1,
            "task_results": task_results,
        }

    # 获取项目工作区路径
    project_id = context.get("project_id", "")
    if not project_id:
        log.warning("[data_probe_node] 缺少 project_id，降级为空结果")
        task_results = state.get("task_results", {})
        task_results[task_id] = {"status": "error", "reason": "missing_project_id"}
        return {
            "intent_data": state.get("intent_data", {}),
            "current_task_idx": idx + 1,
            "task_results": task_results,
        }

    project_dir = str(Path(settings.UPLOAD_DIR) / f"project_{project_id}")
    workspace_path = project_dir

    # 解析 LLM 配置
    try:
        llm_config = get_fast_llm_config(session, user_id)
    except Exception as e:
        log.error(f"[data_probe_node] LLM 配置解析失败: {e}")
        task_results = state.get("task_results", {})
        task_results[task_id] = {"status": "error", "reason": f"llm_config_error: {e}"}
        return {
            "intent_data": state.get("intent_data", {}),
            "current_task_idx": idx + 1,
            "task_results": task_results,
        }

    is_local = _is_local_model(llm_config.base_url)
    is_ollama = _is_ollama(llm_config.base_url)
    api_key = llm_config.api_key or "not-needed"

    log.info(
        f"[data_probe_node] LLM: model={llm_config.model_name}, "
        f"is_local={is_local}, is_ollama={is_ollama}"
    )

    # 3. 构建系统提示词
    system_prompt = DATA_PROBE_SYSTEM_PROMPT.format(workspace_path=workspace_path)

    # 如果有 active_file，追加文件上下文提示
    if active_file:
        system_prompt += f"\n\n用户当前关注的文件: {active_file}"
    if task_params:
        system_prompt += f"\n\n用户指定的参数: {json.dumps(task_params, ensure_ascii=False)}"

    # 构建消息列表
    lc_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    # 4. 工具调用循环
    accumulated_response = ""
    max_tool_rounds = 5

    try:
        if is_ollama:
            # === Ollama 原生客户端路径 ===
            accumulated_response = await _run_ollama_tool_loop(
                llm_config=llm_config,
                messages=lc_messages,
                project_dir=project_dir,
                max_rounds=max_tool_rounds,
            )
        else:
            # === ChatOpenAI 兼容路径（第三方 API + 本地 vLLM/LiteLLM） ===
            accumulated_response = await _run_openai_tool_loop(
                llm_config=llm_config,
                api_key=api_key,
                messages=lc_messages,
                project_dir=project_dir,
                max_rounds=max_tool_rounds,
            )

    except Exception as e:
        log.error(f"[data_probe_node] 工具调用循环失败: {e}")
        accumulated_response = f"数据探查失败: {str(e)}"

    # 5. 写入结果并推进 DAG 指针
    task_results = state.get("task_results", {})
    task_results[task_id] = {
        "status": "success",
        "node": "data_probe_node",
        "result": accumulated_response,
    }

    intent_data = state.get("intent_data", {})
    intent_data["node"] = "data_probe_node"

    log.info(
        f"[data_probe_node] 任务完成: task_id={task_id}, "
        f"response_len={len(accumulated_response)}, next_idx={idx + 1}"
    )

    return {
        "intent_data": intent_data,
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }


async def _run_ollama_tool_loop(
    llm_config: Any,
    messages: list,
    project_dir: str,
    max_rounds: int = 5,
) -> str:
    """Ollama 原生客户端工具调用循环。"""
    import ollama as ollama_sdk

    host = llm_config.base_url
    if host and host.endswith('/v1'):
        host = host[:-3]
    if not host:
        host = "http://localhost:11434"

    client = ollama_sdk.AsyncClient(host=host)

    # 将 LangChain @tool 转为 Ollama tools 格式
    ollama_tools = []
    for t in probe_tools_list:
        tool_schema = {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": (
                    t.args_schema.schema()
                    if hasattr(t, 'args_schema') and t.args_schema
                    else {}
                ),
            },
        }
        ollama_tools.append(tool_schema)

    ollama_messages = [
        {'role': m['role'], 'content': m['content']}
        for m in messages
    ]

    accumulated = ""
    for round_idx in range(max_rounds):
        response = await client.chat(
            model=llm_config.model_name,
            messages=ollama_messages,
            tools=ollama_tools,
            options={'temperature': 0.0},
        )

        # 收集文本内容
        if response.get('message', {}).get('content'):
            accumulated += response['message']['content']

        # 检查工具调用
        tool_calls = response.get('message', {}).get('tool_calls', [])
        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc['function']['name']
            tool_args = tc['function']['arguments']
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    tool_args = {}

            log.info(f"[data_probe_node] Ollama 工具调用: {tool_name}({tool_args})")

            # 路径安全修正
            tool_args = _apply_path_safety(tool_name, tool_args, project_dir)

            # 执行工具
            tool_result = ""
            try:
                for t in probe_tools_list:
                    if t.name == tool_name:
                        tool_result = t.invoke(tool_args)
                        break
            except Exception as te:
                tool_result = f"工具执行失败: {str(te)}"
                log.error(f"[data_probe_node] 工具执行失败: {tool_name}, error={te}")

            accumulated += f"\n\n{tool_result}"

            # 追加工具调用和结果到消息列表
            ollama_messages.append({
                'role': 'assistant',
                'content': '',
                'tool_calls': [{'function': {'name': tool_name, 'arguments': tool_args}}],
            })
            ollama_messages.append({
                'role': 'tool',
                'content': tool_result,
            })

    return accumulated.strip()


async def _run_openai_tool_loop(
    llm_config: Any,
    api_key: str,
    messages: list,
    project_dir: str,
    max_rounds: int = 5,
) -> str:
    """ChatOpenAI 兼容路径工具调用循环（第三方 API + 本地 vLLM/LiteLLM）。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
        model=llm_config.model_name,
        temperature=0.0,
    )
    llm_with_tools = llm.bind_tools(probe_tools_list)

    # 构建 LangChain 消息
    lc_messages = []
    for m in messages:
        if m['role'] == 'system':
            lc_messages.append(SystemMessage(content=m['content']))
        elif m['role'] == 'user':
            lc_messages.append(HumanMessage(content=m['content']))

    accumulated = ""
    for round_idx in range(max_rounds):
        response = await llm_with_tools.ainvoke(lc_messages)

        # 收集文本内容
        if response.content:
            accumulated += response.content

        # 检查工具调用
        if not hasattr(response, 'tool_calls') or not response.tool_calls:
            break

        # 追加 AI 消息
        lc_messages.append(response)

        for tc in response.tool_calls:
            tool_name = tc['name']
            tool_args = tc.get('args', {})
            log.info(f"[data_probe_node] LangChain 工具调用: {tool_name}({tool_args})")

            # 路径安全修正
            tool_args = _apply_path_safety(tool_name, tool_args, project_dir)

            # 执行工具
            tool_result = ""
            try:
                for t in probe_tools_list:
                    if t.name == tool_name:
                        tool_result = t.invoke(tool_args)
                        break
            except Exception as te:
                tool_result = f"工具执行失败: {str(te)}"
                log.error(f"[data_probe_node] 工具执行失败: {tool_name}, error={te}")

            accumulated += f"\n\n{tool_result}"

            # 追加 ToolMessage
            lc_messages.append(ToolMessage(
                content=tool_result,
                tool_call_id=tc.get('id', ''),
            ))

    return accumulated.strip()
