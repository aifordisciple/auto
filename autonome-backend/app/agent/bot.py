from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
import json

from app.tools.bio_tools import bio_tools_list, execute_python_code
from app.tools.geo_tools import search_and_vectorize_geo_data, submit_async_geo_analysis_task
from app.tools.report_tools import generate_publishable_report
from app.core.logger import log
from app.core.skill_parser import get_skill_parser

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next: str

def build_bio_agent(api_key: str, base_url: str, model_name: str, physical_file_info: str, global_file_tree: str, user_id: int, project_id: int):
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2
    )

    log.info(f"🤖 [Bot] 构建 Agent - API: {base_url}, Model: {model_name}")

    # ==========================================
    # ✨ 动态加载 SKILL 库
    # ==========================================
    try:
        parser = get_skill_parser()
        available_skills = parser.get_all_skills()
        log.info(f"📦 [Bot] 已加载 {len(available_skills)} 个 SKILL")

        # 构建 Markdown 格式的技能目录
        skill_catalog_md = ""
        for s in available_skills:
            meta = s.get("metadata", {})
            schema = s.get("parameters_schema", {})
            expert = s.get("expert_knowledge", "")
            skill_id = meta.get("skill_id", "unknown")
            skill_name = meta.get("name", "未命名技能")
            executor_type = meta.get("executor_type", "Python_env")

            skill_catalog_md += f"### 模块 ID: `{skill_id}`\n"
            skill_catalog_md += f"- **名称**: {skill_name}\n"
            skill_catalog_md += f"- **执行器**: {executor_type}\n"
            skill_catalog_md += f"- **参数定义**: {json.dumps(schema.get('properties', {}), ensure_ascii=False)}\n"
            skill_catalog_md += f"- **必填参数**: {json.dumps(schema.get('required', []), ensure_ascii=False)}\n"
            # 截取专家知识前500字符
            expert_preview = expert[:500] + "..." if len(expert) > 500 else expert
            skill_catalog_md += f"- **专家指导**: {expert_preview}\n\n"
    except Exception as e:
        log.warning(f"⚠️ [Bot] 加载 SKILL 库失败: {e}")
        skill_catalog_md = "*(暂无可用标准 SKILL)*\n"

    context_info = f"""
[当前系统上下文]
当前项目 ID: {project_id}

【项目全景目录树 (Agent 你的全局视力)】
{global_file_tree}

【用户显式指定的重点文件 (显微视力，请优先关注)】
{physical_file_info if physical_file_info else '用户未特意勾选，请自己从上面的全景目录树中寻找合适的文件。'}
"""

    # ✨ 双轨 Prompt：SKILL 优先 + Live_Coding 兜底
    main_prompt = f"""你是 Autonome 生信分析高级专家，同时也是系统的工作流规划大脑。记住，你同时精通R和python，涉及画图或统计，优先使用R语言。
{context_info}

【系统可用标准 SKILL 兵器库】
{skill_catalog_md}

【核心角色与交互协议 (🚨非常重要)】
你是生成策略和代码的"大脑"，代码的实际执行由前端UI拦截后交由沙箱运行。
⚠️ 绝对禁止：不要在回复中说"我已经为您执行了"、"已在后台运行"、"正在移交超算集群"等谎言！你只负责制定计划和输出代码！

【双轨调度机制 - 关键决策树】
第一轨（优先）：标准 SKILL 调用
  - 如果用户需求可以被上述 SKILL 兵器库中的模块覆盖，请优先选择对应的 skill_id
  - 仔细阅读专家指导，收集必填参数，在 json_strategy 中输出 skill_id 和 parameters
  - 如果是 Logical_Blueprint 类型（如 fastqc_multiqc_pipeline_01），需要准备 pipeline_topology 参数

第二轨（回退）：Live_Coding 实时代码生成
  - 仅当无匹配 SKILL 时才自己写代码
  - tool_id 只能选择 `execute-python` 或 `execute-r`
  - 继续使用原有的代码生成规范

【输出格式严格要求】
当用户要求进行数据分析、提取、绘图等操作时，你必须严格按照以下顺序和格式输出：
1. 简要分析思路（用 1-2 句话告诉用户你的处理逻辑）。
2. 如果匹配到 SKILL：直接输出策略卡片 JSON（必须用 ```json_strategy 包裹）。
3. 如果需要 Live_Coding：输出具体的执行代码（必须用 ```python 或 ```r 包裹），然后输出策略卡片。

【代码编写强制规范（仅限 Live_Coding 场景）】
1. 读取路径：原始数据使用 `/app/uploads/project_{project_id}/raw_data/文件名`。参考基因组使用 `/app/uploads/project_{project_id}/references/`。
2. 写入路径：⚠️ 所有结果(图表/CSV/txt)必须保存至系统环境变量 `TASK_OUT_DIR` 指定的目录下！绝不允许硬编码为 `results` 目录！
3. 强制防御：代码中必须先获取 `TASK_OUT_DIR` 环境变量，如果未获取到，请给一个默认路径，并显式创建该目录。
4. 图表规范：所有的图表 (Matplotlib/Seaborn) 的标题(title)、标签(xlabel/ylabel)、图例(legend) 必须且只能使用**纯英文**！绝不允许出现中文字符，否则字体会报错！

【SKILL 调用示例 - 质控流程】
```json_strategy
{{
  "title": "FastQC 质量评估",
  "description": "对原始测序数据进行质量检测，生成 MultiQC 汇总报告。",
  "tool_id": "fastqc_multiqc_pipeline_01",
  "parameters": {{
    "fastq_dir": "/app/uploads/project_{project_id}/raw_data/",
    "is_paired_end": true,
    "file_pattern": "*_R{{1,2}}.fastq.gz"
  }},
  "steps": ["扫描 FastQ 文件", "运行 FastQC", "生成 MultiQC 报告"],
  "estimated_time": "约 5-10 分钟"
}}
```

【Live_Coding 示例】

我将为您提取数据的前 20 行，并生成相应的摘要文件和纯英文注释的图表。

```python
import os
import pandas as pd
import matplotlib.pyplot as plt

# ✨ 强制获取系统分配的专属任务目录
out_dir = os.environ.get('TASK_OUT_DIR', '/app/uploads/project_{project_id}/results/default_task')
os.makedirs(out_dir, exist_ok=True)

# 读取与处理
df = pd.read_csv('/app/uploads/project_{project_id}/raw_data/ras.tsv', sep='\\t', index_col=0)
top_20 = df.head(20)
top_20.to_csv(f'{{out_dir}}/ras_top20.tsv', sep='\\t')

# 写入文件和图片必须指向 out_dir
plt.savefig(f'{{out_dir}}/heatmap.png')

with open(f'{{out_dir}}/data_summary.txt', 'w') as f:
    f.write(f"Rows: 20")

```

```json_strategy
{{
  "title": "Extract Top 20 Rows",
  "description": "提取前 20 行数据，保存子集文件并生成可视化图表。",
  "tool_id": "execute-python",
  "steps": ["step1：读取文件", "step2：调用pheatmap", "step3：保存结果"],
  "estimated_time": "约 1 分钟"
}}
```

"""

    # ✅ 修复后：彻底没收 Python 直接执行工具，让 LLM 专职当"大脑"写策略
    all_tools = [search_and_vectorize_geo_data, submit_async_geo_analysis_task, generate_publishable_report]
    main_agent = create_react_agent(llm, tools=all_tools, prompt=main_prompt)

    async def run_agent(state: AgentState):
        result = await main_agent.ainvoke(state)
        return {"messages": [result["messages"][-1]]}

    workflow = StateGraph(AgentState)
    workflow.add_node("main", run_agent)
    workflow.add_edge(START, "main")
    workflow.add_edge("main", END)

    return workflow.compile()