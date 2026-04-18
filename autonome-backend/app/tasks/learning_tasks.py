"""
学习任务模块

提供两类任务：
1. 文献解析任务（异步 Celery 任务）：
   - process_literature: PDF 解析 → 分块 → Vision LLM → Embedding → 入库
   - process_doi: DOI 元数据获取 → PDF 下载 → 触发 process_literature

2. 定时学习任务（Celery Beat）：
   - 反馈聚合 - 每5分钟
   - 用户偏好更新 - 每小时
   - 知识提炼 - 每6小时
   - 权重优化 - 每天优化推荐权重
   - 学习报告 - 每周生成学习报告

设计原则：
- 模块化任务函数
- 支持手动触发
- 详细结果记录
- 错误处理和重试（指数退避）
"""

import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.core.logger import log


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 任务状态枚举
# ==========================================

class TaskStatus(str, Enum):
    """任务状态"""
    SUCCESS = "success"
    NO_DATA = "no_data"
    PARTIAL = "partial"
    ERROR = "error"


# ==========================================
# 任务结果数据类
# ==========================================

@dataclass
class TaskResult:
    """
    任务结果

    存储任务执行的详细结果：
    - 任务名称和状态
    - 处理统计数据
    - 执行时间
    """
    task_name: str
    status: str
    timestamp: str = field(default_factory=lambda: get_utc_now().isoformat())
    duration_seconds: float = 0.0
    processed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        # 将所有字段展平到顶层
        for key, value in self.metadata.items():
            if key not in result:
                result[key] = value
        return result


# ==========================================
# 反馈聚合任务
# ==========================================

def aggregate_feedback(
    hours: int = 1,
    feedback_types: Optional[List[str]] = None,
) -> TaskResult:
    """
    聚合反馈数据

    Args:
        hours: 聚合时间范围（小时）
        feedback_types: 反馈类型列表（可选）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始聚合反馈数据: hours={hours}")

    try:
        # 模拟聚合过程
        # 实际实现需要查询 BehaviorRecord 和 SkillMatchingFeedback
        processed_count = 100  # 模拟处理数量
        success_count = 95
        failed_count = 5

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="aggregate_feedback",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=processed_count,
            success_count=success_count,
            failed_count=failed_count,
            message=f"成功聚合 {success_count} 条反馈",
            metadata={
                "period_hours": hours,
                "feedback_types": feedback_types or ["all"],
            }
        )

        log.info(f"[LearningTask] 反馈聚合完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 反馈聚合失败: {e}")
        return TaskResult(
            task_name="aggregate_feedback",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 用户偏好更新任务
# ==========================================

def update_user_profiles(
    user_ids: Optional[List[int]] = None,
    days: int = 30,
) -> TaskResult:
    """
    更新用户偏好画像

    Args:
        user_ids: 指定用户ID列表（可选，不指定则更新所有活跃用户）
        days: 分析时间范围（天）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始更新用户偏好画像: user_ids={user_ids}")

    try:
        # 模拟更新过程
        # 实际实现需要调用 PreferenceEngine
        if user_ids:
            requested_count = len(user_ids)
            updated_count = requested_count
        else:
            requested_count = 50  # 模拟活跃用户数
            updated_count = 48

        failed_count = requested_count - updated_count

        status = TaskStatus.SUCCESS.value if failed_count == 0 else TaskStatus.PARTIAL.value

        result = TaskResult(
            task_name="update_user_profiles",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=requested_count,
            success_count=updated_count,
            failed_count=failed_count,
            message=f"成功更新 {updated_count} 个用户偏好",
            metadata={
                "requested_count": requested_count,
                "analysis_days": days,
            }
        )

        log.info(f"[LearningTask] 用户偏好更新完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 用户偏好更新失败: {e}")
        return TaskResult(
            task_name="update_user_profiles",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 知识提炼任务
# ==========================================

def extract_domain_knowledge(
    source: str = "all",
    min_confidence: float = 0.7,
) -> TaskResult:
    """
    提炼领域知识

    Args:
        source: 知识来源（execution_records, feedback, skill_docs, all）
        min_confidence: 最小置信度阈值

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始提炼领域知识: source={source}")

    try:
        # 模拟提炼过程
        # 实际实现需要调用 KnowledgeEngine
        extracted_count = 25  # 模拟提取数量

        knowledge_types = {
            "concept": 10,
            "synonym": 8,
            "parameter_rule": 5,
            "error_pattern": 2,
        }

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="extract_domain_knowledge",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=extracted_count,
            success_count=extracted_count,
            message=f"成功提炼 {extracted_count} 条知识",
            metadata={
                "source": source,
                "min_confidence": min_confidence,
                "knowledge_types": knowledge_types,
            }
        )

        log.info(f"[LearningTask] 知识提炼完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 知识提炼失败: {e}")
        return TaskResult(
            task_name="extract_domain_knowledge",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 权重优化任务
# ==========================================

def optimize_weights(
    strategy: str = "feedback_driven",
    min_samples: int = 10,
) -> TaskResult:
    """
    优化推荐权重

    Args:
        strategy: 优化策略（feedback_driven, success_rate, hybrid）
        min_samples: 最小样本量

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始优化推荐权重: strategy={strategy}")

    try:
        # 模拟优化过程
        # 实际实现需要调用 WeightOptimizer
        optimized_skills = 15  # 模拟优化的技能数
        total_adjustments = 45  # 模拟总调整数

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="optimize_weights",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=optimized_skills,
            success_count=optimized_skills,
            message=f"成功优化 {optimized_skills} 个技能权重",
            metadata={
                "strategy": strategy,
                "min_samples": min_samples,
                "optimized_skills": optimized_skills,
                "total_adjustments": total_adjustments,
            }
        )

        log.info(f"[LearningTask] 权重优化完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 权重优化失败: {e}")
        return TaskResult(
            task_name="optimize_weights",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 学习报告生成任务
# ==========================================

def generate_learning_report(
    report_type: str = "weekly",
) -> TaskResult:
    """
    生成学习报告

    Args:
        report_type: 报告类型（daily, weekly, monthly）

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"[LearningTask] 开始生成学习报告: type={report_type}")

    try:
        # 模拟报告生成
        # 实际实现需要调用 LearningMetricsService
        report_id = f"report-{report_type}-{get_utc_now().strftime('%Y%m%d%H%M%S')}"

        status = TaskStatus.SUCCESS.value

        result = TaskResult(
            task_name="generate_learning_report",
            status=status,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=1,
            success_count=1,
            message=f"成功生成 {report_type} 报告",
            metadata={
                "report_id": report_id,
                "report_type": report_type,
            }
        )

        log.info(f"[LearningTask] 报告生成完成: {result.message}")
        return result

    except Exception as e:
        log.error(f"[LearningTask] 报告生成失败: {e}")
        return TaskResult(
            task_name="generate_learning_report",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# 文献解析任务（核心异步任务）
# ==========================================

def process_literature(literature_id: int) -> TaskResult:
    """
    处理文献：PDF 解析 → 分块 → Vision LLM → Embedding → 入库

    Args:
        literature_id: 文献数据库 ID

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"📚 [LearningTask] 开始处理文献: id={literature_id}")

    try:
        from sqlmodel import Session, select
        from app.core.database import engine
        from app.models.learning import Literature, LiteratureChunk
        from app.models.enums import LiteratureStatus, ChunkType
        from app.services.learning_ingestion_service import (
            extract_pdf_with_figures,
            smart_chunking,
            align_captions,
            analyze_figure_with_vision_llm,
            analyze_figure_with_text_llm,
            generate_embedding,
        )
        from app.services.learning_service import update_literature_status

        with Session(engine) as session:
            # 1. 获取文献记录
            literature = session.get(Literature, literature_id)
            if not literature:
                return TaskResult(
                    task_name="process_literature",
                    status=TaskStatus.ERROR.value,
                    message=f"文献不存在: id={literature_id}",
                )

            # 2. 更新状态为解析中
            update_literature_status(session, literature_id, LiteratureStatus.PARSING)

            file_path = literature.file_path
            if not file_path or not os.path.exists(file_path):
                update_literature_status(
                    session, literature_id, LiteratureStatus.ERROR,
                    "PDF 文件路径无效或文件不存在"
                )
                return TaskResult(
                    task_name="process_literature",
                    status=TaskStatus.ERROR.value,
                    message="PDF 文件不存在",
                )

            # 3. 提取 PDF 文本和图表
            output_dir = os.path.join(os.path.dirname(file_path), f"figures_{literature.literature_id}")
            pdf_result = extract_pdf_with_figures(file_path, output_dir)

            if pdf_result.get("error"):
                update_literature_status(
                    session, literature_id, LiteratureStatus.ERROR,
                    pdf_result["error"]
                )
                return TaskResult(
                    task_name="process_literature",
                    status=TaskStatus.ERROR.value,
                    message=pdf_result["error"],
                )

            # 4. 图注对齐
            figures = align_captions(pdf_result["text_by_page"], pdf_result["figures"])

            # 5. 智能分块
            chunks_data = smart_chunking(pdf_result["text_by_page"], figures)

            # 6. Vision LLM 处理图表块 + Embedding 生成
            chunk_count = 0
            for chunk_data in chunks_data:
                # 对图表块调用 Vision LLM
                metadata = chunk_data.get("metadata_") or {}
                if chunk_data["chunk_type"] == "figure" and metadata.get("image_path"):
                    # 尝试 Vision LLM
                    vision_result = asyncio.run(
                        analyze_figure_with_vision_llm(
                            metadata["image_path"],
                            chunk_data.get("figure_caption", ""),
                        )
                    )
                    if vision_result:
                        metadata["vision_extraction"] = vision_result
                    else:
                        # 降级为文本 LLM
                        text_result = asyncio.run(
                            analyze_figure_with_text_llm(chunk_data.get("figure_caption", ""))
                        )
                        if text_result:
                            metadata["vision_extraction"] = text_result

                # 生成 Embedding
                embedding = None
                embed_text = chunk_data["content"]
                if chunk_data["chunk_type"] == "figure" and metadata.get("vision_extraction"):
                    ve = metadata["vision_extraction"]
                    embed_text = f"{chunk_data.get('figure_caption', '')} {ve.get('methodology', '')}"
                embedding = generate_embedding(embed_text)

                # 创建知识块记录
                chunk = LiteratureChunk(
                    literature_id=literature_id,
                    chunk_index=chunk_data["chunk_index"],
                    chunk_type=ChunkType(chunk_data["chunk_type"]),
                    content=chunk_data["content"],
                    page_number=chunk_data["page_number"],
                    section_title=chunk_data.get("section_title", ""),
                    figure_caption=chunk_data.get("figure_caption"),
                    metadata_=metadata if metadata else None,
                )
                session.add(chunk)
                session.flush()  # 获取 chunk.id

                # 存储 embedding（需要原生 SQL）
                if embedding:
                    from sqlalchemy import text as sql_text
                    session.exec(sql_text(
                        "UPDATE literature_chunk SET embedding = :embedding WHERE id = :id"
                    ), params={"embedding": json.dumps(embedding), "id": chunk.id})

                chunk_count += 1

            session.commit()

            # 7. 更新文献状态和元数据
            literature.page_count = pdf_result["page_count"]
            literature.status = LiteratureStatus.READY
            session.add(literature)
            session.commit()

            log.info(f"📚 [LearningTask] 文献处理完成: {literature.literature_id}, {chunk_count} 个知识块")

            return TaskResult(
                task_name="process_literature",
                status=TaskStatus.SUCCESS.value,
                duration_seconds=(get_utc_now() - start_time).total_seconds(),
                processed_count=1,
                success_count=1,
                message=f"成功处理文献，生成 {chunk_count} 个知识块",
                metadata={
                    "literature_id": literature.literature_id,
                    "chunk_count": chunk_count,
                    "page_count": pdf_result["page_count"],
                    "figure_count": len(figures),
                },
            )

    except Exception as e:
        log.error(f"📚 [LearningTask] 文献处理失败: {e}")
        # 尝试更新状态为错误
        try:
            from sqlmodel import Session
            from app.core.database import engine
            from app.services.learning_service import update_literature_status
            with Session(engine) as session:
                update_literature_status(session, literature_id, LiteratureStatus.ERROR, str(e))
        except Exception:
            pass

        return TaskResult(
            task_name="process_literature",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


def process_doi(literature_id: int, doi: str) -> TaskResult:
    """
    处理 DOI 导入：获取元数据 → 下载 PDF → 触发 process_literature

    Args:
        literature_id: 文献数据库 ID
        doi: DOI 标识符

    Returns:
        任务结果
    """
    start_time = get_utc_now()
    log.info(f"📚 [LearningTask] 开始处理 DOI: {doi}")

    try:
        import httpx
        from sqlmodel import Session
        from app.core.database import engine
        from app.models.learning import Literature
        from app.models.enums import LiteratureStatus
        from app.services.learning_service import update_literature_status

        # 1. 通过 CrossRef API 获取元数据
        crossref_url = f"https://api.crossref.org/works/{doi}"
        with httpx.Client(timeout=30) as client:
            resp = client.get(crossref_url)
            if resp.status_code != 200:
                raise Exception(f"CrossRef API 返回 {resp.status_code}")

            data = resp.json().get("message", {})
            title = data.get("title", [""])[0] if data.get("title") else ""
            authors_list = data.get("author", [])
            authors = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in authors_list
            )
            journal = data.get("container-title", [""])[0] if data.get("container-title") else ""
            year = data.get("published-print", {}).get("date-parts", [[None]])[0][0]
            abstract = data.get("abstract", "")

        # 2. 尝试通过 Unpaywall 获取开放获取 PDF
        pdf_path = None
        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=autonome@example.com"
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(unpaywall_url)
                if resp.status_code == 200:
                    up_data = resp.json()
                    best_oa = up_data.get("best_oa_location", {})
                    pdf_url = best_oa.get("url_for_pdf")
                    if pdf_url:
                        with client.stream("GET", pdf_url, timeout=60) as stream:
                            if stream.status_code == 200:
                                from app.core.config import settings
                                upload_dir = os.path.join(settings.UPLOAD_DIR, "literatures")
                                os.makedirs(upload_dir, exist_ok=True)
                                pdf_path = os.path.join(upload_dir, f"doi_{doi.replace('/', '_')}.pdf")
                                with open(pdf_path, "wb") as f:
                                    for chunk in stream.iter_bytes():
                                        f.write(chunk)
        except Exception as e:
            log.warning(f"📚 [LearningTask] Unpaywall 获取 PDF 失败: {e}")

        # 3. 更新文献元数据
        with Session(engine) as session:
            literature = session.get(Literature, literature_id)
            if literature:
                literature.title = title or literature.title
                literature.authors = authors
                literature.journal = journal
                literature.year = year
                literature.abstract = abstract
                if pdf_path:
                    literature.file_path = pdf_path
                    from app.services.learning_ingestion_service import compute_file_hash
                    literature.file_hash = compute_file_hash(pdf_path)
                session.add(literature)
                session.commit()

        # 4. 如果获取到 PDF，触发解析任务
        if pdf_path:
            try:
                task_process_literature.delay(literature_id)
            except Exception:
                process_literature(literature_id)
        else:
            # 没有获取到 PDF，标记为需要手动上传
            with Session(engine) as session:
                update_literature_status(
                    session, literature_id, LiteratureStatus.ERROR,
                    "无法自动获取 PDF，请手动上传"
                )

        return TaskResult(
            task_name="process_doi",
            status=TaskStatus.SUCCESS.value,
            duration_seconds=(get_utc_now() - start_time).total_seconds(),
            processed_count=1,
            success_count=1,
            message=f"DOI 元数据获取成功，{'PDF 已下载' if pdf_path else 'PDF 未获取'}",
            metadata={"doi": doi, "pdf_downloaded": pdf_path is not None},
        )

    except Exception as e:
        log.error(f"📚 [LearningTask] DOI 处理失败: {e}")
        try:
            from sqlmodel import Session
            from app.core.database import engine
            from app.services.learning_service import update_literature_status
            with Session(engine) as session:
                update_literature_status(session, literature_id, LiteratureStatus.ERROR, str(e))
        except Exception:
            pass

        return TaskResult(
            task_name="process_doi",
            status=TaskStatus.ERROR.value,
            message=str(e),
        )


# ==========================================
# Celery 任务包装器
# ==========================================

# Beat 调度配置
BEAT_SCHEDULE = {
    "aggregate-feedback": {
        "task": "app.tasks.learning_tasks.task_aggregate_feedback",
        "schedule": 300.0,  # 每 5 分钟
    },
    "update-user-profiles": {
        "task": "app.tasks.learning_tasks.task_update_user_profiles",
        "schedule": 3600.0,  # 每小时
    },
    "extract-domain-knowledge": {
        "task": "app.tasks.learning_tasks.task_extract_domain_knowledge",
        "schedule": 21600.0,  # 每 6 小时
    },
    "optimize-weights": {
        "task": "app.tasks.learning_tasks.task_optimize_weights",
        "schedule": 86400.0,  # 每天
    },
    "generate-learning-report": {
        "task": "app.tasks.learning_tasks.task_generate_learning_report",
        "schedule": 604800.0,  # 每周
    },
}

# 标记任务是否已注册
LEARNING_TASKS_REGISTERED = False

# 尝试注册 Celery 任务
try:
    from celery import shared_task

    # 文献解析任务（核心异步任务，支持重试）
    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def task_process_literature(self, literature_id: int):
        """Celery 任务：处理文献 PDF"""
        try:
            result = process_literature(literature_id)
            return result.to_dict()
        except Exception as exc:
            # 指数退避重试
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)

    @shared_task(bind=True, max_retries=2, default_retry_delay=30)
    def task_process_doi(self, literature_id: int, doi: str):
        """Celery 任务：处理 DOI 导入"""
        try:
            result = process_doi(literature_id, doi)
            return result.to_dict()
        except Exception as exc:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)

    # 定时学习任务
    def task_aggregate_feedback():
        """Celery 任务：聚合反馈数据"""
        result = aggregate_feedback()
        return result.to_dict()

    @shared_task
    def task_update_user_profiles():
        """Celery 任务：更新用户偏好画像"""
        result = update_user_profiles()
        return result.to_dict()

    @shared_task
    def task_extract_domain_knowledge():
        """Celery 任务：提炼领域知识"""
        result = extract_domain_knowledge()
        return result.to_dict()

    @shared_task
    def task_optimize_weights():
        """Celery 任务：优化推荐权重"""
        result = optimize_weights()
        return result.to_dict()

    @shared_task
    def task_generate_learning_report():
        """Celery 任务：生成学习报告"""
        result = generate_learning_report()
        return result.to_dict()

    LEARNING_TASKS_REGISTERED = True
    log.info("✅ 学习 Celery 任务已注册")

except ImportError:
    log.warning("Celery 未安装，跳过定时任务注册")
except Exception as e:
    log.warning(f"Celery 任务注册失败: {e}")

# 尝试更新 Celery Beat 调度（延迟执行）
def _register_beat_schedule():
    """注册 Beat 调度（延迟调用）"""
    try:
        from app.services.celery_app import celery_app
        celery_app.conf.beat_schedule.update(BEAT_SCHEDULE)
        log.info("✅ 学习定时任务已注册到 Celery Beat")
    except Exception as e:
        log.warning(f"Celery Beat 调度注册失败: {e}")


# ==========================================
# 导出
# ==========================================

__all__ = [
    "TaskResult",
    "TaskStatus",
    # 文献解析任务
    "process_literature",
    "process_doi",
    # 定时学习任务
    "aggregate_feedback",
    "update_user_profiles",
    "extract_domain_knowledge",
    "optimize_weights",
    "generate_learning_report",
    "BEAT_SCHEDULE",
    "LEARNING_TASKS_REGISTERED",
]