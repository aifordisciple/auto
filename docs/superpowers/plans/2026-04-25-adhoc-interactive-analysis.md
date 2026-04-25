# 即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS) 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现即席交互式分析意图的 Phase 1 核心流转：L1 识别 → adhoc_analysis_node 生成策略包 → 前端渲染策略卡片 → 用户确认执行 → Docker 沙箱运行

**Architecture:** 新增第 13 种意图 `INTENT_ADHOC_INTERACTIVE_ANALYSIS`，独立节点 `adhoc_analysis_node` 调用 LLM 生成策略包（策略+代码+参数Schema），复用 Active Probing 挂起机制向前端推送 `render_adhoc_card` ToolCall，前端渲染 `AdhocAnalysisCard` 组件，用户确认后恢复 LangGraph 状态机执行。

**Tech Stack:** Python/FastAPI/LangGraph (后端), TypeScript/React/Vercel AI SDK (前端), Docker (沙箱执行)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `autonome-backend/app/agent/router/schemas.py` | Modify | 新增 IntentType 枚举、TaskNode.adhoc_metadata、ProbingRequest 扩展 |
| `autonome-backend/app/agent/router/l1_classifier.py` | Modify | L1 提示词新增意图 13 描述和判定规则 |
| `autonome-backend/app/agent/router/l2_extractor.py` | Modify | 新增即席分析参数检查函数 |
| `autonome-backend/app/agent/nodes/adhoc_analysis_node.py` | Create | 核心执行节点：调用 LLM 生成策略包 |
| `autonome-backend/app/agent/graph.py` | Modify | 图编排：新增节点、条件边 |
| `autonome-backend/app/agent/router/nodes/probing_response_node.py` | Modify | 扩展以处理即席分析的参数回注 |
| `autonome-backend/app/agent/router/nodes/l3_executor_node.py` | Modify | 新增即席分析执行路径 |
| `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx` | Create | 前端策略卡片组件 |
| `autonome-studio/src/components/chat/components/index.ts` | Modify | 导出新组件 |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | Modify | 新增 render_adhoc_card 工具调用渲染 |

---

### Task 1: 后端协议升级 — schemas.py

**Files:**
- Modify: `autonome-backend/app/agent/router/schemas.py`

- [ ] **Step 1: 在 IntentType 枚举中新增 ADHOC_INTERACTIVE_ANALYSIS**

在 `autonome-backend/app/agent/router/schemas.py` 的 `IntentType` 类中，在 `SYSTEM_MACRO` 之前新增枚举值：

```python
    # 组1 新增：计算与编排
    ADHOC_INTERACTIVE_ANALYSIS = "INTENT_ADHOC_INTERACTIVE_ANALYSIS"  # 即席交互式分析
```

- [ ] **Step 2: 在 INTENT_NODE_MAP 中新增映射**

在 `INTENT_NODE_MAP` 字典中，在 `IntentType.SYSTEM_MACRO` 之前新增：

```python
    IntentType.ADHOC_INTERACTIVE_ANALYSIS: "adhoc_analysis_node",
```

- [ ] **Step 3: 在 TaskNode 中新增 adhoc_metadata 字段**

在 `TaskNode` 类的 `parameters` 字段之后新增：

```python
    # 新增：用于即席分析的元数据（策略、生成的Schema、临时代码等）
    # 仅 ADHOC_INTERACTIVE_ANALYSIS 意图时有值
    adhoc_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析元数据：策略描述、生成的代码、参数 Schema、输入映射"
    )
```

- [ ] **Step 4: 在 ProbingRequest 中新增 render_type 和 adhoc_card_data 字段**

在 `ProbingRequest` 类的 `message_to_user` 字段之后新增：

```python
    # 新增：区分参数反问卡片和即席分析卡片的渲染类型
    render_type: str = Field(
        default="parameter_probing",
        description="渲染类型：parameter_probing(参数反问) | adhoc_card(即席分析卡片)"
    )
    # 新增：即席分析卡片数据（仅 render_type=adhoc_card 时有值）
    adhoc_card_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析卡片数据（仅 render_type=adhoc_card 时有值）"
    )
```

- [ ] **Step 5: 更新 schemas.py 模块文档字符串**

将文件顶部的文档字符串中"12 种"改为"13 种"：

```python
"""
意图识别引擎 V2.0 数据结构定义。

包含 13 种原子意图类型枚举、意图-节点映射、提取结果模型、
DAG 调度数据模型、Active Probing 请求模型和 LangGraph 状态定义。

升级要点：
- 意图从 6 种扩展为 13 种 MECE 原子意图（4 组）
- 新增 TaskNode / TaskDAG 支持多任务有向无环图调度
- 新增 ProbingRequest 支持主动反问与前端 Generative UI 表单
- 新增 RouteResult 作为路由引擎的完整输出结果
- AgentState 扩展 DAG 调度状态字段
- V2.1 新增即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS)
"""
```

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/router/schemas.py
git commit -m "feat: 新增 INTENT_ADHOC_INTERACTIVE_ANALYSIS 意图枚举及协议扩展"
```

---

### Task 2: L1 分类器升级 — l1_classifier.py

**Files:**
- Modify: `autonome-backend/app/agent/router/l1_classifier.py`

- [ ] **Step 1: 在 L1_DECOMPOSER_PROMPT_TEMPLATE 中新增意图 13 描述**

在 `L1_DECOMPOSER_PROMPT_TEMPLATE` 中，将"可用意图类型（11 种原子意图）"改为"可用意图类型（13 种原子意图）"，并在 `| 通用问答 | INTENT_GENERAL_CHAT |` 行之后新增：

```
| 即席分析 | INTENT_ADHOC_INTERACTIVE_ANALYSIS | 用户提供数据文件+分析需求+无技能匹配 |
```

- [ ] **Step 2: 在 L1 提示词中新增即席分析判定规则**

在 `L1_DECOMPOSER_PROMPT_TEMPLATE` 的"指令"部分第 5 条之后追加：

```
6. 即席分析判定原则：
   - 如果用户指令包含具体数据文件，且要求进行通用的分析/可视化操作（非系统预设标准技能），优先路由为 INTENT_ADHOC_INTERACTIVE_ANALYSIS
   - 如果用户明确说"写代码"、"写脚本"、"帮我写一个..."，路由为 INTENT_SKILL_FORGE
   - 如果技能库中有匹配的技能，路由为 INTENT_EXPLICIT_EXEC
```

- [ ] **Step 3: 在 _decompose_with_json_mode 的 json_instruction 中追加枚举值**

在 `l1_classifier.py` 的 `_decompose_with_json_mode` 方法中，`json_instruction` 字符串的 intent 枚举值列表末尾追加 `|INTENT_ADHOC_INTERACTIVE_ANALYSIS`：

将：
```python
'      "intent": "INTENT_GENERAL_CHAT|INTENT_WORKFLOW_ORCHESTRATE|INTENT_SKILL_FORGE|INTENT_EXPLICIT_EXEC|INTENT_VERSION_CONTROL|INTENT_VISUAL_PERCEPTION_AND_TWEAK|INTENT_DATA_PROBE|INTENT_LITERATURE_MINING|INTENT_SYSTEM_ASSET_OPS|INTENT_COLLABORATION|INTENT_DIAGNOSTIC_RECOVERY",\n'
```
改为：
```python
'      "intent": "INTENT_GENERAL_CHAT|INTENT_WORKFLOW_ORCHESTRATE|INTENT_SKILL_FORGE|INTENT_EXPLICIT_EXEC|INTENT_VERSION_CONTROL|INTENT_VISUAL_PERCEPTION_AND_TWEAK|INTENT_DATA_PROBE|INTENT_LITERATURE_MINING|INTENT_SYSTEM_ASSET_OPS|INTENT_COLLABORATION|INTENT_DIAGNOSTIC_RECOVERY|INTENT_ADHOC_INTERACTIVE_ANALYSIS",\n'
```

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/agent/router/l1_classifier.py
git commit -m "feat: L1 分类器新增即席分析意图识别规则"
```

---

### Task 3: L2 参数探测器升级 — l2_extractor.py

**Files:**
- Modify: `autonome-backend/app/agent/router/l2_extractor.py`

- [ ] **Step 1: 在 PROBING_INTENTS 和 ENRICHMENT_INTENTS 中新增即席分析**

在 `L2SlotExtractor` 类中，`PROBING_INTENTS` 集合末尾新增：

```python
        IntentType.ADHOC_INTERACTIVE_ANALYSIS,  # 即席分析：检查输入文件
```

在 `ENRICHMENT_INTENTS` 集合末尾新增：

```python
        IntentType.ADHOC_INTERACTIVE_ANALYSIS,  # 即席分析：自动注入 active_file
```

- [ ] **Step 2: 在 check_task_parameters 中新增即席分析分支**

在 `check_task_parameters` 函数中，`LITERATURE_MINING` 分支之后、`return ProbingRequest(is_missing=False)` 之前新增：

```python
    # ADHOC_INTERACTIVE_ANALYSIS 意图：检查输入文件
    if task.intent == IntentType.ADHOC_INTERACTIVE_ANALYSIS:
        return _check_adhoc_analysis_params(task, context)
```

- [ ] **Step 3: 新增 _check_adhoc_analysis_params 函数**

在 `l2_extractor.py` 文件末尾（`_enrich_from_context` 函数之前）新增：

```python
def _check_adhoc_analysis_params(
    task: TaskNode,
    context: Dict[str, Any]
) -> ProbingRequest:
    """
    检查即席交互式分析的参数完整性。

    程序说明：
    即席分析必须至少有一个 resolved_assets（输入文件）。
    如果缺失，返回 ProbingRequest 要求用户指定文件；
    如果有文件，放行。

    Args:
        task: L1 解构器输出的 TaskNode
        context: 工作区上下文

    Returns:
        ProbingRequest: 参数探查结果
    """
    has_file = task.resolved_assets or context.get("active_file")
    if not has_file:
        log.info("[L2] ADHOC_INTERACTIVE_ANALYSIS 缺失文件目标")
        return ProbingRequest(
            is_missing=True,
            missing_params=["input_file"],
            ui_schema={
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "title": "待分析的数据文件",
                        "description": "请从左侧资产树拖入文件或输入文件路径"
                    }
                },
                "required": ["input_file"]
            },
            message_to_user="即席分析需要指定目标文件，请问您想对哪个数据执行此操作？"
        )
    log.debug("[L2] ADHOC_INTERACTIVE_ANALYSIS 参数完整，放行")
    return ProbingRequest(is_missing=False)
```

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/agent/router/l2_extractor.py
git commit -m "feat: L2 参数探测器新增即席分析参数检查"
```

---

### Task 4: 新增 adhoc_analysis_node 核心节点

**Files:**
- Create: `autonome-backend/app/agent/nodes/adhoc_analysis_node.py`

- [ ] **Step 1: 创建 adhoc_analysis_node.py**

创建文件 `autonome-backend/app/agent/nodes/adhoc_analysis_node.py`，内容如下：

```python
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
from app.utils.llm_config import get_thinking_llm_config, _is_local_model, _is_ollama


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

    log.info(f"[adhoc_analysis_node] 策略包生成成功，挂起等待用户确认")

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

    log.info(f"[adhoc_analysis_node] 策略包验证通过: language={strategy_pack.get('code_language')}, params={list(strategy_pack.get('parameter_schema', {}).get('properties', {}).keys())}")

    return strategy_pack
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/nodes/adhoc_analysis_node.py
git commit -m "feat: 新增 adhoc_analysis_node 即席分析策略包生成节点"
```

---

### Task 5: LangGraph 图编排变更 — graph.py

**Files:**
- Modify: `autonome-backend/app/agent/graph.py`

- [ ] **Step 1: 导入 adhoc_analysis_node**

在 `graph.py` 的导入区域，`from app.agent.nodes.system_macro_node import system_macro_node` 之后新增：

```python
from app.agent.nodes.adhoc_analysis_node import adhoc_analysis_node
```

- [ ] **Step 2: 在 build_intent_graph 中添加节点**

在 `build_intent_graph` 函数中，`workflow.add_node("system_macro_node", system_macro_node)` 之后新增：

```python
    workflow.add_node("adhoc_analysis_node", adhoc_analysis_node)
```

- [ ] **Step 3: 将 adhoc_analysis_node 加入 all_worker_nodes**

在 `all_worker_nodes` 列表中，`"system_macro_node"` 之后新增：

```python
        "adhoc_analysis_node",
```

- [ ] **Step 4: 扩展 ask_user_node 支持 render_adhoc_card**

将 `graph.py` 中的 `ask_user_node` 函数替换为：

```python
async def ask_user_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """向前端抛出参数补全表单或即席分析卡片的节点（Active Probing 挂起点）。"""
    probing_dict = state.get("active_probing")
    if not probing_dict:
        return {}

    probing = ProbingRequest(**probing_dict) if isinstance(probing_dict, dict) else probing_dict
    current_idx = state.get("current_task_idx", 0)

    # 根据 render_type 决定渲染哪种卡片
    if probing.render_type == "adhoc_card":
        # 即席分析卡片：使用 render_adhoc_card ToolCall
        card_data = probing.adhoc_card_data or {}
        tool_call = {
            "name": "render_adhoc_card",
            "args": {
                "strategy": card_data.get("strategy", ""),
                "code": card_data.get("code", ""),
                "code_language": card_data.get("code_language", "python"),
                "parameter_schema": card_data.get("parameter_schema", {}),
                "input_mapping": card_data.get("input_mapping", {}),
            },
            "id": f"call_adhoc_{current_idx}",
        }
        log.info(f"[ask_user_node] 发送即席分析卡片: strategy={card_data.get('strategy', '')[:50]}")
    else:
        # 原有参数反问逻辑
        tool_call = {
            "name": "request_parameters",
            "args": {
                "message": probing.message_to_user,
                "schema": probing.ui_schema,
            },
            "id": f"call_probe_{current_idx}",
        }
        log.info(f"[ask_user_node] 发送参数补全请求: missing={probing.missing_params}")

    message = AIMessage(content="", tool_calls=[tool_call])

    return {"messages": [message]}
```

- [ ] **Step 5: 更新 graph.py 顶部文档字符串**

在 Graph 结构注释中，`→ system_macro_node → task_advance_or_end` 之后新增：

```
        → adhoc_analysis_node → ask_user_node (挂起等待用户确认)
```

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/graph.py
git commit -m "feat: LangGraph 图编排新增 adhoc_analysis_node 及 ask_user_node 扩展"
```

---

### Task 6: probing_response_node 扩展

**Files:**
- Modify: `autonome-backend/app/agent/router/nodes/probing_response_node.py`

- [ ] **Step 1: 扩展 probing_response_node 以处理即席分析参数回注**

将 `probing_response_node` 函数替换为：

```python
async def probing_response_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    处理用户提交的 Active Probing 参数。

    程序说明：
    从 AgentState.probing_response 读取用户提交的参数，
    合并到当前 TaskNode 的 parameters 中，
    清除 active_probing 和 probing_response 以解除挂起。

    V2.2 扩展：支持即席分析卡片的参数回注。
    当 render_type == "adhoc_card" 时，用户提交的参数包含
    action='execute' 和 payload（含 parameters、inputs、code_snapshot），
    需要将代码快照和最终参数一并存入 TaskNode.parameters。
    """
    probing_response = state.get("probing_response")
    if not probing_response:
        log.warning("[probing_response_node] 无 probing_response，跳过")
        return {"active_probing": None, "probing_response": None}

    # 提取用户提交的参数
    user_params = probing_response.get("parameters", {})
    message_id = probing_response.get("message_id", "")

    # 检查是否为即席分析的参数回注
    # 即席分析时，user_params 包含 action 和 payload
    action = user_params.get("action", "")
    is_adhoc_execute = action == "execute"

    if is_adhoc_execute:
        payload = user_params.get("payload", {})
        log.info(f"[probing_response_node] 收到即席分析执行请求: action={action}, params={list(payload.get('parameters', {}).keys())}")
    else:
        log.info(f"[probing_response_node] 收到用户参数: message_id={message_id}, params={list(user_params.keys())}")

    # 将用户参数合并到当前 TaskNode
    dag_dict = state.get("dag")
    idx = state.get("current_task_idx", 0)
    if dag_dict and dag_dict.get("nodes"):
        nodes = dag_dict["nodes"]
        if idx < len(nodes):
            existing_params = nodes[idx].get("parameters", {})

            if is_adhoc_execute:
                # 即席分析：合并 payload 中的参数、输入映射和代码快照
                payload = user_params.get("payload", {})
                merged_params = {
                    **existing_params,
                    **payload.get("inputs", {}),
                    **payload.get("parameters", {}),
                    "code_snapshot": payload.get("code_snapshot", ""),
                    "code_language": nodes[idx].get("adhoc_metadata", {}).get("code_language", "python"),
                }
            else:
                # 原有逻辑：用户提交的参数优先级最高
                merged_params = {**existing_params, **user_params}

            nodes[idx]["parameters"] = merged_params
            log.info(f"[probing_response_node] 参数已回注到 task_{idx}: {list(merged_params.keys())}")

    # 清除挂起状态，允许继续执行
    return {
        "dag": dag_dict,
        "active_probing": None,
        "probing_response": None,
        "execution_status": "pending",
    }
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/router/nodes/probing_response_node.py
git commit -m "feat: probing_response_node 扩展支持即席分析参数回注"
```

---

### Task 7: l3_executor_node 扩展 — 即席分析执行路径

**Files:**
- Modify: `autonome-backend/app/agent/router/nodes/l3_executor_node.py`

- [ ] **Step 1: 在 l3_executor_node 中新增即席分析执行分支**

在 `l3_executor_node` 函数中，`skill_id` 提取之后、`if not skill_id:` 检查之前，新增即席分析执行分支：

将原有的：
```python
    skill_id = current_task.get("parameters", {}).get("skill_id") or state.get("skill_id")
    parameters = current_task.get("parameters", {})

    if not skill_id:
```

替换为：
```python
    skill_id = current_task.get("parameters", {}).get("skill_id") or state.get("skill_id")
    parameters = current_task.get("parameters", {})
    adhoc_metadata = current_task.get("adhoc_metadata")

    # 即席分析执行路径：adhoc_metadata 存在或 parameters 中有 code_snapshot
    code_snapshot = parameters.get("code_snapshot", "")
    if adhoc_metadata or code_snapshot:
        return await _execute_adhoc_analysis(state, config, current_task, task_id, idx, nodes)

    if not skill_id:
```

- [ ] **Step 2: 新增 _execute_adhoc_analysis 函数**

在 `l3_executor_node.py` 文件末尾新增：

```python
async def _execute_adhoc_analysis(
    state: AgentState,
    config: RunnableConfig,
    current_task: Dict[str, Any],
    task_id: str,
    idx: int,
    nodes: list,
) -> Dict[str, Any]:
    """
    即席分析的 Docker 沙箱执行路径。

    程序说明：
    从 parameters.code_snapshot 获取代码内容，
    写入临时文件，使用 run_container 在 Docker 沙箱中执行，
    返回执行结果。

    Args:
        state: LangGraph 状态
        config: Runnable 配置
        current_task: 当前 TaskNode 字典
        task_id: 任务 ID
        idx: 当前任务索引
        nodes: DAG 节点列表

    Returns:
        状态更新字典
    """
    import tempfile
    import os
    from app.tools.bio_tools import run_container

    parameters = current_task.get("parameters", {})
    code_snapshot = parameters.get("code_snapshot", "")
    code_language = parameters.get("code_language", "python")

    if not code_snapshot:
        log.error(f"[l3_executor_node] 即席分析缺少 code_snapshot，无法执行")
        task_result = TaskResult(
            task_id=task_id,
            status="failed",
            error="即席分析缺少代码快照，无法执行",
        )
        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        return {
            "task_results": task_results,
            "current_task_idx": idx + 1,
            "execution_status": "failed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content="即席分析执行失败：缺少代码快照")],
        }

    log.info(f"[l3_executor_node] 即席分析执行: task={task_id}, language={code_language}")

    try:
        # 将代码写入临时文件
        suffix = ".py" if code_language == "python" else ".R"
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(code_snapshot)
            script_path = f.name

        # 构建执行命令
        if code_language == "python":
            cmd = ["python", script_path]
        else:
            cmd = ["Rscript", script_path]

        # 构建命令行参数（从 parameters 中提取，排除内部字段）
        for key, value in parameters.items():
            if key.startswith("_") or key in ("code_snapshot", "code_language", "skill_id"):
                continue
            if value is None:
                continue
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.append(f"--{key}")
                cmd.append(str(value))

        log.info(f"[l3_executor_node] 即席分析命令: {' '.join(cmd)}")

        # 获取用户 ID
        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")

        # 在 Docker 沙箱中执行
        output, exit_code = run_container(
            image='autonome-tool-env',
            command=cmd,
            language=code_language,
            environment={
                "TASK_OUT_DIR": parameters.get("TASK_OUT_DIR", "/workspace/results/default"),
                "PROJECT_ID": parameters.get("PROJECT_ID", "default"),
            },
            timeout=3600,
            cli_mode=True,
            user_id=int(user_id) if user_id else None,
        )

        # 清理临时文件
        try:
            os.unlink(script_path)
        except OSError:
            pass

        # 解析执行结果
        success = exit_code == 0
        task_result = TaskResult(
            task_id=task_id,
            skill_id="adhoc_analysis",
            status="success" if success else "failed",
            output=output[:5000] if success else None,
            error=output[:2000] if not success else None,
            execution_time_seconds=0.0,
        )

        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        new_idx = idx + 1

        result_msg = f"即席分析执行{'成功' if success else '失败'}"
        if success and task_result.output:
            result_msg += f"\n结果: {str(task_result.output)[:500]}"

        log.info(f"[l3_executor_node] 即席分析 task={task_id} 执行完成: status={task_result.status}")

        return {
            "task_results": task_results,
            "current_task_idx": new_idx,
            "execution_status": "running" if new_idx < len(nodes) else "completed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content=result_msg)],
        }

    except Exception as e:
        log.error(f"[l3_executor_node] 即席分析执行异常: task={task_id}, error={str(e)}")

        # 清理临时文件（如果存在）
        try:
            if 'script_path' in locals():
                os.unlink(script_path)
        except OSError:
            pass

        task_result = TaskResult(
            task_id=task_id,
            skill_id="adhoc_analysis",
            status="failed",
            error=str(e),
        )
        task_results = {**state.get("task_results", {}), task_id: task_result.model_dump()}
        new_idx = idx + 1

        return {
            "task_results": task_results,
            "current_task_idx": new_idx,
            "execution_status": "failed",
            "execution_result": task_result.model_dump(),
            "messages": [AIMessage(content=f"即席分析执行失败: {str(e)}")],
        }
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/agent/router/nodes/l3_executor_node.py
git commit -m "feat: l3_executor_node 新增即席分析 Docker 沙箱执行路径"
```

---

### Task 8: 前端 AdhocAnalysisCard 组件

**Files:**
- Create: `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`

- [ ] **Step 1: 创建 AdhocAnalysisCard.tsx**

创建文件 `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`，内容如下：

```tsx
'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, Play, Star, Loader2 } from 'lucide-react'

/**
 * JSON Schema 属性定义（与 ParameterProbingCard 一致）
 */
interface SchemaProperty {
  type: 'string' | 'number' | 'boolean'
  title?: string
  description?: string
  enum?: string[]
  default?: string | number | boolean
  minimum?: number
  maximum?: number
  step?: number
}

/**
 * 即席分析卡片 Props
 */
export interface AdhocAnalysisCardProps {
  /** 策略描述 */
  strategy: string
  /** 生成的代码 */
  code: string
  /** 代码语言 */
  code_language: 'python' | 'r'
  /** 参数 Schema */
  parameter_schema: {
    type: string
    properties: Record<string, SchemaProperty>
    required?: string[]
  }
  /** 输入文件映射 */
  input_mapping: Record<string, string>
  /** Vercel AI SDK addToolResult 回调 */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addToolResult: any
  /** ToolCall ID */
  toolCallId: string
}

/**
 * AdhocAnalysisCard — 即席交互式分析策略卡片。
 *
 * 当 adhoc_analysis_node 生成策略包后，通过 render_adhoc_card ToolCall
 * 触发前端渲染此卡片。用户可以在卡片上修改参数、查看代码、执行分析。
 *
 * 四个区域：
 * 1. 策略说明区（顶部，靛蓝色背景）
 * 2. 参数面板（中部，网格布局，动态表单）
 * 3. 代码预览区（折叠）
 * 4. 操作区（底部，执行按钮 + 固化技能按钮）
 */
export function AdhocAnalysisCard({
  strategy,
  code,
  code_language,
  parameter_schema,
  input_mapping,
  addToolResult,
  toolCallId,
}: AdhocAnalysisCardProps) {
  // 从 Schema 默认值初始化表单状态
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {}
    for (const [key, prop] of Object.entries(parameter_schema?.properties || {})) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default
      }
    }
    return defaults
  })

  const [isExecuting, setIsExecuting] = useState(false)
  const [showCode, setShowCode] = useState(false)

  // 处理参数变化
  const handleParamChange = (key: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value }))
  }

  // 核心：点击执行，将参数通过 Vercel AI SDK 送回后端
  const handleExecute = () => {
    if (isExecuting) return
    setIsExecuting(true)

    // 合并用户填写的参数和底层文件映射
    const finalPayload = {
      parameters: formData,
      inputs: input_mapping,
      code_snapshot: code, // 将代码快照一并传回，防止后端丢失上下文
    }

    // 调用 Vercel AI SDK 的回调，触发后端的流式响应继续进行
    addToolResult({
      toolCallId,
      output: {
        action: 'execute',
        payload: finalPayload,
      },
    })
  }

  // 固化技能到资产库（Phase 2 实现，当前为占位提示）
  const handleSaveSkill = () => {
    // Phase 2: 弹出技能编辑表单，预填代码和 Schema
    alert('技能固化功能将在后续版本实现')
  }

  return (
    <div className="my-3 rounded-xl border border-indigo-500/40 bg-white dark:bg-[#1a1a1c] shadow-sm overflow-hidden">
      {/* 1. 策略说明区（顶部，靛蓝色背景） */}
      <div className="bg-indigo-50/50 dark:bg-indigo-900/20 p-4 border-b border-indigo-100 dark:border-indigo-500/20">
        <h3 className="font-bold text-indigo-900 dark:text-indigo-300 flex items-center gap-2 text-sm">
          <span>⚡ 即席分析就绪</span>
        </h3>
        <p className="text-gray-600 dark:text-zinc-300 text-sm mt-2">{strategy}</p>
      </div>

      {/* 2. 参数面板（中部，网格布局，动态表单） */}
      {Object.keys(parameter_schema?.properties || {}).length > 0 && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Object.entries(parameter_schema.properties).map(([key, field]) => (
            <div key={key} className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">
                {field.title || key}
                {parameter_schema.required?.includes(key) && <span className="ml-1 text-red-400">*</span>}
              </label>

              {/* enum → 下拉选择框 */}
              {field.enum ? (
                <select
                  value={String(formData[key] ?? field.default ?? '')}
                  onChange={(e) => handleParamChange(key, e.target.value)}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                >
                  {field.enum.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              ) : field.type === 'boolean' ? (
                /* boolean → 开关 */
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(formData[key] ?? field.default ?? false)}
                    onChange={(e) => handleParamChange(key, e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-600 text-indigo-500 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-zinc-400">{field.description || '启用'}</span>
                </label>
              ) : field.type === 'number' ? (
                /* number → 数字输入框 */
                <input
                  type="number"
                  value={Number(formData[key] ?? field.default ?? 0)}
                  onChange={(e) => handleParamChange(key, Number(e.target.value))}
                  min={field.minimum}
                  max={field.maximum}
                  step={field.step ?? 1}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                />
              ) : (
                /* string → 文本输入框 */
                <input
                  type="text"
                  value={String(formData[key] ?? field.default ?? '')}
                  onChange={(e) => handleParamChange(key, e.target.value)}
                  placeholder={field.description || `请输入 ${field.title || key}`}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* 3. 代码预览区（折叠） */}
      <div className="px-4">
        <button
          onClick={() => setShowCode(!showCode)}
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline mb-2 flex items-center gap-1"
        >
          {showCode ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {showCode ? '隐藏底层代码' : '查看底层代码'}
        </button>
        {showCode && (
          <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto mb-4 max-h-64">
            <code>{code}</code>
          </pre>
        )}
      </div>

      {/* 4. 操作区（底部） */}
      <div className="p-4 bg-gray-50 dark:bg-[#1e1e20] flex justify-between items-center border-t border-gray-200 dark:border-zinc-800">
        <button
          onClick={handleSaveSkill}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-zinc-600 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <Star size={14} />
          固化为团队技能
        </button>
        <button
          onClick={handleExecute}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50 disabled:cursor-not-allowed rounded-md transition-colors"
        >
          {isExecuting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Play size={14} />
          )}
          {isExecuting ? '沙箱启动中...' : '执行分析'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx
git commit -m "feat: 新增 AdhocAnalysisCard 即席分析策略卡片组件"
```

---

### Task 9: 前端集成 — index.ts 导出 + MemoizedMessageItem 渲染

**Files:**
- Modify: `autonome-studio/src/components/chat/components/index.ts`
- Modify: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`

- [ ] **Step 1: 在 index.ts 中导出 AdhocAnalysisCard**

在 `autonome-studio/src/components/chat/components/index.ts` 末尾新增：

```typescript
// 即席分析策略卡片
export { AdhocAnalysisCard } from './AdhocAnalysisCard';
```

- [ ] **Step 2: 在 MemoizedMessageItem.tsx 中导入 AdhocAnalysisCard**

在 `MemoizedMessageItem.tsx` 的导入区域，`import { ParameterProbingCard, type ParameterProbingCardProps } from "./ParameterProbingCard";` 之后新增：

```typescript
import { AdhocAnalysisCard } from "./components/AdhocAnalysisCard";
```

- [ ] **Step 3: 在 MemoizedMessageItem.tsx 中新增 render_adhoc_card 渲染逻辑**

在 `MemoizedMessageItem.tsx` 的工具调用渲染区域，`if (toolName === 'request_parameters' ...)` 分支之前新增：

```tsx
                    // ✨ render_adhoc_card 工具：渲染 AdhocAnalysisCard 即席分析策略卡片
                    if (toolName === 'render_adhoc_card' && toolState !== 'output-available' && toolState !== 'output-error') {
                      const strategy = (toolInput?.strategy || '') as string;
                      const code = (toolInput?.code || '') as string;
                      const code_language = (toolInput?.code_language || 'python') as 'python' | 'r';
                      const parameter_schema = (toolInput?.parameter_schema || {}) as {
                        type: string;
                        properties: Record<string, unknown>;
                        required?: string[];
                      };
                      const input_mapping = (toolInput?.input_mapping || {}) as Record<string, string>;

                      return (
                        <AdhocAnalysisCard
                          key={toolCallId}
                          strategy={strategy}
                          code={code}
                          code_language={code_language}
                          parameter_schema={parameter_schema as any}
                          input_mapping={input_mapping}
                          addToolResult={addToolResult}
                          toolCallId={toolCallId}
                        />
                      );
                    }
```

- [ ] **Step 4: Commit**

```bash
git add autonome-studio/src/components/chat/components/index.ts autonome-studio/src/components/chat/MemoizedMessageItem.tsx
git commit -m "feat: 前端集成 AdhocAnalysisCard 渲染逻辑"
```

---

### Task 10: 端到端验证与部署

**Files:**
- 无新文件

- [ ] **Step 1: 重启 Docker 服务验证后端启动**

```bash
docker-compose down && docker-compose up -d
```

检查后端日志确认无启动错误：

```bash
docker logs autonome-api | tail -30
```

预期：无 ImportError 或语法错误，`adhoc_analysis_node` 节点注册成功。

- [ ] **Step 2: 检查前端构建**

```bash
cd autonome-studio && npm run build 2>&1 | tail -20
```

预期：构建成功，无 TypeScript 类型错误。

- [ ] **Step 3: 重建前端 Docker 镜像**

```bash
docker-compose build --no-cache frontend && docker-compose up -d
```

- [ ] **Step 4: 部署**

```bash
./auto_deploy.sh -s "feat: 新增即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS)" -d "实现即席交互式分析意图的 Phase 1 核心流转：新增 IntentType 枚举、L1/L2 升级、adhoc_analysis_node 节点、LangGraph 图编排变更、前端 AdhocAnalysisCard 组件、probing_response_node 和 l3_executor_node 扩展。"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Task | Status |
|---|---|---|
| 2.1 IntentType 枚举 | Task 1 Step 1 | Covered |
| 2.2 INTENT_NODE_MAP 映射 | Task 1 Step 2 | Covered |
| 2.3 TaskNode.adhoc_metadata | Task 1 Step 3 | Covered |
| 2.4 ProbingRequest 扩展 | Task 1 Step 4 | Covered |
| 3.1 L1 意图描述注入 | Task 2 Step 1 | Covered |
| 3.2 L1 判定规则注入 | Task 2 Step 2 | Covered |
| 3.3 JSON 格式输出扩展 | Task 2 Step 3 | Covered |
| 4.1-4.2 PROBING/ENRICHMENT_INTENTS | Task 3 Step 1 | Covered |
| 4.3 即席分析参数检查 | Task 3 Steps 2-3 | Covered |
| 5.1-5.5 adhoc_analysis_node | Task 4 | Covered |
| 6.1 graph.py 变更 | Task 5 Steps 1-3 | Covered |
| 6.2 ask_user_node 扩展 | Task 5 Step 4 | Covered |
| 6.3 probing_response_node 扩展 | Task 6 | Covered |
| 6.4 l3_executor_node 执行路径 | Task 7 | Covered |
| 7.1-7.4 AdhocAnalysisCard 组件 | Task 8 | Covered |
| 7.7 ChatStage/MemoizedMessageItem 集成 | Task 9 | Covered |

### Placeholder Scan

No TBD, TODO, or placeholder patterns found.

### Type Consistency

- `adhoc_metadata` type: `Optional[Dict[str, Any]]` — consistent across schemas.py, adhoc_analysis_node.py, l3_executor_node.py
- `render_type` type: `str` with values `"parameter_probing"` | `"adhoc_card"` — consistent across schemas.py, graph.py
- `adhoc_card_data` type: `Optional[Dict[str, Any]]` — consistent across schemas.py, graph.py
- `AdhocAnalysisCardProps` interface matches the args structure in `ask_user_node`'s `render_adhoc_card` ToolCall
- `addToolResult` callback signature consistent with existing ParameterProbingCard usage
