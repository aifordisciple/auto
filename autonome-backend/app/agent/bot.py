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

    # 简化版：直接使用单一 Agent，不再使用多 Agent Supervisor 模式
    # 这样更稳定，兼容所有模型
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
