from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.tools.bio_tools import bio_tools_list, execute_python_code, rnaseq_qc
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

📁 【核心强制规范：文件存储与路径】
1. 读取数据：用户原始数据都在 `raw_data/` 目录下。代码中读取必须使用完整绝对路径，如：`/app/uploads/project_{project_id}/raw_data/文件名`
2. 输出数据：你的所有分析结果(图表/CSV)必须保存在 `results/` 目录下。写入时必须使用绝对路径，如：`/app/uploads/project_{project_id}/results/文件名`
"""
    
    # 简化版：直接使用单一 Agent
    main_prompt = f"""你是 Autonome 生信分析高级专家。
{context_info}

【双语编程与策略卡片协议】
🚨🚨🚨 绝对指令：
1. 禁止使用 Function Calling 或底层工具！
2. 必须先输出代码，再输出策略卡片 JSON！

【第一部分：执行代码示例】
```r
sink(nullfile())
suppressPackageStartupMessages(library(pheatmap))

# ✨ 注意路径：从 raw_data 读，向 results 写
data <- read.table('/app/uploads/project_{project_id}/raw_data/ras.tsv', header=TRUE, row.names=1)
pheatmap(data, filename='/app/uploads/project_{project_id}/results/heatmap.png')

tryCatch({{
  summary_info <- paste("【维度】:", nrow(data), "行", ncol(data), "列")
  # 写入 results 目录
  writeLines(summary_info, '/app/uploads/project_{project_id}/results/data_summary.txt')
}}, error = function(e) {{ NULL }})

sink()

```

【第二部分：策略卡片示例】

```json_strategy
{{
  "title": "单细胞基因表达热图",
  "description": "读取表达矩阵绘制热图，结果保存至 results 目录。",
  "tool_id": "execute-r",
  "steps": ["读取 raw_data 数据", "绘制并保存至 results"],
  "estimated_time": "约 1-2 分钟"
}}
```
"""
    
    # ✅ 修复后：彻底没收 Python 直接执行工具，让 LLM 专职当"大脑"写策略
    all_tools = [rnaseq_qc, search_and_vectorize_geo_data, submit_async_geo_analysis_task, generate_publishable_report]
    main_agent = create_react_agent(llm, tools=all_tools, prompt=main_prompt)

    async def run_agent(state: AgentState):
        result = await main_agent.ainvoke(state)
        return {"messages": [result["messages"][-1]]}

    workflow = StateGraph(AgentState)
    workflow.add_node("main", run_agent)
    workflow.add_edge(START, "main")
    workflow.add_edge("main", END)

    return workflow.compile()
