from typing import Annotated, Literal, TypedDict, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
import json
import re

from app.tools.bio_tools import execute_python_code
from app.tools.geo_tools import search_and_vectorize_geo_data, submit_async_geo_analysis_task
from app.tools.report_tools import generate_publishable_report
from app.core.logger import log
from app.core.skill_parser import get_skill_parser, get_combined_skill_by_id, get_combined_skills

from app.agent.pi_agent import is_complex_task, generate_blueprint

# 系统学习技能注入器
from app.services.system_learning.skill_injector import get_skill_injector

# Token 预算控制器
from app.services.token_budget import (
    get_token_budget_controller,
    BudgetLevel,
    check_llm_budget
)

# ✨ 新增：动态上下文构建器
from app.agent.context_builder import (
    is_casual_chat,
    build_skill_catalog_md,
    build_knowledge_catalog_md,
    build_selected_skill_context,
)

# ✨ 新增：闲聊节点
from app.agent.nodes.chat import chat_node

# ✨ V2 架构：极速路由节点
from app.agent.nodes.router import router_node, get_intent_routing_edges, RouterState
from app.agent.schemas import IntentClassification

# ✨ V2 架构：专业节点
from app.agent.nodes.retrieval import retrieval_node
from app.agent.nodes.troubleshooting import troubleshooting_node
from app.agent.nodes.system_action import system_action_node
from app.agent.nodes.blueprint import blueprint_node
from app.agent.nodes.param_update import param_update_node
from app.agent.nodes.skill_form_builder import skill_form_builder_node
from app.agent.nodes.skill_execute import skill_execute_node, handle_skill_execute


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next: str


# ✨ 闲聊快速响应映射（无需调用 LLM）
CASUAL_RESPONSES = {
    "greeting": "你好！有什么我可以帮助你的吗？可以问我关于数据分析、代码编写、SKILL 执行等问题。",
    "thanks": "不客气！还有什么需要帮忙的吗？",
    "bye": "再见！有需要随时回来。",
    "help": "我可以帮你：\n1. 分析生物数据\n2. 编写 Python/R 代码\n3. 执行 SKILL 工作流\n4. 生成可视化图表\n\n有什么具体需求吗？",
    "default": "明白，请说。",
}


def _detect_casual_type(message: str) -> str:
    """检测闲聊类型"""
    msg = message.strip().lower()
    if any(kw in msg for kw in ["你好", "hi", "hello", "嗨", "您好", "hey"]):
        return "greeting"
    if any(kw in msg for kw in ["谢谢", "thanks", "thx"]):
        return "thanks"
    if any(kw in msg for kw in ["再见", "bye", "拜拜"]):
        return "bye"
    if any(kw in msg for kw in ["帮忙", "help", "帮帮我", "请问", "question"]):
        return "help"
    return "default"


def build_bio_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    physical_file_info: str,
    global_file_tree: str,
    user_id: int,
    project_id: int,
    selected_skill_id: Optional[str] = None,
    vision_config: Optional[dict] = None,
    task_mode: Optional[str] = None  # ✨ 任务模式：'complex' 强制蓝图，None 自动判断
):
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    # ==========================================
    # Token 预算控制
    # ==========================================
    # 根据任务模式选择预算级别
    if task_mode == 'complex':
        budget_level = BudgetLevel.HIGH
    else:
        budget_level = BudgetLevel.NORMAL

    budget_controller = get_token_budget_controller(budget_level)

    # 默认 max_tokens（会在构建 prompt 后动态调整）
    default_max_tokens = 128000

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2,
        max_tokens=default_max_tokens  # 增大 token 限制，支持长代码输出和完整策略卡片
    )

    vision_llm = None
    if vision_config:
        vision_api_key = vision_config.get("api_key", actual_api_key)
        vision_base_url = vision_config.get("base_url", base_url)
        vision_model = vision_config.get("model", model_name)

        if vision_model != model_name or vision_base_url != base_url:
            vision_llm = ChatOpenAI(
                api_key=vision_api_key,
                base_url=vision_base_url,
                model=vision_model,
                temperature=0.1,
                streaming=True,
                max_retries=2,
                max_tokens=128000  # 增大 token 限制，支持长代码输出
            )
            log.info(f"🖼️ [Bot] 创建独立视觉模型 - {vision_model} @ {vision_base_url}")
        else:
            log.info(f"🖼️ [Bot] 视觉模型与主模型相同 - {model_name}")

    log.info(f"🤖 [Bot] 构建 Agent - API: {base_url}, Model: {model_name}")

    # ✨ 延迟加载占位符（将在 invoke 时替换为真实内容）
    # 使用唯一占位符方便后续替换
    _SKILL_PLACEHOLDER = "__DYNAMIC_SKILL_CATALOG__\n"
    _KNOWLEDGE_PLACEHOLDER = "__DYNAMIC_KNOWLEDGE_CATALOG__\n"
    _SELECTED_SKILL_PLACEHOLDER = "__DYNAMIC_SELECTED_SKILL__"

    skill_catalog_md = _SKILL_PLACEHOLDER
    knowledge_catalog_md = _KNOWLEDGE_PLACEHOLDER
    knowledge_intent_keywords = []

    # ==========================================
    # 系统学习技能注入（隐身）
    # ==========================================
    # 从用户输入推断意图，注入相关系统级学习方法论
    system_learning_context = ""
    try:
        injector = get_skill_injector()
        # 使用用户输入或文件信息作为查询
        query_hint = physical_file_info[:500] if physical_file_info else ""
        if query_hint:
            system_skills = injector.inject_for_query(query_hint, limit=3)

            if system_skills:
                system_learning_context = f"""
[系统学习方法论库 - 自动推荐]
以下是从历史成功对话中学习到的方法论，供参考：
{'---'.join(system_skills)}
"""
                log.info(f"🧠 [Bot] 注入了 {len(system_skills)} 个系统学习技能")
    except Exception as e:
        log.warning(f"⚠️ [Bot] 系统技能注入失败: {e}")

    # ✨ selected_skill_context 也延迟加载
    selected_skill_context = _SELECTED_SKILL_PLACEHOLDER

    # 构建知识型 SKILL 意图关键词提示（必须在 try-except 块外定义，确保变量始终存在）
    knowledge_intent_md = ""
    for kw in knowledge_intent_keywords:
        knowledge_intent_md += f"- `{kw['skill_id']}`: {kw['description'][:100]}...\n" if len(kw['description']) > 100 else f"- `{kw['skill_id']}`: {kw['description']}\n"

    # ==========================================
    # ✨ 任务模式处理
    # 根据用户选择的任务模式调整执行路径
    # ==========================================
    task_mode_context = ""
    if task_mode == 'complex':
        task_mode_context = """
<task_mode_directive priority="highest">
【🚨 用户已选择"复杂任务"模式】
**强制执行规则**：
1. 忽略 SKILL 匹配，不输出 json_strategy
2. 必须输出 ```json_blueprint 格式的 DAG 蓝图
3. 任务拆解需遵循：颗粒度细、上下文传递（下游 input = 上游 output）、探针先行、路径明确
4. 每个任务需指定 tool（peek_tabular_data / scan_workspace / execute_python_code / SKILL_ID）
5. 必须包含数据探查任务作为第一步
</task_mode_directive>
"""
        log.info(f"🔀 [Bot] 复杂任务模式已启用，将强制输出 json_blueprint")

    elif task_mode == 'interactive':
        task_mode_context = """
<task_mode_directive priority="highest">
【🎨 用户已选择"交互式可视化"模式】

**🚨 核心约束（违反将导致系统错误）**：
- `tool_id` **必须是** `"execute-python"` 或 `"execute-r"`，**禁止**使用其他值
- **禁止**输出 `json_interactive_plot`（由系统自动生成）
- 必须输出数据处理代码（Python 或 R）

**输出格式（严格遵守）**：

**第一步：数据处理代码**
```python
import os
import pandas as pd

# 获取输出目录
out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_xxx/results/default_task')
os.makedirs(out_dir, exist_ok=True)

# 读取原始数据（使用实际项目路径）
df = pd.read_csv('实际数据路径', sep='\\t')

# 数据处理逻辑（根据用户需求）
result_df = df.groupby('列名').size().reset_index(name='count')

# 保存处理结果
result_df.to_csv(f'{out_dir}/results.tsv', sep='\\t', index=False)
print(f'处理完成，结果已保存到 {out_dir}/results.tsv')
print(f'列名: {list(result_df.columns)}')
```

**第二步：策略卡片**
```json_strategy
{
  "title": "数据处理任务",
  "description": "统计各分组的数量",
  "tool_id": "execute-python",
  "task_mode": "interactive_visualization",
  "visualization_config": {
    "plot_type": "bar",
    "title": "分组统计图",
    "data_source": "results.tsv",
    "parameters": {
      "x_column": {
        "key": "group",
        "label": "X轴分组",
        "type": "select",
        "options": ["group"],
        "default": "group"
      },
      "y_column": {
        "key": "count",
        "label": "Y轴数值",
        "type": "select",
        "options": ["count"],
        "default": "count"
      },
      "color_scheme": {
        "key": "color_scheme",
        "label": "配色方案",
        "type": "select",
        "options": ["viridis", "plasma", "Set2", "Set3", "Dark2"],
        "default": "viridis"
      },
      "bar_width": {
        "key": "bar_width",
        "label": "柱宽",
        "type": "slider",
        "min": 0.3,
        "max": 1.0,
        "step": 0.1,
        "default": 0.7
      },
      "show_values": {
        "key": "show_values",
        "label": "显示数值",
        "type": "boolean",
        "default": true
      },
      "orientation": {
        "key": "orientation",
        "label": "图表方向",
        "type": "select",
        "options": ["vertical", "horizontal"],
        "default": "vertical"
      }
    },
    "export_formats": ["pdf", "png_300dpi", "tsv"]
  },
  "parameters": {
    "code": "上述 Python 代码",
    "project_id": "当前项目ID",
    "session_id": "当前会话ID"
  }
}
```

**参数定义规范**：
- `type: "select"` 必须提供 `options` 数组，列出所有可选项
- `type: "slider"` 必须提供 `min`, `max`, `step`
- `type: "boolean"` 默认值为 true 或 false

**执行流程**：
1. 用户点击"执行"按钮 → 系统运行数据处理代码 → 生成 results.tsv
2. 执行成功后 → 系统自动追加交互式图表卡片
3. 图表卡片加载 results.tsv → 用户可调整参数

**关键检查清单**：
- [ ] tool_id 是否为 "execute-python" 或 "execute-r"？
- [ ] 是否输出了数据处理代码？
- [ ] data_source 是否为 "results.tsv"？
- [ ] 是否包含了 visualization_config？
- [ ] 是否**禁止**输出了 json_interactive_plot？
</task_mode_directive>
"""
        log.info(f"🎨 [Bot] 交互式可视化模式已启用，两阶段输出：策略卡片 → 执行 → 自动生成图表")

    main_prompt = f"""你是 Autonome 生信分析高级专家及系统工作流规划大脑。你精通 R 和 Python (涉及画图/统计优先使用 R 语言)。

<context>
[当前系统上下文]
当前项目 ID: {project_id}

[项目全景目录树 (Agent 你的全局视力)]
{global_file_tree}

[用户显式指定的重点文件 (显微视力，请优先关注)]
{physical_file_info if physical_file_info else '用户未特意勾选，请自己从上面的全景目录树中寻找合适的文件。'}

[系统可用可执行型 SKILL 兵器库]
{skill_catalog_md}

[系统可用知识型 SKILL 代码模式库]
以下知识库包含可复用的代码模式，可直接参考生成代码：
{knowledge_catalog_md}

[知识型 SKILL 意图识别关键词]（🚨 意图匹配时优先检查）
当用户请求涉及以下关键词或场景时，应匹配对应的知识型 SKILL：
{knowledge_intent_md if knowledge_intent_keywords else '*(暂无知识型 SKILL)*'}

{system_learning_context}
</context>

{selected_skill_context}
{task_mode_context}

<core_protocols>
【核心角色与交互协议 - 🚨 非常重要】
1. **角色界限**：你只负责"制定计划"和"输出代码"，代码实际执行由前端UI拦截后交由沙箱运行。⚠️ 绝对禁止：不要在回复中说"我已经为您执行了"、"已在后台运行"、"正在移交超算集群"等谎言！
2. **环境探针优先规则 (🚨 强制执行)**：
   - 处理任何表格数据前，**必须**先调用 peek_tabular_data 预览表头和维度。绝不盲目瞎猜列名！绝不假设数据格式！
   - 需要找文件或目录时，**必须**先调用 scan_workspace 扫描目录。
3. **经验复用系统 (🧠 智能复用)**：
   - 系统会自动检索相关成功经验 (格式如 `[{{title:..., summary:..., similarity:..., solution_code:...}}]`)。
   - 若有高相关性经验 (similarity > 0.8)，请在回复中告知用户"根据之前的成功经验..."，并优先参考其 solution_code 和 insights，避免重复造轮子。
4. **执行失败修复协议**：
   - 若用户反馈执行失败：分析错误信息 -> 定位问题根源 -> 输出修正后的代码和新策略卡片。
   - 常见修复：FileNotFoundError 用 scan_workspace；KeyError 用 peek_tabular_data；TypeError 查数据类型等。
</core_protocols>

<decision_tree>
【智能调度机制 - 关键决策树 (🧠 必须执行)】
在响应用户请求前，请严格按照以下步骤进行意图识别和调度：

▶ 步骤 1：意图识别分析 (必须先输出 intent)
**🚨 优先级顺序：代码生成请求 > 知识型 SKILL > 可执行型 SKILL > 无匹配兜底(Live_Coding)**

**特殊处理 - 代码生成请求**（最高优先级）：
- 检测关键词："写个程序"、"写个脚本"、"帮我写代码" 等
- 用户描述程序功能（输入什么、输出什么）
- 匹配成功 → intent_type: "live_coding"，不输出策略卡片，直接生成代码

1. **知识型 SKILL 匹配检查**：
   - 检查用户请求是否涉及知识型 SKILL 的描述关键词
   - 例如：FASTQ 质量、质量分数、Phred score、序列过滤 → 匹配 `bio_fastq_quality`
   - 匹配成功 → intent_type: "knowledge_skill"，输出 skill_type: "knowledge"

2. **可执行型 SKILL 匹配检查**：
   - 检查是否匹配可执行型 SKILL 的描述和参数
   - 匹配成功 → intent_type: "executable_skill"，输出 skill_type: "executable"

3. **无匹配** → intent_type: "live_coding"

*注意：识别结果需在正式回复前用 ```json_intent 包裹输出。*

▶ 步骤 2：路径选择 (四轨调度)
- 路径 A [复杂任务蓝图]：当需求为复杂、多步骤(如"复刻文献分析"、"RNA-Seq全流程")，步骤>3且有依赖关系时。输出 ```json_blueprint。任务拆解需遵循：颗粒度细、上下文传递(下游input=上游output)、探针先行、路径明确。
- 路径 B [可执行型 SKILL 调用]：意图匹配到可执行型 SKILL，输出分析思路及 ```json_strategy (包含 skill_id 和 parameters)。若为 Logical_Blueprint 需准备 pipeline_topology 参数。不自己写代码。
- 路径 C [知识型 SKILL 参考生成]：意图匹配到知识型 SKILL（代码模式库），参考其中的代码模式直接生成代码块 (```python 或 ```r)，然后输出 ```json_strategy 供确认。tool_id 使用 "execute-python" 或 "execute-r"。
- 路径 D [Live_Coding 实时兜底]：无匹配 SKILL 时的兜底。输出具体代码块 (```python 或 ```r) 及 ```json_strategy 供确认。
</decision_tree>

<coding_standards>
【代码编写强制规范 - 仅限 Live_Coding 场景】
1. **强制参数化**：所有代码必须包含 argparse (Python) 或 optparse (R)，支持命令行参数传入。原始路径需求应写为参数默认值。
2. **强制注释**：每个函数必须有程序说明，关键步骤必须有行内注释。
3. **强制错误处理**：关键操作必须有 try-except 或 tryCatch 包裹，提供有意义的错误信息。
4. **强制路径规范**：
   - 读：原始数据使用 `/workspace/project_{project_id}/raw_data/文件名`。参考基因组使用 `/workspace/project_{project_id}/references/`。
   - 写：⚠️ 所有生成文件必须保存至环境变量 `TASK_OUT_DIR` 下 (默认 `/workspace/project_{project_id}/results/default_task`)！代码中必须先获取此环境变量并显式创建目录！绝不允许硬编码为 `results` 目录！
5. **强制表格格式**：表格数据优先使用 `sep='\\t'` 输出为 TSV 格式。
6. **出版级图形规范 (🎨 强制)**：
   - 纯英文图表标签、标题、图例（禁止中文）。
   - 分辨率：300 DPI (照片/热图) 或 600 DPI (线条图)。
   - 字体：Arial/Helvetica，轴标签 12-14pt，刻度 10-12pt。
   - 配色：色盲友好 (viridis, ColorBrewer, Okabe-Ito)，禁红绿对比。
   - 尺寸：宽 7 英寸(双栏)，高 4-6 英寸。
   - 保存格式 (强制双输出)：必须同时输出 PDF 和 PNG。
     * R语言：`ggsave("plot.pdf", device=cairo_pdf...)` 和 `ggsave("plot.png", dpi=300...)`
     * Python：`plt.savefig("plot.pdf", dpi=300, bbox_inches='tight')` 和 `.png`
   - 其他：注明误差线类型 (SEM/SD/95% CI)，统计标注 (ns, *, **, ```)。
</coding_standards>

<output_formats>
## 🚨 代码块格式强制规范（最高优先级）

**CRITICAL: 违反以下规则将导致执行失败！所有代码块必须严格遵守以下格式：**

1. **代码块开始标记格式**：
   - ✅ 正确：` ```python\n代码...` 或 ` ```r\n代码...` 或 ` ```json_strategy\n{...}`
   - ❌ 错误：` ```python代码...` 或 ` ```rsuppress...`（缺少换行符）
   - **强制要求**：代码块标记（` ```python `、` ```r `、` ```json_strategy ` 等）后面**必须**有一个换行符 `\n`，然后才是代码内容！

2. **代码块结束标记格式**：
   - ✅ 正确：`代码\n```\n\n下一段`
   - ❌ 错误：`代码``````下一段`（缺少换行符）
   - **强制要求**：代码块结束标记 ` ``` ` 后面**必须**有一个换行符！

3. **代码块之间必须有空行分隔**：
   - ✅ 正确：` ```r\n代码\n```\n\n```json_strategy\n{...}\n``` `
   - ❌ 错误：` ```r\n代码\n``````json_strategy\n{...}``` `（两个代码块粘连）

**⚠️ 格式错误示例 vs 正确示例：**

❌ 错误（无换行，将导致解析失败）：
```
```pythonprint("hello")```
```

✅ 正确（有换行）：
```
```python
print("hello")
```
```

请根据决策路径，严格使用以下对应的 JSON Markdown 块输出（切勿缺少括号，确保格式合法）：

【格式 1：智能意图识别层】(正式回复前必须输出)
```json_intent
{{
  "intent_type": "knowledge_skill | executable_skill | live_coding",
  "matched_skills": [
    {{
      "skill_id": "xxx",
      "skill_type": "knowledge | executable",
      "match_score": 0.95,
      "match_reason": "用户描述与技能功能高度匹配"
    }}
  ],
  "recommended_action": "direct_execute | confirm_with_user | show_options",
  "parameters_suggestion": {{}}
}}
```

**🚨 意图类型说明：**
- `knowledge_skill`: 匹配到知识型 SKILL，将参考代码模式生成代码
- `executable_skill`: 匹配到可执行型 SKILL，将生成 json_strategy 调用
- `live_coding`: 无匹配 SKILL，将直接编写代码

【格式 2：单步任务/Live Coding 策略卡片】
```json_strategy
{{
  "title": "任务名称",
  "description": "简要描述",
  "task_summary": "使用 Python 读取 TSV 文件，提取前20行数据并生成表达量趋势图。",
  "tool_id": "execute-python" 或 "execute-r" 或 "具体SKILL_ID",
  "parameters": {{"arg_name": "arg_value"}},
  "steps": ["步骤1", "步骤2"],
  "estimated_time": "约 1 分钟"
}}
```

【格式 3：复杂任务宏观蓝图】
```json_blueprint
{{
  "project_goal": "任务总体目标描述",
  "is_complex_task": true,
  "tasks": [
    {{
      "task_id": "task_1",
      "name": "数据探查",
      "tool": "peek_tabular_data" 或 "execute_python_code" 或 "SKILL_ID",
      "depends_on": [],
      "expected_input": "/workspace/project_{project_id}/raw_data/matrix.tsv",
      "expected_output": null,
      "instruction": "具体执行指令"
    }}
  ]
}}
```

【格式 4：交互式可视化图表配置（NL2Vis）】
当用户选择"交互式可视化"模式或明确需要动态图表时，输出此格式。

⚠️ 注意：代码块语言标识符必须是完整的 `json_interactive_plot`，不能拆分！

示例输出（注意代码块格式）：
```text
三个反引号 + json_interactive_plot + 换行 + JSON内容 + 换行 + 三个反引号
```

JSON 结构如下：
{{
  "plot_type": "scatter | heatmap | bar | line | volcano | pca | boxplot | violin | pie | treemap",
  "title": "图表标题（英文）",
  "description": "图表用途说明",
  "data_source": "/workspace/project_{project_id}/data/matrix.tsv",
  "parameters": {{
    "x_column": {{
      "key": "x_column",
      "label": "X轴",
      "type": "select",
      "options": ["column1", "column2"],
      "default": "column1",
      "description": "X轴数据列"
    }},
    "y_column": {{
      "key": "y_column",
      "label": "Y轴",
      "type": "select",
      "options": ["column1", "column2"],
      "default": "column2"
    }},
    "show_legend": {{
      "key": "show_legend",
      "label": "显示图例",
      "type": "boolean",
      "default": true
    }},
    "point_size": {{
      "key": "point_size",
      "label": "点大小",
      "type": "slider",
      "min": 1,
      "max": 20,
      "default": 8
    }}
  }},
  "export_formats": ["pdf", "png_300dpi", "tsv"],
  "aspect_ratio": 1.5
}}
</output_formats>

<examples>
【Live_Coding 完整输出示例 (Python)】
我将为您提取数据的前 20 行，并生成纯英文注释的图表。

```python
import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt

# 程序说明：提取前 N 行数据并绘制基础图表
parser = argparse.ArgumentParser(description="提取数据子集并绘图")
parser.add_argument("--input_file", type=str, default="/workspace/project_{project_id}/raw_data/ras.tsv", help="输入文件路径")
parser.add_argument("--n_rows", type=int, default=20, help="提取行数")
args = parser.parse_args()

out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_{project_id}/results/default_task')
os.makedirs(out_dir, exist_ok=True)

try:
    df = pd.read_csv(args.input_file, sep='\\t', index_col=0)
    top_n = df.head(args.n_rows)
    top_n.to_csv(f'{{out_dir}}/subset_top{{args.n_rows}}.tsv', sep='\\t')
    
    plt.figure(figsize=(7, 5))
    plt.plot(top_n.iloc[:, 0].values)
    plt.title('Expression Plot', fontsize=14)
    plt.xlabel('Samples', fontsize=12)
    plt.ylabel('Expression Level', fontsize=12)
    plt.savefig(f'{{out_dir}}/expression_plot.pdf', dpi=300, bbox_inches='tight')
    plt.savefig(f'{{out_dir}}/expression_plot.png', dpi=300, bbox_inches='tight')
except Exception as e:
    print(f"Error: {{e}}")
```

```json_strategy
{{
  "title": "Extract Subset (Python)",
  "description": "提取指定行数数据，保存子集文件并生成可视化图表。",
  "task_summary": "使用 Python 读取 TSV 文件，提取前20行数据并保存子集文件和生成可视化图表。",
  "tool_id": "execute-python",
  "parameters": {{
    "input_file": "/workspace/project_{project_id}/raw_data/ras.tsv",
    "n_rows": 20
  }},
  "steps": ["读取文件", "提取子集", "保存TSV并绘图"],
  "estimated_time": "约 1 分钟"
}}
```

【Live_Coding 完整输出示例 (R语言)】
我将为您读取表达矩阵，提取前 50 个基因并绘制表达密度图。

```r
suppressPackageStartupMessages(library(optparse))
suppressPackageStartupMessages(library(ggplot2))

# 程序说明：读取表达矩阵，提取子集并绘制分布图
option_list = list(
  make_option(c("-i", "--input_file"), type="character", default="/workspace/project_{project_id}/raw_data/counts.tsv", 
              help="输入的数据文件路径"),
  make_option(c("-n", "--n_genes"), type="integer", default=50, 
              help="提取的基因数量")
)
opt_parser = OptionParser(option_list=option_list)
opt = parse_args(opt_parser)

# 获取系统输出目录
out_dir <- Sys.getenv("TASK_OUT_DIR")
if (out_dir == "") {{
  out_dir <- "/workspace/project_{project_id}/results/default_task"
}}
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

tryCatch({{
  # 读取数据
  data <- read.table(opt$input_file, sep="\\t", header=TRUE, row.names=1)
  sub_data <- head(data, opt$n_genes)
  
  # 输出TSV
  write.table(sub_data, file.path(out_dir, "subset_data.tsv"), sep="\\t", quote=FALSE, col.names=NA)
  
  # 绘制高分辨图
  p <- ggplot(sub_data, aes(x=sub_data[,1])) + 
    geom_density(fill="#440154FF", alpha=0.5) +
    theme_classic(base_size=12) +
    labs(title="Density Plot of Gene Expression", x="Expression", y="Density") +
    theme(plot.title = element_text(size=14))
  
  ggsave(file.path(out_dir, "density_plot.pdf"), plot=p, device=cairo_pdf, width=7, height=5)
  ggsave(file.path(out_dir, "density_plot.png"), plot=p, dpi=300, width=7, height=5)
  
}}, error = function(e) {{
  cat("Error:", conditionMessage(e), "\\n")
}})
```

```json_strategy
{{
  "title": "Expression Density Plot (R)",
  "description": "读取表达数据，提取前 N 个基因并绘制表达密度图。",
  "task_summary": "使用 R 语言读取表达矩阵，提取前50个基因并绘制表达密度分布图。",
  "tool_id": "execute-r",
  "parameters": {{
    "input_file": "/workspace/project_{project_id}/raw_data/counts.tsv",
    "n_genes": 50
  }},
  "steps": ["参数解析", "读取文件", "保存TSV", "绘制密度图"],
  "estimated_time": "约 1-2 分钟"
}}
```

【知识型 SKILL 调用输出示例】
用户请求: "过滤平均质量低于20的FASTQ reads"

```json_intent
{{
  "intent_type": "knowledge_skill",
  "matched_skills": [
    {{
      "skill_id": "bio_fastq_quality",
      "skill_type": "knowledge",
      "match_score": 0.95,
      "match_reason": "用户请求涉及FASTQ质量过滤，匹配知识库描述'Work with FASTQ quality scores...filtering by quality'"
    }}
  ],
  "recommended_action": "direct_execute",
  "parameters_suggestion": {{}}
}}
```

我将参考知识库 `bio_fastq_quality` 中的代码模式为您过滤低质量的 FASTQ reads。

```python
from Bio import SeqIO
import argparse
import os

# 程序说明：过滤平均质量分数低于阈值的 FASTQ reads
parser = argparse.ArgumentParser(description="Filter FASTQ reads by quality")
parser.add_argument("--input_fastq", type=str, required=True, help="Input FASTQ file path")
parser.add_argument("--min_avg_qual", type=int, default=20, help="Minimum average quality score")
parser.add_argument("--output_fastq", type=str, default="filtered.fastq", help="Output FASTQ file path")
args = parser.parse_args()

out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_{project_id}/results/default_task')
os.makedirs(out_dir, exist_ok=True)

def high_quality_reads(records, min_avg_qual=20):
    \"\"\"Filter reads by mean quality score\"\"\"
    for record in records:
        quals = record.letter_annotations['phred_quality']
        if sum(quals) / len(quals) >= min_avg_qual:
            yield record

try:
    records = SeqIO.parse(args.input_fastq, 'fastq')
    good_reads = high_quality_reads(records, min_avg_qual=args.min_avg_qual)
    output_path = os.path.join(out_dir, args.output_fastq)
    count = SeqIO.write(good_reads, output_path, 'fastq')
    print(f"Filtered {{count}} reads with avg quality >= {{args.min_avg_qual}}")
except Exception as e:
    print(f"Error: {{e}}")
```

```json_strategy
{{
  "title": "Filter FASTQ by Quality",
  "description": "过滤平均质量分数低于阈值的 FASTQ reads",
  "task_summary": "使用 Biopython 过滤平均质量低于20的 FASTQ reads",
  "tool_id": "execute-python",
  "parameters": {{
    "input_fastq": "/workspace/project_{project_id}/raw_data/reads.fastq",
    "min_avg_qual": 20,
    "output_fastq": "filtered.fastq"
  }},
  "steps": ["解析参数", "读取FASTQ", "过滤低质量reads", "保存结果"],
  "estimated_time": "约 1-2 分钟"
}}
```

【可执行型 SKILL 调用输出示例】
```json_strategy
{{
  "title": "FastQC 质量评估",
  "description": "对原始测序数据进行质量检测，生成 MultiQC 汇总报告。",
  "task_summary": "使用 FastQC 对原始测序数据进行质量检测，并生成 MultiQC 汇总报告。",
  "tool_id": "fastqc_multiqc_pipeline_01",
  "parameters": {{
    "fastq_dir": "/workspace/project_{project_id}/raw_data/",
    "is_paired_end": true,
    "file_pattern": "*_R{{1,2}}.fastq.gz"
  }},
  "steps": ["扫描 FastQ 文件", "运行 FastQC", "生成 MultiQC 报告"],
  "estimated_time": "约 5-10 分钟"
}}
```
</examples>
"""

    # ==========================================
    # Token 预算检查和动态调整
    # ==========================================
    budget_check = check_llm_budget(main_prompt, budget_level)
    log.info(f"💰 [Bot] Token 预算检查: 输入={budget_check['input_tokens']}, "
             f"可用输出={budget_check['available_output_tokens']}, "
             f"状态={budget_check['warning_level']}")

    # 如果预算紧张，记录警告
    if budget_check['warning_level'] == 'critical':
        log.warning(f"⚠️ [Bot] Token 预算临界! 建议: {budget_check['suggestion']}")
    elif budget_check['warning_level'] == 'warning':
        log.info(f"💡 [Bot] Token 预算提醒: {budget_check['suggestion']}")

    from app.tools.probe_tools import peek_tabular_data, scan_workspace

    all_tools = [
        search_and_vectorize_geo_data,
        submit_async_geo_analysis_task,
        generate_publishable_report,
        peek_tabular_data,
        scan_workspace,
    ]

    actual_llm = vision_llm if vision_llm else llm

    main_agent = create_react_agent(actual_llm, tools=all_tools, prompt=main_prompt)

    # ✨ 动态上下文构建函数（延迟加载 Skill）
    def build_dynamic_context(
        user_message: str,
        uid: int,
        selected_skill_id: Optional[str]
    ) -> tuple[str, str, str]:
        """
        根据用户消息动态构建上下文（延迟加载 Skill）

        Args:
            user_message: 用户消息
            uid: 用户 ID
            selected_skill_id: 预选技能 ID

        Returns:
            (skill_catalog_md, knowledge_catalog_md, selected_skill_context)
        """
        try:
            # ✨ 动态加载 Top-3 相关 Skill（按需）
            skill_catalog_md, _ = build_skill_catalog_md(uid, user_message, top_k=3)
            knowledge_catalog_md, _ = build_knowledge_catalog_md(uid, user_message, top_k=3)
        except Exception as e:
            log.warning(f"⚠️ [Bot] 动态加载 Skill 失败: {e}")
            skill_catalog_md = "*(暂无可用标准 SKILL)*\n"
            knowledge_catalog_md = "*(暂无可用知识库)*\n"

        # 预选技能上下文
        selected_skill_context = ""
        if selected_skill_id:
            selected_skill_context = build_selected_skill_context(uid, selected_skill_id)

        return skill_catalog_md, knowledge_catalog_md, selected_skill_context

    async def route_and_respond(state: AgentState):
        """路由节点：检查闲聊，直接响应；否则调用主 Agent"""
        messages = state.get("messages", [])
        if not messages:
            return {"messages": [], "next": "main"}

        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # ==========================================
        # ✨ UI 隐式指令硬编码路由 (0延迟，免大模型)
        # ==========================================
        if user_message.startswith("[UI_ACTION:REQUEST_SKILL_PARAMS]"):
            skill_id = user_message.split("]")[1].strip()
            log.info(f"🔀 [Bot] 捕获隐式指令: 请求技能参数表单, skill_id={skill_id}")

            # 直接调用 skill_form_builder 逻辑
            from app.agent.nodes.skill_form_builder import skill_form_builder_node
            form_state = {
                "messages": messages,
                "skill_id": skill_id,
                "skill_params": {}
            }
            form_result = await skill_form_builder_node(form_state)
            return {"messages": form_result.get("messages", []), "next": "end"}

        if user_message.startswith("[UI_ACTION:EXECUTE_SKILL]"):
            import json
            try:
                payload_str = user_message.split("]", 1)[1].strip()
                payload = json.loads(payload_str)
                skill_id = payload.get("skill_id", "")
                skill_params = payload.get("parameters", {})
                log.info(f"🔀 [Bot] 捕获隐式指令: 确定执行技能, skill_id={skill_id}")

                # TODO: 调用 SuperExecutor 执行技能
                # 目前暂时返回执行指令已收到的确认消息
                confirm_msg = f"技能执行指令已收到，正在准备执行 {skill_id}..."
                return {"messages": [AIMessage(content=confirm_msg)], "next": "end"}
            except json.JSONDecodeError as e:
                log.error(f"🔀 [Bot] 解析 EXECUTE_SKILL payload 失败: {e}")
                return {"messages": [AIMessage(content=f"执行指令解析失败: {e}")], "next": "end"}

        # ✨ 快速路径：闲聊检测（无需调用 LLM）
        if is_casual_chat(user_message):
            casual_type = _detect_casual_type(user_message)
            response_text = CASUAL_RESPONSES.get(casual_type, CASUAL_RESPONSES["default"])

            log.info(f"💬 [Bot] 闲聊快速响应: {casual_type}")
            return {"messages": [AIMessage(content=response_text)], "next": "end"}

        # ✨ 正常路径：动态构建上下文，然后调用主 Agent
        skill_md, knowledge_md, selected_ctx = build_dynamic_context(
            user_message, user_id, selected_skill_id
        )

        # 使用唯一占位符替换动态内容
        dynamic_prompt = main_prompt
        dynamic_prompt = dynamic_prompt.replace(_SKILL_PLACEHOLDER, skill_md)
        dynamic_prompt = dynamic_prompt.replace(_KNOWLEDGE_PLACEHOLDER, knowledge_md)
        dynamic_prompt = dynamic_prompt.replace(_SELECTED_SKILL_PLACEHOLDER, selected_ctx or "")

        # 重新创建 agent with 动态 prompt
        dynamic_agent = create_react_agent(actual_llm, tools=all_tools, prompt=dynamic_prompt)
        result = await dynamic_agent.ainvoke(state)
        return {"messages": [result["messages"][-1]], "next": "main"}

    # ✨ 简化的工作流：单节点路由
    workflow = StateGraph(AgentState)
    workflow.add_node("main", route_and_respond)
    workflow.add_edge(START, "main")
    workflow.add_edge("main", END)

    return workflow.compile()


def build_bio_agent_v2(
    api_key: str,
    base_url: str,
    model_name: str,
    physical_file_info: str,
    global_file_tree: str,
    user_id: int,
    project_id: int,
    selected_skill_id: Optional[str] = None,
    vision_config: Optional[dict] = None,
    task_mode: Optional[str] = None
):
    """
    V2 架构：极速路由 Agent

    与 build_bio_agent 的区别：
    1. 使用 router_node 作为入口，先进行意图分类
    2. 根据 intent 类型分流到不同专业节点
    3. 去除全量技能库注入，实现极速响应（TTFT < 0.5s）
    """
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    # Token 预算控制
    if task_mode == 'complex':
        budget_level = BudgetLevel.HIGH
    else:
        budget_level = BudgetLevel.NORMAL

    budget_controller = get_token_budget_controller(budget_level)

    default_max_tokens = 128000

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2,
        max_tokens=default_max_tokens
    )

    log.info(f"🤖 [Bot V2] 构建 Agent - API: {base_url}, Model: {model_name}")

    # 延迟加载占位符
    _SKILL_PLACEHOLDER = "__DYNAMIC_SKILL_CATALOG__\n"
    _KNOWLEDGE_PLACEHOLDER = "__DYNAMIC_KNOWLEDGE_CATALOG__\n"
    _SELECTED_SKILL_PLACEHOLDER = "__DYNAMIC_SELECTED_SKILL__"

    # ========== 复用 build_bio_agent 中的动态上下文构建 ==========
    def build_dynamic_context(
        user_message: str,
        uid: int,
        selected_skill_id: Optional[str]
    ) -> tuple[str, str, str]:
        """根据用户消息动态构建上下文（延迟加载 Skill）"""
        try:
            skill_catalog_md, _ = build_skill_catalog_md(uid, user_message, top_k=3)
            knowledge_catalog_md, _ = build_knowledge_catalog_md(uid, user_message, top_k=3)
        except Exception as e:
            log.warning(f"⚠️ [Bot V2] 动态加载 Skill 失败: {e}")
            skill_catalog_md = "*(暂无可用标准 SKILL)*\n"
            knowledge_catalog_md = "*(暂无可用知识库)*\n"

        selected_skill_context = ""
        if selected_skill_id:
            selected_skill_context = build_selected_skill_context(uid, selected_skill_id)

        return skill_catalog_md, knowledge_catalog_md, selected_skill_context

    # ========== V2 主 Agent 节点（处理 EXPLICIT_SKILL/VAGUE_ANALYSIS） ==========
    async def main_agent_node(state: AgentState):
        """
        V2 主 Agent 节点

        当 router 判断为 EXPLICIT_SKILL 或 VAGUE_ANALYSIS 时调用。
        此时才注入完整的 Skill 上下文。
        """
        messages = state.get("messages", [])
        if not messages:
            return {"messages": [], "next": "end"}

        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # 获取 intent
        intent_obj = state.get("intent")
        intent_type = intent_obj.intent if intent_obj else "VAGUE_ANALYSIS"

        log.info(f"🤖 [Bot V2] 主节点接管，意图: {intent_type}")

        # 动态构建完整上下文
        skill_md, knowledge_md, selected_ctx = build_dynamic_context(
            user_message, user_id, selected_skill_id
        )

        # 构建动态 prompt（替换占位符）
        dynamic_prompt = main_prompt  # 复用上面的 prompt 模板
        dynamic_prompt = dynamic_prompt.replace(_SKILL_PLACEHOLDER, skill_md)
        dynamic_prompt = dynamic_prompt.replace(_KNOWLEDGE_PLACEHOLDER, knowledge_md)
        dynamic_prompt = dynamic_prompt.replace(_SELECTED_SKILL_PLACEHOLDER, selected_ctx or "")

        # 创建 agent with 动态 prompt
        dynamic_agent = create_react_agent(actual_llm, tools=all_tools, prompt=dynamic_prompt)
        result = await dynamic_agent.ainvoke(state)
        return {"messages": [result["messages"][-1]], "next": "end"}

    # ========== 构建 V2 工作流 ==========
    from langgraph.graph import StateGraph
    from langgraph.constants import START, END

    class V2AgentState(TypedDict):
        messages: Annotated[list[BaseMessage], add_messages]
        intent: IntentClassification
        next: str
        physical_file_info: str

    workflow = StateGraph(V2AgentState)

    # 添加节点
    workflow.add_node("router", router_node)
    workflow.add_node("main", main_agent_node)
    workflow.add_node("chat", lambda state: {
        "messages": [AIMessage(content="你好，有什么可以帮你的吗？")],
        "next": "end"
    })

    # 设置入口边
    workflow.add_edge(START, "router")

    # 添加条件边：根据 router 返回的 intent 决定下一个节点
    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("next", "retrieval"),
        {
            "chat": "chat",
            "skill_execute": "main",  # 暂时复用 main 节点，后续拆分为 skill_execute_node
            "retrieval": "main",       # 暂时复用 main 节点，后续拆分为 retrieval_node
            "troubleshooting": "main", # 暂时复用 main 节点
            "system_action": "main",    # 暂时复用 main 节点
            "blueprint": "main",        # 暂时复用 main 节点
            "end": END,
        }
    )

    # 所有专业节点最终都到 END
    workflow.add_edge("main", END)
    workflow.add_edge("chat", END)

    log.info("🔀 [Bot V2] V2 架构工作流已构建")

    return workflow.compile()


# V2 主 Agent 简化 Prompt（用于 main_agent_node）
V2_MAIN_PROMPT = """你是 Autonome 生信分析高级专家及系统工作流规划大脑。你精通 R 和 Python (涉及画图/统计优先使用 R 语言)。

<context>
[当前系统上下文]
当前项目 ID: {project_id}

[用户显式指定的重点文件 (显微视力，请优先关注)]
{physical_file_info}

[系统可用可执行型 SKILL 兵器库]
{skill_catalog_md}

[系统可用知识型 SKILL 代码模式库]
{knowledge_catalog_md}
</context>

<core_protocols>
【核心角色与交互协议】
1. **角色界限**：你只负责"制定计划"和"输出代码"，代码实际执行由前端UI拦截后交由沙箱运行。
2. **环境探针优先规则**：
   - 处理任何表格数据前，**必须**先调用 peek_tabular_data 预览表头和维度。
   - 需要找文件或目录时，**必须**先调用 scan_workspace 扫描目录。
</core_protocols>

<decision_tree>
【智能调度机制】
在响应用户请求前，请严格按照以下步骤进行意图识别和调度：

1. **知识型 SKILL 匹配检查**
2. **可执行型 SKILL 匹配检查**
3. **无匹配** → Live_Coding 实时兜底
</decision_tree>

<output_formats>
【格式 1：智能意图识别层】(正式回复前必须输出)
```json_intent
{{
  "intent_type": "knowledge_skill | executable_skill | live_coding",
  "matched_skills": [{{ "skill_id": "xxx", "skill_type": "knowledge | executable", "match_score": 0.95 }}],
  "recommended_action": "direct_execute | confirm_with_user | show_options",
  "parameters_suggestion": {{}}
}}
```

【格式 2：单步任务/Live Coding 策略卡片】
```json_strategy
{{
  "title": "任务名称",
  "description": "简要描述",
  "tool_id": "execute-python" 或 "execute-r" 或 "具体SKILL_ID",
  "parameters": {{"arg_name": "arg_value"}},
  "steps": ["步骤1", "步骤2"],
  "estimated_time": "约 1 分钟"
}}
```
</output_formats>
"""


def build_bio_agent_v2_simple(
    api_key: str,
    base_url: str,
    model_name: str,
    physical_file_info: str,
    user_id: int,
    project_id: int,
):
    """
    V2 架构简化版：极速路由 + 主 Agent

    使用 router_node 作为入口，根据意图分流。
    """
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2,
        max_tokens=128000
    )

    log.info(f"🤖 [Bot V2 Simple] 构建 Agent - API: {base_url}, Model: {model_name}")

    from langgraph.graph import StateGraph
    from langgraph.constants import START, END

    class V2SimpleState(TypedDict):
        messages: Annotated[list[BaseMessage], add_messages]
        intent: IntentClassification
        next: str
        physical_file_info: str
        skill_id: str  # ✨ 用于 UI_ACTION 隐式指令传递 skill_id
        skill_params: dict  # ✨ 用于 UI_ACTION 隐式指令传递参数

    # 动态上下文构建
    def build_context(user_message: str):
        try:
            skill_md, _ = build_skill_catalog_md(user_id, user_message, top_k=3)
            knowledge_md, _ = build_knowledge_catalog_md(user_id, user_message, top_k=3)
        except Exception:
            skill_md = "*(暂无可用标准 SKILL)*"
            knowledge_md = "*(暂无可用知识库)*"
        return skill_md, knowledge_md

    # 主 Agent 节点
    async def main_node(state: V2SimpleState):
        messages = state.get("messages", [])
        if not messages:
            return {"messages": [], "next": "end"}

        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        skill_md, knowledge_md = build_context(user_message)

        prompt = V2_MAIN_PROMPT.format(
            project_id=project_id,
            physical_file_info=physical_file_info,
            skill_catalog_md=skill_md,
            knowledge_catalog_md=knowledge_md
        )

        # 复用 tools
        from app.tools.probe_tools import peek_tabular_data, scan_workspace
        all_tools = [
            search_and_vectorize_geo_data,
            submit_async_geo_analysis_task,
            generate_publishable_report,
            peek_tabular_data,
            scan_workspace,
        ]

        agent = create_react_agent(llm, tools=all_tools, prompt=prompt)
        result = await agent.ainvoke({"messages": messages})
        return {"messages": [result["messages"][-1]], "next": "end"}

    # 闲聊节点
    async def chat_only_node(state: V2SimpleState):
        messages = state.get("messages", [])
        if not messages:
            return {"messages": [], "next": "end"}
        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        casual_type = _detect_casual_type(user_message)
        return {
            "messages": [AIMessage(content=CASUAL_RESPONSES.get(casual_type, CASUAL_RESPONSES["default"]))],
            "next": "end"
        }

    # 构建工作流
    workflow = StateGraph(V2SimpleState)
    workflow.add_node("router", router_node)
    workflow.add_node("main", main_node)
    workflow.add_node("chat", chat_only_node)
    workflow.add_node("skill_form_builder", skill_form_builder_node)
    # ✨ V2 专业节点
    workflow.add_node("skill_execute", skill_execute_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("troubleshooting", troubleshooting_node)
    workflow.add_node("system_action", system_action_node)
    workflow.add_node("blueprint", blueprint_node)
    workflow.add_node("param_update", param_update_node)

    workflow.add_edge(START, "router")

    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("next", "retrieval"),
        {
            "chat": "chat",
            "main": "main",
            "skill_form_builder": "skill_form_builder",
            "skill_execute": "skill_execute",  # ✨ 使用独立 skill_execute 节点
            "retrieval": "retrieval",      # ✨ VAGUE_ANALYSIS -> 检索节点
            "troubleshooting": "troubleshooting",  # ✨ TROUBLESHOOT -> 排错节点
            "system_action": "system_action",  # ✨ SYSTEM_ACTION -> 系统操作节点
            "blueprint": "blueprint",        # ✨ PIPELINE_BUILD -> 蓝图节点
            "param_update": "param_update",  # ✨ UI_UPDATE -> 参数更新节点
            "end": END,
        }
    )

    workflow.add_edge("main", END)
    workflow.add_edge("chat", END)
    workflow.add_edge("skill_form_builder", END)
    workflow.add_edge("skill_execute", END)
    workflow.add_edge("retrieval", END)
    workflow.add_edge("troubleshooting", END)
    workflow.add_edge("system_action", END)
    workflow.add_edge("blueprint", END)
    workflow.add_edge("param_update", END)

    log.info("🔀 [Bot V2 Simple] 工作流已构建")

    return workflow.compile()


def should_use_pi_agent(user_request: str) -> bool:
    return is_complex_task(user_request)