"""
LiteratureAgent - 文献分析 Agent

独立 LangGraph 节点，专门处理文献相关请求和代码生成

系统提示词硬编码代码规范：
- argparse 参数系统
- TSV 数据输出
- 发表级绘图（PDF + PNG）
- 详细中文注释
"""

from app.core.logger import log


# ==========================================
# 系统提示词（硬编码代码规范）
# ==========================================

LITERATURE_SYSTEM_PROMPT = """你是 Autonome 的文献分析 Agent。基于学习中心知识库，帮助用户理解文献方法或生成可执行分析代码。

代码生成绝对规则：
1. 所有代码必须包含详细注释，说明"为什么"而非仅"做什么"
2. 必须使用 argparse (Python) 或 commandArgs (R) 构建参数系统，设置合理默认值
3. 表格数据必须输出 TSV 格式，禁用 CSV
4. 绘图必须同时输出 PDF 和 PNG，使用发表级配色
5. 每个图形必须附带对应的底层数据文件（TSV）

保持科学客观，直接输出结构化分析逻辑和高质量代码。"""


# ==========================================
# Agent 构建
# ==========================================

def get_literature_agent():
    """
    构建并返回 LiteratureAgent

    使用 LangGraph 的 create_react_agent 模式，
    配备 search_learning_center 和 create_skill_draft 工具

    Returns:
        LangGraph Agent 实例
    """
    try:
        from langgraph.prebuilt import create_react_agent
        from langchain_openai import ChatOpenAI
        from app.core.config import settings
        from app.tools.literature_tools import get_learning_tools

        # 获取学习中心工具
        learning_tools = get_learning_tools()

        # 可选：添加 create_skill_draft 工具
        try:
            from app.tools.literature_tools import search_learning_center
            from langchain_core.tools import tool

            @tool
            def create_skill_draft_tool(
                code: str,
                language: str,
                tool_stack: str,
                skill_name: str,
            ) -> str:
                """
                将生成的代码创建为技能草稿（Skill Draft）。
                代码必须符合 Autonome 规范：包含参数系统、TSV 输出、发表级绘图。

                Args:
                    code: 生成的代码内容
                    language: 编程语言（python 或 r）
                    tool_stack: 依赖的工具链（JSON 格式）
                    skill_name: 技能名称
                """
                try:
                    import json
                    from sqlmodel import Session
                    from app.core.database import engine
                    from app.models.learning import Literature
                    from app.services.skill_bundle_writer import create_skill_draft

                    tool_stack_dict = json.loads(tool_stack) if isinstance(tool_stack, str) else {}

                    with Session(engine) as session:
                        draft_id = create_skill_draft(
                            session=session,
                            name=skill_name,
                            code=code,
                            language=language,
                            dependencies=tool_stack_dict,
                            source="learning_center",
                        )
                    return f"技能草稿已创建: draft_id={draft_id}"
                except Exception as e:
                    return f"创建技能草稿失败: {e}"

            all_tools = learning_tools + [create_skill_draft_tool]
        except ImportError:
            all_tools = learning_tools

        # 构建 LLM
        llm = ChatOpenAI(
            model=settings.OPENAI_MODEL_NAME or "gpt-4o",
            temperature=0.1,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        # 创建 ReAct Agent
        agent = create_react_agent(
            model=llm,
            tools=all_tools,
            state_modifier=LITERATURE_SYSTEM_PROMPT,
        )

        log.info("📚 [LiteratureAgent] Agent 构建完成")
        return agent

    except ImportError as e:
        log.warning(f"📚 [LiteratureAgent] LangGraph/LangChain 未安装，Agent 不可用: {e}")
        return None
    except Exception as e:
        log.error(f"📚 [LiteratureAgent] Agent 构建失败: {e}")
        return None


# ==========================================
# 意图路由集成
# ==========================================

def should_route_to_literature_agent(user_message: str, context: dict = None) -> bool:
    """
    判断是否应将用户请求路由到 LiteratureAgent

    路由条件：
    1. 用户消息包含文献相关关键词
    2. 上下文中包含学习中心引用

    Args:
        user_message: 用户消息文本
        context: 对话上下文（可选）

    Returns:
        是否应路由到 LiteratureAgent
    """
    from app.tools.literature_tools import should_use_learning_tools

    # 关键词匹配
    if should_use_learning_tools(user_message):
        return True

    # 上下文检查
    if context and context.get("active_context") == "learning_center":
        return True

    return False
