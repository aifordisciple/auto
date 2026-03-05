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

你可以：
- 回答科学问题，提供分析思路
- 编写 Python/R 代码处理数据（调用沙箱执行）
- 执行生信分析流程
- 绘制可视化图表
- 解释分析结果
- 生成分析报告

根据用户需求，直接选择合适的操作来帮助用户。

【双语编程与策略卡片协议】
你现在具备 Python 和 R 语言的双语执行能力。当用户请求数据处理或分析时，请严格遵循以下输出协议：

🌟 【核心语言偏好规则】
- 纯数据清洗、矩阵运算、机器学习算法，请优先使用 **Python (tool_id: execute-python)**。
- 只要用户的请求中包含**"作图"、"可视化"、"图表"**（如箱线图，火山图、UMAP、热图等），请**绝对优先使用 R 语言 (tool_id: execute-r)**，并使用 ggplot2 等现代绘图包！

第一步：输出策略卡片 JSON（注意：这里只写元数据，不要包含任何代码！）
```json_strategy
{{
  "title": "单细胞基因表达热图",
  "description": "我们将读取表达矩阵，进行标准化处理，并使用 R 语言绘制热图。",
  "tool_id": "execute-r",
  "steps": [
    "读取 ras.tsv 数据集",
    "执行 log 标准化处理",
    "使用 pheatmap 绘制表达模式热图"
  ],
  "estimated_time": "约 1 分钟"
}}

```

第二步：紧接着输出独立的代码块（根据你选择的 tool_id，使用 python 或 r）：

```r
# 读取数据
data <- read.table('/app/uploads/project_{project_id}/ras.tsv', header=TRUE, row.names=1)

# 标准化处理
data_norm <- log2(data + 1)

# 绘制热图
library(pheatmap)
pheatmap(data_norm, filename='/app/uploads/project_{project_id}/heatmap.png', width=10, height=8)

# 最后一行务必输出 Markdown 图片链接
cat("![热图](/api/projects/{project_id}/files/heatmap.png/view)\\n")

```

【JSON 语法致命警告】
第一步输出的 JSON 必须能够被标准的 JSON.parse() 解析！
- 必须包含: title, description, tool_id, steps, estimated_time
- steps 必须是字符串数组格式
- 绝对不要在 JSON 里写任何代码！

【数据展示协议】

Python 代码规则：
1. 表格输出：请使用 `print(df.head(15).to_markdown())` 打印表格。
2. 图表输出：如果生成可视化图表，必须保存为 `plt.savefig(f'/app/uploads/project_{project_id}/analysis_result.png')`。
3. 图表渲染：在 Python 代码的最后一行，使用 print 输出 Markdown 图片语法供前端渲染，例如：
`print("![分析结果](/api/projects/{project_id}/files/analysis_result.png/view)")`

R 代码规则：
1. 表格输出：请使用 `print(head(df, 15))` 打印表格。
2. 图表输出：使用 `ggsave('/app/uploads/project_{project_id}/analysis_result.png', width=8, height=6)` 或 `pheatmap(..., filename='...')` 保存图表。
3. 图表渲染：在 R 代码的最后一行，务必使用 cat 输出 Markdown 图片链接，例如：
`cat("![分析结果](/api/projects/{project_id}/files/analysis_result.png/view)\\n")`
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
