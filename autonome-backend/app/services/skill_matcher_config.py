"""
技能匹配器配置 - 同义词映射与关键词权重

功能:
1. SYNONYM_MAP: 同义词映射表，支持同义词扩展匹配
2. KEYWORD_WEIGHTS: 关键词权重配置，不同关键词有不同的匹配权重
3. NEGATION_WORDS: 否定词列表，用于排除否定意图
4. CONTEXT_BOOST_WORDS: 上下文增强词，提高特定场景的匹配权重

设计理念：
- 同义词映射支持多语言、多表达形式的统一
- 关键词权重反映关键词与技能的相关程度
- 否定词处理避免误匹配（如"不要做单细胞分析"不应推荐单细胞技能）
"""

import re
from typing import Dict, List, Set, Pattern


# ==========================================
# 同义词映射表 (SYNONYM_MAP)
# ==========================================
# 格式: {标准形式: [同义词列表]}
# 当用户输入同义词时，自动扩展到标准形式进行匹配

SYNONYM_MAP: Dict[str, List[str]] = {
    # 单细胞相关
    "single_cell": ["单细胞", "single-cell", "scrna", "sc-rna", "scrna-seq", "单细胞测序", "scRNA-seq", "scrnaseq"],
    "seurat": ["seurat", "seurat分析", "Seurat"],
    "scanpy": ["scanpy", "scanpy分析", "Scanpy"],
    "cell_clustering": ["细胞聚类", "细胞分群", "clustering", "细胞分类"],
    "cell_annotation": ["细胞注释", "细胞类型注释", "cell type annotation", "细胞类型鉴定"],
    "marker_gene": ["marker基因", "标记基因", "marker gene", "特征基因"],

    # 质量控制相关
    "quality_control": ["质控", "qc", "质量控制", "质量检测", "quality control"],
    "fastqc": ["fastqc", "fastqc分析", "FastQC"],
    "multiqc": ["multiqc", "multiqc报告", "MultiQC"],

    # FASTQ 处理相关（新增）
    "fastq_filter": ["fastq过滤", "reads过滤", "质量过滤", "低质量过滤", "过滤reads", "过滤fastq", "fastq filtering"],
    "fastq_trim": ["fastq修剪", "reads修剪", "trim", "trimming", "截取", "切除", "adapter", "接头"],
    "fastq_quality": ["fastq质量", "reads质量", "质量筛选", "低质量剔除", "quality filtering"],
    "reads_processing": ["reads处理", "reads加工", "序列处理", "序列过滤"],
    "low_quality": ["低质量", "低质量reads", "低质量序列", "low quality"],

    # 转录组相关
    "rna_seq": ["rna-seq", "rnaseq", "转录组", "转录组测序", "rna-seq分析", "rna seq"],
    "gene_expression": ["基因表达", "表达谱", "gene expression", "表达量"],
    "transcriptome": ["转录组", "transcriptome", "转录本"],
    "fpkm": ["fpkm", "FPKM"],
    "tpm": ["tpm", "TPM"],
    "counts": ["counts", "count矩阵", "计数矩阵"],

    # 差异表达相关
    "differential_expression": ["差异表达", "差异基因", "deg", "differential expression", "差异分析"],
    "deseq2": ["deseq2", "deseq", "DESeq2", "DESeq"],
    "edger": ["edger", "edgeR", "EdgeR"],
    "volcano_plot": ["火山图", "volcano", "volcano plot"],
    "fold_change": ["fold change", "fc", "倍数变化", "差异倍数"],

    # 流程相关
    "pipeline": ["流程", "pipeline", "工作流", "workflow", "流水线"],
    "nextflow": ["nextflow", "nf", "Nextflow", "nf-core"],
    "workflow": ["工作流", "workflow", "pipeline", "自动化流程"],
    "automation": ["自动化", "automation", "批量处理", "自动化分析"],

    # 可视化相关
    "visualization": ["可视化", "画图", "绑图", "plot", "figure", "图表", "数据可视化"],
    "heatmap": ["热图", "heatmap", "表达热图", "聚类热图"],
    "scatter_plot": ["散点图", "scatter", "scatter plot", "相关性图"],
    "boxplot": ["箱线图", "boxplot", "box plot", "箱型图"],
    "bar_plot": ["条形图", "柱状图", "bar plot", "bar chart"],
    "violin_plot": ["小提琴图", "violin", "violin plot"],
    "umap": ["umap", "UMAP", "UMAP图", "umap降维"],
    "tsne": ["tsne", "t-SNE", "t-sne", "tSNE", "t-SNE图"],
    "pca": ["pca", "PCA", "主成分分析", "pca降维"],

    # ChIP-seq 相关
    "chip_seq": ["chip-seq", "chipseq", "chip", "ChIP-seq", "ChIP"],
    "peak_calling": ["peak calling", "peak", "peak检测", "峰检测"],
    "motif_analysis": ["motif分析", "motif", "motif analysis"],

    # ATAC-seq 相关
    "atac_seq": ["atac-seq", "atacseq", "atac", "ATAC-seq", "ATAC"],
    "chromatin_accessibility": ["染色质开放", "染色质可及性", "chromatin accessibility"],

    # 甲基化相关
    "methylation": ["甲基化", "methylation", "dna甲基化"],
    "bisulfite": ["bisulfite", "bs-seq", "亚硫酸氢盐"],
    "dmr": ["dmr", "DMR", "差异甲基化区域"],

    # 变异检测相关
    "variant_calling": ["变异检测", "variant calling", "变异位点", "snp calling"],
    "snp": ["snp", "SNP", "单核苷酸多态性"],
    "indel": ["indel", "INDEL", "插入缺失"],
    "vcf": ["vcf", "VCF", "变异文件"],
    "gatk": ["gatk", "GATK", "Genome Analysis Toolkit"],
    "wes": ["wes", "WES", "外显子测序", "全外显子"],
    "wgs": ["wgs", "WGS", "全基因组测序"],

    # 空间转录组相关
    "spatial": ["空间转录组", "spatial", "visium", "空间分析"],
    "visium": ["visium", "Visium", "10x Visium"],

    # 通用操作
    "analysis": ["分析", "analysis", "数据处理"],
    "processing": ["处理", "processing", "数据加工"],
    "comparison": ["比较", "comparison", "对比分析"],
    "annotation": ["注释", "annotation", "功能注释"],
    "alignment": ["比对", "alignment", "mapping", "序列比对"],
    "quantification": ["定量", "quantification", "表达定量"],
}


# ==========================================
# 反向同义词映射 (REVERSE_SYNONYM_MAP)
# ==========================================
# 用于将用户输入映射到标准形式
# 格式: {同义词: 标准形式}

REVERSE_SYNONYM_MAP: Dict[str, str] = {}
for standard, synonyms in SYNONYM_MAP.items():
    for synonym in synonyms:
        REVERSE_SYNONYM_MAP[synonym.lower()] = standard
    # 标准形式本身也加入映射
    REVERSE_SYNONYM_MAP[standard.lower()] = standard


# ==========================================
# 关键词权重配置 (KEYWORD_WEIGHTS)
# ==========================================
# 不同类型的关键词有不同的权重，反映其对技能匹配的贡献度
# 权重范围: 0.0 - 1.0

KEYWORD_WEIGHTS: Dict[str, Dict[str, float]] = {
    # 主要关键词权重（高权重，直接关联技能核心功能）
    "primary": {
        # 单细胞
        "单细胞": 0.95,
        "scrna": 0.95,
        "seurat": 0.90,
        "scanpy": 0.90,
        "细胞聚类": 0.85,
        "细胞注释": 0.85,

        # 质控
        "质控": 0.90,
        "qc": 0.90,
        "fastqc": 0.95,
        "multiqc": 0.90,

        # FASTQ 处理（新增）
        "fastq": 0.90,
        "reads": 0.85,
        "过滤": 0.80,
        "trim": 0.85,
        "trimming": 0.85,
        "低质量": 0.85,
        "quality": 0.75,
        "filter": 0.80,
        "filtering": 0.80,

        # 转录组
        "rna-seq": 0.90,
        "转录组": 0.90,
        "差异表达": 0.90,
        "deseq2": 0.90,
        "edger": 0.90,

        # 流程
        "流程": 0.85,
        "pipeline": 0.85,
        "nextflow": 0.95,

        # 可视化
        "可视化": 0.80,
        "画图": 0.75,
        "热图": 0.85,
        "火山图": 0.85,
        "umap": 0.85,
        "tsne": 0.85,
    },

    # 次要关键词权重（中等权重，提供上下文信息）
    "secondary": {
        "分析": 0.50,
        "处理": 0.45,
        "比对": 0.60,
        "定量": 0.60,
        "注释": 0.55,
        "差异": 0.60,
        "聚类": 0.65,
        "marker基因": 0.70,
        "doublet": 0.65,
        "拟时序": 0.70,
        # FASTQ 相关（新增）
        "接头": 0.55,
        "adapter": 0.55,
        "截取": 0.50,
        "修剪": 0.50,
        "剔除": 0.50,
        "序列": 0.45,
    },

    # 上下文关键词权重（低权重，增强置信度）
    "context": {
        "数据": 0.20,
        "样本": 0.25,
        "结果": 0.15,
        "输出": 0.15,
        "参数": 0.20,
        "10x": 0.40,
        "umi": 0.35,
        "线粒体": 0.30,
        "barcode": 0.30,
    }
}


# ==========================================
# 否定词列表 (NEGATION_WORDS)
# ==========================================
# 当这些词出现在关键词之前时，应该排除匹配
# 例如: "不要做单细胞分析" 不应推荐单细胞技能

NEGATION_WORDS: Set[str] = {
    # 中文否定词
    "不", "不要", "不用", "无需", "别", "不要", "无需",
    "不是", "并非", "没有", "未", "无",

    # 英文否定词
    "no", "not", "don't", "dont", "without", "avoid", "skip",
    "exclude", "except", "rather than"
}


# ==========================================
# 代码生成请求识别模式 (CODE_GENERATION_PATTERNS)
# ==========================================
# 当用户请求匹配这些模式时，应该走 live_coding 路径
# 而不是技能匹配路径

CODE_GENERATION_PATTERNS: List[str] = [
    # 中文编程请求模式
    r"写个程序",
    r"写一个程序",
    r"编写程序",
    r"写个脚本",
    r"写一个脚本",
    r"编写脚本",
    r"帮我写代码",
    r"帮我写个",
    r"写一段代码",
    r"实现一个",
    r"开发一个",
    r"写个函数",
    r"写一个函数",
    r"编个程序",
    r"编一个程序",
    r"给我写个",
    r"给我写一个",
    r"能写个",
    r"能写一个",
    r"可以写个",
    r"可以写一个",

    # 英文编程请求模式
    r"write a program",
    r"write a script",
    r"write a function",
    r"write code",
    r"write me a",
    r"can you write",
    r"help me write",
    r"implement a",
    r"develop a",
    r"create a script",
    r"create a program",
]

# 分析请求模式（用户想让系统执行分析）
ANALYSIS_REQUEST_PATTERNS: List[str] = [
    r"帮我分析",
    r"分析一下",
    r"帮我处理",
    r"处理一下",
    r"帮我跑",
    r"跑一下",
    r"运行一下",
    r"执行一下",
    r"帮我做",
    r"分析这些",
    r"处理这些",
    r"run analysis",
    r"analyze",
    r"process this",
]

# ==========================================
# 预编译正则表达式模式 (COMPILED_PATTERNS)
# ==========================================
# 在模块加载时编译正则表达式，避免每次调用函数时重复编译

COMPILED_CODE_GENERATION_PATTERNS: List[Pattern] = [
    re.compile(p, re.IGNORECASE) for p in CODE_GENERATION_PATTERNS
]

COMPILED_ANALYSIS_REQUEST_PATTERNS: List[Pattern] = [
    re.compile(p, re.IGNORECASE) for p in ANALYSIS_REQUEST_PATTERNS
]


def is_code_generation_request(query: str) -> bool:
    """
    判断是否为代码生成请求

    代码生成请求的特征：
    1. 用户想要一段代码/脚本
    2. 描述了程序的功能（输入什么、输出什么）
    3. 而不是让系统执行分析

    Args:
        query: 用户查询

    Returns:
        如果是代码生成请求返回 True
    """
    query_lower = query.lower()

    # 使用预编译的正则表达式模式进行检查
    for pattern in COMPILED_CODE_GENERATION_PATTERNS:
        if pattern.search(query_lower):
            # 进一步检查：确保不是分析请求
            for analysis_pattern in COMPILED_ANALYSIS_REQUEST_PATTERNS:
                if analysis_pattern.search(query_lower):
                    # 如果同时匹配分析模式，优先走分析路径
                    return False
            return True

    return False


# ==========================================
# 上下文增强词 (CONTEXT_BOOST_WORDS)
# ==========================================
# 当这些词与领域关键词同时出现时，提高匹配置信度

CONTEXT_BOOST_WORDS: Dict[str, List[str]] = {
    "single_cell": ["10x", "umi", "barcode", "cellranger", "表达矩阵", "seurat对象"],
    "quality_control": ["原始数据", "fastq", "测序质量", "illumina", "reads"],
    "rna_seq": ["比对", "定量", "表达", "counts", "fpkm", "tpm"],
    "differential_expression": ["对照组", "实验组", "重复", "显著性", "pvalue", "padj"],
    "pipeline": ["多样本", "自动化", "批量", "并行", "可复现"],
    "visualization": ["出版", "文章", "figure", "图表", "展示"]
}


# ==========================================
# 领域分类映射 (DOMAIN_CATEGORY_MAP)
# ==========================================
# 用于将匹配的关键词映射到领域分类

DOMAIN_CATEGORY_MAP: Dict[str, str] = {
    "single_cell": "single_cell",
    "scrna": "single_cell",
    "seurat": "single_cell",
    "scanpy": "single_cell",
    "细胞聚类": "single_cell",
    "细胞注释": "single_cell",

    "quality_control": "quality_control",
    "qc": "quality_control",
    "fastqc": "quality_control",
    "multiqc": "quality_control",
    "质控": "quality_control",

    # FASTQ 处理相关（新增）
    "fastq_filter": "quality_control",
    "fastq_trim": "quality_control",
    "fastq_quality": "quality_control",
    "reads_processing": "quality_control",
    "low_quality": "quality_control",
    "过滤": "quality_control",
    "trim": "quality_control",
    "trimming": "quality_control",

    "rna_seq": "rna_seq",
    "转录组": "rna_seq",
    "差异表达": "differential_expression",
    "deg": "differential_expression",
    "deseq2": "differential_expression",
    "edger": "differential_expression",

    "pipeline": "pipeline",
    "nextflow": "pipeline",
    "工作流": "pipeline",

    "visualization": "visualization",
    "可视化": "visualization",
    "画图": "visualization",
    "热图": "visualization",
    "火山图": "visualization",

    "chip_seq": "chip_seq",
    "atac_seq": "atac_seq",
    "methylation": "methylation",
    "variant_calling": "variant_calling",
    "spatial": "spatial"
}


# ==========================================
# 辅助函数
# ==========================================

def expand_synonyms(keyword: str) -> List[str]:
    """
    扩展关键词的同义词

    Args:
        keyword: 输入关键词

    Returns:
        包含原始关键词及其同义词的列表
    """
    keyword_lower = keyword.lower()

    # 查找标准形式
    standard = REVERSE_SYNONYM_MAP.get(keyword_lower)

    if standard:
        # 返回标准形式的所有同义词
        synonyms = SYNONYM_MAP.get(standard, [])
        return [keyword] + [s for s in synonyms if s.lower() != keyword_lower]

    return [keyword]


def get_keyword_weight(keyword: str) -> float:
    """
    获取关键词权重

    Args:
        keyword: 关键词

    Returns:
        权重值 (0.0 - 1.0)
    """
    keyword_lower = keyword.lower()

    # 查找标准形式
    standard = REVERSE_SYNONYM_MAP.get(keyword_lower, keyword_lower)

    # 在各级权重中查找
    for weight_type, weights in KEYWORD_WEIGHTS.items():
        if standard in weights:
            return weights[standard]
        # 检查同义词
        for kw, w in weights.items():
            if kw.lower() == keyword_lower:
                return w

    # 默认权重
    return 0.3


def is_negation_context(text: str, keyword_position: int) -> bool:
    """
    检查关键词是否在否定上下文中

    Args:
        text: 完整文本
        keyword_position: 关键词在文本中的位置

    Returns:
        如果是否定上下文返回 True
    """
    # 检查关键词前的文本片段
    prefix = text[:keyword_position].lower()

    for neg_word in NEGATION_WORDS:
        if neg_word in prefix:
            # 检查否定词是否紧邻关键词（10个字符内）
            last_neg_pos = prefix.rfind(neg_word)
            if keyword_position - last_neg_pos <= 10:
                return True

    return False


def get_context_boost(keywords: List[str], domain: str) -> float:
    """
    计算上下文增强分数

    Args:
        keywords: 匹配的关键词列表
        domain: 领域分类

    Returns:
        上下文增强分数 (0.0 - 0.2)
    """
    boost_words = CONTEXT_BOOST_WORDS.get(domain, [])
    if not boost_words:
        return 0.0

    boost_count = sum(1 for kw in keywords if kw.lower() in [b.lower() for b in boost_words])

    # 每个增强词增加 0.05，最多 0.2
    return min(0.2, boost_count * 0.05)


def get_domain_from_keyword(keyword: str) -> str:
    """
    根据关键词获取领域分类

    Args:
        keyword: 关键词

    Returns:
        领域分类，如果无法确定返回 "general"
    """
    keyword_lower = keyword.lower()
    standard = REVERSE_SYNONYM_MAP.get(keyword_lower, keyword_lower)

    return DOMAIN_CATEGORY_MAP.get(standard, DOMAIN_CATEGORY_MAP.get(keyword_lower, "general"))