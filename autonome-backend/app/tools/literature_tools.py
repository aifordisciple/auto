"""
学习中心 RAG 工具

提供 LangGraph 工具，使主 Agent 能够检索学习中心知识库

工具：
- search_learning_center: 语义检索学习中心知识块
"""

import json
from typing import List, Dict, Any

from app.core.logger import log


def search_learning_center(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    检索学习中心知识库

    当用户询问生信分析方法或引用文献时调用此工具。
    返回从文献知识库中提取的方法论、使用工具链及关键参数。

    Args:
        query: 搜索查询（自然语言）
        top_k: 返回结果数量

    Returns:
        匹配的知识块列表，每项包含内容、来源文献信息
    """
    log.info(f"📚 [RAG] 检索学习中心: query='{query[:50]}...', top_k={top_k}")

    try:
        from sqlmodel import Session
        from app.core.database import engine
        from app.services.learning_service import search_knowledge

        # 使用默认用户（系统级检索）
        # 注意：实际使用时需要传入 user_id，此处使用全局检索
        with Session(engine) as session:
            # 获取所有 ready 状态的文献的知识块
            results = search_knowledge(
                session,
                user_id=0,  # 0 表示系统级检索（所有用户）
                query=query,
                top_k=top_k,
                use_semantic=True,
            )

        if not results:
            log.info("📚 [RAG] 未找到匹配的知识块")
            return []

        log.info(f"📚 [RAG] 检索到 {len(results)} 个匹配知识块")
        return results

    except Exception as e:
        log.error(f"📚 [RAG] 检索失败: {e}")
        return []


# ==========================================
# LangGraph 工具注册
# ==========================================

def get_learning_tools() -> list:
    """
    获取学习中心 LangGraph 工具列表

    返回可用于 LangGraph Agent 的工具列表
    """
    try:
        from langchain_core.tools import tool

        @tool
        def search_learning_center_tool(query: str, top_k: int = 5) -> str:
            """
            当用户询问生信分析方法或引用文献时调用此工具。
            返回从学习中心知识库中检索到的相关文献知识块。

            适用场景：
            - 用户提到某篇文献或论文
            - 用户询问某种生信分析方法
            - 用户想复现文献中的分析
            - 用户提到"学习中心"中的内容

            Args:
                query: 搜索查询（自然语言描述）
                top_k: 返回结果数量（默认5）
            """
            results = search_learning_center(query, top_k)
            if not results:
                return "学习中心中未找到匹配的知识。建议用户先上传相关文献。"

            # 格式化结果为文本
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(
                    f"[{i}] 来源: {r.get('source_title', '未知')} "
                    f"(DOI: {r.get('source_doi', 'N/A')}, "
                    f"第{r.get('page_number', '?')}页)\n"
                    f"类型: {r.get('chunk_type', 'text')} | "
                    f"章节: {r.get('section_title', 'N/A')}\n"
                    f"内容: {r.get('content', '')[:500]}"
                )
            return "\n\n---\n\n".join(formatted)

        return [search_learning_center_tool]

    except ImportError:
        log.warning("📚 [RAG] langchain_core 未安装，跳过工具注册")
        return []


# ==========================================
# 意图路由关键词
# ==========================================

# 当用户消息包含这些关键词时，主 Agent 应考虑使用学习中心工具
LEARNING_KEYWORDS = [
    "文献", "论文", "paper", "article", "publication",
    "复现", "reproduce", "replicate",
    "图表", "figure", "fig",
    "学习中心", "learning center",
    "算法", "algorithm",
    "拟时序", "trajectory", "pseudotime",
    "单细胞", "single cell", "scRNA",
    "差异表达", "differential expression",
    "聚类", "clustering",
]


def should_use_learning_tools(user_message: str) -> bool:
    """
    判断用户消息是否应触发学习中心工具

    Args:
        user_message: 用户消息文本

    Returns:
        是否应使用学习中心工具
    """
    message_lower = user_message.lower()
    return any(kw in message_lower for kw in LEARNING_KEYWORDS)
