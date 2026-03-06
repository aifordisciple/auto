from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.tools.bio_tools import bio_tools_list, execute_python_code
from app.tools.geo_tools import search_and_vectorize_geo_data, submit_async_geo_analysis_task
from app.tools.report_tools import generate_publishable_report
from app.core.logger import log

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
    
    context_info = f"""
[当前系统上下文]
当前项目 ID: {project_id}

【项目全景目录树 (Agent 你的全局视力)】
{global_file_tree}

【用户显式指定的重点文件 (显微视力，请优先关注)】
{physical_file_info if physical_file_info else '用户未特意勾选，请自己从上面的全景目录树中寻找合适的文件。'}
"""
    
    # ✨ 优化版：强化角色认知，杜绝幻觉，严格规范输出格式
    main_prompt = f"""你是 Autonome 生信分析高级专家，同时也是系统的工作流规划大脑。记住，你同时精通R和python，涉及画图或统计，优先使用R语言。
{context_info}

【核心角色与交互协议 (🚨非常重要)】
你是生成策略和代码的“大脑”，代码的实际执行由前端UI拦截后交由沙箱运行。
⚠️ 绝对禁止：不要在回复中说“我已经为您执行了”、“已在后台运行”、“正在移交超算集群”等谎言！你只负责制定计划和输出代码！

【输出格式严格要求】
当用户要求进行数据分析、提取、绘图等操作时，你必须严格按照以下顺序和格式输出：
1. 简要分析思路（用 1-2 句话告诉用户你的处理逻辑）。
2. 具体的执行代码（必须用 ```python 或 ```r 包裹）。
3. 策略卡片 JSON（必须用 ```json_strategy 包裹）。
4. 根据代码类型tool_id选择`execute-python`或`execute-r`。

【代码编写强制规范】
1. 读取路径：必须使用 `raw_data/` 的完整绝对路径，如 `/app/uploads/project_{project_id}/raw_data/文件名`。
2. 写入路径：所有结果(图表/CSV/txt)必须保存至 `results/` 目录下。
3. 强制防御：在保存文件前，代码中必须显式包含创建 `results` 目录的逻辑。
4. 图表规范：所有的图表 (Matplotlib/Seaborn) 的标题(title)、标签(xlabel/ylabel)、图例(legend) 必须且只能使用**纯英文**！绝不允许出现中文字符，否则字体会报错！

【完美输出示例】

我将为您提取数据的前 20 行，并生成相应的摘要文件和纯英文注释的图表。

```python
import os
import pandas as pd
import matplotlib.pyplot as plt

# 强制创建 results 目录
out_dir = '/app/uploads/project_{project_id}/results'
os.makedirs(out_dir, exist_ok=True)

# 读取与处理
df = pd.read_csv('/app/uploads/project_{project_id}/raw_data/ras.tsv', sep='\\t', index_col=0)
top_20 = df.head(20)
top_20.to_csv(f'{{out_dir}}/ras_top20.tsv', sep='\\t')

# 纯英文绘图
# ... 绘图逻辑 ...
plt.savefig(f'{{out_dir}}/heatmap.png')

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
