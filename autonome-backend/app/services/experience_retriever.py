"""
经验检索引擎 — 基于语义检索相关历史经验。

程序说明：
在生成新即席分析代码前，根据用户的分析需求进行语义检索，
找到相似的历史经验（DEBUG_PATTERN 和 CODE_SNIPPET），
以"经验教训"文本注入 System Prompt，帮助 LLM 避免重复错误。

检索策略：
1. 对用户 instruction 生成 text-embedding-3-large 嵌入
2. 从数据库加载所有有嵌入的经验（按语言/分类过滤）
3. Python 侧计算余弦相似度排序
4. 混合加权：语义相似度(0.5) + 有用度(0.3) + 重用次数(0.2)
5. 返回格式化文本可直接注入 prompt

设计原则：
- 不依赖 pgvector 扩展（Docker PostgreSQL 容器未安装）
- 百/千级经验规模在 Python 侧计算足以满足性能要求
- 检索失败静默降级（不阻塞主流程）
- 经验注入文本紧凑（< 800 tokens）
"""
import json
import os
import math
import numpy as np
from typing import Optional, List

from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.experience import ExperienceAsset


# 最大注入经验数
MAX_EXPERIENCES = 3

# 检索权重
WEIGHT_SIMILARITY = 0.5
WEIGHT_USEFULNESS = 0.3
WEIGHT_REUSE = 0.2

# DEBUG_PATTERN 类型在排序时的额外 boost（教训比成功案例更关键）
DEBUG_PATTERN_BOOST = 1.2


def _resolve_embedding_api_key() -> Optional[str]:
    """
    解析 Embedding 模型 API Key，复用项目统一的配置回退机制。

    优先级：User embedding_* → SystemConfig embedding_* → thinking config → env OPENAI_API_KEY
    说明：经验检索是系统级后台服务，无用户上下文，因此传入 user_id=None，
    仅走系统级回退链。如需用户级 Key，需在调用方传入 user_id 后扩展。
    """
    try:
        from app.utils.llm_config import get_embedding_llm_config_standalone
        config = get_embedding_llm_config_standalone(user_id=None)
        if config and config.api_key:
            return config.api_key
    except Exception:
        pass

    return os.getenv("OPENAI_API_KEY")


def _resolve_embedding_config():
    """
    解析完整的 Embedding 模型配置（api_key + base_url + model_name）。

    Returns:
        (api_key, base_url, model_name) 三元组，api_key 为 None 时表示未配置
    """
    try:
        from app.utils.llm_config import get_embedding_llm_config_standalone
        config = get_embedding_llm_config_standalone(user_id=None)
        if config and config.api_key:
            return config.api_key, config.base_url, config.model_name
    except Exception:
        pass

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return api_key, base_url, "text-embedding-3-large"


def _generate_query_embedding(query: str) -> Optional[List[float]]:
    """为检索查询生成嵌入向量（模型由配置决定，默认 text-embedding-3-large）"""
    try:
        import openai

        api_key, base_url, model_name = _resolve_embedding_config()

        if not api_key:
            log.warning("[ExperienceRetriever] Embedding API Key 未配置（数据库和 OPENAI_API_KEY 环境变量均未设置），跳过语义检索")
            return None

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.embeddings.create(
            model=model_name,
            input=f"生物信息学分析需求: {query}"[:8000],
        )
        return response.data[0].embedding
    except Exception as e:
        log.error(
            f"[ExperienceRetriever] 查询嵌入生成失败: {e} "
            f"(base_url={base_url}, model={model_name})"
        )
        return None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def retrieve_relevant_experiences(
    instruction: str,
    language: Optional[str] = None,
    limit: int = MAX_EXPERIENCES,
) -> List[ExperienceAsset]:
    """
    语义检索相关历史经验。

    步骤：
    1. 生成查询嵌入向量
    2. 从数据库加载有嵌入的经验（按语言过滤）
    3. 计算余弦相似度 + 加权评分
    4. 返回 top-K

    Args:
        instruction: 用户当前分析需求
        language: 代码语言过滤 (python / r)，None 为不过滤
        limit: 最大返回数

    Returns:
        按综合分数降序排列的 ExperienceAsset 列表
    """
    try:
        query_embedding = _generate_query_embedding(instruction)
        if not query_embedding:
            return await _fallback_recent_experiences(language, limit)

        # 加载所有有嵌入文本的经验
        with Session(engine) as db_session:
            stmt = select(ExperienceAsset).where(
                ExperienceAsset.embedding_text.isnot(None)  # type: ignore
            )
            if language:
                stmt = stmt.where(ExperienceAsset.language == language)
            # 限制候选数量以控制计算开销
            candidates = db_session.exec(stmt.limit(100)).all()

        if not candidates:
            return await _fallback_recent_experiences(language, limit)

        # 计算加权分数
        scored = []
        for exp in candidates:
            try:
                emb = json.loads(exp.embedding_text)
                cosine_sim = _cosine_similarity(query_embedding, emb)
            except (json.JSONDecodeError, TypeError):
                continue

            # 综合分数
            type_boost = DEBUG_PATTERN_BOOST if str(exp.experience_type) == "debug_pattern" else 1.0
            score = (
                cosine_sim * WEIGHT_SIMILARITY
                + (exp.usefulness_score or 0.0) * WEIGHT_USEFULNESS
                + math.log((exp.reuse_count or 0) + 1) * 0.1 * WEIGHT_REUSE
            ) * type_boost

            scored.append((score, exp))

        # 按分数降序排列
        scored.sort(key=lambda x: x[0], reverse=True)
        experiences = [exp for _, exp in scored[:limit]]

        if experiences:
            log.info(
                f"[ExperienceRetriever] 检索到 {len(experiences)} 条相关经验: "
                f"{[e.title[:30] for e in experiences]}"
            )

        return experiences

    except Exception as e:
        log.error(f"[ExperienceRetriever] 语义检索失败: {e}")
        return await _fallback_recent_experiences(language, limit)


async def _fallback_recent_experiences(
    language: Optional[str] = None,
    limit: int = MAX_EXPERIENCES,
) -> List[ExperienceAsset]:
    """回退检索：按最近创建时间和有用度排序"""
    try:
        with Session(engine) as db_session:
            stmt = select(ExperienceAsset).where(
                ExperienceAsset.embedding_text.isnot(None)  # type: ignore
            )
            if language:
                stmt = stmt.where(ExperienceAsset.language == language)
            stmt = stmt.order_by(
                ExperienceAsset.usefulness_score.desc(),
                ExperienceAsset.reuse_count.desc(),
            ).limit(limit)
            return list(db_session.exec(stmt).all())
    except Exception as e:
        log.error(f"[ExperienceRetriever] 回退检索失败: {e}")
        return []


def format_experiences_for_prompt(experiences: List[ExperienceAsset]) -> str:
    """
    将检索到的经验格式化为可供 System Prompt 注入的文本。

    紧凑格式，控制 token 消耗（目标：< 800 tokens）。
    """
    if not experiences:
        return ""

    debug_patterns = [
        e for e in experiences
        if str(e.experience_type) == "debug_pattern"
    ]
    code_snippets = [
        e for e in experiences
        if str(e.experience_type) != "debug_pattern"
    ]

    sections = ["\n## 历史经验教训（从相似分析中自动总结，请特别注意避免以下常见错误）\n"]

    # Debug patterns first (more important)
    if debug_patterns:
        sections.append("### ⚠️ 常见错误及修复方案（务必注意）\n")
        for i, exp in enumerate(debug_patterns, 1):
            sections.append(f"**经验 {i}：{exp.title}**")
            if exp.summary:
                sections.append(f"问题与修复：{exp.summary}")
            if exp.key_insights:
                for insight in exp.key_insights[:3]:
                    sections.append(f"- {insight}")
            sections.append("")

    # Successful patterns
    if code_snippets:
        sections.append("### ✅ 成功案例参考（可直接借鉴的代码模式）\n")
        for i, exp in enumerate(code_snippets, 1):
            sections.append(f"**案例 {i}：{exp.title}**")
            if exp.summary:
                sections.append(f"最佳实践：{exp.summary}")
            if exp.key_insights:
                for insight in exp.key_insights[:2]:
                    sections.append(f"- {insight}")
            sections.append("")

    result = "\n".join(sections).strip()

    # 粗略 token 估算：限制在 ~800 tokens
    if len(result) > 3000:
        result = result[:3000] + "\n... (经验列表已截断)"

    return result


def get_experience_ids(experiences: List[ExperienceAsset]) -> List[str]:
    """提取经验 ID 列表，用于后续反馈闭环"""
    return [e.experience_id for e in experiences if e.experience_id]
