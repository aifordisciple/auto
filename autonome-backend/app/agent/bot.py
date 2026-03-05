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
已挂载物理文件: {physical_file_info if physical_file_info else '无'}

📁 【重要】文件存储位置说明：
- 所有项目文件都保存在项目专属文件夹中：/app/uploads/project_{project_id}/
- 当需要读取或操作项目文件时，请使用 os.listdir('/app/uploads/project_{project_id}/') 列出文件
- 读取文件时使用完整路径，例如：pd.read_csv('/app/uploads/project_{project_id}/ras.tsv')
"""
    
    # 简化版：直接使用单一 Agent
    main_prompt = f"""你是 Autonome 生信分析助手。
{context_info}

你可以：
- 回答科学问题，提供分析思路
- 编写 Python 代码处理数据（调用沙箱执行）
- 执行生信分析流程
- 绘制可视化图表
- 解释分析结果
- 生成分析报告

根据用户需求，直接选择合适的操作来帮助用户。

【策略卡片模式】当用户请求画图、处理数据或执行生信分析时，你 **绝不能** 直接调用沙箱！
你必须严格按照以下 JSON 格式输出策略卡片，注意使用 ```json_strategy 包裹：

```json_strategy
{{
  "title": "数据分析与可视化",
  "description": "简要描述此分析的目的和步骤",
  "tool_id": "execute-python",
  "code": "import pandas as pd\\nimport matplotlib.pyplot as plt\\n# 这里写完整的分析代码...",
  "estimated_time": "约 1 分钟"
}}

```

【数据展示协议】编写 `code` 时请严格遵守：

1. 表格输出：请使用 `print(df.head(15).to_markdown())` 打印表格。
2. 图表输出：如果生成可视化图表，必须保存为 `plt.savefig(f'/app/uploads/project_{project_id}/analysis_result.png')`。
3. 图表渲染：在 Python 代码的最后一行，使用 print 输出 Markdown 图片语法供前端渲染，例如：
`print("![分析结果](/api/projects/{project_id}/files/analysis_result.png/view)")`
"""
    
    all_tools = [execute_python_code, rnaseq_qc, search_and_vectorize_geo_data, submit_async_geo_analysis_task, generate_publishable_report]
    main_agent = create_react_agent(llm, tools=all_tools, prompt=main_prompt)

    async def run_agent(state: AgentState):
        result = await main_agent.ainvoke(state)
        return {"messages": [result["messages"][-1]]}

    workflow = StateGraph(AgentState)
    workflow.add_node("main", run_agent)
    workflow.add_edge(START, "main")
    workflow.add_edge("main", END)

    return workflow.compile()
