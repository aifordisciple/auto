"""
技能匹配器 - 带降级策略

降级策略：
1. 本地嵌入优先（Ollama bge-m3）
2. 远程API回退（OpenAI）
3. 规则引擎兜底（关键词匹配）

使用场景：
- 正常情况：使用本地嵌入，快速且稳定
- 本地不可用：回退到OpenAI API
- 两者都不可用：使用关键词匹配
"""

import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.core.logger import log


class EmbeddingSource(str, Enum):
    """嵌入来源"""
    LOCAL = "local"      # 本地 Ollama
    REMOTE = "remote"    # 远程 OpenAI
    KEYWORD = "keyword"  # 关键词匹配


@dataclass
class MatchResult:
    """匹配结果"""
    skill_id: str
    name: str
    score: float
    source: EmbeddingSource
    metadata: Dict[str, Any]


class SkillMatcherWithFallback:
    """
    技能匹配器（带降级策略）

    按以下顺序尝试：
    1. 本地嵌入（Ollama bge-m3）
    2. 远程嵌入（OpenAI API）
    3. 关键词匹配
    """

    def __init__(self):
        """初始化匹配器"""
        self._local_service = None
        self._remote_service = None

        # 健康状态缓存
        self._local_healthy: Optional[bool] = None
        self._remote_healthy: Optional[bool] = None
        self._last_health_check: float = 0

        log.info("[SkillMatcher] 初始化带降级策略的匹配器")

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本嵌入向量

        按优先级尝试：本地 → 远程 → None

        Args:
            text: 输入文本

        Returns:
            嵌入向量，失败返回 None
        """
        # 1. 尝试本地嵌入
        try:
            embedding = await self._get_local_embedding(text)
            if embedding:
                self._local_healthy = True
                return embedding
        except Exception as e:
            log.warning(f"[SkillMatcher] 本地嵌入失败: {e}")
            self._local_healthy = False

        # 2. 回退到远程嵌入
        try:
            embedding = await self._get_remote_embedding(text)
            if embedding:
                self._remote_healthy = True
                return embedding
        except Exception as e:
            log.warning(f"[SkillMatcher] 远程嵌入失败: {e}")
            self._remote_healthy = False

        # 3. 都失败了
        log.error("[SkillMatcher] 所有嵌入服务都不可用")
        return None

    async def _get_local_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取本地嵌入（已移除）

        Args:
            text: 输入文本

        Returns:
            None（本地嵌入服务已移除）
        """
        log.warning("[SkillMatcher] 本地嵌入服务已移除")
        return None

    async def _get_remote_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取远程嵌入（已移除）

        Args:
            text: 输入文本

        Returns:
            None（远程嵌入服务已移除）
        """
        log.warning("[SkillMatcher] 远程嵌入服务已移除")
        return None

    async def match_skills(
        self,
        query: str,
        skills: List[Dict[str, Any]],
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        匹配技能

        Args:
            query: 查询文本
            skills: 技能列表
            top_n: 返回前N个结果

        Returns:
            匹配结果列表
        """
        # 1. 尝试向量匹配
        query_embedding = await self.get_embedding(query)

        if query_embedding:
            # 使用向量相似度匹配
            results = await self._vector_match(query_embedding, skills)
            return results[:top_n]

        # 2. 回退到关键词匹配
        log.info("[SkillMatcher] 使用关键词匹配")
        results = self._keyword_match(query, skills)
        return results[:top_n]

    async def _vector_match(
        self,
        query_embedding: List[float],
        skills: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        向量相似度匹配

        Args:
            query_embedding: 查询向量
            skills: 技能列表

        Returns:
            匹配结果
        """
        results = []

        for skill in skills:
            # 获取技能嵌入
            skill_embedding = await self._get_skill_embedding(skill)

            if skill_embedding:
                # 计算余弦相似度
                similarity = self._cosine_similarity(query_embedding, skill_embedding)

                results.append({
                    'skill_id': skill.get('skill_id'),
                    'name': skill.get('name'),
                    'score': similarity,
                    'source': 'vector',
                })

        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    async def _get_skill_embedding(self, skill: Dict[str, Any]) -> Optional[List[float]]:
        """
        获取技能嵌入向量

        优先从数据库读取缓存的嵌入，否则生成新的
        """
        skill_id = skill.get('skill_id')

        # 尝试从数据库获取缓存的嵌入
        try:
            from app.core.database import get_session
            from sqlmodel import select
            from app.models.domain import SkillAsset

            session_gen = get_session()
            session = next(session_gen)

            try:
                statement = select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                skill_record = session.exec(statement).first()

                if skill_record and hasattr(skill_record, 'combined_embedding') and skill_record.combined_embedding:
                    return skill_record.combined_embedding

            finally:
                session.close()

        except Exception as e:
            log.debug(f"[SkillMatcher] 获取缓存嵌入失败: {e}")

        # 生成新的嵌入
        text = f"{skill.get('name', '')} {skill.get('description', '')}"
        return await self.get_embedding(text)

    def _keyword_match(
        self,
        query: str,
        skills: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        关键词匹配

        Args:
            query: 查询文本
            skills: 技能列表

        Returns:
            匹配结果
        """
        results = []
        query_lower = query.lower()

        for skill in skills:
            score = 0
            name = skill.get('name', '').lower()
            description = skill.get('description', '').lower()
            skill_id = skill.get('skill_id', '').lower()
            tags = skill.get('tags', [])

            # 名称匹配（权重最高）
            if query_lower in name:
                score += 0.8

            # 描述匹配
            if query_lower in description:
                score += 0.5

            # ID匹配
            if query_lower in skill_id:
                score += 0.6

            # 标签匹配
            for tag in tags:
                if query_lower in tag.lower():
                    score += 0.4
                    break

            if score > 0:
                results.append({
                    'skill_id': skill.get('skill_id'),
                    'name': skill.get('name'),
                    'score': score,
                    'source': 'keyword',
                })

        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def check_health(self) -> Dict[str, Any]:
        """
        检查服务健康状态

        Returns:
            健康状态字典
        """
        # 检查本地嵌入
        local_health = await self._check_local_health()

        # 检查远程嵌入
        remote_health = await self._check_remote_health()

        return {
            'local_embedding': local_health,
            'remote_embedding': remote_health,
            'timestamp': time.time(),
        }

    async def _check_local_health(self) -> Dict[str, Any]:
        """检查本地嵌入服务健康状态（已移除）"""
        return {
            'status': 'not_configured',
            'error': '本地嵌入服务已移除',
        }

    async def _check_remote_health(self) -> Dict[str, Any]:
        """检查远程嵌入服务健康状态（已移除）"""
        return {
            'status': 'not_configured',
            'error': '远程嵌入服务已移除',
        }


# ==========================================
# 全局单例
# ==========================================

_matcher_instance: Optional[SkillMatcherWithFallback] = None


def get_skill_matcher_with_fallback() -> SkillMatcherWithFallback:
    """获取技能匹配器单例"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = SkillMatcherWithFallback()
    return _matcher_instance


log.info("✅ 技能匹配器（带降级策略）已加载")