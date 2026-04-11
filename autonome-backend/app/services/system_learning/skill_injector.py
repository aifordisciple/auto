"""
技能注入器 - Agent 调用时隐身注入系统技能

核心功能:
1. 混合检索（向量 + 关键词）
2. Top-K 返回
3. 隐身注入到 Agent 上下文

这是系统学习层的出口组件，在 Agent 处理用户请求时，
自动检索并注入相关的系统级技能，提升响应质量。

使用方式:
    from app.services.system_learning.skill_injector import get_skill_injector

    injector = get_skill_injector()
    instructions = injector.inject_for_query(user_query)
"""

from typing import List, Dict, Any, Optional, Tuple
from sqlmodel import Session, select
import os
import numpy as np

from app.core.logger import log
from app.core.database import engine
from app.models.system_skill import SystemSkill


# ============================================================================
# 配置常量
# ============================================================================

class InjectorConfig:
    """
    注入器配置

    控制技能检索和注入的行为参数。
    """

    # 最多注入技能数量
    TOP_K: int = 3

    # 向量相似度阈值
    SIMILARITY_THRESHOLD: float = 0.7

    # 向量检索权重
    VECTOR_WEIGHT: float = 0.7

    # 关键词检索权重
    KEYWORD_WEIGHT: float = 0.3

    # 嵌入模型
    EMBEDDING_MODEL: str = "text-embedding-3-small"


# ============================================================================
# 技能注入器
# ============================================================================

class SkillInjector:
    """
    技能注入器

    核心职责:
    1. 根据用户查询检索相关系统技能
    2. 混合排序（向量相似度 + 关键词匹配）
    3. 格式化技能指令供 Agent 使用
    4. 记录注入事件用于效果追踪

    检索策略:
    - 向量检索: 使用 pgvector 计算语义相似度
    - 关键词检索: 使用 Jaccard 相似度匹配触发词
    - 混合排序: 加权融合两种检索结果

    使用示例:
        >>> injector = SkillInjector()
        >>> instructions = injector.inject_for_query("如何进行DESeq2差异分析")
        >>> for inst in instructions:
        ...     print(inst)
    """

    def __init__(self, session: Session = None):
        """
        初始化注入器

        Args:
            session: 数据库会话（可选）
        """
        self.session = session

    def inject_for_query(
        self,
        query: str,
        context: Optional[Dict] = None,
        limit: Optional[int] = None
    ) -> List[str]:
        """
        为查询注入相关系统技能

        主入口方法，根据用户查询返回相关的技能指令。

        流程:
        1. 混合检索获取候选技能
        2. 格式化技能指令
        3. 记录注入事件

        Args:
            query: 用户查询文本
            context: 额外上下文信息（可选）
            limit: 最大返回数量

        Returns:
            List[str]: 技能指令列表，用于注入到 system prompt
        """
        limit = limit or InjectorConfig.TOP_K

        # 混合检索
        skills = self.hybrid_search(query, limit=limit)

        if not skills:
            log.debug(f"未找到相关系统技能 (查询: {query[:50]}...)")
            return []

        # 提取指令
        instructions = []
        for skill in skills:
            instruction = self._format_instruction(skill)
            instructions.append(instruction)

            # 记录注入
            self._record_injection(skill.skill_id, query)

        log.info(f"注入 {len(instructions)} 个系统技能 (查询: {query[:50]}...)")
        return instructions

    def hybrid_search(
        self,
        query: str,
        limit: int = 5
    ) -> List[SystemSkill]:
        """
        混合检索：向量相似度 + 关键词匹配

        结合语义检索和关键词匹配，提高召回率和准确率。

        Args:
            query: 查询文本
            limit: 最大返回数量

        Returns:
            List[SystemSkill]: 匹配的系统技能列表
        """
        # 1. 向量检索
        vector_results = self._vector_search(query, limit=limit * 2)

        # 2. 关键词检索
        keyword_results = self._keyword_search(query, limit=limit * 2)

        # 3. 合并排序
        merged = self._merge_results(vector_results, keyword_results)

        return merged[:limit]

    def _vector_search(
        self,
        query: str,
        limit: int = 10
    ) -> List[Tuple[SystemSkill, float]]:
        """
        向量语义检索

        使用 pgvector 计算查询与技能向量的余弦相似度。

        Args:
            query: 查询文本
            limit: 最大返回数量

        Returns:
            List[Tuple[SystemSkill, float]]: [(技能, 相似度分数), ...]
        """
        try:
            # 生成查询向量
            query_embedding = self._get_embedding(query)
            if query_embedding is None:
                log.debug("无法生成查询向量，跳过向量检索")
                return []

            # 数据库查询
            session = self.session or Session(engine)
            try:
                # 查询所有有向量的活跃技能
                statement = select(SystemSkill).where(
                    SystemSkill.status == "active",
                    SystemSkill.combined_embedding.isnot(None)
                )

                skills = session.exec(statement).all()

                # 计算相似度
                results = []
                for skill in skills:
                    if skill.combined_embedding:
                        similarity = self._cosine_similarity(
                            query_embedding,
                            skill.combined_embedding
                        )
                        if similarity >= InjectorConfig.SIMILARITY_THRESHOLD:
                            results.append((skill, similarity))

                # 按相似度排序
                results.sort(key=lambda x: x[1], reverse=True)
                log.debug(f"向量检索返回 {len(results)} 个候选")
                return results[:limit]

            finally:
                if not self.session:
                    session.close()

        except Exception as e:
            log.error(f"向量检索失败: {e}")
            return []

    def _keyword_search(
        self,
        query: str,
        limit: int = 10
    ) -> List[Tuple[SystemSkill, float]]:
        """
        关键词匹配检索

        使用 Jaccard 相似度匹配查询与技能的触发词和标签。

        Args:
            query: 查询文本
            limit: 最大返回数量

        Returns:
            List[Tuple[SystemSkill, float]]: [(技能, 匹配分数), ...]
        """
        try:
            session = self.session or Session(engine)
            try:
                # 提取查询关键词
                query_keywords = set(query.lower().split())

                statement = select(SystemSkill).where(
                    SystemSkill.status == "active"
                )
                skills = session.exec(statement).all()

                results = []
                for skill in skills:
                    # 计算关键词匹配分数
                    skill_keywords = set()

                    # 从触发词提取
                    for trigger in (skill.triggers or []):
                        skill_keywords.update(trigger.lower().split())

                    # 从标签提取
                    for tag in (skill.tags or []):
                        skill_keywords.update(tag.lower().split())

                    # Jaccard 相似度
                    if skill_keywords and query_keywords:
                        intersection = len(query_keywords & skill_keywords)
                        union = len(query_keywords | skill_keywords)
                        score = intersection / union if union > 0 else 0

                        if score > 0:
                            results.append((skill, score))

                results.sort(key=lambda x: x[1], reverse=True)
                log.debug(f"关键词检索返回 {len(results)} 个候选")
                return results[:limit]

            finally:
                if not self.session:
                    session.close()

        except Exception as e:
            log.error(f"关键词检索失败: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[Tuple[SystemSkill, float]],
        keyword_results: List[Tuple[SystemSkill, float]]
    ) -> List[SystemSkill]:
        """
        合并向量和关键词结果

        使用加权融合策略合并两种检索结果。

        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果

        Returns:
            List[SystemSkill]: 合并后的技能列表
        """
        # 分数归一化
        skill_scores: Dict[str, float] = {}

        # 向量结果加权
        for skill, score in vector_results:
            skill_scores[skill.skill_id] = skill_scores.get(skill.skill_id, 0) + \
                                           score * InjectorConfig.VECTOR_WEIGHT

        # 关键词结果加权
        for skill, score in keyword_results:
            skill_scores[skill.skill_id] = skill_scores.get(skill.skill_id, 0) + \
                                           score * InjectorConfig.KEYWORD_WEIGHT

        # 按分数排序并获取技能
        session = self.session or Session(engine)
        try:
            skills = []
            for skill_id, score in sorted(skill_scores.items(),
                                          key=lambda x: x[1],
                                          reverse=True):
                statement = select(SystemSkill).where(
                    SystemSkill.skill_id == skill_id
                )
                skill = session.exec(statement).first()
                if skill:
                    skills.append(skill)
            return skills
        finally:
            if not self.session:
                session.close()

    def _format_instruction(self, skill: SystemSkill) -> str:
        """
        格式化技能指令

        将技能信息格式化为可注入到 system prompt 的文本。

        Args:
            skill: 系统技能对象

        Returns:
            str: 格式化的指令文本
        """
        return f"""## 系统学习技能: {skill.name}

{skill.instructions}

*置信度: {skill.confidence_score:.2f} | 来源会话: {skill.source_sessions}*
"""

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本向量嵌入

        使用 OpenAI Embeddings API 生成文本向量。

        Args:
            text: 输入文本

        Returns:
            Optional[List[float]]: 向量嵌入，失败返回 None
        """
        try:
            from langchain_openai import OpenAIEmbeddings

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                log.debug("OPENAI_API_KEY 未配置，跳过向量生成")
                return None

            embeddings = OpenAIEmbeddings(
                model=InjectorConfig.EMBEDDING_MODEL,
                openai_api_key=api_key
            )

            result = embeddings.embed_query(text)
            log.debug(f"生成向量嵌入成功，维度: {len(result)}")
            return result

        except ImportError:
            log.warning("langchain_openai 未安装，跳过向量生成")
            return None
        except Exception as e:
            log.error(f"获取向量嵌入失败: {e}")
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """
        计算余弦相似度

        Args:
            a: 向量 a
            b: 向量 b

        Returns:
            float: 相似度分数 (0-1)
        """
        a_np = np.array(a)
        b_np = np.array(b)
        return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))

    def _record_injection(self, skill_id: str, query: str) -> None:
        """
        记录注入事件

        更新技能的注入计数，用于效果追踪。

        Args:
            skill_id: 技能ID
            query: 触发注入的查询
        """
        try:
            session = self.session or Session(engine)
            try:
                statement = select(SystemSkill).where(
                    SystemSkill.skill_id == skill_id
                )
                skill = session.exec(statement).first()
                if skill:
                    skill.injection_count += 1
                    session.add(skill)
                    session.commit()
            finally:
                if not self.session:
                    session.close()
        except Exception as e:
            log.error(f"记录注入失败: {e}")


# ============================================================================
# 全局单例管理
# ============================================================================

_injector: Optional[SkillInjector] = None


def get_skill_injector(session: Session = None) -> SkillInjector:
    """
    获取技能注入器单例

    Args:
        session: 数据库会话（可选）

    Returns:
        SkillInjector: 技能注入器实例

    使用示例:
        >>> injector = get_skill_injector()
        >>> instructions = injector.inject_for_query("差异分析")
    """
    global _injector
    if _injector is None:
        _injector = SkillInjector(session)
        log.info("技能注入器单例已初始化")
    return _injector


def reset_skill_injector() -> None:
    """
    重置技能注入器单例

    用于测试或需要重新初始化的场景。
    """
    global _injector
    _injector = None
    log.debug("技能注入器单例已重置")