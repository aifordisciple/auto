"""
经验提取器 — 从即席分析执行结果中自动提取经验资产。

程序说明：
当 auto-fix 修复代码错误或 Docker 沙箱执行完成时，自动从中提取经验教训，
存储为 ExperienceAsset（含 pgvector 嵌入），供后续相似分析检索复用。

三大提取场景：
1. auto-fix 修复 → DEBUG_PATTERN：记录原始错误 + 修复方案
2. 执行成功 → CODE_SNIPPET：记录工作代码模式
3. 执行失败 → DEBUG_PATTERN：记录错误诊断 + 修复建议

设计原则：
- 异步非阻塞：提取过程抛出异常不影响主流程
- LLM 总结：用快速模型总结经验要点，人可读 + 机器可检索
- 向量化检索：用 text-embedding-3-large 生成 embedding 用于语义检索
"""
import json
import os
from typing import Optional, List

from sqlmodel import Session, select, text
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.database import engine
from app.core.logger import log
from app.models.experience import ExperienceAsset, ExperienceAssetCreate
from app.models.enums import ExperienceType


# 即席分析经验分类体系
EXPERIENCE_CATEGORIES = [
    "file_io",                  # 文件读写/路径问题
    "parameter_parsing",        # argparse/optparse 参数处理
    "package_import",           # 库导入/加载
    "visualization",            # CNS 作图规范
    "differential_expression",  # 差异表达分析
    "clustering",               # 聚类分析
    "normalization",            # 标准化/归一化
    "qc",                       # 质量控制
    "pathway_enrichment",       # 通路富集
    "general",                  # 通用
]


def _generate_embedding(text: str) -> Optional[List[float]]:
    """
    使用 text-embedding-3-large 生成嵌入向量。

    复用与 learning_ingestion_service 相同的模式。

    Args:
        text: 待嵌入的文本（自动截断到 8000 字符）

    Returns:
        1536 维浮点数列表，失败返回 None
    """
    try:
        import openai

        # 复用统一的配置回退机制解析 Embedding 模型配置
        from app.services.experience_retriever import _resolve_embedding_config
        api_key, base_url, model_name = _resolve_embedding_config()

        if not api_key:
            log.warning("[ExperienceExtractor] Embedding API Key 未配置，跳过嵌入生成")
            return None

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.embeddings.create(
            model=model_name,
            input=text[:8000],
        )
        return response.data[0].embedding
    except Exception as e:
        log.error(f"[ExperienceExtractor] 嵌入生成失败: {e}")
        return None


async def extract_experience_from_autofix(
    original_code: str,
    fixed_code: str,
    issues: list,
    instruction: str,
    language: str,
    user_id: int,
    project_id: Optional[str] = None,
    message_id: Optional[str] = None,
    session = None,
) -> Optional[ExperienceAsset]:
    """
    从 auto-fix 修复结果中提取 DEBUG_PATTERN 经验。

    当 validate_generated_code 发现语法错误或关键模式问题，
    且 auto_fix_generated_code 成功修复后调用。

    提取内容：
    - 原始错误类型和位置
    - 修复方案
    - 避免同类错误的通用建议

    Args:
        original_code: 修复前的原始代码（含错误）
        fixed_code: 修复后的代码
        issues: ValidationIssue 列表
        instruction: 用户原始分析需求
        language: 代码语言 (python / r)
        user_id: 用户 ID
        project_id: 项目 ID
        message_id: 聊天消息 ID
        session: LLM config 需要的数据库会话

    Returns:
        ExperienceAsset 或 None（提取失败时）
    """
    try:
        # 构建问题摘要
        issue_summaries = []
        for issue in issues:
            location = f"第{issue.line}行" if getattr(issue, 'line', None) else "未知位置"
            issue_summaries.append(
                f"[{issue.severity}] {location}: {issue.message}"
            )
        issues_text = "\n".join(issue_summaries)

        # 推断分类
        category = _infer_category(instruction + "\n" + issues_text, language)

        # 用 LLM 总结经验要点
        summary_result = await _summarize_experience(
            experience_type="debug_pattern",
            instruction=instruction,
            issues_text=issues_text,
            original_code=original_code[:3000],
            fixed_code=fixed_code[:3000],
            session=session,
            user_id=user_id,
        )

        if not summary_result:
            return None

        # 生成嵌入向量（用 instruction + summary 组合文本）
        embed_text = f"分析需求: {instruction}\n经验摘要: {summary_result.get('summary', '')}"
        embedding = _generate_embedding(embed_text)

        # 写入数据库
        with Session(engine) as db_session:
            experience = ExperienceAsset(
                experience_type=ExperienceType.DEBUG_PATTERN,
                title=summary_result.get("title", f"修复: {issues_text[:80]}"),
                summary=summary_result.get("summary", ""),
                key_insights=summary_result.get("key_insights", []),
                original_query=instruction,
                solution_code=fixed_code[:10000],
                solution_strategy=summary_result.get("solution_strategy", ""),
                debug_iterations=1,
                category=category,
                tags=summary_result.get("tags", []),
                language=language,
                source_user_id=user_id,
                source_project_id=project_id,
                usefulness_score=0.5,
            )
            # 写入嵌入向量（JSON 文本格式）
            if embedding:
                experience.embedding_text = json.dumps(embedding)

            db_session.add(experience)
            db_session.commit()
            db_session.refresh(experience)
            log.info(
                f"[ExperienceExtractor] DEBUG_PATTERN 经验已创建: "
                f"id={experience.id}, title={experience.title}, category={category}"
            )
            return experience

    except Exception as e:
        log.error(f"[ExperienceExtractor] auto-fix 经验提取失败（非致命）: {e}")
        return None


async def extract_experience_from_execution(
    code: str,
    instruction: str,
    language: str,
    success: bool,
    output_text: Optional[str] = None,
    error_text: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    record_id: Optional[int] = None,
    session = None,
) -> Optional[ExperienceAsset]:
    """
    从即席分析执行结果中提取经验。

    执行完成（成功或失败）后调用，异步提取不阻塞主流程。

    Args:
        code: 最终执行的代码
        instruction: 用户原始分析需求
        language: 代码语言
        success: 执行是否成功
        output_text: 成功时的输出文本
        error_text: 失败时的错误文本
        user_id: 用户 ID
        project_id: 项目 ID
        record_id: AdhocAnalysisRecord.id (source_record_id)
        session: LLM config 需要的数据库会话

    Returns:
        ExperienceAsset 或 None
    """
    try:
        category = _infer_category(instruction, language)

        if success:
            return await _extract_success_experience(
                code=code,
                instruction=instruction,
                language=language,
                output_text=output_text,
                category=category,
                user_id=user_id,
                project_id=project_id,
                record_id=record_id,
                session=session,
            )
        else:
            return await _extract_failure_experience(
                code=code,
                instruction=instruction,
                language=language,
                error_text=error_text,
                category=category,
                user_id=user_id,
                project_id=project_id,
                record_id=record_id,
                session=session,
            )

    except Exception as e:
        log.error(f"[ExperienceExtractor] 执行经验提取失败（非致命）: {e}")
        return None


async def _extract_success_experience(
    code: str,
    instruction: str,
    language: str,
    output_text: Optional[str],
    category: str,
    user_id: Optional[int],
    project_id: Optional[str],
    record_id: Optional[int],
    session,
) -> Optional[ExperienceAsset]:
    """从成功执行中提取 CODE_SNIPPET 经验"""
    try:
        summary_result = await _summarize_experience(
            experience_type="code_snippet",
            instruction=instruction,
            code=code[:3000],
            output_text=output_text[:2000] if output_text else "",
            session=session,
            user_id=user_id,
        )

        if not summary_result:
            return None

        embed_text = f"分析需求: {instruction}\n经验摘要: {summary_result.get('summary', '')}"
        embedding = _generate_embedding(embed_text)

        with Session(engine) as db_session:
            experience = ExperienceAsset(
                experience_type=ExperienceType.CODE_SNIPPET,
                title=summary_result.get("title", f"成功分析: {instruction[:80]}"),
                summary=summary_result.get("summary", ""),
                key_insights=summary_result.get("key_insights", []),
                original_query=instruction,
                solution_code=code[:10000],
                solution_strategy=summary_result.get("solution_strategy", ""),
                debug_iterations=0,
                category=category,
                tags=summary_result.get("tags", []),
                language=language,
                source_user_id=user_id or 0,
                source_project_id=project_id,
                source_record_id=record_id,
                usefulness_score=0.5,
            )
            if embedding:
                experience.embedding_text = json.dumps(embedding)

            db_session.add(experience)
            db_session.commit()
            db_session.refresh(experience)
            log.info(
                f"[ExperienceExtractor] CODE_SNIPPET 经验已创建: "
                f"id={experience.id}, title={experience.title}, category={category}"
            )
            return experience

    except Exception as e:
        log.error(f"[ExperienceExtractor] 成功经验提取失败: {e}")
        return None


async def _extract_failure_experience(
    code: str,
    instruction: str,
    language: str,
    error_text: Optional[str],
    category: str,
    user_id: Optional[int],
    project_id: Optional[str],
    record_id: Optional[int],
    session,
) -> Optional[ExperienceAsset]:
    """从失败执行中提取 DEBUG_PATTERN 经验"""
    try:
        summary_result = await _summarize_experience(
            experience_type="debug_pattern",
            instruction=instruction,
            code=code[:3000],
            error_text=error_text[:2000] if error_text else "",
            session=session,
            user_id=user_id,
        )

        if not summary_result:
            return None

        embed_text = f"分析需求: {instruction}\n经验摘要: {summary_result.get('summary', '')}"
        embedding = _generate_embedding(embed_text)

        with Session(engine) as db_session:
            experience = ExperienceAsset(
                experience_type=ExperienceType.DEBUG_PATTERN,
                title=summary_result.get("title", f"执行失败: {error_text[:80] if error_text else '未知错误'}"),
                summary=summary_result.get("summary", ""),
                key_insights=summary_result.get("key_insights", []),
                original_query=instruction,
                solution_code=code[:10000],
                solution_strategy=summary_result.get("solution_strategy", ""),
                debug_iterations=1,
                category=category,
                tags=summary_result.get("tags", []),
                language=language,
                source_user_id=user_id or 0,
                source_project_id=project_id,
                source_record_id=record_id,
                usefulness_score=0.3,
            )
            db_session.add(experience)
            db_session.commit()

            if embedding:
                _set_embedding(db_session, experience.id, embedding)

            db_session.refresh(experience)
            log.info(
                f"[ExperienceExtractor] DEBUG_PATTERN 经验已创建(失败): "
                f"id={experience.id}, title={experience.title}, category={category}"
            )
            return experience

    except Exception as e:
        log.error(f"[ExperienceExtractor] 失败经验提取失败: {e}")
        return None


def _infer_category(instruction: str, language: str) -> str:
    """从分析需求文本推断经验分类"""
    instruction_lower = instruction.lower()

    category_keywords = {
        "file_io": ["文件", "读取", "写入", "路径", "file", "import", "read", "load"],
        "parameter_parsing": ["argparse", "optparse", "参数", "commandargs"],
        "package_import": ["library", "import", "包", "库", "加载"],
        "visualization": ["热图", "heatmap", "火山图", "volcano", "散点图", "scatter",
                          "箱线图", "boxplot", "pca", "降维", "图", "plot", "ggsave",
                          "ggsci", "ggplot", "matplotlib", "seaborn", "可视化"],
        "differential_expression": ["差异表达", "差异基因", "deseq2", "edger", "limma",
                                     "deg", "differential", "fold change", "logfc"],
        "clustering": ["聚类", "cluster", "kmeans", "层次聚类", "hclust"],
        "normalization": ["标准化", "归一化", "normalize", "scale", "z-score", "log2"],
        "qc": ["质控", "质量", "qc", "fastqc", "过滤", "filter"],
        "pathway_enrichment": ["富集", "go", "kegg", "通路", "enrichment", "pathway"],
    }

    scores = {}
    for cat, keywords in category_keywords.items():
        scores[cat] = sum(1 for kw in keywords if kw in instruction_lower)

    if scores:
        best_cat = max(scores, key=scores.get)
        if scores[best_cat] > 0:
            return best_cat

    return "general"


async def _summarize_experience(
    experience_type: str,
    instruction: str,
    session=None,
    user_id: Optional[int] = None,
    **kwargs,
) -> Optional[dict]:
    """
    用 LLM 总结经验要点，生成 title/summary/key_insights/tags。

    使用快速模型（temperature=0.0），输出严格 JSON 格式。

    Args:
        experience_type: "debug_pattern" | "code_snippet"
        instruction: 用户原始分析需求
        session: 数据库会话
        user_id: 用户 ID
        **kwargs: 根据 type 不同，传入不同的上下文

    Returns:
        {"title", "summary", "key_insights", "solution_strategy", "tags"}
    """
    try:
        from app.utils.llm_config import get_fast_llm_config_standalone
        from langchain_openai import ChatOpenAI

        llm_config = get_fast_llm_config_standalone(user_id=user_id)
        llm = ChatOpenAI(
            api_key=llm_config.api_key or "not-needed",
            base_url=llm_config.base_url,
            model=llm_config.model_name,
            temperature=0.0,
        )

        # 根据类型构建不同的提示
        if experience_type == "debug_pattern":
            issues_text = kwargs.get("issues_text", "")
            original_code = kwargs.get("original_code", "")
            fixed_code = kwargs.get("fixed_code", "")
            prompt = f"""你是一个生物信息学经验总结专家。请分析以下代码修复过程，提取关键经验教训。

用户需求：{instruction}

修复前代码中的问题：
{issues_text}

修复方案（代码从旧到新的变化）："""

            if original_code and fixed_code:
                prompt += f"""
原代码（含错误）：
```python
{original_code[:1500]}
```

修复后代码：
```python
{fixed_code[:1500]}
```"""
        else:
            code = kwargs.get("code", "")
            output_text = kwargs.get("output_text", "")
            error_text = kwargs.get("error_text", "")
            has_error = bool(error_text)

            if has_error:
                prompt = f"""你是一个生物信息学经验总结专家。请分析以下代码执行失败案例，提取关键经验教训。

用户需求：{instruction}

执行失败的代码：
```python
{code[:1500]}
```

错误信息：
{error_text[:1000]}"""
            else:
                prompt = f"""你是一个生物信息学经验总结专家。请总结以下成功执行的即席分析代码中的最佳实践。

用户需求：{instruction}

成功执行的代码：
```python
{code[:1500]}
```

执行输出摘要：
{output_text[:1000] if output_text else "无"}"""

        prompt += """

请输出以下 JSON 格式（严格 JSON，不要包含 markdown 标记）：
```json
{
  "title": "经验标题（中文，20字以内，简明扼要）",
  "summary": "经验摘要（中文，2-3句话，包含问题/需求、关键点、解决方案）",
  "key_insights": ["关键洞察1（一句话，可操作的教训）", "关键洞察2"],
  "solution_strategy": "解决策略描述（中文，1句话）",
  "tags": ["标签1", "标签2"]
}
```

要求：
- title 要具体，不要泛泛而谈（如"DESeq2差异分析中必须用argparse传入文件路径"，而非"文件路径问题"）
- key_insights 是可操作的教训，后续代码生成时能从中受益
- 如果涉及文件路径、参数处理、导入库等通用问题，在 tags 中体现
- tags 全部使用小写英文"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="请输出严格 JSON 格式的经验总结。"),
        ]

        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # 清理 markdown
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        import json as json_mod
        from json_repair import repair_json
        repaired = repair_json(raw)
        result = json_mod.loads(repaired)

        return {
            "title": result.get("title", f"经验: {instruction[:60]}"),
            "summary": result.get("summary", ""),
            "key_insights": result.get("key_insights", []),
            "solution_strategy": result.get("solution_strategy", ""),
            "tags": result.get("tags", []),
        }

    except Exception as e:
        log.error(f"[ExperienceExtractor] 经验总结 LLM 调用失败: {e}")
        # 降级：返回基于关键词的简单摘要
        return {
            "title": instruction[:80],
            "summary": f"分析需求: {instruction[:200]}",
            "key_insights": [],
            "solution_strategy": "",
            "tags": [],
        }


async def update_experience_feedback(
    experience_ids: List[str],
    execution_success: bool,
) -> None:
    """
    反馈闭环：根据执行结果更新经验的有用度评分。

    执行成功 → 提升有用度（该经验确实有帮助）
    执行失败 → 降低有用度（该经验可能不准确或过时）

    Args:
        experience_ids: 参与本次生成的经验 ID 列表
        execution_success: 依赖这些经验的代码是否成功执行
    """
    try:
        with Session(engine) as db_session:
            for exp_id in experience_ids:
                experience = db_session.exec(
                    select(ExperienceAsset).where(
                        ExperienceAsset.experience_id == exp_id
                    )
                ).first()

                if not experience:
                    continue

                if execution_success:
                    # 指数移动平均提升有用度
                    experience.usefulness_score = min(
                        1.0,
                        experience.usefulness_score * 0.7 + 0.3
                    )
                    experience.reuse_count = (experience.reuse_count or 0) + 1
                else:
                    # 轻微降低有用度
                    experience.usefulness_score = max(
                        0.0,
                        experience.usefulness_score * 0.9
                    )

                db_session.add(experience)

            db_session.commit()
            log.info(
                f"[ExperienceExtractor] 经验反馈更新: {len(experience_ids)} 条, "
                f"success={execution_success}"
            )

    except Exception as e:
        log.error(f"[ExperienceExtractor] 经验反馈更新失败: {e}")
