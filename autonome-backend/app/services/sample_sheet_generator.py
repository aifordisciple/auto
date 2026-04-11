"""
Sample Sheet Generator Service - 样本表自动生成与处理服务

提供以下核心功能：
1. 扫描 FastQ 目录，自动配对双端测序数据
2. 扫描单细胞数据目录，识别 10x/h5/BD 等格式
3. 从样本名自动推断分组标签
4. 生成 TSV 格式的 Sample Sheet

支持的 FastQ 配对模式：
- _R1/_R2
- _1/_2
- .R1/.R2

支持的单细胞数据格式：
- 10x: 目录包含 filtered_feature_bc_matrix/
- h5: 文件后缀 .h5
- BD: 文件名含 _RSEC_MolsPerCell
- exp: 表达矩阵文件 .tsv/.csv
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from app.core.logger import log


# ==========================================
# 数据结构定义
# ==========================================

class SampleEntry:
    """单个样本条目"""

    def __init__(
        self,
        name: str,
        path: str,
        data_type: str = "unknown",
        group: str = "default",
        read2_path: Optional[str] = None
    ):
        self.name = name
        self.path = path
        self.data_type = data_type
        self.group = group
        self.read2_path = read2_path  # 仅用于 FastQC 双端数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "path": self.path,
            "data_type": self.data_type,
            "group": self.group,
            "read2_path": self.read2_path
        }


class ComparisonGroupEntry:
    """
    比较组条目

    用于定义差异分析中的比较组组合，如：
    - Treatment vs Control
    - Treat_A vs Control
    - Drug_High vs Drug_Low

    每个比较组包含：
    - case_group: 实验组/处理组（如 Treatment）
    - control_group: 对照组（如 Control）
    - comparison_name: 比较组名称，格式：{case}_vs_{control}
    """

    def __init__(
        self,
        case_group: str,
        control_group: str,
        comparison_name: Optional[str] = None
    ):
        self.case_group = case_group
        self.control_group = control_group
        # 自动生成比较组名称，格式：{case}_vs_{control}
        self.comparison_name = comparison_name or f"{case_group}_vs_{control_group}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "case_group": self.case_group,
            "control_group": self.control_group,
            "comparison_name": self.comparison_name
        }

    def __repr__(self) -> str:
        return f"ComparisonGroupEntry({self.comparison_name}: {self.case_group} vs {self.control_group})"


class SampleSheetGenerator:
    """
    Sample Sheet 自动生成器

    支持两种主要模式：
    1. FastQC 模式：扫描 FastQ 文件，自动配对双端数据
    2. 单细胞模式：扫描单细胞数据目录，识别多种格式
    """

    # FastQ 文件扩展名
    FASTQ_EXTENSIONS = {'.fastq', '.fq', '.fastq.gz', '.fq.gz'}

    # 分组推断关键词
    CONTROL_KEYWORDS = ['control', 'ctrl', 'normal', 'healthy', 'untreated', 'wildtype', 'wt']
    TREATMENT_KEYWORDS = ['treat', 'treatment', 'drug', 'tumor', 'cancer', 'disease', 'mutant', 'ko', 'kd']

    def __init__(self):
        """初始化生成器"""
        log.info("[SampleSheetGenerator] 初始化 Sample Sheet 生成器")

    # ==========================================
    # FastQ 扫描与配对
    # ==========================================

    def scan_fastq_directory(
        self,
        directory: str,
        recursive: bool = True,
        auto_pair: bool = True
    ) -> List[SampleEntry]:
        """
        扫描 FastQ 目录，自动配对双端数据

        Args:
            directory: 要扫描的目录路径
            recursive: 是否递归扫描子目录
            auto_pair: 是否自动配对双端数据

        Returns:
            SampleEntry 列表
        """
        log.info(f"[SampleSheetGenerator] 扫描 FastQ 目录: {directory}")

        if not os.path.exists(directory):
            log.error(f"目录不存在: {directory}")
            return []

        if not os.path.isdir(directory):
            log.error(f"路径不是目录: {directory}")
            return []

        # 收集所有 FastQ 文件
        fastq_files = self._collect_fastq_files(directory, recursive)
        log.info(f"发现 {len(fastq_files)} 个 FastQ 文件")

        if auto_pair:
            # 自动配对双端数据
            samples = self._pair_fastq_files(fastq_files)
        else:
            # 不配对，每个文件作为单独样本
            samples = self._create_single_samples(fastq_files)

        # 自动推断分组
        self._infer_groups(samples)

        log.info(f"生成 {len(samples)} 个样本条目")
        return samples

    def _collect_fastq_files(self, directory: str, recursive: bool) -> List[str]:
        """
        收集目录中所有的 FastQ 文件

        Args:
            directory: 目录路径
            recursive: 是否递归扫描

        Returns:
            FastQ 文件路径列表
        """
        fastq_files = []

        if recursive:
            for root, dirs, files in os.walk(directory):
                # 跳过隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for file in files:
                    if self._is_fastq_file(file):
                        fastq_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path) and self._is_fastq_file(file):
                    fastq_files.append(file_path)

        return sorted(fastq_files)

    def _is_fastq_file(self, filename: str) -> bool:
        """检查文件是否为 FastQ 格式"""
        filename_lower = filename.lower()
        return any(filename_lower.endswith(ext) for ext in self.FASTQ_EXTENSIONS)

    def _pair_fastq_files(self, fastq_files: List[str]) -> List[SampleEntry]:
        """
        自动配对双端 FastQ 文件

        配对策略：
        1. 尝试匹配 _R1/_R2、_1/_2、.R1/.R2 等模式
        2. 未匹配的文件作为单端数据

        Args:
            fastq_files: FastQ 文件路径列表

        Returns:
            SampleEntry 列表
        """
        samples = []
        paired = set()  # 已配对的文件索引

        # 将文件名映射到索引
        file_basenames = [os.path.basename(f) for f in fastq_files]

        # 配对模式定义：R1 标记 -> 对应的 R2 标记
        # 使用简单的字符串查找，避免复杂的正则替换
        r1_markers = ['_R1', '_1', '.R1', '_r1', '.r1']
        r2_markers = ['_R2', '_2', '.R2', '_r2', '.r2']

        for i, filepath in enumerate(fastq_files):
            if i in paired:
                continue

            basename = file_basenames[i]
            sample_name = self._extract_sample_name(basename)

            # 尝试找到配对文件
            paired_file = None
            paired_idx = None

            # 检查当前文件是否包含 R1 标记
            for j, r1_marker in enumerate(r1_markers):
                r2_marker = r2_markers[j]

                if r1_marker in basename:
                    # 构造 R2 文件名（简单字符串替换）
                    r2_basename = basename.replace(r1_marker, r2_marker)
                    if r2_basename in file_basenames:
                        paired_idx = file_basenames.index(r2_basename)
                        paired_file = fastq_files[paired_idx]
                        break

            # 如果没找到 R1 标记，检查是否是 R2
            if not paired_file:
                for j, r2_marker in enumerate(r2_markers):
                    r1_marker = r1_markers[j]

                    if r2_marker in basename:
                        # 构造 R1 文件名
                        r1_basename = basename.replace(r2_marker, r1_marker)
                        if r1_basename in file_basenames:
                            paired_idx = file_basenames.index(r1_basename)
                            paired_file = fastq_files[paired_idx]
                            sample_name = self._extract_sample_name(r1_basename)
                            # 交换路径，确保 R1 是主路径
                            filepath = fastq_files[paired_idx]
                            paired_file = fastq_files[i]  # 原来的 R2
                            break

            if paired_file:
                # 双端数据
                samples.append(SampleEntry(
                    name=sample_name,
                    path=filepath,  # R1 作为主路径
                    data_type="paired",
                    read2_path=paired_file
                ))
                paired.add(i)
                paired.add(paired_idx)
            else:
                # 单端数据
                samples.append(SampleEntry(
                    name=sample_name,
                    path=filepath,
                    data_type="single",
                    read2_path=None
                ))
                paired.add(i)

        return samples

    def _create_single_samples(self, fastq_files: List[str]) -> List[SampleEntry]:
        """将每个文件作为单独样本"""
        samples = []
        for filepath in fastq_files:
            basename = os.path.basename(filepath)
            sample_name = self._extract_sample_name(basename)
            samples.append(SampleEntry(
                name=sample_name,
                path=filepath,
                data_type="single",
                read2_path=None
            ))
        return samples

    def _extract_sample_name(self, filename: str) -> str:
        """
        从 FastQ 文件名中提取样本名

        移除常见的后缀模式：
        - _R1, _R2, _1, _2, .R1, .R2
        - 扩展名
        """
        name = filename

        # 移除扩展名
        for ext in sorted(self.FASTQ_EXTENSIONS, key=len, reverse=True):
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break

        # 移除配对后缀（使用简单字符串替换，避免正则表达式问题）
        # 按长度降序排列，确保先匹配更长的模式（如 _R1 优于 _1）
        markers = ['_R1', '_R2', '_1', '_2', '.R1', '.R2', '_r1', '_r2', '.r1', '.r2']
        for marker in markers:
            if marker in name:
                name = name.replace(marker, '')
                break  # 只移除第一个匹配的标记

        # 移除尾部下划线或点号
        name = name.rstrip('_.')

        return name or filename

    # ==========================================
    # 单细胞数据扫描
    # ==========================================

    def scan_singlecell_directory(
        self,
        directory: str,
        recursive: bool = True
    ) -> Tuple[List[SampleEntry], List[str]]:
        """
        扫描单细胞数据目录，识别多种格式

        支持格式：
        - 10x: 目录包含 filtered_feature_bc_matrix/
        - h5: .h5 文件
        - BD: *_RSEC_MolsPerCell.csv 文件
        - exp: 表达矩阵 .tsv/.csv 文件

        Args:
            directory: 要扫描的目录路径
            recursive: 是否递归扫描子目录

        Returns:
            (SampleEntry 列表, 警告信息列表)
        """
        log.info(f"[SampleSheetGenerator] 扫描单细胞目录: {directory}")

        if not os.path.exists(directory):
            log.error(f"目录不存在: {directory}")
            return [], [f"目录不存在: {directory}"]

        samples = []
        warnings = []

        # ==========================================
        # 首先检测是否有 FastQ 文件（常见错误场景）
        # 用户可能选择了错误的技能类型
        # ==========================================
        fastq_files = self._collect_fastq_files(directory, recursive)
        if fastq_files:
            fastq_count = len(fastq_files)
            log.info(f"[SampleSheetGenerator] 检测到 {fastq_count} 个 FastQ 文件，但当前是单细胞扫描模式")
            warnings.append(
                f"检测到 {fastq_count} 个 FastQ 文件，但这些文件不会被单细胞流程识别。"
                f"如需处理 FastQ 数据，请选择 FastQC/质量控制 技能。"
            )

        if recursive:
            for root, dirs, files in os.walk(directory):
                # 跳过隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                # 检测 10x 格式（目录）
                for d in dirs:
                    matrix_path = os.path.join(root, d, "filtered_feature_bc_matrix")
                    if os.path.exists(matrix_path):
                        samples.append(SampleEntry(
                            name=d,
                            path=matrix_path,
                            data_type="10x"
                        ))

                # 检测其他格式（文件）
                for f in files:
                    filepath = os.path.join(root, f)
                    sample = self._detect_singlecell_file(filepath)
                    if sample:
                        samples.append(sample)
        else:
            items = os.listdir(directory)
            for item in items:
                item_path = os.path.join(directory, item)

                if os.path.isdir(item_path):
                    # 检测 10x 格式
                    matrix_path = os.path.join(item_path, "filtered_feature_bc_matrix")
                    if os.path.exists(matrix_path):
                        samples.append(SampleEntry(
                            name=item,
                            path=matrix_path,
                            data_type="10x"
                        ))
                else:
                    # 检测文件格式
                    sample = self._detect_singlecell_file(item_path)
                    if sample:
                        samples.append(sample)

        # 自动推断分组
        self._infer_groups(samples)

        log.info(f"发现 {len(samples)} 个单细胞样本")
        return samples, warnings

    def _detect_singlecell_file(self, filepath: str) -> Optional[SampleEntry]:
        """
        检测单细胞数据文件格式

        Args:
            filepath: 文件路径

        Returns:
            SampleEntry 或 None
        """
        filename = os.path.basename(filepath)
        filename_lower = filename.lower()

        # 提取样本名
        sample_name = os.path.splitext(filename)[0]

        # h5 格式
        if filename_lower.endswith('.h5'):
            return SampleEntry(
                name=sample_name,
                path=filepath,
                data_type="h5"
            )

        # BD 格式
        if '_RSEC_MolsPerCell' in filename and filename_lower.endswith('.csv'):
            return SampleEntry(
                name=sample_name.replace('_RSEC_MolsPerCell', ''),
                path=filepath,
                data_type="BD"
            )

        # RDS 格式
        if filename_lower.endswith('.rds'):
            data_type = "rdsraw" if "_raw" in filename_lower else "rds"
            return SampleEntry(
                name=sample_name,
                path=filepath,
                data_type=data_type
            )

        # 表达矩阵 (TSV/CSV)
        if filename_lower.endswith('.tsv') or filename_lower.endswith('.csv'):
            # 排除已识别的 BD 文件
            if '_RSEC_MolsPerCell' not in filename:
                return SampleEntry(
                    name=sample_name,
                    path=filepath,
                    data_type="exp"
                )

        return None

    # ==========================================
    # 分组推断
    # ==========================================

    def _infer_groups(self, samples: List[SampleEntry]) -> None:
        """
        从样本名自动推断分组标签

        规则：
        - 包含 Control/Ctrl/Normal → Control
        - 包含 Treat/Drug/Tumor → Treat
        - 其他 → 保留原值或设为 "default"
        """
        for sample in samples:
            name_lower = sample.name.lower()

            # 检查 Control 关键词
            for kw in self.CONTROL_KEYWORDS:
                if kw in name_lower:
                    sample.group = "Control"
                    break
            else:
                # 检查 Treatment 关键词
                for kw in self.TREATMENT_KEYWORDS:
                    if kw in name_lower:
                        sample.group = "Treat"
                        break
                else:
                    # 未匹配，保留 default
                    if sample.group == "default":
                        sample.group = ""

    # ==========================================
    # TSV 生成
    # ==========================================

    def generate_fastqc_tsv(self, samples: List[SampleEntry], include_header: bool = True) -> str:
        """
        生成 FastQC 格式的 Sample Sheet TSV

        格式：
        sample_name    read1_path    read2_path

        Args:
            samples: SampleEntry 列表
            include_header: 是否包含表头

        Returns:
            TSV 格式字符串
        """
        lines = []

        if include_header:
            lines.append("sample_name\tread1_path\tread2_path")

        for sample in samples:
            row = [
                sample.name,
                sample.path,
                sample.read2_path or ""
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def generate_singlecell_tsv(self, samples: List[SampleEntry], include_header: bool = True) -> str:
        """
        生成单细胞格式的 Sample Sheet TSV

        格式：
        sample_name    input_path    input_format    group_label

        Args:
            samples: SampleEntry 列表
            include_header: 是否包含表头

        Returns:
            TSV 格式字符串
        """
        lines = []

        if include_header:
            lines.append("sample_name\tinput_path\tinput_format\tgroup_label")

        for sample in samples:
            row = [
                sample.name,
                sample.path,
                sample.data_type,
                sample.group
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    # ==========================================
    # 列配置获取
    # ==========================================

    def get_column_config(self, skill_type: str) -> List[Dict[str, Any]]:
        """
        获取指定 SKILL 类型的列配置

        Args:
            skill_type: SKILL 类型，如 "fastqc" 或 "singlecell"

        Returns:
            列配置列表
        """
        if "fastqc" in skill_type.lower():
            return [
                {"key": "sample_name", "label": "样本名", "required": True, "editable": True},
                {"key": "read1_path", "label": "Read1 路径", "required": True, "editable": True},
                {"key": "read2_path", "label": "Read2 路径", "required": False, "editable": True}
            ]
        elif "singlecell" in skill_type.lower() or "single_cell" in skill_type.lower():
            return [
                {"key": "sample_name", "label": "样本名", "required": True, "editable": True},
                {"key": "input_path", "label": "输入路径", "required": True, "editable": True},
                {"key": "input_format", "label": "数据格式", "required": True, "editable": True,
                 "options": ["10x", "exp", "h5", "BD", "rds", "rdsraw"]},
                {"key": "group_label", "label": "分组标签", "required": True, "editable": True}
            ]
        else:
            # 默认通用格式
            return [
                {"key": "sample_name", "label": "样本名", "required": True, "editable": True},
                {"key": "path", "label": "路径", "required": True, "editable": True},
                {"key": "type", "label": "类型", "required": False, "editable": True},
                {"key": "group", "label": "分组", "required": False, "editable": True}
            ]

    # ==========================================
    # 工具方法
    # ==========================================

    def validate_tsv_content(self, content: str, skill_type: str) -> Dict[str, Any]:
        """
        验证 TSV 内容的有效性

        Args:
            content: TSV 内容
            skill_type: SKILL 类型

        Returns:
            验证结果 {"valid": bool, "errors": [], "warnings": [], "row_count": int}
        """
        errors = []
        warnings = []
        lines = [l.strip() for l in content.strip().split("\n") if l.strip() and not l.startswith("#")]

        if not lines:
            return {"valid": False, "errors": ["文件内容为空"], "warnings": [], "row_count": 0}

        # 解析表头
        header = lines[0].split("\t")
        row_count = len(lines) - 1

        # 检查列数一致性
        for i, line in enumerate(lines[1:], start=2):
            cols = line.split("\t")
            if len(cols) != len(header):
                errors.append(f"第 {i} 行列数不匹配：期望 {len(header)} 列，实际 {len(cols)} 列")

        # 检查必填列
        required_cols = self._get_required_columns(skill_type)
        for col in required_cols:
            if col not in header:
                errors.append(f"缺少必填列: {col}")

        # 检查样本名唯一性
        sample_col_idx = None
        for i, col in enumerate(header):
            if col in ["sample_name", "name", "sample"]:
                sample_col_idx = i
                break

        if sample_col_idx is not None:
            sample_names = []
            for line in lines[1:]:
                cols = line.split("\t")
                if len(cols) > sample_col_idx:
                    sample_names.append(cols[sample_col_idx])

            duplicates = [n for n in set(sample_names) if sample_names.count(n) > 1]
            if duplicates:
                errors.append(f"样本名重复: {', '.join(duplicates)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "row_count": row_count
        }

    def _get_required_columns(self, skill_type: str) -> List[str]:
        """获取指定 SKILL 类型的必填列"""
        if "fastqc" in skill_type.lower():
            return ["sample_name", "read1_path"]
        elif "singlecell" in skill_type.lower():
            return ["sample_name", "input_path", "input_format"]
        else:
            return ["sample_name"]

    # ==========================================
    # 比较组生成与处理
    # ==========================================

    # 对照组识别关键词（用于自动推断时排序）
    CONTROL_GROUP_KEYWORDS = ['control', 'ctrl', 'normal', 'healthy', 'wildtype', 'wt', 'untreated', 'baseline', 'reference', 'ref']

    def infer_comparison_groups(self, groups: List[str]) -> List[ComparisonGroupEntry]:
        """
        从分组列表自动推断所有可能的比较组组合

        推断规则：
        1. 将分组排序，control 类分组优先排在前面
        2. 生成所有两两组合，格式为 {later_group}_vs_{earlier_group}
        3. 这样确保 control 组作为对照组（如 Treatment_vs_Control）

        Args:
            groups: 分组名称列表（来自 sample_sheet 的 group_label 列）

        Returns:
            比较组条目列表
        """
        if not groups:
            return []

        # 过滤空值并去重
        unique_groups = [g for g in groups if g and g.strip()]
        unique_groups = list(set(unique_groups))

        if len(unique_groups) < 2:
            log.warning(f"[SampleSheetGenerator] 分组数量不足，无法生成比较组: {unique_groups}")
            return []

        # 将分组排序，control 类分组优先排在前面
        # 排序规则：包含 control 关键词的分组排前面
        sorted_groups = sorted(
            unique_groups,
            key=lambda g: (
                # 包含 control 关键词的分组排前面（返回 0）
                0 if any(kw in g.lower() for kw in self.CONTROL_GROUP_KEYWORDS) else 1,
                # 同级别按字母顺序排列
                g.lower()
            )
        )

        log.info(f"[SampleSheetGenerator] 分组排序结果: {sorted_groups}")

        # 生成所有两两组合
        # 格式：{后组}_vs_{前组}，前组作为对照组
        comparisons = []
        for i in range(len(sorted_groups)):
            for j in range(i + 1, len(sorted_groups)):
                # sorted_groups[i] 是对照组（排在前面）
                # sorted_groups[j] 是实验组（排在后面）
                comparisons.append(ComparisonGroupEntry(
                    case_group=sorted_groups[j],
                    control_group=sorted_groups[i]
                ))

        log.info(f"[SampleSheetGenerator] 自动推断生成 {len(comparisons)} 个比较组")
        return comparisons

    def validate_comparison_groups(
        self,
        comparisons: List[ComparisonGroupEntry],
        available_groups: List[str]
    ) -> Dict[str, Any]:
        """
        验证比较组的有效性

        检查项：
        1. case_group 和 control_group 是否在可用分组中
        2. 比较组是否重复（相同的 case-control 组合）
        3. 比较组名称是否规范（不包含特殊字符）
        4. case_group 和 control_group 不能相同

        Args:
            comparisons: 比较组列表
            available_groups: 可用的分组列表

        Returns:
            验证结果 {"valid": bool, "errors": [], "warnings": []}
        """
        errors = []
        warnings = []

        # 过滤空值并去重可用分组
        valid_groups = [g for g in available_groups if g and g.strip()]
        valid_groups = list(set(valid_groups))

        # 用于检查重复的组合集合
        seen_combinations = set()

        for comp in comparisons:
            # 检查分组是否存在
            if comp.case_group not in valid_groups:
                errors.append(f"实验组 '{comp.case_group}' 不存在于样本分组中（可用分组: {valid_groups}）")
            if comp.control_group not in valid_groups:
                errors.append(f"对照组 '{comp.control_group}' 不存在于样本分组中（可用分组: {valid_groups}）")

            # 检查 case 和 control 是否相同
            if comp.case_group == comp.control_group:
                errors.append(f"比较组 '{comp.comparison_name}' 的实验组和对照组相同")

            # 检查组合是否重复
            combination_key = f"{comp.case_group}|{comp.control_group}"
            if combination_key in seen_combinations:
                errors.append(f"比较组组合重复: {comp.case_group} vs {comp.control_group}")
            seen_combinations.add(combination_key)

            # 检查比较组名称是否规范
            if not comp.comparison_name or not comp.comparison_name.strip():
                warnings.append(f"比较组 '{comp.case_group} vs {comp.control_group}' 缺少名称")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "total_comparisons": len(comparisons)
        }

    def generate_comparison_tsv(
        self,
        comparisons: List[ComparisonGroupEntry],
        include_header: bool = True
    ) -> str:
        """
        生成比较组 TSV 文件内容

        TSV 格式：
        case_group    control_group    comparison_name

        Args:
            comparisons: 比较组列表
            include_header: 是否包含表头

        Returns:
            TSV 格式字符串
        """
        lines = []

        if include_header:
            lines.append("# Comparison Table - 比较组定义表")
            lines.append("# case_group\tcontrol_group\tcomparison_name")

        for comp in comparisons:
            row = [
                comp.case_group,
                comp.control_group,
                comp.comparison_name
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def parse_comparison_tsv(self, content: str) -> List[ComparisonGroupEntry]:
        """
        解析比较组 TSV 文件内容

        Args:
            content: TSV 文件内容

        Returns:
            比较组列表
        """
        comparisons = []
        lines = content.strip().split("\n")

        for line in lines:
            # 跳过注释行和空行
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 2:
                case_group = parts[0].strip()
                control_group = parts[1].strip()
                # 第三列为比较组名称（可选）
                comparison_name = parts[2].strip() if len(parts) >= 3 else None

                if case_group and control_group:
                    comparisons.append(ComparisonGroupEntry(
                        case_group=case_group,
                        control_group=control_group,
                        comparison_name=comparison_name
                    ))

        log.info(f"[SampleSheetGenerator] 解析 TSV 得到 {len(comparisons)} 个比较组")
        return comparisons

    def extract_groups_from_sample_sheet(self, sample_sheet_content: str) -> List[str]:
        """
        从 Sample Sheet 内容中提取分组列表

        查找 group_label 或 group 列，提取所有唯一的分组值

        Args:
            sample_sheet_content: Sample Sheet TSV 内容

        Returns:
            分组名称列表
        """
        groups = []
        lines = sample_sheet_content.strip().split("\n")

        if not lines:
            return groups

        # 解析表头
        header = lines[0].split("\t")

        # 查找分组列索引
        group_col_idx = None
        for i, col in enumerate(header):
            col_lower = col.lower().strip()
            if col_lower in ["group_label", "group", "grouplabel", "分组"]:
                group_col_idx = i
                break

        if group_col_idx is None:
            log.warning("[SampleSheetGenerator] Sample Sheet 中未找到分组列")
            return groups

        # 提取所有分组值
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) > group_col_idx:
                group_value = parts[group_col_idx].strip()
                if group_value and group_value not in groups:
                    groups.append(group_value)

        log.info(f"[SampleSheetGenerator] 从 Sample Sheet 提取到 {len(groups)} 个分组: {groups}")
        return groups


# ==========================================
# 全局实例
# ==========================================

_generator_instance = None

def get_sample_sheet_generator() -> SampleSheetGenerator:
    """获取全局 SampleSheetGenerator 实例"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = SampleSheetGenerator()
    return _generator_instance