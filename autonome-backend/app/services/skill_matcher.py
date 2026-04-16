"""
技能统一匹配器 - 基于关键词/规则的技能匹配

架构:
┌──────────────────────────────────────────────────┐
│          技能推荐系统架构 (关键词模式)              │
├──────────────────────────────────────────────────┤
│  用户查询 ──→ 规则引擎(关键词+同义词快速匹配)      │
│     │              (<50ms)                        │
│     │                │                            │
│     │                ▼                            │
│     │          候选技能集                          │
│     │                │                            │
│     └───────────────→│                            │
│                      ▼                            │
│              推荐结果 + 参数建议                    │
└──────────────────────────────────────────────────┘

匹配流程:
| 场景          | 规则置信度 | 说明                       |
|---------------|-----------|----------------------------|
| 高置信度      | >= 0.85   | 直接返回规则匹配结果        |
| 中置信度      | 0.3-0.85  | 返回规则结果+操作菜单       |
| 低置信度      | < 0.3     | 返回 Live Coding 兜底       |

缓存策略:
- 推荐结果缓存: L1 TTL=5min, L2 TTL=10min
- 热门查询预计算: 后台定时任务预热
"""

import asyncio
import hashlib
from typing import Dict, List, Any, Optional
from sqlmodel import Session

from app.core.logger import log
from app.core.database import engine
from app.models.domain import SkillMatchingFeedback
from app.services.skill_keywords_indexer import SkillKeywordsIndexer, get_keywords_indexer
from app.services.skill_matcher_config import (
    get_keyword_weight, is_negation_context,
    get_domain_from_keyword,
    is_code_generation_request,  # 编程请求检测
    get_compatible_categories, FILE_TYPE_COMPATIBILITY  # 文件类型兼容性
)

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

    快速模式 (fast): 仅规则匹配，响应时间 <50ms
    精准模式 (precise): 同快速模式（保留接口兼容性）
    自动模式 (auto): 同快速模式（保留接口兼容性，默认）
    """
    FAST = "fast"        # 快速模式：规则匹配
    PRECISE = "precise"  # 精准模式：规则匹配（接口兼容）
    AUTO = "auto"        # 自动模式：规则匹配（接口兼容）


class SkillMatcher:
    """
    技能统一匹配器 - 基于关键词/规则的技能匹配

    匹配流程:
    1. 规则引擎: 基于关键词和同义词进行快速匹配

    决策逻辑:
    - 高置信度 (>=0.85): 直接返回规则结果
    - 中置信度 (0.3-0.85): 返回规则结果+操作菜单
    - 低置信度 (<0.3): 返回 Live Coding 兜底
    """

    # 置信度阈值
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5

    # V2 架构阈值：数据感知路由
    # 当置信度 >= V2_HIGH_CONFIDENCE 时，直接返回 json_strategy
    # 当置信度 < V2_HIGH_CONFIDENCE 时，返回 json_action_menu
    V2_HIGH_CONFIDENCE = 0.90

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

    def _extract_file_extensions(self, context: Optional[Dict] = None) -> List[str]:
        """
        从上下文提取文件扩展名

        V2 数据感知 RAG：支持从 physical_file_info 或 file_paths 中提取文件类型。

        Args:
            context: 上下文信息，可能包含 physical_file_info 或 file_paths

        Returns:
            文件扩展名列表，如 [".h5ad", ".csv"]
        """
        if not context:
            return []

        extensions = set()

        # 方式1：从 physical_file_info 字符串中提取
        physical_info = context.get("physical_file_info", "")
        if physical_info and isinstance(physical_info, str):
            import re
            # 匹配常见文件扩展名
            ext_pattern = r'\.([a-zA-Z0-9]+)'
            found_exts = re.findall(ext_pattern, physical_info)
            for ext in found_exts:
                full_ext = f".{ext.lower()}"
                if full_ext in FILE_TYPE_COMPATIBILITY or ext.lower() in ["h5ad", "loom", "fastq"]:
                    # 处理特殊情况
                    if ext.lower() in ["h5ad", "loom"]:
                        extensions.add(f".{ext.lower()}")
                    elif ext.lower() == "gz" and len(found_exts) > 0:
                        # 可能是 .fastq.gz
                        idx = found_exts.index(ext)
                        if idx > 0 and found_exts[idx - 1].lower() in ["fastq", "fq"]:
                            extensions.add(f".{found_exts[idx - 1].lower()}.gz")
                        extensions.add(".gz")
                    else:
                        extensions.add(f".{ext.lower()}")

        # 方式2：从 file_paths 列表中提取
        file_paths = context.get("file_paths", [])
        for path in file_paths:
            if isinstance(path, str):
                import re
                ext_pattern = r'\.([a-zA-Z0-9.]+)(?:\.gz)?$'
                match = re.search(ext_pattern, path.lower())
                if match:
                    extensions.add(f".{match.group(1)}")

        return list(extensions)

    def _get_file_type_boost(self, skill_categories: List[str], file_extensions: List[str]) -> float:
        """
        计算文件类型兼容性好坏

        Args:
            skill_categories: 技能所属类别列表
            file_extensions: 用户文件扩展名列表

        Returns:
            加成分数 (0.0 - 0.3)
        """
        if not skill_categories or not file_extensions:
            return 0.0

        boost = 0.0
        for ext in file_extensions:
            compatible_cats = get_compatible_categories(ext)
            if compatible_cats:
                # 检查技能类别是否与文件类型兼容
                for skill_cat in skill_categories:
                    if skill_cat in compatible_cats:
                        boost += 0.1
                        break

        return min(boost, 0.3)  # 最多加成 0.3

    async def match(
        self,
        user_query: str,
        context: Optional[Dict] = None,
        mode: str = MatchMode.AUTO,
        message_category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        统一匹配接口

        基于关键词/规则进行技能匹配，返回最优推荐结果。

        Args:
            user_query: 用户查询
            context: 上下文信息（项目文件、历史会话等）
            mode: 匹配模式（保留接口兼容性，所有模式均使用关键词匹配）
            message_category: V3 第一性原理消息类别
                - "DETERMINED_ACTION": 使用更低阈值(0.3)，因为意图明确
                - 其他: 使用默认阈值

        Returns:
            {
                "intent_type": "...",
                "matched_skills": [...],
                "confidence": 0.0-1.0,
                "parameters_suggestion": {...},
                "match_source": "rule",
                "match_mode": "fast | precise | auto | determined",
                "reason": "..."
            }
        """
        # V3: DETERMINED_ACTION 模式使用更低阈值
        determined_mode = message_category == "DETERMINED_ACTION"
        if determined_mode:
            effective_high_threshold = 0.5   # 默认 0.85 -> 0.5
            effective_medium_threshold = 0.3  # 默认 0.5 -> 0.3
            log.info(f"[SkillMatcher] DETERMINED_ACTION 模式: 降低阈值 high={effective_high_threshold}, medium={effective_medium_threshold}")
        else:
            effective_high_threshold = self.HIGH_CONFIDENCE_THRESHOLD
            effective_medium_threshold = self.MEDIUM_CONFIDENCE_THRESHOLD

        log.info(f"[SkillMatcher] 开始匹配: query='{user_query[:50]}...', user_id={self.user_id}, mode={mode}, category={message_category}")

        # 关键词/规则匹配
        rule_result = await self._rule_match(user_query, context)

        # 高置信度直接返回
        if rule_result["confidence"] >= effective_high_threshold:
            log.info(f"[SkillMatcher] 规则高置信度匹配: {rule_result['confidence']:.2f}")
            rule_result["match_mode"] = "determined" if determined_mode else mode
            rule_result["routing_decision"] = "direct_strategy"
            rule_result["reason"] = rule_result.get("reason", "") + f" [高置信度 {rule_result['confidence']:.2f}]"
            await self._record_feedback(user_query, rule_result, "rule")
            return rule_result

        # 中置信度（有匹配技能）直接返回规则结果
        if rule_result["confidence"] >= effective_medium_threshold and rule_result.get("matched_skills"):
            log.info(f"[SkillMatcher] 规则中置信度匹配: {rule_result['confidence']:.2f}")
            rule_result["match_mode"] = "determined" if determined_mode else mode
            # V2 路由决策
            if rule_result["confidence"] >= self.V2_HIGH_CONFIDENCE:
                rule_result["routing_decision"] = "direct_strategy"
            else:
                rule_result["routing_decision"] = "action_menu"
                matched = rule_result.get("matched_skills", [])
                rule_result["action_menu_options"] = matched[:2] if len(matched) >= 2 else matched
                if not any(opt.get("skill_id") == "live_coding" for opt in rule_result.get("action_menu_options", [])):
                    rule_result["action_menu_options"].append({
                        "skill_id": "live_coding",
                        "name": "⚡ 实时编写代码 (Live Coding)",
                        "match_score": 0.5,
                        "match_reason": "兜底选项"
                    })
            await self._record_feedback(user_query, rule_result, "rule")
            return rule_result

        # 低置信度或无匹配结果：应用个性化加成后返回
        rule_result["match_mode"] = mode

        # 应用个性化加成
        rule_result = await self._apply_personalization_boost(rule_result)

        # V2 架构：置信度路由决策
        confidence = rule_result.get("confidence", 0)
        if confidence >= self.V2_HIGH_CONFIDENCE:
            rule_result["routing_decision"] = "direct_strategy"
            rule_result["reason"] = rule_result.get("reason", "") + f" [V2高置信度 {confidence:.2f} >= {self.V2_HIGH_CONFIDENCE}]"
            log.info(f"[SkillMatcher] V2路由: 直接策略卡片 (confidence={confidence:.2f})")
        else:
            rule_result["routing_decision"] = "action_menu"
            rule_result["reason"] = rule_result.get("reason", "") + f" [V2中低置信度 {confidence:.2f} < {self.V2_HIGH_CONFIDENCE}]"
            log.info(f"[SkillMatcher] V2路由: 操作菜单 (confidence={confidence:.2f})")

            # 添加备选技能列表（Top 2 + Live Coding 兜底）
            matched = rule_result.get("matched_skills", [])
            if len(matched) >= 2:
                rule_result["action_menu_options"] = matched[:2]
            elif len(matched) == 1:
                rule_result["action_menu_options"] = matched[:1]
            else:
                rule_result["action_menu_options"] = []
            rule_result["action_menu_options"].append({
                "skill_id": "live_coding",
                "name": "⚡ 实时编写代码 (Live Coding)",
                "match_score": 0.5,
                "match_reason": "兜底选项：根据需求实时编写代码"
            })

        await self._record_feedback(user_query, rule_result, "rule")
        return rule_result

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

        # ✨ V2 数据感知加成：根据文件类型提升置信度
        file_extensions = self._extract_file_extensions(context)
        base_confidence = keyword_matches["confidence"]

        if file_extensions:
            # 从匹配的技能中提取类别
            skill_cats = []
            for skill in keyword_matches["skills"]:
                skill_id = skill.get("skill_id", "")
                # 简单根据 skill_id 推断类别（后续可优化为从 SKILL.md 读取）
                if any(kw in skill_id.lower() for kw in ["fastqc", "multiqc", "quality"]):
                    skill_cats.append("quality_control")
                elif any(kw in skill_id.lower() for kw in ["single", "cell", "sc", "seurat", "scanpy"]):
                    skill_cats.append("single_cell")
                elif any(kw in skill_id.lower() for kw in ["rna", "count", "express"]):
                    skill_cats.append("rna_seq")
                elif any(kw in skill_id.lower() for kw in ["diff", "deseq", "deg"]):
                    skill_cats.append("differential_expression")
                elif any(kw in skill_id.lower() for kw in ["cluster", "annot", "celltype"]):
                    skill_cats.append("cell_clustering")

            file_type_boost = self._get_file_type_boost(skill_cats, file_extensions)
            base_confidence = min(base_confidence + file_type_boost, 1.0)

            if file_type_boost > 0:
                log.info(f"[SkillMatcher] 文件类型加成: extensions={file_extensions}, boost={file_type_boost:.2f}, final_confidence={base_confidence:.2f}")

        return {
            "intent_type": IntentType.IMPLICIT_SKILL,
            "matched_skills": keyword_matches["skills"],
            "confidence": base_confidence,
            "parameters_suggestion": {},
            "match_source": "rule",
            "matched_domains": keyword_matches.get("matched_domains", []),
            "reason": self._build_match_reason(keyword_matches),
            "file_extensions": file_extensions if file_extensions else None  # 用于调试
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

        # ✨ 查看意图降权检测：当用户只是想"查看/浏览"文件而非"分析/处理"时，
        # 降低技能匹配置信度，避免文件名中的领域词（deg、fpkm等）误触发分析技能
        VIEW_INTENT_VERBS = ["查看", "看下", "看一下", "看看", "浏览", "打开", "显示", "列出", "瞅", "瞧"]
        ANALYSIS_INTENT_VERBS = ["分析", "处理", "运行", "执行", "计算", "统计", "聚类", "差异分析", "画图", "可视化"]
        has_view_intent = any(verb in query_lower for verb in VIEW_INTENT_VERBS)
        has_analysis_intent = any(verb in query_lower for verb in ANALYSIS_INTENT_VERBS)
        # 仅当有查看意图且无分析意图时，应用降权因子
        view_intent_penalty = 0.3 if (has_view_intent and not has_analysis_intent) else 1.0
        if view_intent_penalty < 1.0:
            log.info(f"[SkillMatcher] 检测到查看意图（无分析意图），应用降权因子 {view_intent_penalty}")

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

                # ✨ 应用查看意图降权
                skill_weight *= view_intent_penalty

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

    async def _apply_personalization_boost(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用个性化加成（已移除 PreferenceEngine）

        保留接口兼容性，直接返回原始结果

        Args:
            result: 匹配结果

        Returns:
            调整后的匹配结果
        """
        # PreferenceEngine 已移除，跳过个性化加成
        return result

    async def _record_feedback(self, query: str, result: Dict, match_source: str) -> None:
        """
        记录匹配反馈

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
                # 反馈记录（behavior_tracker 已移除，仅保留 SkillMatchingFeedback）
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

    基于关键词/规则进行技能匹配，支持缓存。

    Args:
        user_query: 用户查询
        user_id: 用户 ID
        context: 上下文信息
        mode: 匹配模式（保留接口兼容性，所有模式均使用关键词匹配）

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