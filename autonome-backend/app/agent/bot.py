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

🚨🚨🚨 绝对指令：
1. 绝对禁止使用底层的 Function Calling 或工具调用（Tool Calls）！
2. 你的回复必须严格遵循以下结构，直接以 ``` json_strategy 开头，前面绝对不能有任何问候或引导性文字！

```json_strategy
{{
  "title": "单细胞基因表达热图",
  "description": "读取表达矩阵并使用 R 语言绘制热图。",
  "tool_id": "execute-r",
  "steps": ["读取 ras.tsv", "绘制热图并保存"],
  "estimated_time": "约 1-2 分钟"
}}
```

```r
# 务必静默加载包，防止向控制台输出乱码和废话
suppressPackageStartupMessages(library(pheatmap))

# 读取数据与画图
data <- read.table('/app/uploads/project_{project_id}/ras.tsv', header=TRUE, row.names=1)
pheatmap(data, filename='/app/uploads/project_{project_id}/heatmap.png')

# 输出图片与图形说明
cat("\\n![Analysis_Result](/api/projects/{project_id}/files/heatmap.png/view)\\n\\n")
cat("### 图形解读\\n")
cat("这幅热图展示了基因在不同样本中的表达模式。红色代表高表达，蓝色代表低表达...\\n")
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
