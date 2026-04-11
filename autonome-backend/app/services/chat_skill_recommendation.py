"""
聊天技能推荐服务

基于用户查询获取技能推荐（关键词匹配 + LLM 增强）
实现两层推荐架构：
1. Step 1: 关键词匹配（同步，<50ms）- 快速返回基础推荐
2. Step 2: LLM 增强（异步，1-3s）- 深度语义理解
"""

import re
from typing import Optional
from sqlmodel import Session, select
from sqlalchemy import func, or_, and_

from app.models.domain import (
    SkillAsset, SkillStatus, SkillExecutionHistory, SkillReview
)
from app.core.logger import log


# ==========================================
# 预定义的关键词列表（生物信息常用词汇）
# ==========================================

BIO_KEYWORDS = [
    # 可视化相关
    "热图", "heatmap", "火山图", "volcano", "散点图", "scatter", "箱线图", "boxplot",
    "条形图", "bar", "折线图", "line", "小提琴图", "violin", "umap", "tsne", "pca",
    "聚类", "cluster", "相关性", "correlation",
    # 分析类型
    "单细胞", "scrna", "seurat", "scanpy", "转录", "rna", "差异", "deg", "deseq",
    "质控", "qc", "fastqc", "peak", "chip", "atac", "甲基化", "甲基", "变异", "variant",
    # FASTQ 处理相关
    "fastq", "reads", "过滤", "低质量", "质量分数", "trim", "trimming", "phred",
    "序列", "测序", "质量", "filter",
    # 通用
    "流程", "pipeline", "nextflow", "分析", "处理", "可视化", "plot", "figure"
]

# 领域关键词映射
DOMAIN_KEYWORDS = {
    "单细胞": ["单细胞", "seurat", "scanpy", "cell", "scrna"],
    "rna": ["rna", "转录", "deseq", "表达", "fpkm", "tpm"],
    "qc": ["qc", "质量", "fastqc", "质控"],
    "fastq": ["fastq", "reads", "过滤", "低质量", "质量分数", "trim", "phred"],
    "chip": ["chip", "peak", "tfbs"],
    "atac": ["atac", "染色质"],
    "可视化": ["热图", "heatmap", "火山图", "volcano", "散点图", "scatter",
              "箱线图", "boxplot", "pca", "umap", "tsne", "可视化", "plot", "figure"],
}


async def get_skill_recommendations_for_chat(
    user_query: str,
    session: Session,
    user_id: int,
    limit: int = 3,
    llm_config: Optional[dict] = None
) -> tuple[list, Optional[dict]]:
    """
    基于用户查询获取技能推荐（关键词匹配 + LLM 增强）

    Args:
        user_query: 用户查询内容
        session: 数据库会话
        user_id: 当前用户ID，用于查询用户自己的技能
        limit: 推荐数量
        llm_config: LLM 配置，包含 api_key, base_url, model

    Returns:
        (关键词推荐列表, LLM增强结果或None)

    Note:
        技能可见性规则：
        - PUBLISHED: 所有用户可见
        - PRIVATE/PENDING_REVIEW: 仅创建者本人可见
        - DRAFT/REJECTED/DEPRECATED: 对所有人不可见
    """
    from app.core.skill_parser import get_combined_skills

    # 获取可用技能：数据库技能 + 文件系统技能
    # 1. 数据库技能
    db_skills = session.exec(
        select(SkillAsset).where(
            or_(
                SkillAsset.status == SkillStatus.PUBLISHED,
                and_(
                    SkillAsset.owner_id == user_id,
                    SkillAsset.status.in_([
                        SkillStatus.PRIVATE,
                        SkillStatus.PENDING_REVIEW
                    ])
                )
            )
        )
    ).all()

    # 2. 文件系统技能（官方预置技能）
    fs_skills_data = get_combined_skills(user_id)

    # 合并技能列表
    all_skills = list(db_skills)

    # 将文件系统技能转换为类似数据库技能的格式
    for fs_skill in fs_skills_data:
        metadata = fs_skill.get("metadata", {})
        skill_id = metadata.get("skill_id", "")

        # 检查是否已存在于数据库技能中
        if not any(s.skill_id == skill_id for s in db_skills):
            # 创建一个临时对象来存储技能信息
            class TempSkill:
                pass

            temp = TempSkill()
            temp.skill_id = skill_id
            temp.name = metadata.get("name", "")
            temp.description = metadata.get("description", "")
            temp.owner_id = 0  # 官方技能
            temp.status = SkillStatus.PUBLISHED  # 视为已发布
            all_skills.append(temp)

    skills = all_skills

    if not skills:
        return [], None

    query_lower = user_query.lower()
    scored_skills = []

    # ==========================================
    # 关键词匹配（改进版：支持中英文混合）
    # ==========================================
    # 从查询中提取匹配的关键词
    matched_keywords = []
    for kw in BIO_KEYWORDS:
        if kw.lower() in query_lower:
            matched_keywords.append(kw)

    # 同时提取英文单词
    english_words = re.findall(r'[a-zA-Z]+', query_lower)
    matched_keywords.extend([w for w in english_words if len(w) >= 2])

    for skill in skills:
        score = 0
        reasons = []
        combined = f"{skill.name or ''} {skill.description or ''}".lower()
        name_lower = (skill.name or "").lower()

        # 使用匹配的关键词进行评分
        for kw in matched_keywords:
            kw_lower = kw.lower()
            if kw_lower in name_lower:
                score += 0.4
                reasons.append(f"名称包含 '{kw}'")
            elif kw_lower in combined:
                score += 0.2
                reasons.append(f"相关技能")

        # 领域关键词匹配
        for domain, dkw in DOMAIN_KEYWORDS.items():
            if any(k in query_lower for k in dkw):
                if any(k in combined for k in dkw):
                    score += 0.3
                    reasons.append(f"适用于 {domain} 分析")
                    break

        if score > 0:
            # 获取评分（文件系统技能使用默认值）
            if hasattr(skill, 'owner_id') and skill.owner_id == 0 and not isinstance(skill, SkillAsset):
                avg_rating = 0.0
                usage_count = 0
            else:
                # 数据库技能，查询评分
                rating_result = session.exec(
                    select(func.avg(SkillReview.rating)).where(
                        SkillReview.skill_id == skill.skill_id
                    )
                ).first()
                avg_rating = float(rating_result[0] or 0) if rating_result else 0

                # 获取使用量
                usage_count = session.exec(
                    select(func.count(SkillExecutionHistory.id)).where(
                        SkillExecutionHistory.skill_id == skill.skill_id
                    )
                ).one() or 0

            scored_skills.append({
                "skill": skill,
                "score": min(score, 1.0),
                "reasons": reasons[:2],
                "avg_rating": avg_rating,
                "usage_count": usage_count
            })

    # 按分数排序
    scored_skills.sort(key=lambda x: (x["score"], x["avg_rating"]), reverse=True)
    base_recommendations = scored_skills[:limit]

    # ==========================================
    # Step 2: LLM 增强（如果需要且有配置）
    # ==========================================
    llm_result = None
    if llm_config and base_recommendations:
        from app.services.intent_recognition import detect_intent_with_llm, should_enhance_with_llm

        # 判断是否需要 LLM 增强
        if should_enhance_with_llm(base_recommendations, user_query):
            try:
                # 构建技能数据供 LLM 分析
                skills_data = [
                    {
                        "skill_id": rec["skill"].skill_id,
                        "name": rec["skill"].name,
                        "description": rec["skill"].description
                    }
                    for rec in base_recommendations
                ]

                # 调用 LLM 进行意图识别
                llm_result = await detect_intent_with_llm(
                    user_query=user_query,
                    available_skills=skills_data,
                    api_key=llm_config["api_key"],
                    base_url=llm_config.get("base_url", "https://api.openai.com/v1"),
                    model=llm_config.get("model", "gpt-4o-mini"),
                    timeout=3.0
                )

                if llm_result:
                    log.info(f"🎯 [LLM推荐增强] 意图={llm_result['intent_type']}, 置信度={llm_result['confidence']}")
            except Exception as e:
                log.warning(f"[LLM推荐增强] 调用失败: {e}")

    return base_recommendations, llm_result


def format_skill_recommendations_for_agent(recommendations: list) -> str:
    """
    格式化技能推荐供 Agent 使用

    Args:
        recommendations: 推荐技能列表

    Returns:
        格式化的推荐文本
    """
    if not recommendations:
        return ""

    lines = ["```recommended_skills"]

    for i, rec in enumerate(recommendations, 1):
        skill = rec["skill"]
        lines.append(f"{i}. skill_id: {skill.skill_id}")
        lines.append(f"   name: {skill.name}")
        lines.append(f"   description: {skill.description or '暂无描述'}")
        lines.append(f"   match_score: {rec['score']:.2f}")
        lines.append(f"   match_reason: {'; '.join(rec['reasons']) if rec['reasons'] else '相关技能'}")
        if rec['avg_rating'] > 0:
            lines.append(f"   rating: {rec['avg_rating']:.1f}/5.0")
        lines.append("")

    lines.append("```")
    lines.append("")
    lines.append("【推荐技能使用指南】")
    lines.append("在回复中，请自然地提及这些推荐的技能：")
    lines.append("1. 简要介绍技能功能")
    lines.append("2. 说明为什么适合用户需求")
    lines.append("3. 如果用户确认使用，输出对应的 json_strategy")

    return "\n".join(lines)


def render_file_tree(tree: dict, prefix: str = "") -> str:
    """
    渲染文件树为文本格式

    Args:
        tree: 文件树字典
        prefix: 当前行的前缀（用于缩进）

    Returns:
        文本格式的文件树
    """
    lines = []
    entries = sorted(tree.items(), key=lambda x: (x[1].get("type") == "directory", x[0]))

    for i, (name, node) in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        node_type = node.get("type", "file")

        if node_type == "directory":
            lines.append(f"{prefix}{connector}📁 {name}/")
            # 递归渲染子目录
            children = node.get("children", {})
            if children:
                new_prefix = prefix + ("    " if is_last else "│   ")
                lines.append(render_file_tree(children, new_prefix))
        else:
            # 根据文件扩展名选择图标
            ext = name.split(".")[-1].lower() if "." in name else ""
            icons = {
                "py": "🐍", "js": "📜", "ts": "📘", "tsx": "⚛️", "jsx": "⚛️",
                "md": "📝", "txt": "📄", "json": "📋", "yaml": "⚙️", "yml": "⚙️",
                "html": "🌐", "css": "🎨", "scss": "🎨",
                "r": "📊", "rmd": "📊",
                "csv": "📈", "tsv": "📈", "xlsx": "📊",
                "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "svg": "🎨",
                "pdf": "📕", "doc": "📘", "docx": "📘",
            }
            icon = icons.get(ext, "📄")
            lines.append(f"{prefix}{connector}{icon} {name}")

    return "\n".join(lines)