"""
技能统一匹配器 - 整合规则/向量/LLM三阶段匹配

架构:
┌─────────────────────────────────────────────────────────────────────────┐
│                     技能推荐系统架构 (混合模式)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  用户查询 ──→ 规则引擎(快速筛选) ──→ 向量检索(语义匹配) ──→ LLM精排     │
│     │              (<50ms)           (~100ms)          (~1-2s)          │
│     │                │                    │                │            │
│     │                ▼                    ▼                ▼            │
│     │           候选技能集 ← ← ← ← ← ← ← ←┘                │            │
│     │                │                                      │            │
│     └───────────────→│← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘            │
│                      ▼                                                   │
│              推荐结果 + 参数建议                                          │
└─────────────────────────────────────────────────────────────────────────┘

流程决策逻辑:
| 场景          | 规则置信度 | 向量相似度 | 是否触发LLM |
|---------------|-----------|-----------|------------|
| 高置信度      | ≥ 0.85    | -         | 否         |
| 中置信度      | 0.5-0.85  | ≥ 0.75    | 否         |
| 低置信度      | < 0.5     | < 0.6     | 是         |
| 候选接近      | -         | 多个差距<0.1| 是        |

缓存策略:
- 推荐结果缓存: L1 TTL=5min, L2 TTL=10min
- 热门查询预计算: 后台定时任务预热
"""

import asyncio
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlmodel import Session

from app.core.logger import log
from app.core.database import engine
from app.models.domain import SkillMatchingFeedback, SkillAsset, SkillStatus
from app.services.skill_keywords_indexer import SkillKeywordsIndexer, get_keywords_indexer
from app.services.skill_matcher_config import (
    expand_synonyms, get_keyword_weight, is_negation_context,
    get_context_boost, get_domain_from_keyword, REVERSE_SYNONYM_MAP,
    is_code_generation_request  # 新增导入：编程请求检测
)
from app.services.skill_embedding_service import SkillEmbeddingService
from app.services.skill_vector_search import SkillVectorSearch
from app.services.llm_skill_matcher import LLMSkillMatcher
from app.core.skill_parser import get_combined_skills
from app.services.cache_service import get_cache_service


class IntentType:
    """意图类型"""
    EXPLICIT_SKILL = "explicit_skill"      # 明确提及技能
    IMPLICIT_SKILL = "implicit_skill"      # 隐式技能需求
    LIVE_CODING = "live_coding"            # 需要实时编码
    GENERAL_QUESTION = "general_question"  # 一般问题


class MatchMode:
    """
    匹配模式 - 支持分级响应

    快速模式 (fast): 仅规则+向量匹配，响应时间 <200ms
    精准模式 (precise): 完整三阶段匹配（含LLM精排），响应时间 ~1-2s
    自动模式 (auto): 系统根据置信度自动决定是否需要 LLM（默认）
    """
    FAST = "fast"        # 快速模式：规则+向量
    PRECISE = "precise"  # 精准模式：规则+向量+LLM
    AUTO = "auto"        # 自动模式：根据置信度决定


class SkillMatcher:
    """
    技能统一匹配器 - 整合规则/向量/LLM三阶段匹配

    三阶段匹配流程:
    1. 规则引擎: 快速筛选，基于关键词和同义词匹配
    2. 向量检索: 语义匹配，基于技能向量相似度
    3. LLM精排: 高精度匹配，理解复杂需求并推断参数

    决策逻辑:
    - 高置信度 (≥0.85): 直接返回规则结果
    - 中置信度 (0.5-0.85) + 高向量相似度 (≥0.75): 合并返回
    - 低置信度 + 低向量相似度: 触发 LLM 精排
    """

    # 置信度阈值
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5
    VECTOR_HIGH_THRESHOLD = 0.75
    VECTOR_LOW_THRESHOLD = 0.6

    # 候选技能接近阈值（差距小于此值触发 LLM）
    CLOSE_CANDIDATE_THRESHOLD = 0.1

    def __init__(self, user_id: int = 0, session: Session = None):
        """
        初始化匹配器

        Args:
            user_id: 用户 ID
            session: 数据库会话
        """
        self.user_id = user_id
        self.session = session

        # 子组件
        self._keywords_indexer: Optional[SkillKeywordsIndexer] = None
        self._vector_search: Optional[SkillVectorSearch] = None
        self._llm_matcher: Optional[LLMSkillMatcher] = None

        # 可用技能缓存
        self._available_skills: Optional[List[Dict[str, Any]]] = None

    def _get_keywords_indexer(self) -> SkillKeywordsIndexer:
        """
        获取关键词索引器

        注意：使用与 _get_available_skills 相同的 user_id，
        确保索引器和可用技能列表使用一致的技能集。
        """
        if not self._keywords_indexer:
            # 使用与 _get_available_skills 相同的 user_id 逻辑
            effective_user_id = max(1, self.user_id) if self.user_id <= 0 else self.user_id
            self._keywords_indexer = get_keywords_indexer(effective_user_id)
        return self._keywords_indexer

    def _get_vector_search(self) -> SkillVectorSearch:
        """获取向量检索服务"""
        if not self._vector_search:
            self._vector_search = SkillVectorSearch(self.session)
        return self._vector_search

    def _get_llm_matcher(self) -> LLMSkillMatcher:
        """获取 LLM 匹配器"""
        if not self._llm_matcher:
            self._llm_matcher = LLMSkillMatcher(self.session)
        return self._llm_matcher

    def _get_available_skills(self) -> List[Dict[str, Any]]:
        """
        获取可用技能列表

        修复：当 user_id=0（匿名/系统调用）时，也应该返回所有公开技能，
        而不是空列表，否则规则匹配会完全失败。
        """
        if self._available_skills is None:
            # 获取所有技能（不区分用户）
            # get_combined_skills 在 user_id<=0 时会返回所有公开技能
            self._available_skills = get_combined_skills(max(1, self.user_id))
        return self._available_skills

    async def match(
        self,
        user_query: str,
        context: Optional[Dict] = None,
        mode: str = MatchMode.AUTO
    ) -> Dict[str, Any]:
        """
        统一匹配接口

        整合三阶段匹配，返回最优推荐结果。

        Args:
            user_query: 用户查询
            context: 上下文信息（项目文件、历史会话等）
            mode: 匹配模式
                - "fast": 快速模式，仅规则+向量匹配，<200ms
                - "precise": 精准模式，完整三阶段匹配（含LLM），~1-2s
                - "auto": 自动模式，根据置信度决定是否使用LLM（默认）

        Returns:
            {
                "intent_type": "...",
                "matched_skills": [...],
                "confidence": 0.0-1.0,
                "parameters_suggestion": {...},
                "match_source": "rule | vector | llm | hybrid",
                "match_mode": "fast | precise | auto",
                "reason": "..."
            }
        """
        log.info(f"[SkillMatcher] 开始匹配: query='{user_query[:50]}...', user_id={self.user_id}, mode={mode}")

        # Phase 1: 规则匹配
        rule_result = await self._rule_match(user_query, context)

        # 高置信度直接返回
        if rule_result["confidence"] >= self.HIGH_CONFIDENCE_THRESHOLD:
            log.info(f"[SkillMatcher] 规则高置信度匹配: {rule_result['confidence']:.2f}")
            rule_result["match_mode"] = mode
            await self._record_feedback(user_query, rule_result, "rule")
            return rule_result

        # 中置信度（有匹配技能）直接返回规则结果，不需要向量匹配
        # 这样可以在 embedding API 不可用时仍然提供有意义的推荐
        if rule_result["confidence"] >= self.MEDIUM_CONFIDENCE_THRESHOLD and rule_result.get("matched_skills"):
            log.info(f"[SkillMatcher] 规则中置信度匹配（跳过向量检索）: {rule_result['confidence']:.2f}")
            rule_result["match_mode"] = mode
            await self._record_feedback(user_query, rule_result, "rule")
            return rule_result

        # Phase 2: 向量检索（仅在规则匹配置信度较低时尝试）
        vector_result = await self._vector_match(user_query, context)

        # 检查向量检索是否成功
        vector_available = vector_result.get("confidence", 0) > 0

        if vector_available:
            # 合并结果
            combined = self._merge_results(rule_result, vector_result)

            # 中置信度 + 高向量相似度
            if combined["confidence"] >= self.VECTOR_HIGH_THRESHOLD:
                log.info(f"[SkillMatcher] 合并匹配: confidence={combined['confidence']:.2f}")
                combined["match_mode"] = mode
                await self._record_feedback(user_query, combined, "hybrid")
                return combined
        else:
            # 向量检索不可用，使用规则结果
            combined = rule_result
            log.info("[SkillMatcher] 向量检索不可用，使用规则匹配结果")

        # ✨ 分级响应逻辑
        # 快速模式：直接返回，跳过 LLM
        if mode == MatchMode.FAST:
            log.info("[SkillMatcher] 快速模式：跳过 LLM 精排")
            combined["match_mode"] = mode
            await self._record_feedback(user_query, combined, "hybrid" if vector_available else "rule")
            return combined

        # 精准模式：始终执行 LLM 精排
        if mode == MatchMode.PRECISE:
            log.info("[SkillMatcher] 精准模式：强制执行 LLM 精排")
            llm_result = await self._llm_match(user_query, combined.get("matched_skills", []), context)
            if llm_result.get("confidence", 0) > 0.3:
                llm_result["match_mode"] = mode
                await self._record_feedback(user_query, llm_result, "llm")
                return llm_result
            else:
                # LLM 失败，返回合并结果
                log.info("[SkillMatcher] LLM 匹配失败，返回合并结果")
                combined["match_mode"] = mode
                await self._record_feedback(user_query, combined, "hybrid" if vector_available else "rule")
                return combined

        # 自动模式：根据置信度决定是否使用 LLM
        if self._should_use_llm(rule_result, vector_result, combined):
            log.info("[SkillMatcher] 自动模式：触发 LLM 精排")
            llm_result = await self._llm_match(user_query, combined.get("matched_skills", []), context)

            # 检查 LLM 是否成功
            if llm_result.get("confidence", 0) > 0.3:  # LLM 有有效结果
                llm_result["match_mode"] = mode
                await self._record_feedback(user_query, llm_result, "llm")
                return llm_result
            else:
                # LLM 失败，返回规则结果
                log.info("[SkillMatcher] LLM 匹配失败，返回规则结果")
                combined["match_mode"] = mode
                await self._record_feedback(user_query, combined, "hybrid" if vector_available else "rule")
                return combined

        # 返回合并结果
        combined["match_mode"] = mode

        # ✨ 应用个性化加成
        combined = await self._apply_personalization_boost(combined)

        await self._record_feedback(user_query, combined, "hybrid" if vector_available else "rule")
        return combined

    async def _rule_match(self, user_query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Phase 1: 规则匹配

        基于关键词和同义词进行快速匹配。

        Args:
            user_query: 用户查询
            context: 上下文信息

        Returns:
            匹配结果
        """
        query_lower = user_query.lower()
        keywords_indexer = self._get_keywords_indexer()

        # ✨ 优先级最高：检查是否为代码生成请求
        # 编程请求（用户要代码）应该走 live_coding 路径，而不是技能匹配
        if is_code_generation_request(user_query):
            log.info(f"[SkillMatcher] 检测到代码生成请求，跳过技能匹配: '{user_query[:50]}...'")
            return {
                "intent_type": IntentType.LIVE_CODING,
                "matched_skills": [],
                "confidence": 0.85,
                "parameters_suggestion": {},
                "match_source": "rule",
                "reason": "用户请求代码生成，需要自定义编码实现"
            }

        # 1. 检查显式触发词
        explicit_match = self._check_explicit_trigger(query_lower)
        if explicit_match:
            return {
                "intent_type": IntentType.EXPLICIT_SKILL,
                "matched_skills": explicit_match,
                "confidence": 0.95,
                "parameters_suggestion": {},
                "match_source": "rule",
                "reason": "用户明确提及技能名称或功能"
            }

        # 2. 关键词匹配
        keyword_matches = self._keyword_match(query_lower, keywords_indexer)

        if not keyword_matches["skills"]:
            return {
                "intent_type": IntentType.LIVE_CODING,
                "matched_skills": [],
                "confidence": 0.3,
                "parameters_suggestion": {},
                "match_source": "rule",
                "reason": "未找到匹配的技能"
            }

        # 3. 检查是否为一般问题
        if self._is_general_question(query_lower):
            return {
                "intent_type": IntentType.GENERAL_QUESTION,
                "matched_skills": keyword_matches["skills"],
                "confidence": max(0.3, keyword_matches["confidence"] - 0.2),
                "parameters_suggestion": {},
                "match_source": "rule",
                "matched_domains": keyword_matches.get("matched_domains", []),
                "reason": "检测到知识问答型需求"
            }

        return {
            "intent_type": IntentType.IMPLICIT_SKILL,
            "matched_skills": keyword_matches["skills"],
            "confidence": keyword_matches["confidence"],
            "parameters_suggestion": {},
            "match_source": "rule",
            "matched_domains": keyword_matches.get("matched_domains", []),
            "reason": self._build_match_reason(keyword_matches)
        }

    def _check_explicit_trigger(self, query_lower: str) -> List[Dict[str, Any]]:
        """
        检查显式触发词

        检查用户是否明确提及技能名称或功能。

        Args:
            query_lower: 小写的用户查询

        Returns:
            匹配的技能列表
        """
        skills = self._get_available_skills()
        matched = []

        for skill in skills:
            skill_id = skill.get("metadata", {}).get("skill_id", "")
            name = (skill.get("metadata", {}).get("name", "") or "").lower()
            description = (skill.get("metadata", {}).get("description", "") or "").lower()

            # 检查技能名称是否出现在查询中
            if name and name in query_lower:
                matched.append({
                    "skill_id": skill_id,
                    "name": skill.get("metadata", {}).get("name", ""),
                    "match_score": 0.95,
                    "match_reason": "用户明确提及技能名称"
                })
                continue

            # 检查 skill_id 是否出现在查询中
            if skill_id.lower() in query_lower:
                matched.append({
                    "skill_id": skill_id,
                    "name": skill.get("metadata", {}).get("name", ""),
                    "match_score": 0.95,
                    "match_reason": "用户明确提及技能 ID"
                })

        return matched

    def _keyword_match(self, query_lower: str, indexer: SkillKeywordsIndexer) -> Dict[str, Any]:
        """
        关键词匹配

        基于关键词索引进行匹配，支持同义词扩展。

        Args:
            query_lower: 小写的用户查询
            indexer: 关键词索引器

        Returns:
            匹配结果
        """
        keywords_index = indexer.get_all_keywords()
        if not keywords_index:
            indexer.build_keywords_index()
            keywords_index = indexer.get_all_keywords()

        # 调试日志：显示关键词索引内容
        log.debug(f"[SkillMatcher] 关键词索引包含 {len(keywords_index)} 个技能")
        for sid, kw in list(keywords_index.items())[:3]:  # 只显示前3个
            log.debug(f"[SkillMatcher] 技能 {sid}: primary={kw.primary_keywords[:5]}, secondary={kw.secondary_keywords[:5]}")

        matched_domains = []
        matched_skills = {}
        total_weight = 0.0

        # 遍历所有技能的关键词
        for skill_id, keywords in keywords_index.items():
            skill_weight = 0.0
            skill_reasons = []

            # 检查主要关键词
            for kw in keywords.primary_keywords:
                kw_lower = kw.lower()
                if kw_lower in query_lower:
                    # 检查否定上下文
                    pos = query_lower.find(kw_lower)
                    if not is_negation_context(query_lower, pos):
                        weight = get_keyword_weight(kw)
                        skill_weight += weight * 0.9  # 主要关键词权重
                        skill_reasons.append(f"关键词匹配: {kw}")

                        # 记录领域
                        domain = get_domain_from_keyword(kw)
                        if domain != "general" and domain not in matched_domains:
                            matched_domains.append(domain)

            # 检查次要关键词
            for kw in keywords.secondary_keywords:
                kw_lower = kw.lower()
                if kw_lower in query_lower:
                    pos = query_lower.find(kw_lower)
                    if not is_negation_context(query_lower, pos):
                        weight = get_keyword_weight(kw)
                        skill_weight += weight * 0.6  # 次要关键词权重
                        skill_reasons.append(f"相关关键词: {kw}")

            # 检查上下文关键词（增强置信度）
            context_boost = 0.0
            for kw in keywords.context_keywords:
                kw_lower = kw.lower()
                if kw_lower in query_lower:
                    context_boost += 0.05

            if skill_weight > 0:
                # 添加上下文增强
                skill_weight = min(1.0, skill_weight + context_boost)

                # 获取技能名称
                skill_info = self._get_skill_by_id(skill_id)
                skill_name = skill_info.get("metadata", {}).get("name", "") if skill_info else skill_id

                matched_skills[skill_id] = {
                    "skill_id": skill_id,
                    "name": skill_name,
                    "match_score": skill_weight,
                    "match_reason": " | ".join(skill_reasons[:2])
                }

                total_weight += skill_weight

        # 按分数排序
        sorted_skills = sorted(
            matched_skills.values(),
            key=lambda x: x["match_score"],
            reverse=True
        )

        # 计算整体置信度
        # 使用最高匹配分数作为基础，确保高匹配分数对应高置信度
        # 同时考虑匹配的技能数量，提供额外的置信度加成
        if sorted_skills:
            top_score = sorted_skills[0]["match_score"]
            # 基础置信度 = 最高匹配分数 * 0.8
            base_confidence = top_score * 0.8
            # 如果有多个技能匹配，增加置信度（最多 +0.1）
            multi_skill_bonus = min(0.1, len(sorted_skills) * 0.02)
            confidence = min(0.95, base_confidence + multi_skill_bonus)
        else:
            confidence = 0.0

        # 调试日志：显示匹配结果
        if sorted_skills:
            log.info(f"[SkillMatcher] 关键词匹配结果: {len(sorted_skills)} 个技能, 置信度={confidence:.2f}")
            for s in sorted_skills[:3]:
                log.info(f"[SkillMatcher] - {s['skill_id']}: score={s['match_score']:.2f}, reason={s['match_reason']}")
        else:
            log.info(f"[SkillMatcher] 关键词匹配无结果，查询: {query_lower[:50]}")

        return {
            "skills": sorted_skills[:5],  # 最多返回 5 个
            "confidence": confidence,
            "matched_domains": matched_domains
        }

    def _get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取技能信息"""
        skills = self._get_available_skills()
        for skill in skills:
            if skill.get("metadata", {}).get("skill_id") == skill_id:
                return skill
        return None

    def _is_general_question(self, query_lower: str) -> bool:
        """判断是否为一般问题"""
        question_patterns = [
            "什么是", "怎么理解", "如何理解", "解释一下", "告诉我",
            "什么是", "有什么区别", "有什么不同", "为什么",
            "how to", "what is", "explain", "tell me"
        ]

        for pattern in question_patterns:
            if pattern in query_lower:
                # 排除带有分析需求的问句
                analysis_patterns = ["分析", "处理", "运行", "执行"]
                if not any(ap in query_lower for ap in analysis_patterns):
                    return True

        return False

    def _build_match_reason(self, match_result: Dict[str, Any]) -> str:
        """构建匹配原因说明"""
        domains = match_result.get("matched_domains", [])
        confidence = match_result.get("confidence", 0)

        if not domains:
            return "检测到相关需求"

        domain_names = {
            "single_cell": "单细胞分析",
            "quality_control": "质量控制",
            "rna_seq": "转录组分析",
            "differential_expression": "差异表达",
            "pipeline": "流程自动化",
            "visualization": "数据可视化",
            "chip_seq": "ChIP-seq分析",
            "atac_seq": "ATAC-seq分析",
            "methylation": "甲基化分析",
            "variant_calling": "变异检测",
            "spatial": "空间转录组"
        }

        domain_labels = [domain_names.get(d, d) for d in domains[:3]]
        reason = f"检测到{', '.join(domain_labels)}需求"

        if confidence > 0.7:
            reason += "（高置信度）"
        elif confidence > 0.5:
            reason += "（中等置信度）"

        return reason

    async def _vector_match(self, user_query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Phase 2: 向量检索

        基于语义相似度进行匹配。

        Args:
            user_query: 用户查询
            context: 上下文信息

        Returns:
            匹配结果
        """
        try:
            vector_search = self._get_vector_search()
            results = await vector_search.search_by_text(
                query_text=user_query,
                limit=5,
                threshold=self.VECTOR_LOW_THRESHOLD,
                user_id=self.user_id
            )

            if not results:
                return {
                    "intent_type": IntentType.LIVE_CODING,
                    "matched_skills": [],
                    "confidence": 0.0,
                    "parameters_suggestion": {},
                    "match_source": "vector",
                    "reason": "向量搜索未找到匹配"
                }

            # 计算整体置信度（基于最高相似度）
            top_similarity = results[0].get("similarity", 0) if results else 0
            confidence = top_similarity

            return {
                "intent_type": IntentType.IMPLICIT_SKILL,
                "matched_skills": results,
                "confidence": confidence,
                "parameters_suggestion": {},
                "match_source": "vector",
                "reason": f"语义相似度匹配 (相似度: {top_similarity:.2f})"
            }

        except Exception as e:
            log.error(f"[SkillMatcher] 向量匹配失败: {e}")
            return {
                "intent_type": IntentType.LIVE_CODING,
                "matched_skills": [],
                "confidence": 0.0,
                "parameters_suggestion": {},
                "match_source": "vector",
                "reason": f"向量匹配失败: {e}"
            }

    def _merge_results(self, rule_result: Dict, vector_result: Dict) -> Dict[str, Any]:
        """
        合并规则和向量匹配结果

        Args:
            rule_result: 规则匹配结果
            vector_result: 向量匹配结果

        Returns:
            合并后的结果
        """
        # 收集所有匹配的技能
        skill_scores = {}

        # 处理规则匹配
        for skill in rule_result.get("matched_skills", []):
            skill_id = skill.get("skill_id")
            score = skill.get("match_score", 0)
            skill_scores[skill_id] = {
                "skill_id": skill_id,
                "name": skill.get("name", ""),
                "rule_score": score,
                "vector_score": 0,
                "match_reason": skill.get("match_reason", "")
            }

        # 处理向量匹配
        for skill in vector_result.get("matched_skills", []):
            skill_id = skill.get("skill_id")
            score = skill.get("similarity", 0)
            if skill_id in skill_scores:
                skill_scores[skill_id]["vector_score"] = score
            else:
                skill_scores[skill_id] = {
                    "skill_id": skill_id,
                    "name": skill.get("name", ""),
                    "rule_score": 0,
                    "vector_score": score,
                    "match_reason": skill.get("match_reason", "")
                }

        # 计算综合分数 (规则权重 0.6, 向量权重 0.4)
        for skill_id, skill_data in skill_scores.items():
            combined_score = skill_data["rule_score"] * 0.6 + skill_data["vector_score"] * 0.4
            skill_data["match_score"] = combined_score

        # 按综合分数排序
        sorted_skills = sorted(
            skill_scores.values(),
            key=lambda x: x["match_score"],
            reverse=True
        )

        # 计算整体置信度
        rule_conf = rule_result.get("confidence", 0)
        vector_conf = vector_result.get("confidence", 0)
        combined_conf = rule_conf * 0.6 + vector_conf * 0.4

        # 确定意图类型
        intent_type = rule_result.get("intent_type", IntentType.LIVE_CODING)
        if intent_type == IntentType.LIVE_CODING and vector_result.get("matched_skills"):
            intent_type = IntentType.IMPLICIT_SKILL

        return {
            "intent_type": intent_type,
            "matched_skills": sorted_skills[:5],
            "confidence": combined_conf,
            "parameters_suggestion": {},
            "match_source": "hybrid",
            "matched_domains": rule_result.get("matched_domains", []),
            "reason": f"规则+向量混合匹配 (规则: {rule_conf:.2f}, 向量: {vector_conf:.2f})"
        }

    def _should_use_llm(self, rule_result: Dict, vector_result: Dict, combined: Dict) -> bool:
        """
        判断是否需要使用 LLM 精排

        Args:
            rule_result: 规则匹配结果
            vector_result: 向量匹配结果
            combined: 合并结果

        Returns:
            是否需要 LLM
        """
        # 低置信度触发 LLM
        if combined["confidence"] < self.MEDIUM_CONFIDENCE_THRESHOLD:
            return True

        # 向量相似度过低触发 LLM
        if vector_result.get("confidence", 0) < self.VECTOR_LOW_THRESHOLD:
            return True

        # 检查候选技能是否接近（难以区分）
        skills = combined.get("matched_skills", [])
        if len(skills) >= 2:
            top_score = skills[0].get("match_score", 0)
            second_score = skills[1].get("match_score", 0)
            if top_score - second_score < self.CLOSE_CANDIDATE_THRESHOLD:
                return True

        return False

    async def _llm_match(self, user_query: str, candidates: List[Dict], context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Phase 3: LLM 精排

        使用 LLM 进行高精度匹配。

        Args:
            user_query: 用户查询
            candidates: 候选技能列表
            context: 上下文信息

        Returns:
            匹配结果
        """
        try:
            llm_matcher = self._get_llm_matcher()

            # 获取候选技能详细信息
            candidate_skills = []
            for skill in candidates[:10]:  # 最多 10 个候选
                skill_info = self._get_skill_by_id(skill.get("skill_id"))
                if skill_info:
                    candidate_skills.append(skill_info.get("metadata", {}))

            # 如果没有候选技能，使用所有可用技能
            if not candidate_skills:
                all_skills = self._get_available_skills()
                candidate_skills = [s.get("metadata", {}) for s in all_skills[:10]]

            # 调用 LLM 匹配
            result = await llm_matcher.match(user_query, candidate_skills, context)

            # 确保结果格式正确
            if "matched_skills" in result and result["matched_skills"]:
                # 补充技能名称
                for skill in result["matched_skills"]:
                    if "name" not in skill:
                        skill_info = self._get_skill_by_id(skill.get("skill_id"))
                        if skill_info:
                            skill["name"] = skill_info.get("metadata", {}).get("name", "")

            return result

        except Exception as e:
            log.error(f"[SkillMatcher] LLM 匹配失败: {e}")
            return {
                "intent_type": IntentType.LIVE_CODING,
                "matched_skills": [],
                "confidence": 0.3,
                "parameters_suggestion": {},
                "match_source": "llm",
                "reason": f"LLM 匹配失败: {e}"
            }

    async def _apply_personalization_boost(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用个性化加成

        根据用户偏好调整技能推荐得分：
        1. 常用技能获得加成
        2. 偏好分类获得加成
        3. 高成功率技能获得加成

        Args:
            result: 匹配结果

        Returns:
            调整后的匹配结果
        """
        # 跳过无效用户 ID
        if not self.user_id or self.user_id <= 0:
            return result

        matched_skills = result.get("matched_skills", [])
        if not matched_skills:
            return result

        try:
            from app.services.preference_engine import PreferenceEngine
            from sqlmodel import Session
            from app.core.database import engine

            with Session(engine) as session:
                engine = PreferenceEngine(session)

                for skill in matched_skills:
                    skill_id = skill.get("skill_id")
                    category = skill.get("category")

                    # 获取个性化加成
                    boost = engine.get_skill_recommendation_boost(
                        user_id=self.user_id,
                        skill_id=skill_id,
                        skill_category=category,
                    )

                    # 应用加成到得分
                    original_score = skill.get("score", 0.5)
                    boosted_score = original_score * boost
                    skill["score"] = min(1.0, boosted_score)  # 限制最大 1.0
                    skill["personalization_boost"] = boost

                    log.debug(
                        f"[SkillMatcher] 个性化加成: skill_id={skill_id}, "
                        f"original={original_score:.2f}, boost={boost:.2f}, final={skill['score']:.2f}"
                    )

                # 按调整后的得分重新排序
                matched_skills.sort(key=lambda x: x.get("score", 0), reverse=True)
                result["matched_skills"] = matched_skills
                result["personalization_applied"] = True

        except Exception as e:
            log.warning(f"[SkillMatcher] 应用个性化加成失败: {e}")

        return result

    async def _record_feedback(self, query: str, result: Dict, match_source: str) -> None:
        """
        记录匹配反馈

        整合两种记录方式：
        1. SkillMatchingFeedback - 原有反馈记录
        2. BehaviorTracker - 新的行为埋点

        Args:
            query: 用户查询
            result: 匹配结果
            match_source: 匹配来源
        """
        # 关键修复：跳过无效用户 ID，避免外键约束错误
        # user_id 为 0 或负数时，表示匿名用户或系统调用，不记录反馈
        if not self.user_id or self.user_id <= 0:
            log.debug(f"[SkillMatcher] 跳过匿名用户反馈记录: user_id={self.user_id}")
            return

        try:
            with Session(engine) as session:
                # 1. 原有反馈记录
                feedback = SkillMatchingFeedback(
                    user_id=self.user_id,
                    session_id="unknown",  # 需要从上下文获取
                    query=query,
                    match_source=match_source,
                    recommended_skill_ids=[s.get("skill_id") for s in result.get("matched_skills", [])],
                    confidence=result.get("confidence", 0),
                    accepted=False,
                    match_details={
                        "intent_type": result.get("intent_type"),
                        "reason": result.get("reason")
                    }
                )
                session.add(feedback)
                session.commit()
                log.debug(f"[SkillMatcher] 反馈记录成功: user_id={self.user_id}, query='{query[:30]}...'")

                # 2. 新的行为埋点 - 记录 QUERY 和 RECOMMEND 事件
                try:
                    from app.services.behavior_tracker import (
                        BehaviorTracker, BehaviorType, BehaviorEvent
                    )

                    tracker = BehaviorTracker(session)

                    # 记录查询事件
                    tracker.track(BehaviorEvent(
                        user_id=self.user_id,
                        session_id="unknown",
                        event_type=BehaviorType.QUERY,
                        query=query,
                        metadata={"match_source": match_source, "confidence": result.get("confidence", 0)}
                    ))

                    # 为每个推荐技能记录 RECOMMEND 事件
                    matched_skills = result.get("matched_skills", [])
                    for skill in matched_skills[:3]:  # 只记录前3个
                        tracker.track(BehaviorEvent(
                            user_id=self.user_id,
                            session_id="unknown",
                            event_type=BehaviorType.RECOMMEND,
                            skill_id=skill.get("skill_id"),
                            skill_name=skill.get("name"),
                            query=query,
                            match_source=match_source,
                            confidence=skill.get("score", result.get("confidence", 0))
                        ))

                    log.debug(f"[SkillMatcher] 行为埋点成功: query + {len(matched_skills[:3])} recommends")

                except Exception as e:
                    log.warning(f"[SkillMatcher] 行为埋点失败: {e}")

        except Exception as e:
            log.warning(f"[SkillMatcher] 记录反馈失败: {e}")


# ==========================================
# 辅助函数
# ==========================================

def _generate_cache_key(user_query: str, user_id: int, mode: str = "auto") -> str:
    """
    生成推荐结果缓存键

    Args:
        user_query: 用户查询
        user_id: 用户 ID
        mode: 匹配模式（不同模式使用不同缓存）

    Returns:
        缓存键
    """
    # 使用查询内容和用户 ID 生成唯一键
    # 不同模式使用不同的缓存键，避免快速模式和精准模式结果混淆
    query_hash = hashlib.md5(user_query.lower().encode()).hexdigest()[:8]
    return f"recommend:result:{mode}:{user_id}:{query_hash}"


async def match_skills(
    user_query: str,
    user_id: int = 0,
    context: Optional[Dict] = None,
    mode: str = "auto"
) -> Dict[str, Any]:
    """
    技能匹配（便捷函数）

    支持缓存，热门查询优先从缓存返回。

    Args:
        user_query: 用户查询
        user_id: 用户 ID
        context: 上下文信息
        mode: 匹配模式
            - "fast": 快速模式，仅规则+向量匹配，<200ms
            - "precise": 精准模式，完整三阶段匹配（含LLM），~1-2s
            - "auto": 自动模式，根据置信度决定是否使用LLM（默认）

    Returns:
        匹配结果
    """
    # 尝试从缓存获取
    cache = get_cache_service()
    cache_key = _generate_cache_key(user_query, user_id, mode)
    cached = cache.get(cache_key)

    if cached is not None:
        log.debug(f"[SkillMatcher] 推荐缓存命中: {cache_key}")
        return cached

    # 缓存未命中，执行匹配
    matcher = SkillMatcher(user_id)
    result = await matcher.match(user_query, context, mode=mode)

    # 存入缓存（仅缓存有意义的推荐结果）
    if result.get("matched_skills"):
        cache.set(cache_key, result, cache_type="recommend:result")
        log.debug(f"[SkillMatcher] 推荐结果已缓存: {cache_key}")

    return result


def match_skills_sync(
    user_query: str,
    user_id: int = 0,
    context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    同步技能匹配（便捷函数）

    注意：此函数会阻塞，建议使用 match_skills 异步版本

    Args:
        user_query: 用户查询
        user_id: 用户 ID
        context: 上下文信息

    Returns:
        匹配结果
    """
    return asyncio.run(match_skills(user_query, user_id, context))


log.info("✅ 技能统一匹配器已加载")