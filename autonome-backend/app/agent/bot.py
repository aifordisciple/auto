from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

# 引入你的底层工具
from app.tools.bio_tools import bio_tools_list, execute_python_code, rnaseq_qc
from app.tools.geo_tools import search_and_vectorize_geo_data, submit_async_geo_analysis_task
from app.tools.report_tools import generate_publishable_report

# ==========================================
# 1. 定义多智能体共享的底层记忆状态
# ==========================================
class AgentState(TypedDict):
    # add_messages 会自动合并对话历史，确保 Agent 们能互相"看到"对方的发言
    messages: Annotated[list[BaseMessage], add_messages]
    next: str  # 记录下一步由哪个 Agent 接管

def build_bio_agent(api_key: str, base_url: str, model_name: str, physical_file_info: str, user_id: int, project_id: int):
    """
    构建多智能体专家团队 (兼容 OpenAI 与 Local Ollama)
    """
    # ✨ 核心兼容逻辑：如果检测到没填 key，自动给一个假 key 以通过 langchain 校验
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"
    
    # ✨ 针对本地小模型，降低 temperature 能显著减少工具调用 (Tool Calling) 时的幻觉
    llm = ChatOpenAI(
        api_key=actual_api_key, 
        base_url=base_url, 
        model=model_name, 
        temperature=0.1,
        streaming=True,
        max_retries=2
    )
    """
    构建多智能体专家团队 (Hierarchical Multi-Agent System)
    """
    llm = ChatOpenAI(
        api_key=api_key, 
        base_url=base_url, 
        model=model_name, 
        temperature=0.2, 
        streaming=True
    )
    
    # 动态组装所有专家共享的环境上下文
    context_info = f"""
    [当前系统上下文]
    当前用户 ID: {user_id}
    当前项目 ID: {project_id}
    已挂载物理文件绝对路径 (务必严格使用以下路径读取数据):
    {physical_file_info if physical_file_info else '无挂载文件'}
    
    (🚨极其重要🚨：如果在调用相关分析工具时，请务必传入正确的 user_id 和 project_id)。
    """

    # ==========================================
    # 2. 实例化五大核心职员 Agent
    # ==========================================
    
    # 👨‍🔬 专家一：科学顾问
    advisor_prompt = f"""你是 Autonome 虚拟专家团队的【科学顾问 (Science Advisor)】。
    职责：理解用户分析背后的生物学问题，对分析需求进行完善细化并赋予意义，提出启发性的实验/分析思路。
    {context_info}
    【强制规范】：在你回答的开头，务必先输出一行 `**🧑‍🔬 科学顾问：**`。你只负责给出理论指导和方案设计，绝不写代码！
    """
    advisor_agent = create_react_agent(llm, tools=[], state_modifier=advisor_prompt)

    # 🧹 专家二：数据清洗专员
    cleaner_prompt = f"""你是 Autonome 虚拟专家团队的【数据清洗专员 (Data Cleaner)】。
    职责：专门负责编写 Python 代码处理脏数据，补全缺失值、格式转换等预处理工作。
    {context_info}
    【强制规范】：在你回答的开头，务必先输出一行 `**🧹 数据清洗专员：**`。请调用沙箱执行你的数据处理代码。
    """
    cleaner_agent = create_react_agent(llm, tools=[execute_python_code], state_modifier=cleaner_prompt)

    # 📊 专家三：生信分析师
    analyst_prompt = f"""你是 Autonome 虚拟专家团队的【生信分析师 (Bioinformatics Analyst)】。
    职责：专门负责调用沙箱执行高强度的生信核心分析，调参以及绘制高级可视化图表（UMAP、热图等）。
    {context_info}
    【强制规范】：在你回答的开头，务必先输出一行 `**📊 生信分析师：**`。
    1. 简单图表可生成 Echarts JSON（包裹在 ```echarts 中）。
    2. 对于单细胞等海量数据，请使用 scanpy 画 PNG，保存到 `/app/uploads/`，并返回 Markdown 链接格式 `![分析图表](http://localhost:8000/uploads/图片名.png)`。
    3. 如果涉及长耗时或GEO数据分析，务必调用对应的 submit_async_geo_analysis_task 工具。
    """
    analyst_tools = [execute_python_code, rnaseq_qc, search_and_vectorize_geo_data, submit_async_geo_analysis_task]
    analyst_agent = create_react_agent(llm, tools=analyst_tools, state_modifier=analyst_prompt)

    # 🧬 专家四：生物学解释专家
    interpreter_prompt = f"""你是 Autonome 虚拟专家团队的【生物学解释专家 (Biology Interpreter)】。
    职责：拿着其他同事产出的图表，数据结果，结合生物学背景，写出具有高度科学价值的深度分析结论（如解释 Marker 基因的功能、肿瘤耐药机制等）。
    {context_info}
    【强制规范】：在你回答的开头，务必先输出一行 `**🧬 生物学解释专家：**`。你主要负责结合文献和结果进行 Report 撰写解读。
    """
    interpreter_agent = create_react_agent(llm, tools=[], state_modifier=interpreter_prompt)

    # 📝 专家五：出版撰稿人
    reporter_prompt = f"""你是 Autonome 虚拟专家团队的【出版撰稿人 (Medical Writer)】。
    职责：当团队的其他专家完成了分析、画出了图表并解释了生物学意义后，由你负责将所有信息"组装"成一篇极其严谨的学术论文结构报告。
    {context_info}
    【强制规范】：
    1. 你的回答开头必须是 `**📝 出版撰稿人：**`。
    2. 你必须汇总之前的聊天记录，提取【背景】、【方法学】、【结果图表（带入正确的图片链接）】、【结论】。
    3. 调用 `generate_publishable_report` 工具，将整理好的巨长 Markdown 文本传给它。
    4. 拿到报告 URL 后发送给用户。
    """
    reporter_agent = create_react_agent(llm, tools=[generate_publishable_report], state_modifier=reporter_prompt)


    # ==========================================
    # 3. 构建路由主管 (Supervisor)
    # ==========================================
    members = ["Advisor", "Cleaner", "Analyst", "Interpreter", "Reporter"]
    options = ["FINISH"] + members

    class Route(BaseModel):
        next: Literal[*options]

    supervisor_prompt = f"""你是一名生信分析项目主管 (Supervisor)，管理着专家团队：{members}。
    根据用户的请求以及团队的聊天历史，决定下一个交接的专家：
    - 探讨科学问题、寻求思路、提出模糊的需求 -> 交给 **Advisor**
    - 明确需要清洗脏数据，处理格式，补缺失值 -> 交给 **Cleaner**
    - 需要画图、跑分析流程，下数据、查GEO -> 交给 **Analyst**
    - 分析师画完了图，或者需要对数据结果赋予生物学意义解读 -> 交给 **Interpreter**
    - ✨ 当所有的分析和解释都已经完成，或者用户明确要求"出个报告/写个总结" -> 交给 **Reporter** 让他去排版生成 HTML 报告。
    - 如果用户的任务已经由团队彻底解决完毕 -> 回复 **FINISH**
    """

    async def supervisor_node(state: AgentState):
        messages = [{"role": "system", "content": supervisor_prompt}] + state["messages"]
        # LLM 根据当前进度动态决定路由
        response = await llm.with_structured_output(Route).ainvoke(messages)
        return {"next": response.next}

    # ==========================================
    # 4. 包装专家节点以便状态流转
    # ==========================================
    async def advisor_node(state: AgentState):
        res = await advisor_agent.ainvoke(state)
        return {"messages": [res["messages"][-1]]}

    async def cleaner_node(state: AgentState):
        res = await cleaner_agent.ainvoke(state)
        return {"messages": [res["messages"][-1]]}

    async def analyst_node(state: AgentState):
        res = await analyst_agent.ainvoke(state)
        return {"messages": [res["messages"][-1]]}

    async def interpreter_node(state: AgentState):
        res = await interpreter_agent.ainvoke(state)
        return {"messages": [res["messages"][-1]]}

    async def reporter_node(state: AgentState):
        res = await reporter_agent.ainvoke(state)
        return {"messages": [res["messages"][-1]]}

    # ==========================================
    # 5. 将所有人编织为有向无环图 (Hierarchical Graph)
    # ==========================================
    workflow = StateGraph(AgentState)
    
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("Advisor", advisor_node)
    workflow.add_node("Cleaner", cleaner_node)
    workflow.add_node("Analyst", analyst_node)
    workflow.add_node("Interpreter", interpreter_node)
    workflow.add_node("Reporter", reporter_node)

    # 任务永远先到达主管处
    workflow.add_edge(START, "Supervisor")
    
    # 专家完成工作后，把结果汇报回主管
    workflow.add_edge("Advisor", "Supervisor")
    workflow.add_edge("Cleaner", "Supervisor")
    workflow.add_edge("Analyst", "Supervisor")
    workflow.add_edge("Interpreter", "Supervisor")
    workflow.add_edge("Reporter", "Supervisor")
    
    # 主管的脑部条件分支
    workflow.add_conditional_edges("Supervisor", lambda x: x["next"], {
        "Advisor": "Advisor",
        "Cleaner": "Cleaner",
        "Analyst": "Analyst",
        "Interpreter": "Interpreter",
        "Reporter": "Reporter",
        "FINISH": END
    })

    return workflow.compile()
