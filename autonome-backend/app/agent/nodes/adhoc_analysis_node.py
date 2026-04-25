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
from app.utils.llm_config import get_thinking_llm_config


# 即席分析策略包生成的系统提示词
ADHOC_SYSTEM_PROMPT = """你是一个生物信息学即席分析专家。
用户希望对文件 {file_id} 进行以下分析：{instruction}

你的任务是生成一份"分析策略包"，必须输出严格 JSON 格式，包含以下字段：

1. **strategy**: 简洁的文字描述分析逻辑（1-2 句话）
2. **code**: 完整的、带参数系统的 Python 或 R 代码
3. **code_language**: "python" 或 "r"
4. **parameter_schema**: 符合 JSON Schema 规范的参数定义，用于前端渲染表单。必须包含 default 值。
5. **input_mapping**: 将用户指定的文件 ID 映射到代码的输入参数名

代码要求：
- Python 必须使用 argparse，R 必须使用 optparse 或 commandArgs
- 必须为所有参数设定符合生信经验的默认值（如 p-value 默认 0.05，聚类默认开启）
- 输出目录使用 TASK_OUT_DIR 环境变量
- 代码必须完整可执行，不能有省略或占位符

参数 Schema 要求：
- 每个参数必须有 type、title、default
- 可选参数使用 enum 提供选项列表
- 数值参数可提供 minimum、maximum、step

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
  "input_mapping": {{ "input_file_param": "input", "file_id": "{file_id}" }}
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
        strategy_pack = await _generate_strategy_pack(
            file_id=file_id,
            instruction=raw_instruction,
            session=session,
            user_id=user_id,
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
) -> Dict[str, Any]:
    """
    调用 LLM 生成即席分析策略包。

    程序说明：
    使用 thinking 模型（深度推理），因为策略包生成需要：
    - 理解用户的分析意图
    - 选择合适的分析方法和 R/Python 包
    - 生成带参数系统的完整代码
    - 设计合理的参数 Schema

    Args:
        file_id: 用户指定的文件 ID
        instruction: 用户的分析需求描述
        session: 数据库会话
        user_id: 用户 ID

    Returns:
        策略包字典，包含 strategy、code、code_language、parameter_schema、input_mapping
    """
    # 使用 thinking 模型（深度推理）
    llm_config = get_thinking_llm_config(session, user_id)
    api_key = llm_config.api_key or "not-needed"
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=llm_config.base_url,
        model=llm_config.model_name,
        temperature=0.0,
    )

    # 构造提示词
    prompt = ChatPromptTemplate.from_messages([
        ("system", ADHOC_SYSTEM_PROMPT),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "file_id": file_id,
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
