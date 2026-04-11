"""
Sample Table Module - 样本表解析与处理

提供样本表的结构化解析，支持：
- 核心列：name, path, type, group
- 扩展列：自定义元数据（batch, platform 等）
- 自动分组识别
- 向后兼容旧格式
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from pathlib import Path


class SampleInfo(BaseModel):
    """单个样本信息"""

    name: str = Field(..., description="样本名称")
    path: str = Field(..., description="输入文件路径")
    type: str = Field(default="10x", description="数据类型 (10x/exp/BD/h5/rds)")
    group: str = Field(default="default", description="分组标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")

    class Config:
        extra = "allow"


class SampleTable(BaseModel):
    """
    样本表完整数据结构

    支持从 TSV 格式解析，自动构建分组索引和数据集标签。

    Examples:
        >>> tsv = "Sample1\\t/data/s1\\t10x\\tControl\\nSample2\\t/data/s2\\t10x\\tTreatment"
        >>> table = SampleTable.parse(tsv)
        >>> table.groups
        {'Control': ['Sample1'], 'Treatment': ['Sample2']}
    """

    samples: List[SampleInfo] = Field(default_factory=list, description="样本列表")
    groups: Dict[str, List[str]] = Field(
        default_factory=dict, description="分组索引 {group_name: [sample_names]}"
    )
    datasets: Dict[str, List[str]] = Field(
        default_factory=dict, description="数据集索引 {dataset_id: [sample_names]}"
    )
    extended_columns: List[str] = Field(
        default_factory=list, description="扩展列名列表"
    )

    class Config:
        extra = "allow"

    @classmethod
    def parse(cls, content: str, has_header: bool = False) -> "SampleTable":
        """
        解析 TSV 内容为 SampleTable

        Args:
            content: TSV 格式的样本表内容
            has_header: 是否包含表头行（如果为 True，第一行作为列名）

        Returns:
            SampleTable 实例

        TSV 格式:
            # 核心格式（4列）
            Sample1    /data/s1/matrix.tsv    10x    Control

            # 带扩展列
            Sample1    /data/s1/matrix.tsv    10x    Control    B1    NovaSeq

            # 带表头
            name    path    type    group    batch    platform
            Sample1    /data/s1/matrix.tsv    10x    Control    B1    NovaSeq
        """
        # 清理和分割行
        lines = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)

        if not lines:
            return cls()

        # 解析表头（如果有）
        start_idx = 0
        column_names = ["name", "path", "type", "group"]

        if has_header:
            # 检测第一行是否为表头
            first_line_parts = lines[0].split("\t")
            # 如果第一行第一列是 name 或样本名格式，则认为是表头
            if first_line_parts[0].lower() in ["name", "sample", "sample_name", "sample_name"]:
                column_names = [c.strip() for c in first_line_parts]
                start_idx = 1

        # 确定扩展列
        extended_columns = []
        if len(column_names) > 4:
            extended_columns = [c for c in column_names[4:] if c.strip()]

        samples = []

        for line in lines[start_idx:]:
            parts = line.split("\t")
            if len(parts) < 2:  # 至少需要样本名和路径
                continue

            # 核心列
            sample = SampleInfo(
                name=parts[0].strip(),
                path=parts[1].strip(),
                type=parts[2].strip() if len(parts) > 2 and parts[2].strip() else "10x",
                group=parts[3].strip() if len(parts) > 3 and parts[3].strip() else "default",
            )

            # 解析扩展列元数据
            for i, col in enumerate(extended_columns):
                col_idx = 4 + i
                if len(parts) > col_idx and parts[col_idx].strip():
                    sample.metadata[col] = parts[col_idx].strip()

            samples.append(sample)

        # 构建分组索引
        groups: Dict[str, List[str]] = {}
        for s in samples:
            groups.setdefault(s.group, []).append(s.name)

        # 自动生成数据集标签 (D1, D2, ...) - 基于分组
        unique_groups = list(dict.fromkeys(s.group for s in samples))
        group_to_dataset = {g: f"D{i+1}" for i, g in enumerate(unique_groups)}

        datasets: Dict[str, List[str]] = {}
        for s in samples:
            ds = group_to_dataset[s.group]
            datasets.setdefault(ds, []).append(s.name)

        return cls(
            samples=samples,
            groups=groups,
            datasets=datasets,
            extended_columns=extended_columns,
        )

    @classmethod
    def from_file(cls, filepath: str) -> "SampleTable":
        """
        从文件加载样本表

        Args:
            filepath: TSV 文件路径

        Returns:
            SampleTable 实例
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Sample table file not found: {filepath}")

        content = path.read_text(encoding="utf-8")

        # 自动检测是否有表头
        lines = [l for l in content.strip().split("\n") if l.strip() and not l.startswith("#")]
        if lines:
            first_parts = lines[0].split("\t")
            # 如果第一行第一列是已知表头名称，则认为有表头
            header_names = ["name", "sample", "sample_name", "sample_name", "path", "input"]
            has_header = first_parts[0].lower() in header_names
        else:
            has_header = False

        return cls.parse(content, has_header=has_header)

    def to_legacy_format(self) -> Dict[str, str]:
        """
        转换为旧版逗号分隔格式，保持向后兼容

        Returns:
            包含 sample_names, input_paths, data_types, group_labels, datasets 的字典
        """
        if not self.samples:
            return {
                "sample_names": "",
                "input_paths": "",
                "data_types": "",
                "group_labels": "",
                "datasets": "",
            }

        return {
            "sample_names": ",".join(s.name for s in self.samples),
            "input_paths": ",".join(s.path for s in self.samples),
            "data_types": ",".join(s.type for s in self.samples),
            "group_labels": ",".join(s.group for s in self.samples),
            "datasets": ",".join(self.datasets.keys()),
        }

    def to_tsv(self, include_header: bool = True) -> str:
        """
        导出为 TSV 格式

        Args:
            include_header: 是否包含表头行

        Returns:
            TSV 格式字符串
        """
        lines = []

        if include_header:
            cols = ["name", "path", "type", "group"] + self.extended_columns
            lines.append("\t".join(cols))

        for s in self.samples:
            row = [s.name, s.path, s.type, s.group]
            for col in self.extended_columns:
                row.append(str(s.metadata.get(col, "")))
            lines.append("\t".join(row))

        return "\n".join(lines)

    def get_metadata_values(self, column: str) -> Dict[str, List[str]]:
        """
        获取指定扩展列的值分组

        Args:
            column: 扩展列名

        Returns:
            {value: [sample_names]} 的字典
        """
        result: Dict[str, List[str]] = {}
        for s in self.samples:
            val = str(s.metadata.get(column, "unknown"))
            result.setdefault(val, []).append(s.name)
        return result

    def get_samples_by_group(self, group: str) -> List[SampleInfo]:
        """获取指定分组的样本列表"""
        sample_names = set(self.groups.get(group, []))
        return [s for s in self.samples if s.name in sample_names]

    def get_samples_by_metadata(self, column: str, value: str) -> List[SampleInfo]:
        """获取指定元数据值的样本列表"""
        return [s for s in self.samples if str(s.metadata.get(column, "")) == value]

    def validate(self) -> List[str]:
        """
        验证样本表数据完整性

        Returns:
            错误消息列表，空列表表示验证通过
        """
        errors = []

        if not self.samples:
            errors.append("样本表为空")
            return errors

        # 检查样本名唯一性
        names = [s.name for s in self.samples]
        duplicates = [n for n in set(names) if names.count(n) > 1]
        if duplicates:
            errors.append(f"样本名重复: {', '.join(duplicates)}")

        # 检查必填字段
        for i, s in enumerate(self.samples):
            if not s.name:
                errors.append(f"第 {i+1} 行：样本名为空")
            if not s.path:
                errors.append(f"第 {i+1} 行：路径为空")

        return errors

    @property
    def sample_count(self) -> int:
        """样本总数"""
        return len(self.samples)

    @property
    def group_count(self) -> int:
        """分组数量"""
        return len(self.groups)

    def summary(self) -> Dict[str, Any]:
        """获取样本表摘要信息"""
        summary_info = {
            "total_samples": self.sample_count,
            "total_groups": self.group_count,
            "groups": {g: len(samples) for g, samples in self.groups.items()},
            "data_types": {},
        }

        # 统计数据类型分布
        for s in self.samples:
            summary_info["data_types"][s.type] = summary_info["data_types"].get(s.type, 0) + 1

        # 统计扩展列分布
        if self.extended_columns:
            summary_info["extended_columns"] = {}
            for col in self.extended_columns:
                summary_info["extended_columns"][col] = self.get_metadata_values(col)

        return summary_info