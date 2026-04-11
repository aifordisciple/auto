"""
技能关键词索引器 - 从 SKILL.md 自动提取关键词

功能:
1. 扫描所有 SKILL.md 文件，提取关键词信息
2. 从元数据(name, tags, category)、意图描述、参数描述中提取
3. 构建关键词索引，供意图识别服务使用

数据结构:
{
    "skill_id": {
        "primary_keywords": ["单细胞", "scrna", ...],
        "secondary_keywords": ["聚类", "注释", ...],
        "trigger_phrases": ["分析单细胞数据", ...],
        "context_keywords": ["10x", "umi", ...],
        "intent_description": "单细胞RNA测序数据分析流程",
        "category": "single_cell",
        "tags": ["scrna", "seurat"]
    }
}
"""

import os
import re
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.core.logger import log
from app.core.skill_parser import get_skill_parser, get_combined_skills


class SkillKeywords:
    """技能关键词数据结构"""

    def __init__(
        self,
        skill_id: str,
        primary_keywords: List[str] = None,
        secondary_keywords: List[str] = None,
        trigger_phrases: List[str] = None,
        context_keywords: List[str] = None,
        intent_description: str = "",
        category: str = "",
        tags: List[str] = None
    ):
        self.skill_id = skill_id
        self.primary_keywords = primary_keywords or []
        self.secondary_keywords = secondary_keywords or []
        self.trigger_phrases = trigger_phrases or []
        self.context_keywords = context_keywords or []
        self.intent_description = intent_description
        self.category = category
        self.tags = tags or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "primary_keywords": self.primary_keywords,
            "secondary_keywords": self.secondary_keywords,
            "trigger_phrases": self.trigger_phrases,
            "context_keywords": self.context_keywords,
            "intent_description": self.intent_description,
            "category": self.category,
            "tags": self.tags
        }


class SkillKeywordsIndexer:
    """
    技能关键词索引器 - 从 SKILL.md 自动提取关键词

    提取来源：
    1. 元数据: name, tags, category
    2. 意图描述: "## 1. 技能意图与功能边界"
    3. 触发条件: "### 精确触发条件" 下的列表项
    4. 参数描述: 参数表格中的关键词
    """

    # 领域关键词权重映射（用于判断关键词重要性）
    DOMAIN_KEYWORD_WEIGHTS = {
        # 单细胞相关
        "single_cell": {
            "primary": ["单细胞", "scrna", "sc-rna", "seurat", "scanpy", "单细胞测序", "细胞聚类", "细胞注释", "scrna-seq"],
            "secondary": ["umap", "tsne", "marker基因", "doublet", "拟时序", "细胞亚群", "细胞类型"],
            "context": ["10x", "表达矩阵", "umi", "线粒体", "barcode", "cellranger"]
        },
        # 质量控制相关
        "quality_control": {
            "primary": ["质控", "qc", "fastqc", "质量检测", "测序质量", "质量控制"],
            "secondary": ["multiqc", "数据质量", "质量评估", "fastq质控"],
            "context": ["原始数据", "fastq文件", "测序数据", "illumina", "reads"]
        },
        # 转录组相关
        "rna_seq": {
            "primary": ["rna-seq", "rnaseq", "转录组", "表达谱", "基因表达", "转录组测序"],
            "secondary": ["mrna", "fpkm", "tpm", "counts", "定量"],
            "context": ["测序", "比对", "star", "hisat2", "featurecounts"]
        },
        # 差异表达相关
        "differential_expression": {
            "primary": ["差异", "deg", "deseq", "edger", "差异基因", "差异表达"],
            "secondary": ["火山图", "fold change", "pvalue", "padj", "显著基因"],
            "context": ["对照组", "实验组", "重复", "count矩阵"]
        },
        # 流程相关
        "pipeline": {
            "primary": ["流程", "pipeline", "工作流", "nextflow", "自动化流程"],
            "secondary": ["批量处理", "生信流程", "流水线", "nf-core"],
            "context": ["多样本", "自动化", "可复现", "并行执行"]
        },
        # 可视化相关
        "visualization": {
            "primary": ["可视化", "画图", "图表", "plot", "figure"],
            "secondary": ["热图", "火山图", "散点图", "箱线图", "条形图", "小提琴图"],
            "context": ["展示", "出版", "报告", "ggplot", "matplotlib"]
        },
        # ChIP-seq 相关
        "chip_seq": {
            "primary": ["chip-seq", "chip", "peak", "组蛋白", "转录因子"],
            "secondary": ["peak calling", "motif", "结合位点"],
            "context": ["抗体", "免疫沉淀", "富集"]
        },
        # ATAC-seq 相关
        "atac_seq": {
            "primary": ["atac-seq", "atac", "染色质开放", "染色质可及性"],
            "secondary": ["open chromatin", "accessibility"],
            "context": ["tn5", "转座酶", "开放区域"]
        },
        # 甲基化相关
        "methylation": {
            "primary": ["甲基化", "bisulfite", "bs-seq", "dna甲基化"],
            "secondary": ["cpg", "dmr", "methylation"],
            "context": ["表观遗传", "cpg岛"]
        },
        # 变异检测相关
        "variant_calling": {
            "primary": ["变异检测", "snp", "indel", "vcf", "gatk"],
            "secondary": ["变异位点", "外显子", "全基因组", "wes", "wgs"],
            "context": ["germline", "somatic", "突变"]
        },
        # 空间转录组相关
        "spatial": {
            "primary": ["空间转录组", "spatial", "visium", "空间分析"],
            "secondary": ["spot", "空间基因表达", "组织切片"],
            "context": ["组织", "位置", "空间"]
        }
    }

    def __init__(self, user_id: int = 0):
        """
        初始化索引器

        Args:
            user_id: 用户 ID，用于获取用户可见的技能
        """
        self.user_id = user_id
        self._keywords_index: Dict[str, SkillKeywords] = {}
        self._last_updated: Optional[datetime] = None

    def build_keywords_index(self) -> Dict[str, SkillKeywords]:
        """
        从所有 SKILL.md 构建关键词索引

        提取来源：
        1. 元数据: name, tags, category
        2. 意图描述: "## 1. 技能意图与功能边界"
        3. 触发条件: "### 精确触发条件" 下的列表项
        4. 参数描述: 参数表格中的关键词

        Returns:
            关键词索引字典
        """
        log.info(f"[KeywordsIndexer] 开始构建关键词索引，用户 ID: {self.user_id}")

        # 获取所有可用技能
        # 修复：当 user_id <= 0 时，使用 max(1, user_id) 确保获取所有可见技能
        # 这与 SkillMatcher._get_available_skills 的逻辑保持一致
        effective_user_id = max(1, self.user_id) if self.user_id <= 0 else self.user_id
        skills = get_combined_skills(effective_user_id)

        for skill in skills:
            metadata = skill.get("metadata", {})
            skill_id = metadata.get("skill_id", "")
            if not skill_id:
                continue

            keywords = self._extract_keywords_from_skill(skill)
            self._keywords_index[skill_id] = keywords

        self._last_updated = datetime.utcnow()
        log.info(f"[KeywordsIndexer] 关键词索引构建完成，共 {len(self._keywords_index)} 个技能")

        return self._keywords_index

    def _extract_keywords_from_skill(self, skill: Dict[str, Any]) -> SkillKeywords:
        """
        从单个技能中提取关键词

        Args:
            skill: 技能数据字典

        Returns:
            SkillKeywords 对象
        """
        metadata = skill.get("metadata", {})
        skill_id = metadata.get("skill_id", "")
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        category = metadata.get("category", "")
        tags = metadata.get("tags", [])
        expert_knowledge = skill.get("expert_knowledge", "")

        # 1. 从技能名称提取主要关键词
        primary_keywords = self._extract_keywords_from_text(name, is_primary=True)

        # 2. 从标签提取关键词
        if tags:
            primary_keywords.extend([t.lower() for t in tags if t])

        # 3. 从描述提取次要关键词
        secondary_keywords = self._extract_keywords_from_text(description, is_primary=False)

        # 4. 从专家知识提取上下文关键词
        context_keywords = self._extract_context_keywords(expert_knowledge)

        # 5. 从参数表格提取触发短语
        parameters_schema = skill.get("parameters_schema", {})
        trigger_phrases = self._extract_trigger_phrases(parameters_schema)

        # 6. 根据领域分类补充关键词
        if category:
            domain_keywords = self.DOMAIN_KEYWORD_WEIGHTS.get(category, {})
            primary_keywords.extend(domain_keywords.get("primary", []))
            secondary_keywords.extend(domain_keywords.get("secondary", []))
            context_keywords.extend(domain_keywords.get("context", []))

        # 去重
        primary_keywords = list(set(primary_keywords))
        secondary_keywords = list(set(secondary_keywords))
        context_keywords = list(set(context_keywords))

        return SkillKeywords(
            skill_id=skill_id,
            primary_keywords=primary_keywords,
            secondary_keywords=secondary_keywords,
            trigger_phrases=trigger_phrases,
            context_keywords=context_keywords,
            intent_description=description,
            category=category,
            tags=tags
        )

    def _extract_keywords_from_text(self, text: str, is_primary: bool = True) -> List[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本
            is_primary: 是否为主要关键词

        Returns:
            关键词列表
        """
        if not text:
            return []

        keywords = []

        # 中文关键词提取（简单的分词）
        # 匹配中文字符序列
        chinese_pattern = r'[\u4e00-\u9fa5]+'
        chinese_matches = re.findall(chinese_pattern, text)
        for match in chinese_matches:
            if len(match) >= 2:  # 忽略单字
                keywords.append(match.lower())

        # 英文关键词提取
        # 匹配英文单词序列
        english_pattern = r'[a-zA-Z]+(?:[-_][a-zA-Z]+)*'
        english_matches = re.findall(english_pattern, text)
        for match in english_matches:
            if len(match) >= 3:  # 忽略太短的词
                keywords.append(match.lower())

        # 专业术语识别（包含数字、连字符等）
        # 如: RNA-seq, scRNA-seq, 10x, UMI
        tech_pattern = r'[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*'
        tech_matches = re.findall(tech_pattern, text)
        for match in tech_matches:
            if '-' in match or '_' in match or any(c.isdigit() for c in match):
                keywords.append(match.lower())

        return list(set(keywords))

    def _extract_context_keywords(self, expert_knowledge: str) -> List[str]:
        """
        从专家知识中提取上下文关键词

        Args:
            expert_knowledge: 专家知识文本

        Returns:
            上下文关键词列表
        """
        if not expert_knowledge:
            return []

        # 常见的上下文关键词模式
        context_patterns = [
            r'(\d+x)',  # 如 10x
            r'([A-Z]{2,})',  # 如 UMI, PCA, RNA
            r'(参数|阈值|方法|算法)',  # 中文上下文词
        ]

        keywords = []
        for pattern in context_patterns:
            matches = re.findall(pattern, expert_knowledge)
            keywords.extend([m.lower() for m in matches if m])

        return list(set(keywords))

    def _extract_trigger_phrases(self, parameters_schema: Dict[str, Any]) -> List[str]:
        """
        从参数表格中提取触发短语

        Args:
            parameters_schema: 参数 Schema

        Returns:
            触发短语列表
        """
        # 基于参数生成一些触发短语
        # 例如：如果有 sample_name 参数，可能触发 "分析样本" 等短语
        trigger_phrases = []

        properties = parameters_schema.get("properties", {})

        # 常见参数对应的触发短语
        param_trigger_map = {
            "sample_sheet": ["分析样本", "样本分析"],
            "input_paths": ["处理数据", "分析数据"],
            "genome": ["基因组分析", "比对"],
            "output_dir": ["生成结果", "输出结果"]
        }

        for param_name in properties.keys():
            if param_name in param_trigger_map:
                trigger_phrases.extend(param_trigger_map[param_name])

        return trigger_phrases

    def get_keywords_for_skill(self, skill_id: str) -> Optional[SkillKeywords]:
        """
        获取指定技能的关键词

        Args:
            skill_id: 技能 ID

        Returns:
            SkillKeywords 对象，如果不存在返回 None
        """
        if not self._keywords_index:
            self.build_keywords_index()

        return self._keywords_index.get(skill_id)

    def get_all_keywords(self) -> Dict[str, SkillKeywords]:
        """
        获取所有技能的关键词索引

        Returns:
            关键词索引字典
        """
        if not self._keywords_index:
            self.build_keywords_index()

        return self._keywords_index

    def search_by_keyword(self, keyword: str) -> List[str]:
        """
        根据关键词搜索技能

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的技能 ID 列表
        """
        if not self._keywords_index:
            self.build_keywords_index()

        keyword_lower = keyword.lower()
        matched_skills = []

        for skill_id, keywords in self._keywords_index.items():
            # 检查主要关键词
            if keyword_lower in [k.lower() for k in keywords.primary_keywords]:
                matched_skills.append((skill_id, 0.9))  # 高权重
            # 检查次要关键词
            elif keyword_lower in [k.lower() for k in keywords.secondary_keywords]:
                matched_skills.append((skill_id, 0.7))  # 中等权重
            # 检查上下文关键词
            elif keyword_lower in [k.lower() for k in keywords.context_keywords]:
                matched_skills.append((skill_id, 0.5))  # 较低权重

        # 按权重排序
        matched_skills.sort(key=lambda x: x[1], reverse=True)

        return [s[0] for s in matched_skills]

    def refresh_index(self) -> None:
        """刷新关键词索引"""
        log.info("[KeywordsIndexer] 刷新关键词索引")
        self._keywords_index = {}
        self.build_keywords_index()


# ==========================================
# 全局实例管理
# ==========================================

_indexer_instances: Dict[int, SkillKeywordsIndexer] = {}


def get_keywords_indexer(user_id: int = 0) -> SkillKeywordsIndexer:
    """
    获取关键词索引器实例

    Args:
        user_id: 用户 ID

    Returns:
        SkillKeywordsIndexer 实例
    """
    if user_id not in _indexer_instances:
        _indexer_instances[user_id] = SkillKeywordsIndexer(user_id)
    return _indexer_instances[user_id]


def build_global_keywords_index() -> Dict[str, Dict[str, Any]]:
    """
    构建全局关键词索引（无用户过滤）

    Returns:
        关键词索引字典（转换为 dict 格式）
    """
    indexer = get_keywords_indexer(0)
    index = indexer.build_keywords_index()
    return {skill_id: kw.to_dict() for skill_id, kw in index.items()}


log.info("✅ 技能关键词索引器已加载")