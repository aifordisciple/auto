"""
知识提炼引擎服务

从用户行为和技能执行中提炼生信领域知识：
1. 从成功执行记录提取参数规则
2. 从失败执行记录提取错误模式
3. 从用户反馈提取同义词和概念
4. 从技能元数据提取专家知识
5. 计算知识置信度并整合

设计原则：
- 多来源融合：技能专家知识 + 用户反馈 + 执行记录 + 系统推导
- 置信度动态计算：基于使用次数、成功率、验证状态
- 知识去重与整合：自动合并重复概念
- 领域适配：专注于生信分析领域知识
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from sqlmodel import Session, select, func

from app.core.logger import log
from app.models.domain_knowledge import (
    KnowledgeType,
    KnowledgeSource,
    DomainKnowledgeEntry,
    KnowledgeRelation,
    KnowledgeQueryResult,
    DomainKnowledgeRecord,
)


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 知识提炼配置
# ==========================================

class KnowledgeEngineConfig:
    """知识提炼引擎配置"""

    # 置信度阈值
    MIN_CONFIDENCE_THRESHOLD: float = 0.3  # 最低入库置信度
    HIGH_CONFIDENCE_THRESHOLD: float = 0.7  # 高置信度阈值
    VERIFIED_BOOST: float = 0.2  # 验证后置信度提升

    # 使用次数阈值
    MIN_USAGE_FOR_RULE: int = 3  # 参数规则最低使用次数
    MIN_USAGE_FOR_SYNONYM: int = 10  # 同义词最低出现次数
    FREQUENCY_CONFIDENCE_CAP: float = 100.0  # 使用频度置信度上限

    # 同义词提取
    SYNONYM_INDICATORS: List[str] = ["就是", "等于", "指的是", "也就是", "简称", "又称"]
    MIN_CO_OCCURRENCE: int = 5  # 同义词最低共现次数

    # 错误模式
    ERROR_PATTERN_MIN_COUNT: int = 3  # 错误模式最低出现次数

    # 生信领域关键词（用于概念识别）
    BIOINFORMATICS_KEYWORDS: List[str] = [
        "RNA-seq", "RNA-seq", "转录组", "差异表达", "DEG", "质控", "质量控制",
        "FastQC", "DESeq2", "edgeR", "limma", "单细胞", "scRNA-seq", "Seurat",
        "基因组", "比对", "alignment", "变异", "variant", "SNP", "注释",
        "annotation", "富集", "enrichment", "GO", "KEGG", "通路", "pathway",
        "表达", "expression", "基因", "gene", "测序", "sequencing",
    ]


# ==========================================
# 知识提炼引擎
# ==========================================

class KnowledgeEngine:
    """
    知识提炼引擎

    负责从多种数据源提炼生信领域知识：
    1. 执行记录分析 → 参数规则、错误模式
    2. 用户反馈分析 → 同义词、概念
    3. 技能元数据 → 专家知识
    4. 查询分析 → 概念、同义词

    使用方式：
    ```python
    engine = KnowledgeEngine(session)
    engine.extract_from_executions(skill_id="skill-deseq2")
    engine.extract_from_feedbacks()
    engine.extract_from_skills()
    engine.extract_from_queries()
    ```
    """

    def __init__(
        self,
        session: Session,
        config: Optional[KnowledgeEngineConfig] = None,
    ):
        """
        初始化知识提炼引擎

        Args:
            session: 数据库会话
            config: 配置参数（可选）
        """
        self.session = session
        self.config = config or KnowledgeEngineConfig()

        # 知识缓存（避免重复提取）
        self._knowledge_cache: Dict[str, DomainKnowledgeEntry] = {}

        # 统计计数器
        self._stats = {
            "executions_processed": 0,
            "feedbacks_processed": 0,
            "skills_processed": 0,
            "knowledge_created": 0,
            "knowledge_merged": 0,
        }

    # ==========================================
    # 核心提炼方法
    # ==========================================

    def extract_from_executions(
        self,
        skill_id: Optional[str] = None,
        days: int = 30,
        limit: int = 1000,
    ) -> List[DomainKnowledgeEntry]:
        """
        从执行记录提取知识

        Args:
            skill_id: 指定技能（可选，不指定则全量分析）
            days: 分析最近 N 天的执行记录
            limit: 最大分析记录数

        Returns:
            提取的知识条目列表
        """
        log.info(f"[KnowledgeEngine] 开始从执行记录提取知识: skill_id={skill_id}, days={days}")

        # 获取执行记录
        executions = self._get_execution_records(skill_id, days, limit)

        if not executions:
            log.warning("[KnowledgeEngine] 未找到执行记录")
            return []

        # 按技能分组
        executions_by_skill: Dict[str, List[Any]] = defaultdict(list)
        for exec in executions:
            executions_by_skill[exec.skill_id].append(exec)

        extracted_knowledge: List[DomainKnowledgeEntry] = []

        # 按技能分析
        for skill_id, skill_executions in executions_by_skill.items():
            # 提取参数规则
            param_rules = self._extract_parameter_rules(skill_id, skill_executions)
            extracted_knowledge.extend(param_rules)

            # 提取错误模式
            error_patterns = self._extract_error_patterns(skill_id, skill_executions)
            extracted_knowledge.extend(error_patterns)

            # 提取数据特征
            data_features = self._extract_data_features(skill_id, skill_executions)
            extracted_knowledge.extend(data_features)

        self._stats["executions_processed"] += len(executions)
        self._stats["knowledge_created"] += len(extracted_knowledge)

        log.info(f"[KnowledgeEngine] 从执行记录提取知识完成: {len(extracted_knowledge)} 条")

        return extracted_knowledge

    def extract_from_feedbacks(
        self,
        days: int = 30,
        limit: int = 500,
    ) -> List[DomainKnowledgeEntry]:
        """
        从用户反馈提取知识

        Args:
            days: 分析最近 N 天的反馈
            limit: 最大分析记录数

        Returns:
            提取的知识条目列表
        """
        log.info(f"[KnowledgeEngine] 开始从用户反馈提取知识: days={days}")

        # 获取反馈记录
        feedbacks = self._get_feedback_records(days, limit)

        if not feedbacks:
            log.warning("[KnowledgeEngine] 未找到反馈记录")
            return []

        extracted_knowledge: List[DomainKnowledgeEntry] = []

        # 提取同义词
        synonyms = self._extract_synonyms_from_feedbacks(feedbacks)
        extracted_knowledge.extend(synonyms)

        # 提取概念
        concepts = self._extract_concepts_from_feedbacks(feedbacks)
        extracted_knowledge.extend(concepts)

        self._stats["feedbacks_processed"] += len(feedbacks)
        self._stats["knowledge_created"] += len(extracted_knowledge)

        log.info(f"[KnowledgeEngine] 从反馈提取知识完成: {len(extracted_knowledge)} 条")

        return extracted_knowledge

    def extract_from_skills(
        self,
        skill_ids: Optional[List[str]] = None,
    ) -> List[DomainKnowledgeEntry]:
        """
        从技能元数据提取专家知识

        Args:
            skill_ids: 指定技能列表（可选）

        Returns:
            提取的知识条目列表
        """
        log.info(f"[KnowledgeEngine] 开始从技能元数据提取专家知识")

        # 获取技能元数据
        skills = self._get_skill_metadata(skill_ids)

        if not skills:
            log.warning("[KnowledgeEngine] 未找到技能元数据")
            return []

        extracted_knowledge: List[DomainKnowledgeEntry] = []

        for skill in skills:
            # 提取概念
            concept = self._extract_concept_from_skill(skill)
            if concept:
                extracted_knowledge.append(concept)

            # 提取参数规则（从 SKILL.md）
            rules = self._extract_rules_from_skill(skill)
            extracted_knowledge.extend(rules)

        self._stats["skills_processed"] += len(skills)
        self._stats["knowledge_created"] += len(extracted_knowledge)

        log.info(f"[KnowledgeEngine] 从技能提取知识完成: {len(extracted_knowledge)} 条")

        return extracted_knowledge

    def extract_from_queries(
        self,
        days: int = 30,
        limit: int = 1000,
    ) -> List[DomainKnowledgeEntry]:
        """
        从查询历史提取知识

        分析用户查询与技能的映射关系：
        - 同一技能被多种表达触发 → 同义词
        - 查询关键词 → 概念

        Args:
            days: 分析最近 N 天的查询
            limit: 最大分析记录数

        Returns:
            提取的知识条目列表
        """
        log.info(f"[KnowledgeEngine] 开始从查询历史提取知识")

        # 获取查询-技能映射
        mappings = self._get_query_skill_mappings(days, limit)

        if not mappings:
            log.warning("[KnowledgeEngine] 未找到查询映射")
            return []

        extracted_knowledge: List[DomainKnowledgeEntry] = []

        # 按技能分组
        mappings_by_skill: Dict[str, List[Any]] = defaultdict(list)
        for mapping in mappings:
            mappings_by_skill[mapping.skill_id].append(mapping)

        # 分析同义词：同一技能被不同表达触发
        for skill_id, queries in mappings_by_skill.items():
            if len(queries) >= self.config.MIN_USAGE_FOR_SYNONYM:
                synonyms = self._extract_synonyms_from_queries(skill_id, queries)
                extracted_knowledge.extend(synonyms)

        self._stats["knowledge_created"] += len(extracted_knowledge)

        log.info(f"[KnowledgeEngine] 从查询提取知识完成: {len(extracted_knowledge)} 条")

        return extracted_knowledge

    # ==========================================
    # 参数规则提取
    # ==========================================

    def _extract_parameter_rules(
        self,
        skill_id: str,
        executions: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从执行记录提取参数配置规则

        分析成功执行的参数分布：
        - 常见默认值
        - 参数取值范围
        - 上下文关联参数

        Args:
            skill_id: 技能 ID
            executions: 执行记录列表

        Returns:
            参数规则知识条目
        """
        # 只分析成功执行
        success_execs = [e for e in executions if e.status == "success"]
        if len(success_execs) < self.config.MIN_USAGE_FOR_RULE:
            return []

        # 获取技能名称
        skill_name = success_execs[0].skill_name if success_execs else skill_id

        # 分析参数分布
        param_stats: Dict[str, Dict[Any, int]] = defaultdict(lambda: defaultdict(int))
        param_contexts: Dict[str, List[str]] = defaultdict(list)

        for exec in success_execs:
            if not exec.parameters:
                continue

            for param_name, param_value in exec.parameters.items():
                # 统计参数值频率
                param_stats[param_name][param_value] += 1

                # 收集上下文关键词
                if exec.user_query:
                    keywords = self._extract_bio_keywords(exec.user_query)
                    param_contexts[param_name].extend(keywords)

        # 生成参数规则知识
        rules_knowledge: List[DomainKnowledgeEntry] = []

        for param_name, value_counts in param_stats.items():
            total_count = sum(value_counts.values())
            if total_count < self.config.MIN_USAGE_FOR_RULE:
                continue

            # 找出最常见的值（默认值）
            most_common_value, most_common_count = max(
                value_counts.items(), key=lambda x: x[1]
            )

            # 计算置信度
            confidence = self._calculate_confidence(
                usage_count=total_count,
                success_rate=most_common_count / total_count,
                source_type="execution",
            )

            # 生成规则详情
            rules_data = {
                "parameter": param_name,
                "default_value": most_common_value,
                "value_distribution": dict(value_counts),
                "usage_frequency": {
                    str(v): c for v, c in value_counts.items()
                },
                "recommendation": f"推荐使用 {most_common_value}（出现频率 {most_common_count/total_count:.1%}）",
            }

            # 添加取值范围（如果有多个值）
            unique_values = list(value_counts.keys())
            if len(unique_values) > 1:
                # 尝试推断范围
                if all(isinstance(v, (int, float)) for v in unique_values):
                    rules_data["value_range"] = [min(unique_values), max(unique_values)]

            # 创建知识条目
            knowledge_id = f"rule-{skill_id}-{param_name}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.PARAMETER_RULE,
                concept=f"{skill_name} {param_name}",
                description=f"{skill_name} 技能的 {param_name} 参数配置规则",
                related_skills=[skill_id],
                usage_context=list(set(param_contexts.get(param_name, []))),
                rules=rules_data,
                source=KnowledgeSource.EXECUTION_SUCCESS,
                confidence=confidence,
                usage_count=total_count,
                success_count=most_common_count,
            )

            rules_knowledge.append(entry)

        return rules_knowledge

    # ==========================================
    # 错误模式提取
    # ==========================================

    def _extract_error_patterns(
        self,
        skill_id: str,
        executions: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从失败执行提取错误模式

        分析常见错误：
        - 错误消息聚类
        - 提取错误关键词
        - 查找解决方案（从成功修复的案例）

        Args:
            skill_id: 技能 ID
            executions: 执行记录列表

        Returns:
            错误模式知识条目
        """
        # 只分析失败执行
        failure_execs = [e for e in executions if e.status == "failure"]
        if len(failure_execs) < self.config.ERROR_PATTERN_MIN_COUNT:
            return []

        # 获取技能名称
        skill_name = failure_execs[0].skill_name if failure_execs else skill_id

        # 分析错误消息
        error_patterns: Dict[str, List[Any]] = defaultdict(list)

        for exec in failure_execs:
            if not exec.error_message:
                continue

            # 提取错误关键词
            error_keywords = self._extract_error_keywords(exec.error_message)

            # 按关键词聚类
            for keyword in error_keywords:
                error_patterns[keyword].append(exec)

        # 生成错误模式知识
        pattern_knowledge: List[DomainKnowledgeEntry] = []

        for error_keyword, related_execs in error_patterns.items():
            if len(related_execs) < self.config.ERROR_PATTERN_MIN_COUNT:
                continue

            # 合并错误消息样本
            sample_messages = [
                e.error_message[:200] for e in related_execs[:5] if e.error_message
            ]

            # 查找解决方案（从 SKILL.md 或历史修复）
            solution = self._find_error_solution(skill_id, error_keyword)

            # 计算置信度
            confidence = self._calculate_confidence(
                usage_count=len(related_execs),
                success_rate=0.5,  # 错误模式默认置信度
                source_type="failure",
            )

            # 创建知识条目
            knowledge_id = f"error-{skill_id}-{error_keyword[:30]}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.ERROR_PATTERN,
                concept=f"{skill_name} {error_keyword}",
                description=f"{skill_name} 执行时常见错误：{error_keyword}",
                related_skills=[skill_id],
                usage_context=["错误诊断"],
                solution=solution or f"请检查错误信息：{error_keyword}",
                source=KnowledgeSource.EXECUTION_SUCCESS,  # 从失败中学习
                confidence=confidence,
                usage_count=len(related_execs),
            )

            pattern_knowledge.append(entry)

        return pattern_knowledge

    # ==========================================
    # 同义词提取
    # ==========================================

    def _extract_synonyms_from_feedbacks(
        self,
        feedbacks: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从用户反馈提取同义词

        识别用户表达的概念等价关系：
        - "X就是Y" → X 和 Y 是同义词
        - "X等于Y" → X 和 Y 是同义词
        - 多次出现 → 提高置信度

        Args:
            feedbacks: 反馈记录列表

        Returns:
            同义词知识条目
        """
        synonym_pairs: Dict[Tuple[str, str], int] = defaultdict(int)

        for feedback in feedbacks:
            if not feedback.feedback_text:
                continue

            text = feedback.feedback_text

            # 检查同义词指示词
            for indicator in self.config.SYNONYM_INDICATORS:
                if indicator in text:
                    # 提取等价概念对
                    pairs = self._extract_equivalence_pairs(text, indicator)
                    for pair in pairs:
                        synonym_pairs[pair] += 1

        # 生成同义词知识
        synonym_knowledge: List[DomainKnowledgeEntry] = []

        for (concept_a, concept_b), count in synonym_pairs.items():
            if count < self.config.MIN_CO_OCCURRENCE:
                continue

            # 计算置信度
            confidence = self._calculate_confidence(
                usage_count=count,
                success_rate=0.8,
                source_type="feedback",
            )

            # 创建知识条目
            knowledge_id = f"synonym-{concept_a[:20]}-{concept_b[:20]}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.SYNONYM,
                concept=concept_a,
                description=f"{concept_a} 与 {concept_b} 是同义词",
                synonyms=[concept_b],
                source=KnowledgeSource.USER_FEEDBACK,
                confidence=confidence,
                usage_count=count,
            )

            synonym_knowledge.append(entry)

        return synonym_knowledge

    def _extract_synonyms_from_queries(
        self,
        skill_id: str,
        queries: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从查询历史提取同义词

        分析同一技能被不同表达触发的情况：
        - 不同关键词触发同一技能 → 可能是同义词

        Args:
            skill_id: 技能 ID
            queries: 查询映射列表

        Returns:
            同义词知识条目
        """
        # 提取查询关键词
        keyword_sets: List[Set[str]] = []

        for query in queries:
            keywords = set(self._extract_bio_keywords(query.user_query))
            if keywords:
                keyword_sets.append(keywords)

        if len(keyword_sets) < self.config.MIN_USAGE_FOR_SYNONYM:
            return []

        # 找出常见关键词组合
        all_keywords: Counter = Counter()
        for kset in keyword_sets:
            all_keywords.update(kset)

        # 高频关键词作为概念
        top_keywords = [kw for kw, cnt in all_keywords.most_common(10) if cnt >= 3]

        # 生成同义词知识（关键词变体）
        synonym_knowledge: List[DomainKnowledgeEntry] = []

        for keyword in top_keywords:
            # 找出该关键词的变体（大小写、缩写等）
            variants = self._find_keyword_variants(keyword, keyword_sets)

            if len(variants) >= 2:
                # 计算置信度
                confidence = self._calculate_confidence(
                    usage_count=all_keywords[keyword],
                    success_rate=0.7,
                    source_type="query",
                )

                # 创建知识条目
                knowledge_id = f"synonym-{keyword[:20]}"
                entry = DomainKnowledgeEntry(
                    knowledge_id=knowledge_id,
                    knowledge_type=KnowledgeType.SYNONYM,
                    concept=keyword,
                    description=f"{keyword} 的多种表达形式",
                    synonyms=list(variants),
                    related_skills=[skill_id],
                    example_queries=[q.user_query for q in queries[:5]],
                    source=KnowledgeSource.SYSTEM_DERIVED,
                    confidence=confidence,
                    usage_count=all_keywords[keyword],
                )

                synonym_knowledge.append(entry)

        return synonym_knowledge

    # ==========================================
    # 概念提取
    # ==========================================

    def _extract_concepts_from_feedbacks(
        self,
        feedbacks: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从用户反馈提取概念

        Args:
            feedbacks: 反馈记录列表

        Returns:
            概念知识条目
        """
        concept_counts: Counter = Counter()

        for feedback in feedbacks:
            if not feedback.feedback_text:
                continue

            # 提取生信关键词
            keywords = self._extract_bio_keywords(feedback.feedback_text)
            concept_counts.update(keywords)

        # 生成概念知识
        concept_knowledge: List[DomainKnowledgeEntry] = []

        for concept, count in concept_counts.most_common(20):
            if count < 3:
                continue

            # 计算置信度
            confidence = self._calculate_confidence(
                usage_count=count,
                success_rate=0.6,
                source_type="feedback",
            )

            # 创建知识条目
            knowledge_id = f"concept-{concept[:30]}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.CONCEPT,
                concept=concept,
                description=f"生信分析领域概念：{concept}",
                source=KnowledgeSource.USER_FEEDBACK,
                confidence=confidence,
                usage_count=count,
            )

            concept_knowledge.append(entry)

        return concept_knowledge

    def _extract_concept_from_skill(
        self,
        skill: Dict[str, Any],
    ) -> Optional[DomainKnowledgeEntry]:
        """
        从技能元数据提取概念

        Args:
            skill: 技能元数据

        Returns:
            概念知识条目
        """
        # 提取概念信息
        concept_name = skill.get("category_name") or skill.get("name")
        if not concept_name:
            return None

        # 提取同义词和标签
        tags = skill.get("tags", [])
        synonyms = [tag for tag in tags if tag != concept_name]

        # 提取描述
        description = skill.get("description", f"{concept_name} 分析技能")

        # 计算置信度（专家知识置信度高）
        confidence = 0.9

        # 创建知识条目
        knowledge_id = f"concept-{skill.get('skill_id', concept_name[:30])}"
        entry = DomainKnowledgeEntry(
            knowledge_id=knowledge_id,
            knowledge_type=KnowledgeType.CONCEPT,
            concept=concept_name,
            description=description,
            synonyms=synonyms,
            related_skills=[skill.get("skill_id")],
            related_categories=[skill.get("category")] if skill.get("category") else [],
            usage_context=tags,
            source=KnowledgeSource.SKILL_EXPERT,
            confidence=confidence,
            is_verified=True,  # 技能专家知识已验证
        )

        return entry

    def _extract_rules_from_skill(
        self,
        skill: Dict[str, Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从技能 SKILL.md 提取参数规则

        Args:
            skill: 技能元数据（包含 SKILL.md 解析结果）

        Returns:
            参数规则知识条目列表
        """
        rules_knowledge: List[DomainKnowledgeEntry] = []

        # 从 SKILL.md 解析的参数定义
        parameters = skill.get("parameters", {})
        expert_knowledge = skill.get("expert_knowledge", "")

        for param_name, param_def in parameters.items():
            # 参数定义包含默认值和说明
            default_value = param_def.get("default")
            description = param_def.get("description", "")

            if not description:
                continue

            # 创建规则知识
            knowledge_id = f"rule-{skill.get('skill_id')}-{param_name}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.PARAMETER_RULE,
                concept=f"{skill.get('name')} {param_name}",
                description=f"{skill.get('name')} 参数 {param_name} 的专家建议",
                related_skills=[skill.get("skill_id")],
                rules={
                    "parameter": param_name,
                    "default_value": default_value,
                    "expert_guidance": description,
                },
                source=KnowledgeSource.SKILL_EXPERT,
                confidence=0.95,
                is_verified=True,
            )

            rules_knowledge.append(entry)

        return rules_knowledge

    # ==========================================
    # 数据特征提取
    # ==========================================

    def _extract_data_features(
        self,
        skill_id: str,
        executions: List[Any],
    ) -> List[DomainKnowledgeEntry]:
        """
        从执行记录提取数据特征

        Args:
            skill_id: 技能 ID
            executions: 执行记录列表

        Returns:
            数据特征知识条目
        """
        # 分析用户查询中的数据类型提及
        data_types: Counter = Counter()

        for exec in executions:
            if not exec.user_query:
                continue

            # 提取数据类型关键词
            data_keywords = self._extract_data_keywords(exec.user_query)
            data_types.update(data_keywords)

        # 生成数据特征知识
        feature_knowledge: List[DomainKnowledgeEntry] = []

        skill_name = executions[0].skill_name if executions else skill_id

        for data_type, count in data_types.most_common(10):
            if count < 2:
                continue

            # 计算置信度
            confidence = self._calculate_confidence(
                usage_count=count,
                success_rate=0.7,
                source_type="execution",
            )

            # 创建知识条目
            knowledge_id = f"data-{skill_id}-{data_type[:20]}"
            entry = DomainKnowledgeEntry(
                knowledge_id=knowledge_id,
                knowledge_type=KnowledgeType.DATA_FEATURE,
                concept=f"{skill_name} {data_type}",
                description=f"{skill_name} 常用于处理 {data_type} 数据",
                related_skills=[skill_id],
                usage_context=[data_type],
                source=KnowledgeSource.EXECUTION_SUCCESS,
                confidence=confidence,
                usage_count=count,
            )

            feature_knowledge.append(entry)

        return feature_knowledge

    # ==========================================
    # 辅助方法
    # ==========================================

    def _calculate_confidence(
        self,
        usage_count: int,
        success_rate: float,
        source_type: str,
    ) -> float:
        """
        计算知识置信度

        置信度公式：
        confidence = success_rate * (0.7 + 0.3 * frequency_factor)

        Args:
            usage_count: 使用次数
            success_rate: 成功率
            source_type: 来源类型

        Returns:
            置信度值（0-1）
        """
        # 使用频度因子
        frequency_factor = min(1.0, usage_count / self.config.FREQUENCY_CONFIDENCE_CAP)

        # 基础置信度
        base_confidence = success_rate * (0.7 + 0.3 * frequency_factor)

        # 来源可信度调整
        source_boosts = {
            "skill_expert": 0.2,
            "execution": 0.1,
            "feedback": 0.05,
            "query": 0.0,
            "failure": -0.1,
        }

        boost = source_boosts.get(source_type, 0)
        final_confidence = min(1.0, max(0.0, base_confidence + boost))

        return final_confidence

    def _extract_bio_keywords(self, text: str) -> List[str]:
        """
        从文本提取生信领域关键词

        Args:
            text: 输入文本

        Returns:
            关键词列表
        """
        keywords = []

        for kw in self.config.BIOINFORMATICS_KEYWORDS:
            if kw.lower() in text.lower():
                keywords.append(kw)

        # 额外提取：中文关键词
        chinese_keywords = re.findall(r"[差异表达|质控|转录组|基因|测序|分析]+", text)
        keywords.extend(chinese_keywords)

        return list(set(keywords))

    def _extract_data_keywords(self, text: str) -> List[str]:
        """
        从文本提取数据类型关键词

        Args:
            text: 输入文本

        Returns:
            数据类型关键词列表
        """
        data_keywords = [
            "RNA-seq", "单细胞", "scRNA-seq", "基因组", "转录组",
            "fastq", "bam", "vcf", "csv", "tsv", "matrix",
            "count", "expression", "sequence",
        ]

        found = []
        for kw in data_keywords:
            if kw.lower() in text.lower():
                found.append(kw)

        return found

    def _extract_error_keywords(self, error_message: str) -> List[str]:
        """
        从错误消息提取关键词

        Args:
            error_message: 错误消息

        Returns:
            错误关键词列表
        """
        # 常见错误关键词模式
        error_patterns = [
            r"Error:\s*(\w+)",
            r"(\w+)\s+not found",
            r"invalid\s+(\w+)",
            r"missing\s+(\w+)",
            r"(\w+)\s+is\s+required",
            r"cannot\s+(\w+)",
            r"failed\s+to\s+(\w+)",
            r"negative\s+(\w+)",
        ]

        keywords = []
        for pattern in error_patterns:
            matches = re.findall(pattern, error_message, re.IGNORECASE)
            keywords.extend(matches)

        # 提取更长的关键词短语
        phrases = re.findall(r"[a-zA-Z_]+(?:\s+[a-zA-Z_]+){0,2}", error_message)
        for phrase in phrases:
            if len(phrase) >= 10 and phrase.lower() not in ["the", "a", "an", "is", "are"]:
                keywords.append(phrase)

        return list(set(keywords))[:5]  # 最多返回5个关键词

    def _extract_equivalence_pairs(
        self,
        text: str,
        indicator: str,
    ) -> List[Tuple[str, str]]:
        """
        从文本提取概念等价对

        Args:
            text: 输入文本
            indicator: 等价指示词（如"就是"）

        Returns:
            等价概念对列表
        """
        pairs = []

        # 分割句子
        parts = text.split(indicator)
        if len(parts) >= 2:
            # 提取前后概念
            left = parts[0].strip()
            right = parts[1].strip()

            # 提取关键词
            left_keywords = self._extract_bio_keywords(left)
            right_keywords = self._extract_bio_keywords(right)

            # 配对
            for lk in left_keywords:
                for rk in right_keywords:
                    pairs.append((lk, rk))

        return pairs

    def _find_keyword_variants(
        self,
        keyword: str,
        keyword_sets: List[Set[str]],
    ) -> Set[str]:
        """
        找出关键词的变体形式

        Args:
            keyword: 目标关键词
            keyword_sets: 关键词集合列表

        Returns:
            变体集合
        """
        variants = {keyword}

        # 检查大小写变体
        for kset in keyword_sets:
            for kw in kset:
                if kw.lower() == keyword.lower() and kw != keyword:
                    variants.add(kw)

        # 检查缩写变体
        abbreviations = {
            "DESeq2": ["DESeq", "deseq2"],
            "RNA-seq": ["RNA-seq", "RNA seq", "rnaseq"],
            "FastQC": ["fastqc", "fast quality control"],
        }

        for full, abbr_list in abbreviations.items():
            if keyword in [full] + abbr_list:
                variants.update([full] + abbr_list)

        return variants

    def _find_error_solution(
        self,
        skill_id: str,
        error_keyword: str,
    ) -> Optional[str]:
        """
        查找错误解决方案

        从 SKILL.md 或知识库中查找已知解决方案

        Args:
            skill_id: 技能 ID
            error_keyword: 错误关键词

        Returns:
            解决方案文本
        """
        # 尝试从现有知识库查找
        existing = self.session.exec(
            select(DomainKnowledgeRecord).where(
                DomainKnowledgeRecord.knowledge_type == KnowledgeType.ERROR_PATTERN.value,
                DomainKnowledgeRecord.concept.contains(error_keyword),
            )
        ).first()

        if existing and existing.solution:
            return existing.solution

        # 返回通用解决方案提示
        return None

    # ==========================================
    # 数据获取方法（模拟接口）
    # ==========================================

    def _get_execution_records(
        self,
        skill_id: Optional[str],
        days: int,
        limit: int,
    ) -> List[Any]:
        """获取执行记录"""
        # 实际实现需要查询数据库
        # 这里返回空列表，由外部调用者提供数据
        return []

    def _get_feedback_records(
        self,
        days: int,
        limit: int,
    ) -> List[Any]:
        """获取反馈记录"""
        return []

    def _get_skill_metadata(
        self,
        skill_ids: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """获取技能元数据"""
        return []

    def _get_query_skill_mappings(
        self,
        days: int,
        limit: int,
    ) -> List[Any]:
        """获取查询-技能映射"""
        return []

    # ==========================================
    # 知识持久化
    # ==========================================

    def save_knowledge(
        self,
        knowledge: DomainKnowledgeEntry,
    ) -> DomainKnowledgeRecord:
        """
        保存知识到数据库

        Args:
            knowledge: 知识条目

        Returns:
            数据库记录
        """
        # 检查是否已存在
        existing = self.session.exec(
            select(DomainKnowledgeRecord).where(
                DomainKnowledgeRecord.knowledge_id == knowledge.knowledge_id
            )
        ).first()

        if existing:
            # 合并更新
            return self._merge_knowledge(existing, knowledge)

        # 创建新记录
        record = DomainKnowledgeRecord.from_entry(knowledge)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)

        return record

    def _merge_knowledge(
        self,
        existing: DomainKnowledgeRecord,
        new: DomainKnowledgeEntry,
    ) -> DomainKnowledgeRecord:
        """
        合并重复知识

        Args:
            existing: 已存在记录
            new: 新知识条目

        Returns:
            合并后的记录
        """
        # 合并同义词
        existing_synonyms = set(existing.synonyms_json or [])
        new_synonyms = set(new.synonyms)
        merged_synonyms = list(existing_synonyms | new_synonyms)

        # 合并使用次数
        merged_usage = existing.usage_count + new.usage_count
        merged_success = existing.success_count + new.success_count

        # 更新置信度（加权平均）
        old_weight = existing.usage_count
        new_weight = new.usage_count
        total_weight = old_weight + new_weight

        if total_weight > 0:
            merged_confidence = (
                existing.confidence * old_weight + new.confidence * new_weight
            ) / total_weight
        else:
            merged_confidence = max(existing.confidence, new.confidence)

        # 更新记录
        existing.synonyms_json = merged_synonyms
        existing.usage_count = merged_usage
        existing.success_count = merged_success
        existing.confidence = merged_confidence
        existing.updated_at = get_utc_now()

        self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)

        self._stats["knowledge_merged"] += 1

        return existing

    def batch_save_knowledge(
        self,
        knowledge_list: List[DomainKnowledgeEntry],
    ) -> List[DomainKnowledgeRecord]:
        """
        批量保存知识

        Args:
            knowledge_list: 知识条目列表

        Returns:
            数据库记录列表
        """
        records = []
        for knowledge in knowledge_list:
            # 检查置信度阈值
            if knowledge.effective_confidence >= self.config.MIN_CONFIDENCE_THRESHOLD:
                record = self.save_knowledge(knowledge)
                records.append(record)

        log.info(f"[KnowledgeEngine] 批量保存知识完成: {len(records)} 条入库")
        return records

    # ==========================================
    # 知识查询
    # ==========================================

    def query_knowledge(
        self,
        query: str,
        knowledge_types: Optional[List[KnowledgeType]] = None,
        limit: int = 10,
    ) -> List[KnowledgeQueryResult]:
        """
        查询匹配的知识

        Args:
            query: 查询文本
            knowledge_types: 知识类型过滤（可选）
            limit: 返回数量限制

        Returns:
            匹配结果列表
        """
        # 构建查询条件
        conditions = []

        if knowledge_types:
            type_values = [kt.value for kt in knowledge_types]
            conditions.append(
                DomainKnowledgeRecord.knowledge_type.in_(type_values)
            )

        # 执行查询
        statement = select(DomainKnowledgeRecord)
        if conditions:
            statement = statement.where(*conditions)
        statement = statement.order_by(
            DomainKnowledgeRecord.confidence.desc()
        ).limit(limit * 3)  # 获取更多候选

        records = self.session.exec(statement).all()

        # 匹配和评分
        results: List[KnowledgeQueryResult] = []

        for record in records:
            entry = record.to_entry()

            # 检查匹配
            if entry.matches_query(query):
                # 计算匹配得分
                score = self._calculate_match_score(query, entry)

                # 确定匹配类型
                match_type = self._determine_match_type(query, entry)

                results.append(KnowledgeQueryResult(
                    knowledge=entry,
                    score=score,
                    match_type=match_type,
                ))

        # 按得分排序并限制数量
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _calculate_match_score(
        self,
        query: str,
        entry: DomainKnowledgeEntry,
    ) -> float:
        """
        计算匹配得分

        Args:
            query: 查询文本
            entry: 知识条目

        Returns:
            匹配得分（0-1）
        """
        query_lower = query.lower()

        # 基础匹配得分
        base_score = 0.0

        # 精确匹配概念
        if entry.concept.lower() == query_lower:
            base_score = 1.0
        elif entry.concept.lower() in query_lower:
            base_score = 0.8

        # 同义词匹配
        for synonym in entry.synonyms:
            if synonym.lower() == query_lower:
                base_score = max(base_score, 0.9)
            elif synonym.lower() in query_lower:
                base_score = max(base_score, 0.7)

        # 变体匹配
        for variant in entry.variants:
            if variant.lower() in query_lower:
                base_score = max(base_score, 0.6)

        # 结合置信度
        final_score = base_score * entry.effective_confidence

        return final_score

    def _determine_match_type(
        self,
        query: str,
        entry: DomainKnowledgeEntry,
    ) -> str:
        """
        确定匹配类型

        Args:
            query: 查询文本
            entry: 知识条目

        Returns:
            匹配类型：exact, synonym, semantic
        """
        query_lower = query.lower()

        # 精确匹配
        if entry.concept.lower() == query_lower:
            return "exact"

        for synonym in entry.synonyms:
            if synonym.lower() == query_lower:
                return "exact"

        # 同义词匹配
        if entry.concept.lower() in query_lower:
            return "synonym"

        for synonym in entry.synonyms:
            if synonym.lower() in query_lower:
                return "synonym"

        # 其他为语义匹配
        return "semantic"

    # ==========================================
    # 统计信息
    # ==========================================

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "executions_processed": 0,
            "feedbacks_processed": 0,
            "skills_processed": 0,
            "knowledge_created": 0,
            "knowledge_merged": 0,
        }


# ==========================================
# 导出
# ==========================================

__all__ = [
    "KnowledgeEngine",
    "KnowledgeEngineConfig",
]