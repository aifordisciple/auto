"""
语义化目录命名系统核心模块

命名公式: [YYYYMMDD]_[HHMMSS]_[SKILL_NAME]_[TASK_ALIAS]_[SHORT_ID]
蓝图级联: [BLUEPRINT_ID]/Step_[0X]_[SKILL_NAME]_[SHORT_ID]

设计原则：
- 时间戳前缀确保文件系统按字母排序 = 按时间排序
- 语义化组件让用户无需打开文件夹即可理解内容
- short_id 提供唯一性保障和数据库关联线索
- 严格 sanitization 防止非法字符
"""

import re
import os
from datetime import datetime
from typing import Optional, Union
from loguru import logger


# ============================================================================
# 常量定义
# ============================================================================

# 目录名最大长度（文件系统限制）
MAX_DIR_NAME_LENGTH = 255

# 各组件最大长度（保守值）
MAX_ALIAS_LENGTH = 50
MAX_SHORT_ID_LENGTH = 8

# 合法字符集（只允许字母、数字、下划线、连字符）
VALID_CHARS_PATTERN = re.compile(r"[a-zA-Z0-9_-]")

# 默认 alias（当无法生成时使用）
DEFAULT_ALIAS = "analysis"

# 需要去除的冗余前缀（简化命名）
STRIP_PREFIXES = ["skill_", "task_", "tool_", "blueprint_", "step_"]


# ============================================================================
# 核心函数：单任务语义化命名
# ============================================================================

def generate_semantic_dir_name(
    skill_id: str,
    task_id: str,
    task_alias: Optional[str] = None,
    user_message: Optional[str] = None,
    timestamp: Optional[Union[datetime, float, int]] = None,
) -> str:
    """
    生成单任务的语义化目录名称

    简化格式: YYYYMMDD_HHMMSS_ALIAS_SHORTID
    去除冗余的 skill_ 和 task_ 前缀，只保留核心语义。

    Args:
        skill_id: 技能包 ID（仅用于提取语义，不直接出现在名称中）
        task_id: 任务 UUID 或唯一标识
        task_alias: 用户提供的任务别名（可选）
        user_message: 用户原始意图文本（用于自动生成 alias）
        timestamp: 时间戳（datetime 对象或 Unix timestamp）

    Returns:
        语义化目录名：YYYYMMDD_HHMMSS_ALIAS_SHORTID

    Example:
        >>> generate_semantic_dir_name(
        ...     skill_id="skill_cd22f007",  # 自动去除 skill_ 前缀
        ...     task_id="f5b96e12-3456-7890-abcd-ef1234567890",
        ...     task_alias="task_tl9yipl4",  # 自动去除 task_ 前缀
        ...     timestamp=datetime(2026, 4, 2, 14, 9, 53)
        ... )
        "20260402_140953_tl9yipl4_f5b96e"
    """
    # 1. 处理时间戳
    if timestamp is None:
        timestamp = datetime.now()
    elif isinstance(timestamp, (int, float)):
        timestamp = datetime.fromtimestamp(timestamp)

    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")

    # 2. 提取语义别名（优先使用 task_alias，其次从 skill_id 或 user_message 提取）
    if task_alias:
        # 去除冗余前缀
        clean_alias = _strip_redundant_prefixes(task_alias)
        safe_alias = sanitize_name_component(clean_alias, max_length=MAX_ALIAS_LENGTH)
    elif user_message:
        # 从用户意图自动生成 alias
        safe_alias = generate_task_alias_from_intent(user_message)
    else:
        # 从 skill_id 提取语义部分
        clean_skill = _strip_redundant_prefixes(skill_id)
        safe_alias = sanitize_name_component(clean_skill, max_length=MAX_ALIAS_LENGTH)

    # 如果 alias 为空，使用默认值
    if not safe_alias:
        safe_alias = DEFAULT_ALIAS

    # 3. 提取 short_id
    short_id = extract_short_id(task_id)

    # 4. 组装完整名称（简化格式：TIMESTAMP_ALIAS_SHORTID）
    full_name = f"{ts_str}_{safe_alias}_{short_id}"

    # 5. 最终长度检查（兜底截断）
    if len(full_name) > MAX_DIR_NAME_LENGTH:
        excess = len(full_name) - MAX_DIR_NAME_LENGTH
        safe_alias = safe_alias[:max(10, len(safe_alias) - excess)]
        full_name = f"{ts_str}_{safe_alias}_{short_id}"

    logger.debug(f"Generated semantic dir name: {full_name}")
    return full_name


def _strip_redundant_prefixes(name: str) -> str:
    """
    去除冗余的前缀（skill_, task_, tool_ 等）

    Args:
        name: 原始名称

    Returns:
        清理后的名称

    Example:
        >>> _strip_redundant_prefixes("skill_cd22f007")
        "cd22f007"
        >>> _strip_redundant_prefixes("task_tl9yipl4")
        "tl9yipl4"
    """
    if not name:
        return name

    name_lower = name.lower()
    for prefix in STRIP_PREFIXES:
        if name_lower.startswith(prefix):
            return name[len(prefix):]

    return name


# ============================================================================
# 核心函数：蓝图级联命名
# ============================================================================

def generate_blueprint_root_name(
    blueprint_alias: str,
    blueprint_id: str,
    timestamp: Optional[Union[datetime, float, int]] = None,
) -> str:
    """
    生成蓝图根目录名称

    Args:
        blueprint_alias: 蓝图名称/目标描述（如 RNA_Seq_Pipeline）
        blueprint_id: 蓝图唯一标识
        timestamp: 时间戳

    Returns:
        蓝图根目录名：YYYYMMDD_HHMMSS_BLUEPRINT_ALIAS_SHORTID

    Example:
        >>> generate_blueprint_root_name(
        ...     blueprint_alias="RNA_Seq_Pipeline",
        ...     blueprint_id="pipeline_a_12345678",
        ...     timestamp=datetime(2026, 4, 2, 14, 30, 52)
        ... )
        "20260402_143052_RNA_Seq_Pipeline_a1b2c3"
    """
    # 处理时间戳
    if timestamp is None:
        timestamp = datetime.now()
    elif isinstance(timestamp, (int, float)):
        timestamp = datetime.fromtimestamp(timestamp)

    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")

    # 清理蓝图名称
    safe_alias = sanitize_name_component(blueprint_alias, max_length=MAX_ALIAS_LENGTH)

    # 提取 short_id（从 blueprint_id）
    short_id = extract_short_id(blueprint_id, length=6)

    full_name = f"{ts_str}_{safe_alias}_{short_id}"

    # 长度检查
    if len(full_name) > MAX_DIR_NAME_LENGTH:
        safe_alias = safe_alias[:MAX_DIR_NAME_LENGTH - len(ts_str) - len(short_id) - 2]
        full_name = f"{ts_str}_{safe_alias}_{short_id}"

    return full_name


def generate_step_dir_name(
    step_number: int,
    skill_id: str,
    task_id: str,
) -> str:
    """
    生成蓝图步骤的子目录名称

    Args:
        step_number: 步骤序号（从 1 开始）
        skill_id: 该步骤执行的技能 ID
        task_id: 步骤任务 ID

    Returns:
        步骤目录名：Step_XX_SKILL_SHORTID

    Example:
        >>> generate_step_dir_name(
        ...     step_number=1,
        ...     skill_id="fastqc_multiqc_01",
        ...     task_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        ... )
        "Step_01_fastqc_multiqc_01_a1b2c3"
    """
    # 格式化步骤号（两位数字，01-99）
    step_str = f"{step_number:02d}"

    # 清理 skill_id（去除冗余前缀）
    clean_skill = _strip_redundant_prefixes(skill_id)
    safe_skill = sanitize_name_component(clean_skill, max_length=MAX_ALIAS_LENGTH)

    # 提取 short_id
    short_id = extract_short_id(task_id)

    return f"Step_{step_str}_{safe_skill}_{short_id}"


# ============================================================================
# 辅助函数：名称清理
# ============================================================================

def sanitize_name_component(
    name: Optional[str],
    max_length: Optional[int] = None,
) -> str:
    """
    清理名称组件，只保留合法字符

    Args:
        name: 原始名称（可能包含非法字符）
        max_length: 最大长度限制（可选）

    Returns:
        清理后的安全名称

    Rules:
        - 空格转换为下划线
        - 移除所有非 [a-zA-Z0-9_-] 字符
        - 转换为小写（保持一致性）
        - 截断至指定长度
        - 空输入返回空字符串
    """
    if not name:
        return ""

    # 1. 空格转下划线
    name = name.replace(" ", "_")

    # 2. 只保留合法字符
    name = "".join(c for c in name if VALID_CHARS_PATTERN.match(c))

    # 3. 转换为小写
    name = name.lower()

    # 4. 去除连续下划线
    while "__" in name:
        name = name.replace("__", "_")

    # 5. 去除首尾下划线
    name = name.strip("_")

    # 6. 截断至指定长度
    if max_length and len(name) > max_length:
        name = name[:max_length]

    return name


# ============================================================================
# 辅助函数：short_id 提取
# ============================================================================

def extract_short_id(
    task_id: str,
    length: int = 6,
) -> str:
    """
    从任务 ID 提取短 ID

    Args:
        task_id: 完整任务 ID（通常为 UUID）
        length: 提取长度（默认 6）

    Returns:
        短 ID（前 length 位字符）

    Example:
        >>> extract_short_id("557a24fd-9bf4-4db7-80d8-cb159f66c31e")
        "557a24"
    """
    if not task_id:
        return "unknown"

    # 直接取前 N 位
    return task_id[:length]


# ============================================================================
# 辅助函数：AI 别名生成
# ============================================================================

# ============================================================================
# 辅助函数：分类名称英文映射
# ============================================================================

# 分类名称到英文关键词的映射表
CATEGORY_TO_ENGLISH_MAP = {
    # 一级分类
    "质量控制": "qc",
    "比对": "alignment",
    "定量": "quantification",
    "差异分析": "diff_analysis",
    "注释": "annotation",
    "变异检测": "variant",
    "单细胞": "singlecell",
    "转录组": "rnaseq",
    "基因组": "genome",
    "蛋白质组": "proteomics",
    "代谢组": "metabolomics",
    "可视化": "visualization",
    "统计": "statistics",
    # 二级分类
    "FastQ质控": "fastqc",
    "BAM质控": "bamqc",
    "RNA比对": "rna_alignment",
    "DNA比对": "dna_alignment",
    "基因定量": "gene_quant",
    "转录本定量": "transcript_quant",
    "基因差异": "gene_diff",
    "转录本差异": "transcript_diff",
    "功能注释": "functional_annotation",
    "基因组注释": "genome_annotation",
    "SNP检测": "snp",
    "CNV检测": "cnv",
    "SV检测": "sv",
    "细胞聚类": "cell_clustering",
    "细胞注释": "cell_annotation",
    "轨迹分析": "trajectory",
}

# 生物信息学常见工具关键词
BIO_TOOL_KEYWORDS = [
    "fastqc", "multiqc", "deseq2", "hisat2", "star", "bowtie", "bowtie2",
    "featurecounts", "seurat", "scanpy", "salmon", "kallisto", "gatk",
    "bwa", "samtools", "bcftools", "vcftools", "annovar", "snpeff",
    "cufflinks", "stringtie", "htseq", "edgeR", "limma", "monocle",
    "cellranger", "scvelo", "infercnv", "copykat", "singlecell",
    "rnaseq", "dna_seq", "exome", "wes", "wgs", "chip_seq", "atac_seq",
]


def extract_semantic_from_metadata(
    skill_name: Optional[str] = None,
    skill_id: Optional[str] = None,
    category_name: Optional[str] = None,
    subcategory_name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """
    从技能元数据中提取语义别名

    多级 fallback 优先级：
    1. 技能名称中的英文关键词
    2. 分类名称的英文映射
    3. 子分类名称的英文映射
    4. 技能描述中的生物工具关键词
    5. skill_id 的语义部分（去除前缀后判断是否有元音）

    Args:
        skill_name: 技能显示名称（可能包含中文）
        skill_id: 技能唯一 ID（可能是随机字符串）
        category_name: 一级分类名称（如"质量控制"）
        subcategory_name: 二级分类名称（如"FastQ质控"）
        description: 技能描述文本

    Returns:
        提取的语义别名（英文 snake_case 格式）

    Example:
        >>> extract_semantic_from_metadata(
        ...     skill_name="原始测序数据质量控制",
        ...     skill_id="skill_go9ibaef",
        ...     category_name="质量控制",
        ...     subcategory_name="FastQ质控"
        ... )
        "qc_fastqc"
    """
    semantic_candidates = []

    # 1. 技能名称中的英文关键词（优先）
    if skill_name:
        # 提取英文关键词（至少3个字符）
        english_keywords = re.findall(r"[a-zA-Z]{3,}", skill_name)
        if english_keywords:
            # 过滤常见停用词
            stop_words = {"and", "for", "the", "with", "using", "tool", "pipeline"}
            filtered = [w.lower() for w in english_keywords if w.lower() not in stop_words]
            if filtered:
                semantic_candidates.append("_".join(filtered[:3]))

    # 2. 分类名称的英文映射
    if category_name and category_name in CATEGORY_TO_ENGLISH_MAP:
        semantic_candidates.append(CATEGORY_TO_ENGLISH_MAP[category_name])

    # 3. 子分类名称的英文映射
    if subcategory_name and subcategory_name in CATEGORY_TO_ENGLISH_MAP:
        semantic_candidates.append(CATEGORY_TO_ENGLISH_MAP[subcategory_name])

    # 4. 技能描述中的生物工具关键词
    if description:
        # 提取英文单词（至少4个字符）
        desc_words = re.findall(r"[a-zA-Z]{4,}", description)
        desc_lower = [w.lower() for w in desc_words]
        # 匹配生物工具关键词
        matched = [w for w in desc_lower if w in BIO_TOOL_KEYWORDS]
        if matched:
            semantic_candidates.append(matched[0])

    # 5. skill_id 的语义部分（去除 skill_ 前缀，判断是否有元音）
    if skill_id:
        # 去除常见前缀
        clean_id = skill_id
        for prefix in STRIP_PREFIXES:
            if clean_id.lower().startswith(prefix):
                clean_id = clean_id[len(prefix):]
                break

        # 判断是否为有意义的字符串（包含元音字母）
        if len(clean_id) >= 4:
            clean_lower = clean_id.lower()
            has_vowel = any(c in clean_lower for c in 'aeiou')
            # 如果包含元音，可能是有意义的名称
            if has_vowel:
                semantic_candidates.append(clean_id)

    # 选择最佳语义别名（优先使用第一个候选）
    if semantic_candidates:
        # 组合前两个候选（如果都来自不同来源）
        if len(semantic_candidates) >= 2:
            # 避免重复
            first = semantic_candidates[0]
            second = semantic_candidates[1]
            if first != second and not second.startswith(first):
                combined = f"{first}_{second}"
                # 长度限制
                combined = sanitize_name_component(combined, max_length=MAX_ALIAS_LENGTH)
                return combined
        return sanitize_name_component(semantic_candidates[0], max_length=MAX_ALIAS_LENGTH)

    # 兜底返回默认值
    return DEFAULT_ALIAS


def generate_task_alias_from_intent(
    user_message: Optional[str],
    max_words: int = 4,
) -> str:
    """
    从用户意图文本生成简洁的任务别名

    Args:
        user_message: 用户原始意图描述
        max_words: 别名最大词数（默认 4）

    Returns:
        snake_case 别名（3-4 个关键词）

    Strategy:
        - 提取英文关键词（过滤常见动词）
        - 从中文翻译关键概念（简化处理）
        - 无法提取时返回默认值
    """
    if not user_message:
        return DEFAULT_ALIAS

    # 关键词提取策略
    # 1. 提取英文单词（过滤常见动词）
    stop_words = {
        "run", "perform", "execute", "do", "the", "on", "for", "using",
        "with", "and", "versus", "between", "comparing", "versus", "vs",
        "analysis", "analyze", "process", "data", "samples", "files",
    }

    # 提取英文单词
    english_words = re.findall(r"[a-zA-Z]{3,}", user_message.lower())

    # 过滤停用词
    keywords = [w for w in english_words if w not in stop_words]

    # 特殊关键词优先（生信术语）
    bio_keywords = {
        "fastqc", "multiqc", "deseq2", "hisat2", "star", "bowtie",
        "featurecounts", "qc", "rna", "seq", "rna-seq", "rnaseq",
        "alignment", "expression", "differential", "gene", "genome",
        "quality", "control", "tumor", "normal", "pipeline",
    }

    # 优先保留生信术语
    prioritized = [w for w in keywords if w in bio_keywords]
    remaining = [w for w in keywords if w not in bio_keywords and w not in prioritized]

    # 组合结果
    final_keywords = prioritized + remaining

    # 截断至 max_words
    final_keywords = final_keywords[:max_words]

    # 如果没有提取到关键词，尝试其他策略
    if not final_keywords:
        # 检测中文内容
        chinese_chars = re.findall(r"[一-龥]+", user_message)
        if chinese_chars:
            # 中文关键词简单映射（按重要性排序）
            chinese_map = [
                ("质量控制", "qc"),
                ("测序", "seq"),
                ("比对", "alignment"),
                ("表达", "expression"),
                ("原始", "raw"),
                ("分析", "analysis"),
                ("质量", "qc"),  # 重复条目，用于单独出现时
                ("基因", "gene"),
                ("肿瘤", "tumor"),
                ("正常", "normal"),
                ("样本", "samples"),
            ]
            for cn, en in chinese_map:
                if cn in user_message and en not in final_keywords:
                    final_keywords.append(en)
            final_keywords = final_keywords[:max_words]

    # 兜底
    if not final_keywords:
        return DEFAULT_ALIAS

    # 组合为 snake_case
    alias = "_".join(final_keywords)

    # 最终清理
    alias = sanitize_name_component(alias, max_length=MAX_ALIAS_LENGTH)

    return alias


# ============================================================================
# 实用函数：完整路径生成
# ============================================================================

def get_semantic_output_path(
    project_id: str,
    semantic_dir_name: str,
    base_dir: str = "/workspace",
) -> str:
    """
    获取完整的语义化输出路径

    Args:
        project_id: 项目 ID
        semantic_dir_name: 语义化目录名
        base_dir: 基础上传目录

    Returns:
        完整输出路径：base_dir/project_XXX/results/semantic_name
    """
    return os.path.join(base_dir, f"project_{project_id}", "results", semantic_dir_name)


def ensure_output_directory(
    project_id: str,
    semantic_dir_name: str,
    base_dir: str = "/workspace",
) -> str:
    """
    创建并返回语义化输出目录

    Args:
        project_id: 项目 ID
        semantic_dir_name: 语义化目录名
        base_dir: 基础上传目录

    Returns:
        创建的目录完整路径
    """
    full_path = get_semantic_output_path(project_id, semantic_dir_name, base_dir)
    os.makedirs(full_path, exist_ok=True)
    logger.info(f"Created semantic output directory: {full_path}")
    return full_path