"""
技能向量检索服务 - 基于 pgvector 的语义相似度搜索

功能:
1. search: 执行向量相似度搜索
2. search_by_text: 文本查询转向量搜索
3. hybrid_search: 混合搜索（关键词 + 向量）

使用 pgvector 的余弦相似度搜索:
- SELECT skill_id, 1 - (combined_embedding <=> query_vector) as similarity
- FROM skillasset WHERE combined_embedding IS NOT NULL
- ORDER BY combined_embedding <=> query_vector LIMIT N
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from sqlmodel import Session, select, text
from sqlalchemy import and_, or_

from app.core.logger import log
from app.core.database import engine
from app.models.domain import SkillAsset, SkillStatus
from app.services.skill_embedding_service import SkillEmbeddingService


class SkillVectorSearch:
    """
    技能向量检索服务 - 基于 pgvector 的语义相似度搜索

    使用 PostgreSQL pgvector 扩展进行向量相似度搜索，
    支持基于语义相似度的技能推荐。

    相似度度量: 余弦相似度 (Cosine Similarity)
    距离算子: <=> (余弦距离)
    相似度 = 1 - 余弦距离
    """

    # 默认搜索参数
    DEFAULT_LIMIT = 5
    DEFAULT_THRESHOLD = 0.7  # 相似度阈值

    def __init__(self, session: Session = None):
        """
        初始化向量检索服务

        Args:
            session: 数据库会话，如果为 None 则自动创建
        """
        self.session = session
        self._embedding_service: Optional[SkillEmbeddingService] = None

    def _get_embedding_service(self) -> SkillEmbeddingService:
        """获取嵌入服务实例"""
        if not self._embedding_service:
            self._embedding_service = SkillEmbeddingService(self.session)
        return self._embedding_service

    async def search(
        self,
        query_embedding: List[float],
        limit: int = DEFAULT_LIMIT,
        threshold: float = DEFAULT_THRESHOLD,
        exclude_ids: List[str] = None,
        user_id: int = 0
    ) -> List[Dict[str, Any]]:
        """
        执行向量相似度搜索

        使用 pgvector 的余弦距离算子 (<=>) 进行搜索，
        返回相似度高于阈值的技能列表。

        Args:
            query_embedding: 查询向量
            limit: 返回数量限制
            threshold: 相似度阈值 (0.0 - 1.0)
            exclude_ids: 排除的技能 ID 列表
            user_id: 用户 ID，用于权限过滤

        Returns:
            匹配的技能列表，每个元素包含:
            {
                "skill_id": "...",
                "name": "...",
                "description": "...",
                "similarity": 0.85,
                "match_reason": "语义相似"
            }
        """
        if not query_embedding:
            log.warning("[VectorSearch] 查询向量为空")
            return []

        try:
            # 将向量转换为字符串格式
            vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

            # 构建 SQL 查询
            # 使用 pgvector 的余弦距离算子 <=>
            # 相似度 = 1 - 距离
            sql_query = text(f"""
                SELECT
                    skill_id,
                    name,
                    description,
                    executor_type,
                    category,
                    category_name,
                    tags,
                    1 - (combined_embedding <=> '{vector_str}'::vector) as similarity
                FROM skillasset
                WHERE combined_embedding IS NOT NULL
                AND (
                    status = :published_status
                    OR owner_id = :user_id
                )
                AND 1 - (combined_embedding <=> '{vector_str}'::vector) >= :threshold
                {self._build_exclude_clause(exclude_ids)}
                ORDER BY combined_embedding <=> '{vector_str}'::vector
                LIMIT :limit
            """)

            # 执行查询
            if self.session:
                session = self.session
            else:
                session = Session(engine)

            with session if self.session else session:
                result = session.execute(
                    sql_query,
                    {
                        "published_status": SkillStatus.PUBLISHED.value,
                        "user_id": user_id,
                        "threshold": threshold,
                        "limit": limit
                    }
                )

                skills = []
                for row in result:
                    skills.append({
                        "skill_id": row.skill_id,
                        "name": row.name,
                        "description": row.description,
                        "executor_type": row.executor_type,
                        "category": row.category,
                        "category_name": row.category_name,
                        "tags": row.tags or [],
                        "similarity": float(row.similarity),
                        "match_reason": "语义相似度匹配"
                    })

                log.info(f"[VectorSearch] 向量搜索完成: 找到 {len(skills)} 个技能, 阈值={threshold}")
                return skills

        except Exception as e:
            log.error(f"[VectorSearch] 向量搜索失败: {e}")
            return []

    def _build_exclude_clause(self, exclude_ids: List[str] = None) -> str:
        """构建排除 ID 的 SQL 子句"""
        if not exclude_ids:
            return ""
        ids_str = ",".join(f"'{id}'" for id in exclude_ids)
        return f"AND skill_id NOT IN ({ids_str})"

    async def search_by_text(
        self,
        query_text: str,
        limit: int = DEFAULT_LIMIT,
        threshold: float = DEFAULT_THRESHOLD,
        exclude_ids: List[str] = None,
        user_id: int = 0
    ) -> List[Dict[str, Any]]:
        """
        文本查询转向量搜索

        将用户查询文本转换为向量，然后执行向量搜索。

        Args:
            query_text: 查询文本
            limit: 返回数量限制
            threshold: 相似度阈值
            exclude_ids: 排除的技能 ID 列表
            user_id: 用户 ID

        Returns:
            匹配的技能列表
        """
        if not query_text:
            return []

        try:
            # 计算查询向量
            embedding_service = self._get_embedding_service()
            query_embedding = await embedding_service.compute_query_embedding(query_text)

            if not query_embedding:
                log.warning("[VectorSearch] 无法计算查询向量")
                return []

            # 执行向量搜索
            return await self.search(
                query_embedding=query_embedding,
                limit=limit,
                threshold=threshold,
                exclude_ids=exclude_ids,
                user_id=user_id
            )

        except Exception as e:
            log.error(f"[VectorSearch] 文本搜索失败: {e}")
            return []

    async def hybrid_search(
        self,
        query_text: str,
        keyword_matches: List[Dict[str, Any]] = None,
        limit: int = DEFAULT_LIMIT,
        threshold: float = 0.6,
        user_id: int = 0
    ) -> List[Dict[str, Any]]:
        """
        混合搜索 - 关键词匹配 + 向量相似度

        结合关键词匹配和向量相似度搜索，提供更准确的推荐。

        混合策略:
        1. 关键词匹配结果直接包含
        2. 向量搜索补充语义相似但关键词未匹配的技能
        3. 合并去重，按综合分数排序

        Args:
            query_text: 查询文本
            keyword_matches: 关键词匹配结果
            limit: 返回数量限制
            threshold: 相似度阈值
            user_id: 用户 ID

        Returns:
            合并后的匹配结果
        """
        # 1. 获取关键词匹配的技能 ID（用于排除）
        keyword_skill_ids = set()
        if keyword_matches:
            keyword_skill_ids = {m.get("skill_id") for m in keyword_matches if m.get("skill_id")}

        # 2. 执行向量搜索（排除已匹配的）
        vector_results = await self.search_by_text(
            query_text=query_text,
            limit=limit,
            threshold=threshold,
            exclude_ids=list(keyword_skill_ids) if keyword_skill_ids else None,
            user_id=user_id
        )

        # 3. 合并结果
        # 关键词匹配标记为 "keyword"，向量匹配标记为 "vector"
        for match in (keyword_matches or []):
            match["match_source"] = "keyword"

        for match in vector_results:
            match["match_source"] = "vector"

        # 4. 按分数排序并返回
        all_results = (keyword_matches or []) + vector_results

        # 综合排序：关键词匹配优先，然后按相似度
        all_results.sort(
            key=lambda x: (
                0 if x.get("match_source") == "keyword" else 1,
                -x.get("match_score", x.get("similarity", 0))
            )
        )

        return all_results[:limit]

    async def find_similar_skills(
        self,
        skill_id: str,
        limit: int = 5,
        threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        查找与指定技能相似的其他技能

        Args:
            skill_id: 目标技能 ID
            limit: 返回数量限制
            threshold: 相似度阈值

        Returns:
            相似的技能列表
        """
        try:
            with Session(engine) as session:
                # 获取目标技能的向量
                skill = session.exec(
                    select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                ).first()

                if not skill or not skill.combined_embedding:
                    log.warning(f"[VectorSearch] 技能无向量: {skill_id}")
                    return []

                # 使用目标向量搜索相似技能
                return await self.search(
                    query_embedding=skill.combined_embedding,
                    limit=limit + 1,  # 多取一个，排除自己
                    threshold=threshold,
                    exclude_ids=[skill_id]  # 排除自己
                )

        except Exception as e:
            log.error(f"[VectorSearch] 查找相似技能失败: {e}")
            return []


# ==========================================
# 辅助函数
# ==========================================

async def search_skills_by_vector(
    query_embedding: List[float],
    limit: int = 5,
    threshold: float = 0.7,
    user_id: int = 0
) -> List[Dict[str, Any]]:
    """
    向量搜索技能（便捷函数）

    Args:
        query_embedding: 查询向量
        limit: 返回数量限制
        threshold: 相似度阈值
        user_id: 用户 ID

    Returns:
        匹配的技能列表
    """
    service = SkillVectorSearch()
    return await service.search(
        query_embedding=query_embedding,
        limit=limit,
        threshold=threshold,
        user_id=user_id
    )


async def search_skills_by_text(
    query_text: str,
    limit: int = 5,
    threshold: float = 0.7,
    user_id: int = 0
) -> List[Dict[str, Any]]:
    """
    文本搜索技能（便捷函数）

    Args:
        query_text: 查询文本
        limit: 返回数量限制
        threshold: 相似度阈值
        user_id: 用户 ID

    Returns:
        匹配的技能列表
    """
    service = SkillVectorSearch()
    return await service.search_by_text(
        query_text=query_text,
        limit=limit,
        threshold=threshold,
        user_id=user_id
    )


log.info("✅ 技能向量检索服务已加载")