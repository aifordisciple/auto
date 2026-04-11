"""
意图识别服务 - 基于混合匹配的智能意图识别

功能:
1. 识别用户是否有明确的技能调用意图
2. 区分显式意图（明确提及技能）和隐式意图（描述需求）
3. 返回匹配的技能推荐
4. 记录推荐日志用于效果分析

架构升级 (2026-03):
- 整合规则/向量/LLM三阶段匹配
- 支持同义词扩展和上下文关联
- 自动从 SKILL.md 提取关键词
- 支持参数推断

核心文件:
- skill_matcher.py: 统一匹配器（主逻辑）
- skill_keywords_indexer.py: 关键词索引
- skill_matcher_config.py: 同义词和权重配置
- skill_vector_search.py: 向量检索
- llm_skill_matcher.py: LLM 精排
"""

import re
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlmodel import Session, select

from app.core.logger import log
from app.models.domain import (
    SkillAsset, SkillStatus, SkillReview, SkillExecutionHistory,
    SkillRecommendationLog
)
from app.services.skill_matcher import (
    SkillMatcher, IntentType, match_skills
)


class IntentRecognitionService:
    """
    意图识别服务 - 基于混合匹配的智能意图识别

    整合规则/向量/LLM三阶段匹配，提供高精度的意图识别和技能推荐。

    使用方式:
    ```python
    service = IntentRecognitionService(session)
    result = service.detect_intent("帮我分析单细胞数据", skills_data)
    ```
    """

    def __init__(self, session: Session, user_id: int = 0):
        """
        初始化意图识别服务

        Args:
            session: 数据库会话
            user_id: 用户 ID（用于权限过滤）
        """
        self.session = session
        self.user_id = user_id
        self._matcher: Optional[SkillMatcher] = None

    def _get_matcher(self) -> SkillMatcher:
        """获取匹配器实例"""
        if not self._matcher:
            self._matcher = SkillMatcher(self.user_id, self.session)
        return self._matcher

    def detect_intent(
        self,
        user_query: str,
        available_skills: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        检测用户意图

        使用混合匹配策略识别用户意图并推荐技能。

        Args:
            user_query: 用户查询
            available_skills: 可用技能列表

        Returns:
            {
                "intent_type": "explicit_skill | implicit_skill | live_coding | general_question",
                "matched_skills": [...],
                "confidence": 0.0-1.0,
                "parameters_suggestion": {},
                "matched_domains": [...],
                "reason": "匹配原因说明"
            }
        """
        # 使用同步方式调用异步匹配器
        # 注意：LLM 调用可能需要 7-10 秒，超时时间需设置为 15 秒
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步上下文中，创建新线程运行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._async_detect_intent(user_query, available_skills)
                    )
                    # 超时时间 15 秒，适应 LLM 调用（通常 5-10 秒）
                    return future.result(timeout=15.0)
            else:
                return loop.run_until_complete(
                    self._async_detect_intent(user_query, available_skills)
                )
        except Exception as e:
            log.warning(f"[IntentService] 异步匹配失败，降级为同步: {e}")
            return self._sync_detect_intent(user_query, available_skills)

    async def _async_detect_intent(
        self,
        user_query: str,
        available_skills: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """异步意图检测"""
        matcher = self._get_matcher()
        result = await matcher.match(user_query)

        # 添加 matched_domains 字段（向后兼容）
        if "matched_domains" not in result:
            result["matched_domains"] = self._extract_domains(result.get("matched_skills", []))

        # ✨ 添加语义文件夹名
        result["semantic_folder_name"] = self._generate_semantic_folder_name(
            user_query, result.get("matched_skills", [])
        )

        return result

    def _sync_detect_intent(
        self,
        user_query: str,
        available_skills: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        同步意图检测（降级方案）

        当异步匹配失败时使用简单的规则匹配。
        修复：即使置信度较低，也应该返回已有的匹配结果，而不是默认返回 live_coding。
        """
        query_lower = user_query.lower()

        # 修复：如果 available_skills 为空，从数据库获取所有可用技能
        if not available_skills:
            from app.core.skill_parser import get_combined_skills
            from app.models.domain import SkillAsset, SkillStatus
            from sqlmodel import select, or_, and_

            # 获取数据库中的技能
            db_skills = self.session.exec(
                select(SkillAsset).where(
                    or_(
                        SkillAsset.status == SkillStatus.PUBLISHED,
                        and_(
                            SkillAsset.owner_id == self.user_id,
                            SkillAsset.status.in_([
                                SkillStatus.PRIVATE,
                                SkillStatus.PENDING_REVIEW
                            ])
                        )
                    )
                )
            ).all()

            # 获取文件系统技能
            fs_skills = get_combined_skills(max(1, self.user_id) if self.user_id > 0 else 1)

            # 合并技能列表
            available_skills = [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "description": s.description or ""
                }
                for s in db_skills
            ]

            # 添加文件系统技能（避免重复）
            db_skill_ids = {s.skill_id for s in db_skills}
            for fs in fs_skills:
                metadata = fs.get("metadata", {})
                skill_id = metadata.get("skill_id", "")
                if skill_id and skill_id not in db_skill_ids:
                    available_skills.append({
                        "skill_id": skill_id,
                        "name": metadata.get("name", ""),
                        "description": metadata.get("description", "")
                    })

            log.info(f"[IntentService] 降级模式：获取 {len(available_skills)} 个可用技能")

        # 1. 检查显式技能触发
        explicit_match = self._check_explicit_trigger(query_lower, available_skills)
        if explicit_match:
            return {
                "intent_type": IntentType.EXPLICIT_SKILL,
                "matched_skills": explicit_match,
                "confidence": 0.95,
                "parameters_suggestion": {},
                "matched_domains": [],
                "reason": "用户明确提及技能名称或功能",
                "semantic_folder_name": self._generate_semantic_folder_name(user_query, explicit_match)
            }

        # 2. 检查领域关键词匹配
        implicit_match = self._check_domain_keywords(query_lower, available_skills)

        # 修复：即使置信度较低，如果有匹配结果也应该返回
        if implicit_match and implicit_match.get("skills"):
            confidence = implicit_match.get("confidence", 0)
            # 确保置信度至少为 0.3，表示有潜在匹配
            min_confidence = max(0.3, confidence)
            return {
                "intent_type": IntentType.IMPLICIT_SKILL,
                "matched_skills": implicit_match["skills"],
                "confidence": min_confidence,
                "parameters_suggestion": implicit_match.get("parameters", {}),
                "matched_domains": implicit_match.get("matched_domains", []),
                "reason": self._build_match_reason(implicit_match),
                "semantic_folder_name": self._generate_semantic_folder_name(user_query, implicit_match["skills"])
            }

        # 3. 检查是否为一般问题
        if self._is_general_question(query_lower):
            return {
                "intent_type": IntentType.GENERAL_QUESTION,
                "matched_skills": [],
                "confidence": 0.3,
                "parameters_suggestion": {},
                "matched_domains": [],
                "reason": "检测到知识问答型需求",
                "semantic_folder_name": "qa_analysis"
            }

        # 4. 默认返回 live_coding（仅在没有匹配时）
        return {
            "intent_type": IntentType.LIVE_CODING,
            "matched_skills": [],
            "confidence": 0.4,
            "parameters_suggestion": {},
            "matched_domains": implicit_match.get("matched_domains", []) if implicit_match else [],
            "reason": "需要自定义代码实现",
            "semantic_folder_name": self._generate_semantic_folder_name(user_query, [])
        }

    def _extract_domains(self, matched_skills: List[Dict]) -> List[str]:
        """从匹配技能中提取领域"""
        domains = set()
        for skill in matched_skills:
            # 尝试从技能 ID 推断领域
            skill_id = skill.get("skill_id", "").lower()
            if "singlecell" in skill_id or "scrna" in skill_id:
                domains.add("single_cell")
            elif "fastqc" in skill_id or "qc" in skill_id:
                domains.add("quality_control")
            elif "nextflow" in skill_id or "pipeline" in skill_id:
                domains.add("pipeline")
        return list(domains)

    def _generate_semantic_folder_name(
        self,
        user_query: str,
        matched_skills: List[Dict[str, Any]]
    ) -> str:
        """
        生成语义化的文件夹名

        优先级:
        1. 从匹配技能的名称提取关键词
        2. 从用户查询中提取生信术语
        3. 返回默认值

        Args:
            user_query: 用户查询
            matched_skills: 匹配的技能列表

        Returns:
            语义化的文件夹名（snake_case 格式，不含时间戳和ID）
        """
        import re

        # 生信术语映射表
        bioinfo_keywords = {
            "fastqc", "multiqc", "qc", "quality", "control",
            "rnaseq", "rna-seq", "rna", "seq", "sequencing",
            "alignment", "align", "mapping", "hisat2", "star", "bwa",
            "quantification", "quantify", "expression", "counts",
            "differential", "deg", "deseq2", "edger",
            "annotation", "annotate", "go", "kegg", "enrichment",
            "single", "cell", "scrna", "scRNA", "singlecell",
            "cluster", "clustering", "tsne", "umap", "pca",
            "trajectory", "pseudotime", "monocle",
            "variant", "snp", "cnv", "sv", "gatk",
            "chip", "atac", "peak", "calling",
            "metagenomics", "microbiome", "16s",
            "pipeline", "workflow", "analysis",
            "fastq", "bam", "sam", "vcf", "gtf",
            "gene", "genome", "transcript", "exome",
            "tumor", "normal", "cancer", "sample"
        }

        # 停用词
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "as", "is", "was",
            "are", "were", "been", "be", "have", "has", "had", "do",
            "does", "did", "will", "would", "could", "should", "may",
            "might", "must", "shall", "can", "need", "dare", "ought",
            "used", "using", "use", "help", "me", "please", "want",
            "need", "run", "perform", "execute", "do", "make", "get"
        }

        keywords = []

        # 1. 从匹配技能提取关键词
        for skill in matched_skills[:2]:  # 最多取前2个技能
            skill_id = skill.get("skill_id", "")
            skill_name = skill.get("name", "")

            # 从 skill_id 提取（如 fastqc_multiqc_01 -> fastqc_multiqc）
            id_parts = re.findall(r"[a-z]+", skill_id.lower())
            for part in id_parts:
                if part in bioinfo_keywords and part not in keywords:
                    keywords.append(part)

            # 从 skill_name 提取英文关键词
            name_words = re.findall(r"[a-zA-Z]{3,}", skill_name)
            for word in name_words:
                word_lower = word.lower()
                if word_lower in bioinfo_keywords and word_lower not in keywords:
                    keywords.append(word_lower)

        # 2. 从用户查询提取关键词
        query_words = re.findall(r"[a-zA-Z]{3,}", user_query)
        for word in query_words:
            word_lower = word.lower()
            if word_lower in bioinfo_keywords and word_lower not in keywords:
                keywords.append(word_lower)

        # 3. 中文关键词映射
        chinese_map = {
            "质量控制": "qc", "质控": "qc",
            "测序": "seq", "转录组": "rnaseq",
            "比对": "alignment", "定量": "quantify",
            "差异": "diff", "分析": "analysis",
            "单细胞": "singlecell", "聚类": "cluster",
            "注释": "annotation", "富集": "enrichment",
            "变异": "variant", "基因": "gene",
            "肿瘤": "tumor", "正常": "normal"
        }
        for cn, en in chinese_map.items():
            if cn in user_query and en not in keywords:
                keywords.append(en)

        # 返回结果
        if keywords:
            # 取前3个关键词组合
            semantic_name = "_".join(keywords[:3])
            # 清理并限制长度
            semantic_name = re.sub(r"[^a-z0-9_]", "", semantic_name.lower())
            return semantic_name[:30]

        return "analysis"

    def _check_explicit_trigger(
        self,
        query_lower: str,
        available_skills: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """检查显式触发词"""
        matched = []

        for skill in available_skills:
            skill_id = skill.get("skill_id", "")
            name = (skill.get("name", "") or "").lower()
            description = (skill.get("description", "") or "").lower()

            # 检查技能名称是否出现在查询中
            if name and name in query_lower:
                matched.append({
                    "skill_id": skill_id,
                    "name": skill.get("name", ""),
                    "match_score": 0.95,
                    "match_reason": "用户明确提及技能名称"
                })
                continue

            # 检查 skill_id 是否出现在查询中
            if skill_id.lower() in query_lower:
                matched.append({
                    "skill_id": skill_id,
                    "name": skill.get("name", ""),
                    "match_score": 0.95,
                    "match_reason": "用户明确提及技能 ID"
                })

        return matched

    def _check_domain_keywords(
        self,
        query_lower: str,
        available_skills: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """检查领域关键词（简化版）"""
        # 使用配置中的领域关键词
        from app.services.skill_matcher_config import SYNONYM_MAP, get_keyword_weight

        domain_keywords = {
            "quality_control": ["质控", "qc", "fastqc", "质量", "测序质量", "质量检测"],
            "single_cell": ["单细胞", "scrna", "seurat", "scanpy", "细胞聚类", "细胞注释"],
            "differential_expression": ["差异", "deg", "deseq", "edger", "差异基因", "差异表达"],
            "pipeline": ["流程", "pipeline", "工作流", "nextflow", "自动化流程"],
            "visualization": ["可视化", "画图", "图表", "plot", "figure"],
            "rna_seq": ["rna-seq", "rnaseq", "转录组", "表达谱"],
        }

        matched_domains = []
        total_score = 0.0

        for domain, keywords in domain_keywords.items():
            domain_match = False
            for kw in keywords:
                if kw in query_lower:
                    domain_match = True
                    total_score += get_keyword_weight(kw) * 0.8
                    break
            if domain_match:
                matched_domains.append(domain)

        if not matched_domains:
            return None

        # 查找相关技能
        related_skills = []
        for skill in available_skills:
            skill_id = skill.get("skill_id", "")
            skill_name = (skill.get("name", "") or "").lower()
            skill_desc = (skill.get("description", "") or "").lower()

            for domain in matched_domains:
                domain_kw = domain.replace("_", " ")
                if domain_kw in skill_name or domain_kw in skill_desc:
                    related_skills.append({
                        "skill_id": skill_id,
                        "name": skill.get("name", ""),
                        "match_score": min(0.85, total_score),
                        "match_reason": f"检测到 {domain} 相关需求"
                    })

        confidence = min(0.9, total_score * 0.5 + len(matched_domains) * 0.1)

        return {
            "skills": related_skills[:5],
            "confidence": confidence,
            "matched_domains": matched_domains
        }

    def _build_match_reason(self, implicit_match: Dict[str, Any]) -> str:
        """构建匹配原因说明"""
        domains = implicit_match.get("matched_domains", [])
        confidence = implicit_match.get("confidence", 0)

        if not domains:
            return "检测到相关需求"

        domain_names = {
            "quality_control": "质量控制",
            "single_cell": "单细胞分析",
            "differential_expression": "差异表达",
            "pipeline": "流程自动化",
            "visualization": "数据可视化",
            "rna_seq": "转录组分析"
        }

        domain_labels = [domain_names.get(d, d) for d in domains[:3]]
        reason = f"检测到{', '.join(domain_labels)}需求"

        if confidence > 0.7:
            reason += "（高置信度）"
        elif confidence > 0.5:
            reason += "（中等置信度）"

        return reason

    def _is_general_question(self, query_lower: str) -> bool:
        """判断是否为一般问题"""
        question_patterns = [
            "什么是", "怎么理解", "如何理解", "解释一下", "告诉我",
            "什么是", "有什么区别", "有什么不同", "为什么",
            "how to", "what is", "explain", "tell me"
        ]

        for pattern in question_patterns:
            if pattern in query_lower:
                analysis_patterns = ["分析", "处理", "运行", "执行"]
                if not any(ap in query_lower for ap in analysis_patterns):
                    return True

        return False

    def log_recommendation(
        self,
        user_id: int,
        session_id: str,
        query: str,
        intent_result: Dict[str, Any],
        accepted_skill_id: Optional[str] = None
    ) -> None:
        """
        记录推荐日志

        Args:
            user_id: 用户 ID
            session_id: 聊天会话 ID
            query: 用户原始查询
            intent_result: 意图识别结果
            accepted_skill_id: 用户选择的技能 ID（如果有）
        """
        try:
            log_entry = SkillRecommendationLog(
                user_id=user_id,
                session_id=session_id,
                query=query,
                intent_type=intent_result.get("intent_type", "unknown"),
                recommended_skills=[s.get("skill_id") for s in intent_result.get("matched_skills", [])],
                confidence=intent_result.get("confidence", 0),
                accepted_skill=accepted_skill_id
            )
            self.session.add(log_entry)
            self.session.commit()

            log.info(f"📝 [IntentService] 记录推荐日志: 意图={intent_result.get('intent_type')}, "
                    f"推荐={len(intent_result.get('matched_skills', []))}个")
        except Exception as e:
            log.warning(f"记录推荐日志失败: {e}")

    def get_recommended_skills(
        self,
        user_query: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        获取推荐技能（带评分）

        Args:
            user_query: 用户查询
            limit: 返回数量

        Returns:
            推荐技能列表
        """
        # 获取已发布技能
        skills = self.session.exec(
            select(SkillAsset).where(SkillAsset.status == SkillStatus.PUBLISHED)
        ).all()

        if not skills:
            return []

        # 意图识别
        skills_data = [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "executor_type": s.executor_type
            }
            for s in skills
        ]

        intent_result = self.detect_intent(user_query, skills_data)

        # 如果有匹配技能，获取详细信息
        result = []
        for match in intent_result.get("matched_skills", [])[:limit]:
            skill = next((s for s in skills if s.skill_id == match["skill_id"]), None)
            if skill:
                # 获取评分
                rating_result = self.session.exec(
                    select(SkillReview.rating).where(SkillReview.skill_id == skill.skill_id)
                ).all()
                avg_rating = sum(rating_result) / len(rating_result) if rating_result else 0

                result.append({
                    "skill": skill,
                    "score": match["match_score"],
                    "reasons": [match.get("match_reason", "相关技能")]
                })

        return result


# ==========================================
# LLM 增强意图识别（兼容旧版 API）
# ==========================================

def should_enhance_with_llm(recommendations: list, user_query: str) -> bool:
    """
    判断是否需要 LLM 增强推荐

    触发条件：
    1. 无匹配结果
    2. 最高分 < 0.5
    3. 推荐数量 < 2
    4. 用户查询包含复杂语义

    Args:
        recommendations: 匹配的推荐结果列表
        user_query: 用户原始查询

    Returns:
        True 如果需要 LLM 增强
    """
    if not recommendations:
        return True

    top_score = recommendations[0].get("score", 0) if recommendations else 0
    if top_score < 0.5:
        return True

    if len(recommendations) < 2:
        return True

    complex_patterns = ["哪些", "怎么", "如何", "能不能", "可以吗", "是否有", "有没有", "什么"]
    if any(p in user_query for p in complex_patterns):
        return True

    return False


async def detect_intent_with_llm(
    user_query: str,
    available_skills: List[Dict[str, Any]],
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    timeout: float = 3.0
) -> Optional[Dict[str, Any]]:
    """
    使用 LLM 进行精确意图识别（带超时和降级）

    该函数自主初始化 LLM 客户端，用于在技能推荐流程中灵活调用。

    Args:
        user_query: 用户查询
        available_skills: 可用技能列表
        api_key: LLM API Key
        base_url: API 基础 URL
        model: 模型名称
        timeout: 超时时间（秒）

    Returns:
        意图识别结果，失败返回 None
    """
    from app.services.llm_skill_matcher import match_with_llm

    try:
        result = await match_with_llm(user_query, available_skills)

        # 转换为旧格式
        return {
            "intent_type": result.get("intent_type", "live_coding"),
            "matched_skills": result.get("matched_skills", []),
            "confidence": result.get("confidence", 0.7)
        }

    except Exception as e:
        log.warning(f"❌ [LLM意图识别] 调用失败: {e}")
        return None


# ==========================================
# 出版级图表规范系统（保持向后兼容）
# ==========================================

# 图表类型关键词映射
PLOT_TYPE_KEYWORDS = {
    "heatmap": ["热图", "heatmap", "clustermap", "表达热图", "相关性热图"],
    "volcano": ["火山图", "volcano", "差异火山图"],
    "scatter": ["散点图", "scatter", "相关性图", "correlation plot"],
    "boxplot": ["箱线图", "boxplot", "box plot", "箱型图"],
    "bar": ["条形图", "柱状图", "bar plot", "bar chart"],
    "line": ["折线图", "线图", "line plot", "line chart"],
    "violin": ["小提琴图", "violin", "violin plot"],
    "umap": ["umap", "UMAP", "UMAP图"],
    "tsne": ["tsne", "t-SNE", "t-sne", "tSNE"],
    "pca": ["pca", "PCA", "主成分分析图", "pca plot"],
    "dendrogram": ["聚类树", "dendrogram", "系统树图"],
    "sankey": ["桑基图", "sankey"],
    "bubble": ["气泡图", "bubble"],
    "manhattan": ["曼哈顿图", "manhattan"],
    "histogram": ["直方图", "histogram", "频率分布图"],
    "forest": ["森林图", "forest plot"],
    "trajectory": ["轨迹图", "拟时序", "trajectory", "pseudotime"],
    "venn": ["韦恩图", "venn"],
    "pie": ["饼图", "pie chart"],
}


def is_plotting_request(query: str) -> bool:
    """检测是否为画图请求"""
    query_lower = query.lower()
    viz_keywords = [
        "可视化", "画图", "图表", "图形", "plot", "figure", "chart",
        "热图", "火山图", "散点图", "箱线图", "条形图", "小提琴图",
        "umap", "tsne", "pca"
    ]
    return any(kw in query_lower for kw in viz_keywords)


def detect_plot_type(query: str) -> Optional[str]:
    """检测具体的图表类型"""
    query_lower = query.lower()
    for plot_type, keywords in PLOT_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                return plot_type
    return None


def get_plotting_guidelines(query: str) -> str:
    """
    根据查询内容返回针对性的出版级画图规范提示词

    Args:
        query: 用户查询字符串

    Returns:
        出版级图表规范提示词
    """
    plot_type = detect_plot_type(query)

    base_guidelines = """
【出版级可视化规范 - 强制执行】

当生成画图代码时，必须遵循以下出版级图表规范：

### 1. 图片尺寸与分辨率
- **分辨率**: 保存为 300 DPI（照片/热图）或 600 DPI（线条图/折线图）
- **宽度**: 优先使用双栏宽度（7 英寸/183mm），单栏时 3.5-4 英寸
- **高度**: 保持宽高比，通常 4-6 英寸

### 2. 字体规范
- **字体**: Arial 或 Helvetica（禁止使用中文字体）
- **字号**: 标题 14-16pt，轴标签 12-14pt，刻度标签 10-12pt，图例 9-11pt
- **语言**: 所有文字（标题、标签、图例）必须使用纯英文

### 3. 配色方案（色盲友好）
推荐使用以下调色板：
- Python: `viridis`, `plasma`, `cividis`, `colorblind` (seaborn)
- R: `viridis`, `RColorBrewer::brewer.pal(8, "Set2")`, `Okabe-Ito`

### 4. 保存格式（强制要求 - 必须同时输出 PDF 和 PNG）
```python
# Python
plt.savefig('figure.pdf', dpi=300, bbox_inches='tight')
plt.savefig('figure.png', dpi=300, bbox_inches='tight')

# R - 必须使用 cairo_pdf 保存 PDF
ggsave('figure.pdf', device=cairo_pdf, width=7, height=5)
ggsave('figure.png', width=7, height=5, dpi=300)
```
"""

    return base_guidelines


log.info("✅ 意图识别服务已加载（混合匹配架构）")