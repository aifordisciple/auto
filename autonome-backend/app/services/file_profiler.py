"""
输入文件自动探查服务 - 自动分析用户指定的数据文件结构，为 LLM 策略生成提供精准上下文。

程序说明：
当用户选择数据文件并提出即席分析需求时，此服务自动探查文件的结构特征
（列名、数据类型、统计摘要等），将探查结果注入 LLM prompt，显著提高策略包
首次生成的准确性。

探查策略：
1. CSV/TSV/TXT：使用 pandas 采样分析前 N 行
2. AnnData (h5ad)：使用 anndata 读取 obs/var 元数据
3. FASTQ/BAM 等：仅返回文件类型和大小，不做深度探查
4. 大文件（>100MB）：仅采样首行，避免 OOM

输出格式：
FileProfile {
    format, delimiter, columns (name/dtype/stats), row_count, sample_data
}

集成点：
- context_builder.py: build_workspace_context() 中调用 profile_files()
- adhoc_analysis_node.py: ADHOC_SYSTEM_PROMPT 中注入探查结果
"""
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from app.core.logger import log


# 最大探查文件大小（字节），超过此大小的文件不做深度探查
MAX_PROFILE_SIZE = 100 * 1024 * 1024  # 100MB

# 采样行数
SAMPLE_ROWS = 1000

# 样本数据展示行数
SAMPLE_PREVIEW_ROWS = 5


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    dtype: str
    unique_count: Optional[int] = None
    null_count: int = 0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None


@dataclass
class FileProfile:
    """输入文件探查结果"""
    file_path: str
    format: str  # csv, tsv, txt, h5ad, fastq, etc.
    delimiter: Optional[str] = None
    encoding: str = "utf-8"
    file_size: int = 0
    columns: List[ColumnInfo] = field(default_factory=list)
    row_count: Optional[int] = None
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


def profile_file(file_path: str, project_id: Optional[str] = None) -> FileProfile:
    """
    探查单个数据文件的结构和统计特征。

    Args:
        file_path: 文件在沙箱中的路径（如 /workspace/expression.csv）
        project_id: 项目 ID（预留，用于未来权限校验）

    Returns:
        FileProfile: 文件探查结果
    """
    log.info(f"[FileProfiler] 开始探查文件: {file_path}")

    # 检查文件存在
    if not os.path.exists(file_path):
        return FileProfile(
            file_path=file_path,
            format="unknown",
            error=f"文件不存在: {file_path}",
        )

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    # 复合扩展名处理（如 .fastq.gz）
    if file_path.lower().endswith(".fastq.gz") or file_path.lower().endswith(".fq.gz"):
        ext = ".fastq.gz"
    elif file_path.lower().endswith(".tar.gz"):
        ext = ".tar.gz"

    # 根据扩展名分派探查策略
    if ext in (".csv", ".tsv", ".txt", ".tab"):
        return _profile_delimited_file(file_path, ext, file_size)
    elif ext == ".h5ad":
        return _profile_h5ad_file(file_path, file_size)
    elif ext in (".xlsx", ".xls"):
        return _profile_excel_file(file_path, file_size)
    else:
        # 非表格文件：仅返回类型和大小
        return _profile_binary_file(file_path, ext, file_size)


def profile_files(
    file_paths: List[str],
    project_id: Optional[str] = None,
) -> Dict[str, FileProfile]:
    """
    批量探查多个文件。

    Args:
        file_paths: 文件路径列表
        project_id: 项目 ID

    Returns:
        {file_path: FileProfile} 映射
    """
    results = {}
    for fp in file_paths:
        try:
            results[fp] = profile_file(fp, project_id)
        except Exception as e:
            log.warning(f"[FileProfiler] 文件探查失败 {fp}: {e}")
            results[fp] = FileProfile(
                file_path=fp,
                format="unknown",
                error=str(e),
            )
    return results


def format_profiles_for_prompt(profiles: Dict[str, FileProfile]) -> str:
    """
    将文件探查结果格式化为 LLM prompt 可用的文本片段。

    输出格式被设计为紧凑但信息密集，供 ADHOC_SYSTEM_PROMPT 注入。

    Args:
        profiles: profile_files() 的返回值

    Returns:
        格式化的文本字符串，用于插入 LLM prompt
    """
    if not profiles:
        return ""

    sections = []
    for fp, profile in profiles.items():
        if profile.error:
            sections.append(
                f"  - {fp}: {profile.format} ({_format_size(profile.file_size)}), "
                f"注意: {profile.error}"
            )
            continue

        # 表格文件的详细列信息
        if profile.columns:
            col_lines = []
            for col in profile.columns:
                stats = []
                if col.unique_count is not None:
                    stats.append(f"唯一值={col.unique_count}")
                if col.null_count > 0:
                    stats.append(f"缺失={col.null_count}")
                if col.min_value is not None and col.max_value is not None:
                    stats.append(f"范围=[{col.min_value}, {col.max_value}]")
                stats_str = f" ({', '.join(stats)})" if stats else ""
                col_lines.append(f"    - {col.name}: {col.dtype}{stats_str}")

            cols_section = "\n".join(col_lines)
            rows_info = f", {profile.row_count} 行" if profile.row_count else ""
            sections.append(
                f"  - {fp}: {profile.format}{rows_info}, "
                f"{len(profile.columns)} 列:\n{cols_section}"
            )
        else:
            sections.append(
                f"  - {fp}: {profile.format} ({_format_size(profile.file_size)})"
            )

        # 样本数据
        if profile.sample_data:
            preview = str(profile.sample_data[:3])[:300]
            sections.append(f"    样本数据: {preview}")

    return "\n".join(sections)


def _profile_delimited_file(file_path: str, ext: str, file_size: int) -> FileProfile:
    """探查 CSV/TSV/TXT 等分隔符文件"""
    import pandas as pd

    delimiter_map = {
        ".csv": ",",
        ".tsv": "\t",
        ".tab": "\t",
        ".txt": None,  # 自动检测
    }
    delimiter = delimiter_map.get(ext)

    try:
        # 大文件仅采样
        nrows = SAMPLE_ROWS if file_size > MAX_PROFILE_SIZE else None

        # 尝试读取
        if delimiter:
            df = pd.read_csv(file_path, sep=delimiter, nrows=nrows, encoding="utf-8")
        else:
            # TXT 文件尝试自动检测分隔符
            try:
                df = pd.read_csv(file_path, sep=",", nrows=nrows, encoding="utf-8")
                delimiter = ","
            except Exception:
                try:
                    df = pd.read_csv(file_path, sep="\t", nrows=nrows, encoding="utf-8")
                    delimiter = "\t"
                except Exception:
                    return FileProfile(
                        file_path=file_path,
                        format=ext.lstrip("."),
                        file_size=file_size,
                        error="无法自动检测分隔符",
                    )

        # 提取列信息
        columns = []
        for col_name in df.columns:
            col_dtype = str(df[col_name].dtype)
            col_info = ColumnInfo(
                name=str(col_name),
                dtype=col_dtype,
                null_count=int(df[col_name].isnull().sum()),
            )

            # 数值列：获取统计信息
            if pd.api.types.is_numeric_dtype(df[col_name]):
                col_info.unique_count = int(df[col_name].nunique()) if len(df[col_name]) > 0 else 0
                col_info.min_value = float(df[col_name].min()) if not df[col_name].isnull().all() else None
                col_info.max_value = float(df[col_name].max()) if not df[col_name].isnull().all() else None
                col_info.mean_value = float(df[col_name].mean()) if not df[col_name].isnull().all() else None
            else:
                col_info.unique_count = int(df[col_name].nunique()) if len(df[col_name]) > 0 else 0

            columns.append(col_info)

        # 样本数据（前 N 行）
        sample_data = df.head(SAMPLE_PREVIEW_ROWS).to_dict(orient="records")

        log.info(
            f"[FileProfiler] 探查完成: {file_path}, "
            f"{len(columns)} 列, {len(df)} 行采样"
        )

        return FileProfile(
            file_path=file_path,
            format=ext.lstrip("."),
            delimiter=delimiter,
            file_size=file_size,
            columns=columns,
            row_count=len(df),
            sample_data=sample_data,
        )

    except Exception as e:
        log.warning(f"[FileProfiler] 分隔符文件探查失败 {file_path}: {e}")
        return FileProfile(
            file_path=file_path,
            format=ext.lstrip("."),
            file_size=file_size,
            error=str(e),
        )


def _profile_h5ad_file(file_path: str, file_size: int) -> FileProfile:
    """探查 AnnData (h5ad) 文件"""
    try:
        import anndata

        adata = anndata.read_h5ad(file_path, backed="r")

        columns = []
        # obs (细胞元数据) 列
        for col_name in adata.obs.columns:
            columns.append(ColumnInfo(
                name=f"obs.{col_name}",
                dtype=str(adata.obs[col_name].dtype),
            ))

        # var (基因元数据) 列
        for col_name in adata.var.columns:
            columns.append(ColumnInfo(
                name=f"var.{col_name}",
                dtype=str(adata.var[col_name].dtype),
            ))

        log.info(
            f"[FileProfiler] AnnData 探查完成: {file_path}, "
            f"shape={adata.shape}, {len(columns)} 元数据列"
        )

        return FileProfile(
            file_path=file_path,
            format="h5ad",
            file_size=file_size,
            columns=columns,
            row_count=adata.shape[0],
        )

    except ImportError:
        return FileProfile(
            file_path=file_path,
            format="h5ad",
            file_size=file_size,
            error="anndata 库未安装，无法探查",
        )
    except Exception as e:
        log.warning(f"[FileProfiler] h5ad 探查失败 {file_path}: {e}")
        return FileProfile(
            file_path=file_path,
            format="h5ad",
            file_size=file_size,
            error=str(e),
        )


def _profile_excel_file(file_path: str, file_size: int) -> FileProfile:
    """探查 Excel 文件"""
    try:
        import pandas as pd

        # 仅读取第一个 sheet
        df = pd.read_excel(file_path, nrows=SAMPLE_ROWS)

        columns = []
        for col_name in df.columns:
            col_dtype = str(df[col_name].dtype)
            col_info = ColumnInfo(
                name=str(col_name),
                dtype=col_dtype,
                null_count=int(df[col_name].isnull().sum()),
            )
            columns.append(col_info)

        sample_data = df.head(SAMPLE_PREVIEW_ROWS).to_dict(orient="records")

        return FileProfile(
            file_path=file_path,
            format="excel",
            file_size=file_size,
            columns=columns,
            row_count=len(df),
            sample_data=sample_data,
        )

    except Exception as e:
        log.warning(f"[FileProfiler] Excel 探查失败 {file_path}: {e}")
        return FileProfile(
            file_path=file_path,
            format="excel",
            file_size=file_size,
            error=str(e),
        )


def _profile_binary_file(file_path: str, ext: str, file_size: int) -> FileProfile:
    """非表格/二进制文件的元数据探查"""
    from app.agent.router.context_builder import FILE_TYPE_MAP

    # 从扩展名映射推断格式名
    format_name = FILE_TYPE_MAP.get(ext, ext.lstrip(".") if ext else "unknown")

    return FileProfile(
        file_path=file_path,
        format=format_name,
        file_size=file_size,
    )


def _format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"
