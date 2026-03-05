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


def build_bio_agent(api_key: str, base_url: str, model_name: str, physical_file_info: str, user_id: int, project_id: int):
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
当前用户 ID: {user_id}
当前项目 ID: {project_id}
已挂载物理文件: {physical_file_info if physical_file_info else '当前项目为空，没有文件'}

📁 【重要】文件存储位置说明：
- 用户的物理文件都已经列在上面的"已挂载物理文件"中了，当用户询问有哪些文件时，请直接回答上述列表，不要写代码。
- 当你在策略卡片中编写读取文件的 Python 代码时，请务必使用完整路径，例如：pd.read_csv('/app/uploads/project_{project_id}/ras.tsv')
"""
    
    # 简化版：直接使用单一 Agent
    main_prompt = f"""你是 Autonome 生信分析助手。
{context_info}

🚨🚨🚨 绝对指令（防截断生命线）：
1. 绝对禁止使用 Function Calling 或任何底层工具调用！
2. 为了防止代码截断，你**必须且只能**先输出执行代码，然后再输出策略卡片！

【第一部分：先输出执行代码】
```r
sink(nullfile())
suppressPackageStartupMessages(library(pheatmap))

data <- read.table('/app/uploads/project_{project_id}/ras.tsv', header=TRUE, row.names=1)
pheatmap(data, filename='/app/uploads/project_{project_id}/heatmap.png')
sink()
```

【第二部分：最后输出策略卡片】
```json_strategy
{{
  "title": "单细胞基因表达热图",
  "description": "读取表达矩阵并使用 R 语言绘制热图。",
  "tool_id": "execute-r",
  "steps": ["读取 ras.tsv", "绘制热图并保存"],
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
