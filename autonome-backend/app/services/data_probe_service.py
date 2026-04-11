"""
数据探测服务 - 在规划前执行数据探查

核心理念：
先探测数据，再制定规划。确保 AI Agent 基于真实数据信息生成蓝图，
而非盲目猜测列名、路径和参数。

架构升级 (2026-04):
- 两阶段规划：数据探测 → 规划生成
- 自动检测项目中的数据文件
- 预览每个文件的结构（列名、维度、类型）
- 生成结构化的探测报告注入 LLM prompt

使用方式:
```python
probe_service = DataProbeService()
probe_report = await probe_service.probe_project(project_id)
probe_context = probe_report.to_prompt_context()
# 注入到规划上下文
```
"""

import os
import re
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.core.logger import log
from app.tools.probe_tools import peek_tabular_data, scan_workspace


# ==========================================
# 数据结构定义
# ==========================================

@dataclass
class DataFileInfo:
    """单个数据文件的信息"""
    file_path: str
    file_type: str  # "tabular", "h5ad", "fastq", "bam", "other"
    file_size: Optional[int] = None
    columns: Optional[List[str]] = None  # 列名列表
    dimensions: Optional[str] = None  # "N行×M列"
    preview: Optional[str] = None  # 原始预览输出
    error: Optional[str] = None  # 如果探测失败


@dataclass
class DataProbeReport:
    """
    数据探测报告

    包含项目中所有检测到的数据文件的详细信息，
    用于注入到 LLM prompt 中，确保规划基于真实数据。
    """
    # 项目 ID
    project_id: str

    # 项目目录结构（原始扫描结果）
    directory_tree: str = ""

    # 检测到的数据文件列表
    data_files: List[DataFileInfo] = field(default_factory=list)

    # 探测摘要统计
    total_files: int = 0
    total_data_files: int = 0

    # 探测时间戳
    probe_timestamp: datetime = field(default_factory=datetime.now)

    # 探测耗时（毫秒）
    probe_time_ms: int = 0

    def to_prompt_context(self) -> str:
        """
        生成可注入 LLM prompt 的探测结果摘要

        Returns:
            格式化的探测结果文本，可直接添加到 prompt 中
        """
        lines = []

        # 1. 目录结构概览
        lines.append("## 项目目录结构")
        lines.append(f"```\n{self.directory_tree[:2000]}\n```")
        if len(self.directory_tree) > 2000:
            lines.append(f"_（目录结构已截断，共 {len(self.directory_tree)} 字符）_")

        # 2. 数据文件详情
        if self.data_files:
            lines.append("\n## 检测到的数据文件")
            lines.append(f"共检测到 **{len(self.data_files)}** 个数据文件：\n")

            for i, file_info in enumerate(self.data_files, 1):
                lines.append(f"### 文件 {i}: `{os.path.basename(file_info.file_path)}`")
                lines.append(f"- **路径**: `{file_info.file_path}`")
                lines.append(f"- **类型**: {file_info.file_type}")

                if file_info.dimensions:
                    lines.append(f"- **维度**: {file_info.dimensions}")

                if file_info.columns:
                    # 限制列名显示数量
                    if len(file_info.columns) > 20:
                        cols_display = file_info.columns[:20]
                        lines.append(f"- **列名** (前 20 列，共 {len(file_info.columns)} 列):")
                    else:
                        cols_display = file_info.columns
                        lines.append(f"- **列名** ({len(cols_display)} 列):")
                    lines.append(f"  `{', '.join(cols_display)}`")

                if file_info.error:
                    lines.append(f"- ⚠️ **探测失败**: {file_info.error}")

                # 添加预览（截断）
                if file_info.preview and not file_info.error:
                    preview_lines = file_info.preview.split('\n')[:15]
                    preview_text = '\n'.join(preview_lines)
                    if len(file_info.preview.split('\n')) > 15:
                        preview_text += "\n... （预览已截断）"
                    lines.append(f"\n<details>\n<summary>数据预览</summary>\n\n```\n{preview_text}\n```\n</details>")

                lines.append("")
        else:
            lines.append("\n## ⚠️ 未检测到数据文件")
            lines.append("项目中没有找到常见的数据文件格式（.tsv, .csv, .h5ad 等）")

        # 3. 重要提示
        lines.append("\n## 📋 规划注意事项")
        lines.append("1. **必须使用上述真实的列名**，不要猜测或编造列名")
        lines.append("2. **必须使用上述真实的文件路径**，确保文件存在")
        lines.append("3. 根据数据维度选择合适的参数（如批次大小、迭代次数等）")
        lines.append("4. 如果有特殊字符或格式问题，请在代码中处理")

        return '\n'.join(lines)

    def get_file_paths(self) -> List[str]:
        """获取所有数据文件路径"""
        return [f.file_path for f in self.data_files]

    def get_columns_for_file(self, file_path: str) -> Optional[List[str]]:
        """获取指定文件的列名"""
        for f in self.data_files:
            if f.file_path == file_path:
                return f.columns
        return None


# ==========================================
# 数据探测服务
# ==========================================

class DataProbeService:
    """
    数据探测服务 - 在规划前执行数据探查

    核心功能：
    1. 扫描项目目录结构
    2. 自动检测数据文件（支持多种格式）
    3. 预览每个文件的详细结构
    4. 生成结构化探测报告
    """

    # 支持的数据文件格式
    TABULAR_EXTENSIONS = {'.tsv', '.csv', '.txt', '.tab', '.mtx'}
    H5AD_EXTENSIONS = {'.h5ad', '.h5'}
    FASTQ_EXTENSIONS = {'.fastq', '.fq', '.fastq.gz', '.fq.gz'}
    BAM_EXTENSIONS = {'.bam', '.sam'}
    BED_EXTENSIONS = {'.bed', '.bedgraph', '.bigWig', '.bw'}
    VCF_EXTENSIONS = {'.vcf', '.vcf.gz', '.bcf'}

    def __init__(self, max_files_to_preview: int = 10):
        """
        初始化探测服务

        Args:
            max_files_to_preview: 最多预览的文件数量（避免探测时间过长）
        """
        self.max_files_to_preview = max_files_to_preview

    async def probe_project(self, project_id: str) -> DataProbeReport:
        """
        探测项目数据环境

        Args:
            project_id: 项目 ID

        Returns:
            DataProbeReport 包含所有探测结果
        """
        start_time = datetime.now()

        log.info(f"🔍 [DataProbe] 开始探测项目 {project_id}")

        project_dir = f"/workspace/project_{project_id}"

        report = DataProbeReport(project_id=project_id)

        # 1. 扫描目录结构
        try:
            log.info(f"🔍 [DataProbe] 扫描目录: {project_dir}")
            report.directory_tree = await scan_workspace.ainvoke({
                "directory_path": project_dir,
                "max_depth": 3
            })
        except Exception as e:
            log.warning(f"⚠️ [DataProbe] 目录扫描失败: {e}")
            report.directory_tree = f"目录扫描失败: {str(e)}"

        # 2. 提取数据文件路径
        data_file_paths = self._extract_data_file_paths(report.directory_tree, project_dir)
        report.total_files = len(data_file_paths)

        log.info(f"🔍 [DataProbe] 检测到 {len(data_file_paths)} 个潜在数据文件")

        # 3. 预览数据文件（限制数量）
        files_to_preview = data_file_paths[:self.max_files_to_preview]

        for file_path in files_to_preview:
            try:
                file_info = await self._probe_single_file(file_path)
                report.data_files.append(file_info)
            except Exception as e:
                log.warning(f"⚠️ [DataProbe] 文件探测失败 {file_path}: {e}")
                report.data_files.append(DataFileInfo(
                    file_path=file_path,
                    file_type="unknown",
                    error=str(e)
                ))

        report.total_data_files = len(report.data_files)

        # 4. 计算耗时
        end_time = datetime.now()
        report.probe_time_ms = int((end_time - start_time).total_seconds() * 1000)

        log.info(f"✅ [DataProbe] 探测完成: {report.total_data_files} 个文件, {report.probe_time_ms}ms")

        return report

    def _extract_data_file_paths(self, directory_tree: str, project_dir: str) -> List[str]:
        """
        从目录扫描结果中提取数据文件路径

        Args:
            directory_tree: 目录扫描结果文本
            project_dir: 项目根目录

        Returns:
            数据文件路径列表
        """
        file_paths = []

        # 提取所有 /workspace/... 格式的路径
        # 匹配文件名（不含特殊字符）
        pattern = rf'({re.escape(project_dir)}[^\s\]\)\}}]+\.(tsv|csv|txt|tab|h5ad|h5|fastq|fq|bam|sam|bed|vcf|mtx)(?:\.gz)?)'

        matches = re.findall(pattern, directory_tree, re.IGNORECASE)
        for match in matches:
            file_paths.append(match[0])

        # 去重并排序
        file_paths = sorted(set(file_paths))

        return file_paths

    def _get_file_type(self, file_path: str) -> str:
        """根据扩展名判断文件类型"""
        ext = os.path.splitext(file_path)[1].lower()

        # 处理 .gz 压缩文件
        if ext == '.gz':
            ext = os.path.splitext(file_path[:-3])[1].lower()

        if ext in self.TABULAR_EXTENSIONS:
            return "tabular"
        elif ext in self.H5AD_EXTENSIONS:
            return "h5ad"
        elif ext in self.FASTQ_EXTENSIONS:
            return "fastq"
        elif ext in self.BAM_EXTENSIONS:
            return "bam"
        elif ext in self.BED_EXTENSIONS:
            return "bed"
        elif ext in self.VCF_EXTENSIONS:
            return "vcf"
        else:
            return "other"

    async def _probe_single_file(self, file_path: str) -> DataFileInfo:
        """
        探测单个数据文件

        Args:
            file_path: 文件路径

        Returns:
            DataFileInfo 包含文件详细信息
        """
        file_type = self._get_file_type(file_path)

        file_info = DataFileInfo(
            file_path=file_path,
            file_type=file_type
        )

        # 获取文件大小
        try:
            file_info.file_size = os.path.getsize(file_path)
        except:
            pass

        # 根据文件类型选择预览方法
        try:
            if file_type == "tabular":
                preview_result = await peek_tabular_data.ainvoke({
                    "file_path": file_path,
                    "n_rows": 5
                })
                file_info.preview = preview_result

                # 解析列名和维度
                self._parse_tabular_preview(file_info, preview_result)

            elif file_type == "h5ad":
                # 尝试使用 inspect_h5ad（如果存在）
                try:
                    from app.tools.probe_tools import inspect_h5ad
                    preview_result = await inspect_h5ad.ainvoke({"file_path": file_path})
                    file_info.preview = preview_result
                except ImportError:
                    file_info.preview = f"H5AD 文件: {file_path}"
                    file_info.error = "inspect_h5ad 工具不可用"

            elif file_type in ("fastq", "bam", "bed", "vcf"):
                # 这些格式暂时只记录路径和大小
                file_info.preview = f"{file_type.upper()} 文件: {file_path}"

            else:
                file_info.preview = f"文件: {file_path}"

        except Exception as e:
            file_info.error = str(e)
            log.warning(f"⚠️ [DataProbe] 预览文件失败 {file_path}: {e}")

        return file_info

    def _parse_tabular_preview(self, file_info: DataFileInfo, preview: str) -> None:
        """
        解析表格文件预览结果，提取列名和维度

        Args:
            file_info: 文件信息对象
            preview: 预览结果文本
        """
        try:
            # 提取维度信息（格式: "N 行 × M 列"）
            dim_match = re.search(r'(\d+(?:[,，]\d+)*)\s*行\s*[×xX]\s*(\d+)', preview)
            if dim_match:
                rows = dim_match.group(1).replace(',', '').replace('，', '')
                cols = dim_match.group(2)
                file_info.dimensions = f"{rows}行×{cols}列"

            # 提取列名（在 "表头列表" 或 "headers" 之后）
            # 寻找 JSON 数组格式的列名
            json_match = re.search(r'表头列表[^[]*\[([^\]]+)\]', preview, re.DOTALL)
            if json_match:
                try:
                    # 尝试解析 JSON
                    headers_json = '[' + json_match.group(1) + ']'
                    headers = json.loads(headers_json)
                    file_info.columns = headers
                except json.JSONDecodeError:
                    pass

            # 如果 JSON 解析失败，尝试其他格式
            if not file_info.columns:
                # 尝试匹配 "列名列表: col1, col2, ..."
                cols_match = re.search(r'列名[列表]*[:：]\s*(.+?)(?:\n|$)', preview)
                if cols_match:
                    cols_text = cols_match.group(1)
                    # 分割列名
                    file_info.columns = [c.strip().strip('"\'') for c in cols_text.split(',') if c.strip()]

        except Exception as e:
            log.warning(f"⚠️ [DataProbe] 解析预览结果失败: {e}")