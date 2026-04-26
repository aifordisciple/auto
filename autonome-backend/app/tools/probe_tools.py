"""
环境探针工具模块

提供两个核心探针工具，让 AI Agent 能够"感知"数据环境，不再盲目写代码。
"""

import os
import json
from typing import Optional
from langchain_core.tools import tool
from app.core.logger import log


# ==========================================
# ✨ 探针缓存机制
# 基于文件路径 + 修改时间，避免重复探查
# ==========================================
_probe_cache = {}
_probe_structured_cache = {}  # cache_key → structured dict（与 _probe_cache 并行存储）
_CACHE_MAX_SIZE = 100


def _get_cache_key(file_path: str) -> str:
    """生成缓存 key（路径 + mtime）"""
    try:
        mtime = os.path.getmtime(file_path)
        return f"{file_path}:{mtime}"
    except:
        return file_path


def _check_probe_cache(cache_key: str, tool_name: str = "") -> Optional[str]:
    """
    检查缓存；命中时设置 _last_probe_structured 并返回缓存的摘要文本。
    未命中返回 None。
    """
    if cache_key in _probe_cache:
        if tool_name:
            log.info(f"🔍 [Probe] {tool_name} 缓存命中")
        structured = _probe_structured_cache.get(cache_key)
        if structured is not None:
            _last_probe_structured.update(structured)
        return _probe_cache[cache_key]
    return None


def _cache_result(cache_key: str, result: str) -> None:
    """
    缓存摘要文本 + 当前 _last_probe_structured 中的结构化数据。
    _make_probe_result 已将 structured 写入 _last_probe_structured。
    """
    _probe_cache[cache_key] = result
    if _last_probe_structured:
        _probe_structured_cache[cache_key] = dict(_last_probe_structured)
    if len(_probe_cache) > _CACHE_MAX_SIZE:
        oldest = next(iter(_probe_cache))
        _probe_cache.pop(oldest)
        _probe_structured_cache.pop(oldest, None)


# V2.5: 模块级变量传递结构化数据，避免将 structured 字段写入工具输出（防止明细数据展示到前端）
# 使用普通 dict 而非 ContextVar（LangChain @tool.invoke 会隔离 ContextVar 上下文）
_last_probe_structured: dict = {}


def _make_probe_result(summary: str, structured: dict) -> str:
    """
    V2.5: 生成探针结果 —— 仅返回人类可读摘要文本。

    结构化数据通过模块级变量 _last_probe_structured 带外传递，
    由 data_probe_node 中的 _extract_probe_structured 读取。
    工具输出不再包含 structured JSON，避免明细数据展示到前端。

    Args:
        summary: 人类可读的格式化报告
        structured: 机器可解析的标准化字段字典（仅内部使用，不展示给用户）

    Returns:
        纯文本摘要（非 JSON）
    """
    _last_probe_structured.clear()
    _last_probe_structured.update(structured)
    return summary


@tool
def peek_tabular_data(file_path: str, n_rows: int = 5) -> str:
    """
    预览表格文件（CSV/TSV/TXT）的结构：表头、维度和前几行数据。

    在处理任何表格数据前，强制先调用此工具了解表头和维度，绝不盲目瞎猜列名！

    Args:
        file_path: 表格文件的绝对路径（如 /workspace/project_1/raw_data/counts.tsv）
        n_rows: 预览行数，默认 5 行

    Returns:
        包含表头、维度、前 n_rows 行数据的结构化信息字符串
    """
    # ✨ 检查缓存
    cache_key = _get_cache_key(file_path) + f":{n_rows}"
    cached = _check_probe_cache(cache_key, "peek_tabular_data")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] peek_tabular_data called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    if not os.path.isfile(file_path):
        return _make_probe_result(f"❌ 路径不是文件: {file_path}", {"error": "not_a_file"})

    # 检测文件大小，避免读取超大文件
    file_size = os.path.getsize(file_path)
    if file_size > 100 * 1024 * 1024:  # 100MB
        return _make_probe_result(
            f"⚠️ 文件过大 ({file_size / 1024 / 1024:.1f} MB)，建议使用分块读取方式处理",
            {"error": "file_too_large", "file_size_mb": round(file_size / 1024 / 1024, 1)}
        )

    try:
        # 透明解压 gzip 文件
        is_gzip = file_path.endswith('.gz')
        if is_gzip:
            import gzip as _gz
            f_open = _gz.open
            f_mode = 'rt'
        else:
            f_open = open
            f_mode = 'r'

        # 尝试检测分隔符
        with f_open(file_path, f_mode, encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()

        if not first_line.strip():
            return _make_probe_result("❌ 文件为空", {"error": "empty_file"})

        # 智能检测分隔符
        delimiter = '\t'  # 默认 TSV
        if ',' in first_line and '\t' not in first_line:
            delimiter = ','
        elif ' ' in first_line and '\t' not in first_line and ',' not in first_line:
            # 检测是否为空格分隔（可能多个空格）
            if first_line.count('  ') > 0:
                delimiter = None  # 使用 split() 自动处理多空格

        # ✨ 修复内存风险：改用逐行读取，避免 readlines() 加载整个文件到内存
        # 只读取表头和预览行
        headers = []
        preview_data = []
        n_total_rows = 0

        with f_open(file_path, f_mode, encoding='utf-8', errors='ignore') as f:
            # 读取第一行作为表头
            first_line = f.readline()
            if not first_line.strip():
                return _make_probe_result("❌ 文件为空", {"error": "empty_file"})

            if delimiter:
                headers = [h.strip() for h in first_line.strip().split(delimiter)]
            else:
                headers = first_line.strip().split()

            # 读取预览行并计数总行数
            for i, line in enumerate(f):
                if i < n_rows:
                    if delimiter:
                        cells = [c.strip() for c in line.strip().split(delimiter)]
                    else:
                        cells = line.strip().split()
                    preview_data.append(cells)

                n_total_rows += 1

                # ✨ 安全限制：超过 100 万行停止计数，避免超大文件
                if n_total_rows > 1000000:
                    n_total_rows = ">1000000"
                    break

        # 计算列数
        n_cols = len(headers)

        # 构建结构化输出
        # 先计算分隔符描述（f-string 不支持反斜杠）
        delimiter_desc = "逗号 (CSV)" if delimiter == "," else "制表符 (TSV)" if delimiter == "\t" else "空格"

        result = f"""📊 表格文件预览报告

📁 文件路径: {file_path}
📏 文件大小: {file_size / 1024:.1f} KB
📐 数据维度: {n_total_rows} 行 × {n_cols} 列
🔤 分隔符: {delimiter_desc}

📋 表头列表 (共 {n_cols} 列):
{json.dumps(headers if len(headers) <= 25 else headers[:25] + [f"... 共 {n_cols} 列，完整列表见 structured.headers"], ensure_ascii=False, indent=2)}

📝 前 {min(n_rows, len(preview_data))} 行数据预览:
"""

        # 添加数据预览表格
        if preview_data:
            result += "\n| " + " | ".join(headers[:min(10, len(headers))]) + " |\n"
            result += "| " + " | ".join(["---"] * min(10, len(headers))) + " |\n"

            for row in preview_data:
                row_display = row[:min(10, len(row))]
                # 截断过长的单元格内容
                row_display = [str(cell)[:30] + "..." if len(str(cell)) > 30 else str(cell) for cell in row_display]
                result += "| " + " | ".join(row_display) + " |\n"

        # 检测潜在问题
        warnings = []
        if n_total_rows > 1000000:
            warnings.append("⚠️ 数据量较大（>100万行），建议使用分块处理")
        if n_cols > 100:
            warnings.append("⚠️ 列数较多（>100列），建议先筛选关键列")

        # 检查列名是否包含特殊字符
        special_chars = set()
        for h in headers:
            for c in h:
                if not c.isalnum() and c not in '_-':
                    special_chars.add(c)
        if special_chars:
            warnings.append(f"⚠️ 列名包含特殊字符: {special_chars}")

        if warnings:
            result += "\n⚠️ 潜在问题提示:\n"
            for w in warnings:
                result += f"  - {w}\n"

        log.info(f"✅ [Probe] 预览完成: {n_total_rows} 行, {n_cols} 列")
        # V2.4: 双模输出
        structured = {
            "n_rows": n_total_rows if isinstance(n_total_rows, int) else 1000000,
            "n_cols": n_cols,
            "headers": headers,
            "delimiter": delimiter_desc,
            "file_size_kb": round(file_size / 1024, 1),
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] 读取文件失败: {str(e)}")
        return _make_probe_result(f"❌ 读取文件失败: {str(e)}", {"error": str(e)})


@tool
def scan_workspace(directory_path: str, max_depth: int = 3) -> str:
    """
    扫描指定目录下的所有文件和文件夹，返回结构化的目录树。

    当需要找文件但不确定位置时，调用此工具获取目录结构。

    Args:
        directory_path: 要扫描的目录绝对路径（如 /workspace/project_1）
        max_depth: 最大扫描深度，默认 3 层

    Returns:
        结构化的目录树字符串
    """
    log.info(f"🔍 [Probe] scan_workspace called: {directory_path}")

    if not os.path.exists(directory_path):
        return _make_probe_result(f"❌ 目录不存在: {directory_path}", {"error": "dir_not_found"})

    if not os.path.isdir(directory_path):
        return _make_probe_result(f"❌ 路径不是目录: {directory_path}", {"error": "not_a_directory"})

    try:
        result_lines = []
        file_counts = {"total": 0, "by_extension": {}}
        dir_counts = 0

        def scan_recursive(path: str, prefix: str = "", depth: int = 0):
            nonlocal dir_counts

            if depth > max_depth:
                return

            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                result_lines.append(f"{prefix}❌ [权限不足]")
                return

            # 分类：文件夹在前，文件在后
            folders = []
            files = []

            for entry in entries:
                if entry.startswith('.'):
                    continue  # 跳过隐藏文件
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    folders.append(entry)
                else:
                    files.append(entry)

            # 渲染文件夹
            for i, folder in enumerate(folders):
                is_last_folder = (i == len(folders) - 1) and len(files) == 0
                connector = "└── " if is_last_folder else "├── "
                result_lines.append(f"{prefix}{connector}📁 {folder}/")
                dir_counts += 1

                # 递归扫描子目录
                new_prefix = prefix + ("    " if is_last_folder else "│   ")
                scan_recursive(os.path.join(path, folder), new_prefix, depth + 1)

            # 渲染文件（每目录最多展示 MAX_FILES_PER_DIR 个，避免淹没问题）
            MAX_FILES_PER_DIR = 30
            show_files = files[:MAX_FILES_PER_DIR]
            for i, file in enumerate(show_files):
                is_last = (i == len(show_files) - 1) and (len(files) <= MAX_FILES_PER_DIR)
                connector = "└── " if is_last else "├── "

                # 获取文件大小
                file_path = os.path.join(path, file)
                try:
                    size = os.path.getsize(file_path)
                    size_str = _format_size(size)
                except:
                    size_str = "?"

                # 检测文件类型图标
                ext = os.path.splitext(file)[1].lower()
                icon = _get_file_icon(ext)

                result_lines.append(f"{prefix}{connector}{icon} {file} ({size_str})")

            if len(files) > MAX_FILES_PER_DIR:
                result_lines.append(f"{prefix}└── ... 等 {len(files)} 个文件")

            # 统计文件类型（统计所有文件，不仅展示的）
            for file in files:
                file_counts["total"] += 1
                ext = os.path.splitext(file)[1].lower()
                if ext:
                    file_counts["by_extension"][ext] = file_counts["by_extension"].get(ext, 0) + 1
                else:
                    file_counts["by_extension"]["[no_ext]"] = file_counts["by_extension"].get("[no_ext]", 0) + 1

        # 开始扫描
        result_lines.append(f"📂 {directory_path}/")
        scan_recursive(directory_path)

        # 构建统计信息
        stats = f"""
📊 目录统计:
  - 文件总数: {file_counts['total']}
  - 文件夹总数: {dir_counts}
  - 按类型分布:"""

        # 按数量排序扩展名
        sorted_exts = sorted(file_counts["by_extension"].items(), key=lambda x: x[1], reverse=True)
        for ext, count in sorted_exts[:10]:  # 最多显示 10 种类型
            stats += f"\n    - {ext if ext != '[no_ext]' else '(无扩展名)'}: {count} 个"

        if len(sorted_exts) > 10:
            stats += f"\n    - ... 等共 {len(sorted_exts)} 种类型"

        result = "🌳 目录树扫描结果\n\n" + "\n".join(result_lines) + stats

        log.info(f"✅ [Probe] 扫描完成: {file_counts['total']} 个文件, {dir_counts} 个文件夹")
        # V2.4: 双模输出
        structured = {
            "n_files": file_counts['total'],
            "n_dirs": dir_counts,
            "extensions": file_counts["by_extension"],
        }
        result = _make_probe_result(result, structured)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] 扫描目录失败: {str(e)}")
        return _make_probe_result(f"❌ 扫描目录失败: {str(e)}", {"error": str(e)})


# ==========================================
# ✨ 多组学探针工具（新增）
# ==========================================

@tool
def inspect_h5ad(file_path: str) -> str:
    """
    解析 .h5ad 单细胞 AnnData 文件结构。

    返回 obs（细胞注释）、var（基因注释）、obsm（降维坐标）、varm、uns（非结构化信息）等结构概览。
    在处理单细胞数据前，强烈建议先调用此工具了解数据结构！

    Args:
        file_path: .h5ad 文件的绝对路径

    Returns:
        AnnData 对象的结构化信息字符串
    """
    log.info(f"🔍 [Probe] inspect_h5ad called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    if not file_path.endswith('.h5ad'):
        return _make_probe_result(f"⚠️ 文件扩展名不是 .h5ad，可能不是有效的 AnnData 文件", {"error": "invalid_extension"})

    try:
        # 尝试导入 scanpy
        try:
            import scanpy as sc
        except ImportError:
            return _make_probe_result("❌ scanpy 未安装，无法解析 .h5ad 文件。请在沙箱环境中安装 scanpy。", {"error": "scanpy_not_installed"})

        # 读取文件
        adata = sc.read_h5ad(file_path)

        # 构建结构化报告
        result = f"""🧬 AnnData 单细胞数据结构报告

📁 文件路径: {file_path}
📏 文件大小: {os.path.getsize(file_path) / 1024 / 1024:.2f} MB

📐 核心维度:
  - 观测数 (n_obs): {adata.n_obs} 个细胞
  - 变量数 (n_vars): {adata.n_vars} 个基因
  - 数据矩阵: {adata.n_obs} × {adata.n_vars}

📊 obs (细胞注释，前5列):
"""
        # 显示 obs 列
        if adata.obs is not None and len(adata.obs.columns) > 0:
            obs_cols = list(adata.obs.columns)[:10]
            result += f"  列名: {obs_cols}\n"
            if len(adata.obs.columns) > 10:
                result += f"  ... 共 {len(adata.obs.columns)} 列\n"
            result += f"  示例:\n{adata.obs.head(3).to_string()}\n"
        else:
            result += "  （无细胞注释）\n"

        result += f"""
📊 var (基因注释，前5列):
"""
        # 显示 var 列
        if adata.var is not None and len(adata.var.columns) > 0:
            var_cols = list(adata.var.columns)[:10]
            result += f"  列名: {var_cols}\n"
            if len(adata.var.columns) > 10:
                result += f"  ... 共 {len(adata.var.columns)} 列\n"
            result += f"  示例:\n{adata.var.head(3).to_string()}\n"
        else:
            result += "  （无基因注释）\n"

        # 显示 obsm（降维结果）
        result += f"\n📍 obsm (降维坐标):\n"
        if adata.obsm is not None and len(adata.obsm) > 0:
            for key in list(adata.obsm.keys())[:5]:
                shape = adata.obsm[key].shape
                result += f"  - {key}: {shape}\n"
        else:
            result += "  （无降维结果）\n"

        # 显示 uns（非结构化信息）
        result += f"\n📦 uns (非结构化信息):\n"
        if adata.uns is not None and len(adata.uns) > 0:
            for key in list(adata.uns.keys())[:10]:
                result += f"  - {key}\n"
            if len(adata.uns) > 10:
                result += f"  ... 共 {len(adata.uns)} 项\n"
        else:
            result += "  （无非结构化信息）\n"

        # 显示 layers
        result += f"\n📚 layers (数据层):\n"
        if adata.layers is not None and len(adata.layers) > 0:
            for key in adata.layers.keys():
                result += f"  - {key}\n"
        else:
            result += "  （无额外数据层）\n"

        log.info(f"✅ [Probe] h5ad 解析完成: {adata.n_obs} 细胞, {adata.n_vars} 基因")
        # V2.4: 双模输出
        structured = {
            "n_obs": adata.n_obs,
            "n_vars": adata.n_vars,
            "obs_columns": list(adata.obs.columns) if adata.obs is not None else [],
            "var_columns": list(adata.var.columns) if adata.var is not None else [],
            "obsm_keys": list(adata.obsm.keys()) if adata.obsm is not None else [],
        }
        result = _make_probe_result(result, structured)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] h5ad 解析失败: {str(e)}")
        return _make_probe_result(f"❌ 解析 .h5ad 文件失败: {str(e)}", {"error": str(e)})


@tool
def inspect_fastq(file_path: str, n_reads: int = 5) -> str:
    """
    预览 FASTQ 测序文件的基本信息。

    统计 reads 数量、读取长度分布、GC 含量等基本信息。
    适用于 RNA-Seq、单细胞、ChIP-Seq 等测序数据的快速预览。

    Args:
        file_path: FASTQ 文件路径（支持 .fastq, .fq, .fastq.gz, .fq.gz）
        n_reads: 预览的 reads 数量，默认 5 条

    Returns:
        FASTQ 文件的结构化信息字符串
    """
    log.info(f"🔍 [Probe] inspect_fastq called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.fastq', '.fq', '.gz']:
        return _make_probe_result(f"⚠️ 文件扩展名 {ext} 不是标准的 FASTQ 格式", {"error": "invalid_extension"})

    try:
        import gzip

        # 根据扩展名选择打开方式
        if file_path.endswith('.gz'):
            opener = gzip.open
            mode = 'rt'
        else:
            opener = open
            mode = 'r'

        read_lengths = []
        gc_contents = []
        total_reads = 0
        preview_reads = []

        with opener(file_path, mode) as f:
            while True:
                # FASTQ 格式：每 4 行为一个 read
                header = f.readline()
                if not header:
                    break
                seq = f.readline().strip()
                plus = f.readline()
                qual = f.readline().strip()

                if not seq:
                    break

                total_reads += 1
                read_lengths.append(len(seq))

                # 计算 GC 含量
                gc_count = seq.count('G') + seq.count('C')
                gc_contents.append(gc_count / len(seq) * 100 if len(seq) > 0 else 0)

                # 保存预览
                if len(preview_reads) < n_reads:
                    preview_reads.append({
                        "header": header.strip(),
                        "seq": seq[:80] + "..." if len(seq) > 80 else seq,
                        "qual": qual[:80] + "..." if len(qual) > 80 else qual
                    })

                # 限制统计数量以提高性能
                if total_reads >= 100000:
                    break

        # 统计分析
        import statistics
        avg_length = statistics.mean(read_lengths) if read_lengths else 0
        avg_gc = statistics.mean(gc_contents) if gc_contents else 0

        result = f"""🧬 FASTQ 测序文件预览报告

📁 文件路径: {file_path}
📏 文件大小: {os.path.getsize(file_path) / 1024 / 1024:.2f} MB

📊 统计信息:
  - 总 reads 数: {total_reads:,}{'（已截取前10万条统计）' if total_reads >= 100000 else ''}
  - 平均长度: {avg_length:.1f} bp
  - 长度范围: {min(read_lengths)} - {max(read_lengths)} bp
  - 平均 GC 含量: {avg_gc:.1f}%

📝 前 {len(preview_reads)} 条 reads 预览:
"""
        for i, read in enumerate(preview_reads, 1):
            result += f"""
--- Read {i} ---
Header: {read['header']}
Seq: {read['seq']}
Qual: {read['qual']}
"""

        log.info(f"✅ [Probe] FASTQ 预览完成: {total_reads} reads, 平均长度 {avg_length:.1f}bp")
        # V2.4: 双模输出
        structured = {
            "n_reads": total_reads,
            "avg_length": round(avg_length, 1),
            "min_length": min(read_lengths) if read_lengths else 0,
            "max_length": max(read_lengths) if read_lengths else 0,
            "avg_gc": round(avg_gc, 1),
        }
        result = _make_probe_result(result, structured)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] FASTQ 解析失败: {str(e)}")
        return _make_probe_result(f"❌ 解析 FASTQ 文件失败: {str(e)}", {"error": str(e)})


@tool
def inspect_bam(file_path: str) -> str:
    """
    预览 BAM 比对文件的基本信息。

    统计比对率、染色体分布、插入片段大小等信息。
    适用于 RNA-Seq、WGS、ChIP-Seq 等比对结果的快速预览。

    Args:
        file_path: BAM 文件路径（.bam）

    Returns:
        BAM 文件的结构化信息字符串
    """
    log.info(f"🔍 [Probe] inspect_bam called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    if not file_path.endswith('.bam'):
        return _make_probe_result(f"⚠️ 文件扩展名不是 .bam", {"error": "invalid_extension"})

    try:
        # 检查 pysam 是否可用
        try:
            import pysam
        except ImportError:
            return _make_probe_result("❌ pysam 未安装，无法解析 BAM 文件。请在沙箱环境中安装 pysam。", {"error": "pysam_not_installed"})

        # 打开 BAM 文件
        bamfile = pysam.AlignmentFile(file_path, "rb")

        # 统计信息
        total_reads = 0
        mapped_reads = 0
        unmapped_reads = 0
        chrom_counts = {}
        insert_sizes = []

        for read in bamfile:
            total_reads += 1

            if read.is_unmapped:
                unmapped_reads += 1
            else:
                mapped_reads += 1

                # 染色体统计
                chrom = bamfile.get_reference_name(read.reference_id)
                chrom_counts[chrom] = chrom_counts.get(chrom, 0) + 1

                # 插入片段大小
                if read.template_length > 0:
                    insert_sizes.append(read.template_length)

            # 限制统计数量
            if total_reads >= 100000:
                break

        # V2.3: 解析 BAM header 信息（参考序列、读组、处理程序）
        header_dict = dict(bamfile.header)
        sq_records = header_dict.get('SQ', [])
        rg_records = header_dict.get('RG', [])
        pg_records = header_dict.get('PG', [])
        co_records = header_dict.get('CO', [])

        bamfile.close()

        # 计算统计指标
        mapping_rate = mapped_reads / total_reads * 100 if total_reads > 0 else 0
        avg_insert = sum(insert_sizes) / len(insert_sizes) if insert_sizes else 0

        # 排序染色体
        sorted_chroms = sorted(chrom_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        result = f"""🧬 BAM 比对文件预览报告

📁 文件路径: {file_path}
📏 文件大小: {os.path.getsize(file_path) / 1024 / 1024:.2f} MB

📊 统计信息:
  - 总 reads 数: {total_reads:,}{'（已截取前10万条统计）' if total_reads >= 100000 else ''}
  - 比对成功: {mapped_reads:,} ({mapping_rate:.1f}%)
  - 未比对: {unmapped_reads:,}
  - 平均插入片段: {avg_insert:.1f} bp

📍 染色体分布 (Top 10):
"""
        for chrom, count in sorted_chroms:
            result += f"  - {chrom}: {count:,}\n"

        if len(chrom_counts) > 10:
            result += f"  ... 共 {len(chrom_counts)} 个染色体/contig\n"

        # V2.3: BAM header 解析输出
        result += f"\n📋 BAM Header 信息:\n"

        if sq_records:
            result += f"\n🧬 参考序列 (@SQ, 共 {len(sq_records)} 条):\n"
            for sq in sq_records[:15]:
                sn = sq.get('SN', '?')
                ln = sq.get('LN', '?')
                as_tag = sq.get('AS', '')
                result += f"  - {sn}: {ln} bp"
                if as_tag:
                    result += f" (assembly: {as_tag})"
                result += "\n"
            if len(sq_records) > 15:
                result += f"  ... 共 {len(sq_records)} 条\n"

        if rg_records:
            result += f"\n🏷️ 读组 (@RG, 共 {len(rg_records)} 组):\n"
            for rg in rg_records[:5]:
                result += (
                    f"  - ID={rg.get('ID', '?')}, "
                    f"SM={rg.get('SM', '?')}, "
                    f"PL={rg.get('PL', '?')}, "
                    f"LB={rg.get('LB', '?')}\n"
                )

        if pg_records:
            result += f"\n🔧 处理程序 (@PG):\n"
            for pg in pg_records[:5]:
                result += f"  - {pg.get('ID', '?')}: {pg.get('PN', '?')} v{pg.get('VN', '?')}\n"

        if co_records:
            result += f"\n💬 注释 (@CO):\n"
            for co in co_records[:5]:
                result += f"  - {co}\n"

        log.info(f"✅ [Probe] BAM 预览完成: {total_reads} reads, 比对率 {mapping_rate:.1f}%")
        # V2.4: 双模输出
        ref_genome = ""
        if sq_records:
            ref_genome = sq_records[0].get('AS', '')
        rg_samples = [rg.get('SM', '') for rg in rg_records if rg.get('SM')]
        structured = {
            "total_reads": total_reads,
            "mapped_reads": mapped_reads,
            "mapping_rate": round(mapping_rate, 1),
            "avg_insert_size": round(avg_insert, 1),
            "reference_genome": ref_genome,
            "rg_samples": rg_samples,
        }
        result = _make_probe_result(result, structured)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] BAM 解析失败: {str(e)}")
        return _make_probe_result(f"❌ 解析 BAM 文件失败: {str(e)}", {"error": str(e)})


def _format_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


# ==========================================
# ✨ V2.3 新增探针工具
# ==========================================

@tool
def detect_na(file_path: str, threshold: Optional[float] = None) -> str:
    """
    检测表格文件（CSV/TSV/TXT）中的缺失值（NA/NaN/空值/None）。
    逐列统计缺失数量和比例，用于判断数据质量。

    当用户询问"有没有缺失值"、"NA比例"、"缺失率"时调用此工具。

    Args:
        file_path: 表格文件的绝对路径
        threshold: 可选，只报告缺失比例超过此阈值的列（如 0.05 表示 5%）

    Returns:
        缺失值统计报告，含每列缺失数量和比例
    """
    cache_key = _get_cache_key(file_path) + f":na:{threshold}"
    cached = _check_probe_cache(cache_key, "detect_na")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] detect_na called: {file_path}, threshold={threshold}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    try:
        # 检测分隔符（复用 peek_tabular_data 的逻辑）
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
        if not first_line.strip():
            return _make_probe_result("❌ 文件为空", {"error": "empty_file"})

        delimiter = '\t'
        if ',' in first_line and '\t' not in first_line:
            delimiter = ','

        import pandas as pd
        # 安全检查：仅读取前 100 万行
        df = pd.read_csv(file_path, sep=delimiter, nrows=1000000, low_memory=False)
        n_cols = len(df.columns)
        n_rows = len(df)

        # 统计每列缺失值
        na_counts = df.isna().sum()
        na_ratios = (na_counts / n_rows).round(4)

        # 额外检测空字符串（pandas isna 不包含空字符串）
        empty_str_counts = {}
        for col in df.columns:
            try:
                empty_str_counts[col] = (df[col].astype(str).str.strip() == '').sum()
            except:
                empty_str_counts[col] = 0

        # 合并 NA + 空字符串
        total_missing = {}
        for col in df.columns:
            total_missing[col] = int(na_counts[col]) + int(empty_str_counts[col])

        # 按阈值过滤
        if threshold is not None:
            filtered_cols = [col for col in df.columns if total_missing[col] / n_rows > threshold]
        else:
            filtered_cols = list(df.columns)

        # 构建报告（精简摘要 + 结构化明细）
        total_na_rows = df.isna().any(axis=1).sum()
        overall_na_ratio = sum(total_missing.values()) / (n_rows * n_cols) if n_cols > 0 else 0
        total_missing_count = sum(total_missing.values())

        # 区分问题列和正常列
        problem_cols = []
        clean_count = 0
        for col in df.columns:
            missing = total_missing[col]
            ratio = missing / n_rows if n_rows > 0 else 0
            if ratio > 0.01:  # >1% 缺失
                status = "🔴 严重" if ratio > 0.3 else ("⚠️ 需关注" if ratio > 0.1 else "📌 轻微")
                problem_cols.append((col, missing, ratio, status))
            elif missing > 0:
                problem_cols.append((col, missing, ratio, "✅ 正常"))
            else:
                clean_count += 1

        # 按缺失率降序排列
        problem_cols.sort(key=lambda x: x[2], reverse=True)

        summary_lines = [
            f"🔍 缺失值检测报告",
            f"",
            f"📁 文件: {os.path.basename(file_path)}",
            f"📐 维度: {n_rows} 行 × {n_cols} 列",
            f"📊 总缺失值: {total_missing_count} 个，涉及 {total_na_rows} 行 ({total_na_rows / n_rows * 100:.1f}%)",
            f"📊 总体缺失比例: {overall_na_ratio:.2%}",
        ]

        if clean_count == n_cols:
            summary_lines.append(f"✅ 所有 {n_cols} 列均无缺失值")
        else:
            max_show = 15
            summary_lines.append(f"📋 含缺失值的列 ({len(problem_cols)} 个，显示前{max_show}):")
            for col, missing, ratio, status in problem_cols[:max_show]:
                summary_lines.append(f"  {status} {col}: {missing} 个 ({ratio:.1%})")
            if len(problem_cols) > max_show:
                summary_lines.append(f"  ... 共 {len(problem_cols)} 列，完整明细见 structured.columns")
            summary_lines.append(f"✅ 无缺失列: {clean_count} 个")

        # 总体判断
        if overall_na_ratio > 0.05:
            summary_lines.append(f"💡 缺失比例较高，建议下游分析前进行缺失值处理")
        else:
            summary_lines.append(f"✅ 数据质量良好")

        result = "\n".join(summary_lines)

        log.info(f"✅ [Probe] detect_na 完成: {n_rows} 行, {n_cols} 列")
        # V2.4: 双模输出
        na_columns = []
        for col in df.columns:
            na_columns.append({
                "name": col,
                "missing_count": total_missing[col],
                "missing_ratio": round(total_missing[col] / n_rows, 4) if n_rows > 0 else 0,
            })
        structured = {
            "overall_na_ratio": round(overall_na_ratio, 4),
            "total_missing": total_missing_count,
            "columns": na_columns,
            "n_rows": n_rows,
            "n_cols": n_cols,
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] detect_na 失败: {str(e)}")
        return _make_probe_result(f"❌ 缺失值检测失败: {str(e)}", {"error": str(e)})


@tool
def compute_summary_stats(file_path: str, columns: Optional[str] = None) -> str:
    """
    计算表格文件中数值列的汇总统计信息。
    包括：计数、均值、标准差、最小值、25%/50%/75%分位数、最大值。

    用于判断数据分布、是否已做 Log 转换、值范围等场景。

    Args:
        file_path: 表格文件的绝对路径
        columns: 可选，逗号分隔的列名列表（如 "col1,col2"）；默认统计所有数值列

    Returns:
        汇总统计报告
    """
    cache_key = _get_cache_key(file_path) + f":stats:{columns}"
    cached = _check_probe_cache(cache_key, "compute_summary_stats")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] compute_summary_stats called: {file_path}, columns={columns}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    try:
        import pandas as pd

        # 检测分隔符
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
        delimiter = '\t'
        if ',' in first_line and '\t' not in first_line:
            delimiter = ','

        df = pd.read_csv(file_path, sep=delimiter, nrows=500000, low_memory=False)

        # 选择列
        target_columns = None
        if columns:
            target_columns = [c.strip() for c in columns.split(',')]

        # 筛选数值列
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if target_columns:
            numeric_cols = [c for c in target_columns if c in numeric_cols]
            non_numeric = [c for c in target_columns if c not in numeric_cols]
            if non_numeric:
                log.warning(f"[Probe] 非数值列跳过: {non_numeric}")

        if not numeric_cols:
            return _make_probe_result("⚠️ 没有可统计的数值列（所有列均为非数值类型）", {"error": "no_numeric_columns"})

        # 使用 describe() 计算统计
        stats_df = df[numeric_cols].describe()
        n_rows = len(df)
        n_numeric = len(numeric_cols)

        log.info(f"✅ [Probe] compute_summary_stats 完成: {n_rows} 行, {n_numeric} 数值列")

        # 收集结构化数据 + 计算全局汇总指标
        structured_columns = []
        all_mins, all_maxs, all_medians, all_means = [], [], [], []
        log_transformed_hint = False
        for col in numeric_cols:
            col_stats = {"name": col}
            for stat_key in ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']:
                if stat_key in stats_df.index:
                    val = stats_df.loc[stat_key, col]
                    if stat_key == 'count':
                        col_stats[stat_key] = int(val)
                    else:
                        col_stats[stat_key] = round(float(val), 4) if not pd.isna(val) else None
                else:
                    col_stats[stat_key] = None
            # rename keys for clarity
            col_stats["q1"] = col_stats.pop("25%")
            col_stats["median"] = col_stats.pop("50%")
            col_stats["q3"] = col_stats.pop("75%")
            col_min = col_stats.get("min")
            col_max = col_stats.get("max")
            col_median = col_stats.get("median")
            col_mean = col_stats.get("mean")
            if col_min is not None and col_max is not None:
                all_mins.append(col_min)
                all_maxs.append(col_max)
                if col_max <= 30 and col_min >= -5:
                    log_transformed_hint = True
            if col_median is not None:
                all_medians.append(col_median)
            if col_mean is not None:
                all_means.append(col_mean)
            structured_columns.append(col_stats)

        structured = {
            "columns": structured_columns,
            "log_transformed_hint": log_transformed_hint,
            "n_rows": n_rows,
            "n_numeric_cols": n_numeric,
        }

        # 生成简洁摘要（不含逐列明细，明细在 structured 中）
        global_min = min(all_mins) if all_mins else None
        global_max = max(all_maxs) if all_maxs else None
        median_of_medians = sorted(all_medians)[len(all_medians)//2] if all_medians else None
        median_of_means = sorted(all_means)[len(all_means)//2] if all_means else None

        summary_lines = [
            f"📊 汇总统计报告",
            f"",
            f"📁 文件: {os.path.basename(file_path)}",
            f"📐 维度: {n_rows} 行 × {len(df.columns)} 列（其中 {n_numeric} 个数值列）",
        ]

        if global_min is not None and global_max is not None:
            summary_lines.append(f"📏 全局值范围: [{global_min:.2f}, {global_max:.2f}]")
        if median_of_medians is not None:
            summary_lines.append(f"📈 列中位数分布: 中位值 ≈ {median_of_medians:.2f}，均值中位 ≈ {median_of_means:.2f}")

        # 统计推断
        if log_transformed_hint and global_min is not None and global_min < 0:
            summary_lines.append(f"💡 存在负值（Min={global_min:.2f}），且值范围紧凑，数据很可能已做 Log2(x+1) 转换")
        elif log_transformed_hint and global_min is not None and global_min >= 0:
            summary_lines.append(f"💡 值范围 [{global_min:.2f}, {global_max:.2f}]，可能已做 Log 转换")
        elif global_max is not None and global_max > 1000:
            summary_lines.append(f"💡 最大值超过 1000，可能为原始计数/丰度值，建议 Log2 转换后再分析")

        # 代表性列示例（前5列 + 首列如果是非数值列则标注）
        sample_cols = numeric_cols[:5]
        total_to_show = len(sample_cols)
        summary_lines.append(f"📋 各列统计详情见报告结构化字段（前{total_to_show}列预览）:")
        for col in sample_cols:
            col_m = next((c for c in structured_columns if c["name"] == col), None)
            if col_m:
                summary_lines.append(
                    f"  · {col}: Min={col_m.get('min')}, Median={col_m.get('median')}, "
                    f"Mean={col_m.get('mean')}, Max={col_m.get('max')}"
                )
        if len(numeric_cols) > total_to_show:
            summary_lines.append(f"  ... 共 {len(numeric_cols)} 列，完整明细见 structured.columns")

        # 第一列为非数值列时标注（如 Gene 列）
        first_col = df.columns[0]
        if first_col not in numeric_cols:
            summary_lines.insert(3, f"ℹ️  首列 '{first_col}' 为非数值列，已自动排除")

        result = _make_probe_result("\n".join(summary_lines), structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] compute_summary_stats 失败: {str(e)}")
        return _make_probe_result(f"❌ 汇总统计失败: {str(e)}", {"error": str(e)})


@tool
def detect_file_encoding(file_path: str) -> str:
    """
    检测文本文件的字符编码和字段分隔符。

    用于处理"文件打不开"、"乱码"、"不知道什么编码"等问题。
    采样文件头部（100KB）进行编码检测，分析前 10 行判断分隔符。

    Args:
        file_path: 文件的绝对路径

    Returns:
        编码和分隔符检测报告
    """
    cache_key = _get_cache_key(file_path) + ":encoding"
    cached = _check_probe_cache(cache_key, "detect_file_encoding")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] detect_file_encoding called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    try:
        file_size = os.path.getsize(file_path)

        # 步骤 1: 读取原始字节采样
        with open(file_path, 'rb') as f:
            raw_sample = f.read(min(100 * 1024, file_size))

        # 步骤 2: 检测编码
        encoding_result = None
        encoding_confidence = 0
        encoding_method = ""

        # 尝试 chardet
        try:
            import chardet
            detected = chardet.detect(raw_sample)
            encoding_result = detected.get('encoding')
            encoding_confidence = detected.get('confidence', 0)
            encoding_method = "chardet"
        except ImportError:
            pass

        # 降级：charset_normalizer
        if encoding_result is None:
            try:
                import charset_normalizer
                results = charset_normalizer.from_bytes(raw_sample)
                if results:
                    best = results[0]
                    encoding_result = best.encoding
                    encoding_confidence = 1.0
                    encoding_method = "charset_normalizer"
            except ImportError:
                pass

        # 最终降级：启发式检测
        if encoding_result is None:
            encoding_method = "heuristic"
            # 尝试 UTF-8
            try:
                raw_sample.decode('utf-8')
                encoding_result = 'utf-8'
                encoding_confidence = 0.9
            except UnicodeDecodeError:
                # 尝试常见编码
                for enc in ['gbk', 'gb2312', 'gb18030', 'latin-1', 'cp1252', 'shift_jis']:
                    try:
                        raw_sample.decode(enc)
                        encoding_result = enc
                        encoding_confidence = 0.7
                        break
                    except UnicodeDecodeError:
                        continue

        if encoding_result is None:
            encoding_result = 'unknown'

        # 步骤 3: 检测分隔符
        delimiter_result = "未知"
        delimiter_alternatives = []
        try:
            decoded_sample = raw_sample.decode(encoding_result, errors='replace')
            lines = decoded_sample.split('\n')[:10]
            lines = [l.rstrip('\r') for l in lines if l.strip()]

            if lines:
                # 统计各分隔符出现次数
                candidates = {'\\t (制表符)': 0, ', (逗号)': 0, '; (分号)': 0, '  (空格)': 0, '| (竖线)': 0}
                for line in lines[:5]:
                    candidates['\\t (制表符)'] += line.count('\t')
                    candidates[', (逗号)'] += line.count(',')
                    candidates['; (分号)'] += line.count(';')
                    candidates['| (竖线)'] += line.count('|')
                    # 空格：统计连续空格
                    space_count = len([s for s in line.split('  ') if s])
                    candidates['  (空格)'] += space_count

                # 一致性检查：每行分隔符数量是否相同
                for delim_char, _ in [('\t', '\\t (制表符)'), (',', ', (逗号)'), (';', '; (分号)'), ('|', '| (竖线)')]:
                    counts = [line.count(delim_char) for line in lines]
                    if len(set(counts)) == 1 and counts[0] > 0:
                        delimiter_result = f"{delim_char} (一致，每行 {counts[0]} 个字段)"
                        break

                # 如果上述都没匹配，取出现最多的
                if delimiter_result == "未知":
                    best_delim = max(candidates, key=candidates.get)
                    if candidates[best_delim] > 0:
                        delimiter_result = f"{best_delim} (推测，样本行中总计 {candidates[best_delim]} 次)"
        except:
            delimiter_result = "检测失败"

        # 步骤 4: 检查 BOM
        has_bom = raw_sample[:3] in (b'\xef\xbb\xbf',)  # UTF-8 BOM
        if raw_sample[:2] in (b'\xff\xfe', b'\xfe\xff'):
            has_bom = True

        result = f"""🔤 文件编码与格式检测报告

📁 文件路径: {file_path}
📏 文件大小: {_format_size(file_size)}

🔍 字符编码:
  - 检测编码: {encoding_result}
  - 置信度: {encoding_confidence:.0%}
  - 检测方法: {encoding_method}
  - BOM 标记: {'有' if has_bom else '无'}

📋 字段分隔符:
  - 检测结果: {delimiter_result}

💡 建议:
"""
        if encoding_result and encoding_result.lower() not in ('utf-8', 'ascii'):
            result += f"  - 文件为非 UTF-8 编码 ({encoding_result})，建议转换后使用\n"
        if delimiter_result != "未知":
            result += f"  - 使用 pandas.read_csv(file, sep=<delimiter>, encoding='{encoding_result}') 读取\n"

        log.info(f"✅ [Probe] detect_file_encoding 完成: encoding={encoding_result}")
        # V2.4: 双模输出
        structured = {
            "encoding": encoding_result,
            "confidence": encoding_confidence,
            "delimiter": delimiter_result,
            "has_bom": has_bom,
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] detect_file_encoding 失败: {str(e)}")
        return _make_probe_result(f"❌ 编码检测失败: {str(e)}", {"error": str(e)})


@tool
def compute_set_operations(
    file_path_1: str,
    file_path_2: str,
    column: str,
    column_2: Optional[str] = None,
    operation: str = "overlap"
) -> str:
    """
    对两个表格文件的指定列执行集合操作（交集、并集、差集）。

    用于"基因重叠"、"取交集"、"PTM位点交集"等场景。

    Args:
        file_path_1: 第一个表格文件的绝对路径
        file_path_2: 第二个表格文件的绝对路径
        column: 第一个文件中用于集合操作的列名
        column_2: 可选，第二个文件中的列名（默认与 column 相同）
        operation: 操作类型 — "overlap"(交集), "union"(并集),
                  "diff_1"(在文件1不在文件2), "diff_2"(在文件2不在文件1)

    Returns:
        集合操作结果报告
    """
    cache_key = f"{_get_cache_key(file_path_1)}|{_get_cache_key(file_path_2)}|{column}|{column_2}|{operation}"
    cached = _check_probe_cache(cache_key, "compute_set_operations")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] compute_set_operations called: {file_path_1}, {file_path_2}, col={column}")

    for fp in [file_path_1, file_path_2]:
        if not os.path.exists(fp):
            return _make_probe_result(f"❌ 文件不存在: {fp}", {"error": "file_not_found"})

    try:
        import pandas as pd

        col_2 = column_2 or column

        # 读取两个文件
        dfs = []
        for fp in [file_path_1, file_path_2]:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
            delimiter = '\t'
            if ',' in first_line and '\t' not in first_line:
                delimiter = ','
            dfs.append(pd.read_csv(fp, sep=delimiter))

        df1, df2 = dfs

        # 检查列是否存在
        if column not in df1.columns:
            return _make_probe_result(f"❌ 文件1中不存在列 '{column}'，可用列: {list(df1.columns)}", {"error": "column_not_found"})
        if col_2 not in df2.columns:
            return _make_probe_result(f"❌ 文件2中不存在列 '{col_2}'，可用列: {list(df2.columns)}", {"error": "column_not_found"})

        set1 = set(df1[column].dropna().astype(str).unique())
        set2 = set(df2[col_2].dropna().astype(str).unique())

        n1, n2 = len(set1), len(set2)
        intersection = set1 & set2
        union = set1 | set2
        diff_1 = set1 - set2
        diff_2 = set2 - set1

        result = f"""🔗 集合操作报告

📁 文件 1: {file_path_1} (列: {column})
📁 文件 2: {file_path_2} (列: {col_2})

📊 基本统计:
  - 文件 1 唯一值: {n1:,} 个
  - 文件 2 唯一值: {n2:,} 个
  - 交集 (overlap): {len(intersection):,} 个 ({len(intersection) / max(n1, 1) * 100:.1f}% of 文件1)
  - 并集 (union): {len(union):,} 个
  - 仅在文件1: {len(diff_1):,} 个
  - 仅在文件2: {len(diff_2):,} 个
"""

        if operation == "overlap":
            overlap_ratio = len(intersection) / max(n1, 1) * 100
            result += f"\n📋 交集列表 ({len(intersection)} 个):\n"
            result += ", ".join(sorted(list(intersection))[:20])
            if len(intersection) > 20:
                result += f"\n  ... 共 {len(intersection)} 个"
            result += f"\n\n💡 重叠比例: {overlap_ratio:.1f}% (相对于文件1)"
        elif operation == "union":
            result += f"\n📋 并集大小: {len(union)} 个\n"
        elif operation == "diff_1":
            result += f"\n📋 仅在文件1 ({len(diff_1)} 个):\n"
            result += ", ".join(sorted(list(diff_1))[:20])
        elif operation == "diff_2":
            result += f"\n📋 仅在文件2 ({len(diff_2)} 个):\n"
            result += ", ".join(sorted(list(diff_2))[:20])

        log.info(f"✅ [Probe] compute_set_operations 完成: |A|={n1}, |B|={n2}, |A∩B|={len(intersection)}")
        # V2.4: 双模输出
        structured = {
            "n_set1": n1,
            "n_set2": n2,
            "n_intersection": len(intersection),
            "n_union": len(union),
            "n_diff1": len(diff_1),
            "n_diff2": len(diff_2),
            "overlap_ratio": round(len(intersection) / max(n1, 1) * 100, 1),
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] compute_set_operations 失败: {str(e)}")
        return _make_probe_result(f"❌ 集合运算失败: {str(e)}", {"error": str(e)})


@tool
def inspect_vcf(file_path: str) -> str:
    """
    解析 VCF/BCF 变异检测文件的结构信息。
    返回样本列表、染色体分布、变异类型（SNP/INDEL/SV）统计。

    当用户询问"VCF文件"、"变异信息"、"样本名"时调用此工具。

    Args:
        file_path: VCF/BCF 文件的绝对路径（支持 .vcf, .vcf.gz, .bcf）

    Returns:
        VCF 结构报告
    """
    cache_key = _get_cache_key(file_path)
    cached = _check_probe_cache(cache_key, "inspect_vcf")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] inspect_vcf called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.vcf', '.bcf', '.gz'):
        return _make_probe_result(f"⚠️ 文件扩展名 {ext} 不是标准 VCF 格式（期望 .vcf/.vcf.gz/.bcf）", {"error": "invalid_extension"})

    try:
        # 优先使用 pysam
        try:
            import pysam
            vcf = pysam.VariantFile(file_path)
            samples = list(vcf.header.samples)
            contigs = list(vcf.header.contigs.keys())
            n_samples = len(samples)
            n_contigs = len(contigs)

            # 统计变异（限制扫描 10 万条）
            variant_types = {"SNP": 0, "INDEL": 0, "SV": 0, "OTHER": 0}
            chrom_counts = {}
            filter_stats = {"PASS": 0, "FILTERED": 0}
            total_variants = 0

            for rec in vcf:
                total_variants += 1
                chrom = rec.chrom
                chrom_counts[chrom] = chrom_counts.get(chrom, 0) + 1

                # 变异类型判断
                ref_len = len(rec.ref)
                alts = rec.alts or []
                if alts:
                    alt_lens = [len(a) for a in alts]
                    max_alt_len = max(alt_lens)
                    if ref_len == 1 and max_alt_len == 1:
                        variant_types["SNP"] += 1
                    elif ref_len != max_alt_len:
                        variant_types["INDEL"] += 1
                    elif max_alt_len > 50:
                        variant_types["SV"] += 1
                    else:
                        variant_types["OTHER"] += 1

                # FILTER 统计
                if rec.filter.keys() and len(rec.filter.keys()) > 0 and 'PASS' not in rec.filter.keys():
                    filter_stats["FILTERED"] += 1
                else:
                    filter_stats["PASS"] += 1

                if total_variants >= 100000:
                    break

            vcf.close()

            result = f"""🧬 VCF 变异文件结构报告

📁 文件路径: {file_path}
📏 文件大小: {_format_size(os.path.getsize(file_path))}

📊 概览:
  - 样本数: {n_samples}
  - 参考序列 (contig): {n_contigs} 个
  - 扫描变异数: {total_variants:,}

📋 样本列表 ({n_samples} 个):
"""
            for s in samples[:30]:
                result += f"  - {s}\n"
            if n_samples > 30:
                result += f"  ... 共 {n_samples} 个\n"

            result += f"\n🧬 变异类型分布:\n"
            for vtype, count in variant_types.items():
                if count > 0:
                    result += f"  - {vtype}: {count:,} ({count / max(total_variants, 1) * 100:.1f}%)\n"

            result += f"\n🏷️ FILTER 统计:\n"
            result += f"  - PASS: {filter_stats['PASS']:,}\n"
            result += f"  - 过滤: {filter_stats['FILTERED']:,}\n"

            sorted_chroms = sorted(chrom_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            result += f"\n📍 染色体分布 (Top 10):\n"
            for chrom, count in sorted_chroms:
                result += f"  - {chrom}: {count:,}\n"

            log.info(f"✅ [Probe] inspect_vcf 完成 (pysam): {n_samples} 样本, {total_variants} 变异")
            # V2.4: 双模输出
            structured = {
                "n_samples": n_samples,
                "n_variants": total_variants,
                "samples": samples,
                "variant_types": variant_types,
            }
            result = _make_probe_result(result, structured)
            _cache_result(cache_key, result)
            return result

        except ImportError:
            log.warning("[Probe] pysam 不可用，降级为手动 VCF 解析")

        # 降级：手动解析 VCF
        opener = open
        if file_path.endswith('.gz'):
            import gzip
            opener = gzip.open

        samples = []
        contigs = set()
        variant_types = {"SNP": 0, "INDEL": 0, "SV": 0, "OTHER": 0}
        total_variants = 0

        with opener(file_path, 'rt') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#'):
                    if line.startswith('##contig='):
                        # ##contig=<ID=chr1,length=248956422>
                        import re as regex
                        m = regex.search(r'ID=([^,>]+)', line)
                        if m:
                            contigs.add(m.group(1))
                    elif line.startswith('#CHROM'):
                        # #CHROM  POS  ID  REF  ALT  QUAL  FILTER  INFO  FORMAT  sample1  sample2 ...
                        parts = line.split('\t')
                        if len(parts) > 9:
                            samples = parts[9:]
                    continue

                total_variants += 1
                parts = line.split('\t', 5)
                if len(parts) >= 5:
                    ref = parts[3]
                    alt = parts[4]
                    ref_len = len(ref)
                    alt_fields = alt.split(',')
                    max_alt_len = max(len(a) for a in alt_fields)

                    if ref_len == 1 and max_alt_len == 1:
                        variant_types["SNP"] += 1
                    elif ref_len != max_alt_len:
                        variant_types["INDEL"] += 1
                    elif max_alt_len > 50:
                        variant_types["SV"] += 1
                    else:
                        variant_types["OTHER"] += 1

                if total_variants >= 100000:
                    break

        result = f"""🧬 VCF 变异文件结构报告 (手动解析)

📁 文件路径: {file_path}
📏 文件大小: {_format_size(os.path.getsize(file_path))}

📊 概览:
  - 样本数: {len(samples)}
  - 参考序列: {len(contigs)} 个
  - 扫描变异数: {total_variants:,}

📋 样本列表:
"""
        for s in samples[:30]:
            result += f"  - {s}\n"
        if len(samples) > 30:
            result += f"  ... 共 {len(samples)} 个\n"

        result += f"\n🧬 变异类型分布:\n"
        for vtype, count in variant_types.items():
            if count > 0:
                result += f"  - {vtype}: {count:,}\n"

        if contigs:
            result += f"\n📍 参考序列: {', '.join(sorted(contigs)[:10])}\n"

        log.info(f"✅ [Probe] inspect_vcf 完成 (手动): {len(samples)} 样本, {total_variants} 变异")
        # V2.4: 双模输出
        structured = {
            "n_samples": len(samples),
            "n_variants": total_variants,
            "samples": samples,
            "variant_types": variant_types,
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] inspect_vcf 失败: {str(e)}")
        return _make_probe_result(f"❌ VCF 解析失败: {str(e)}", {"error": str(e)})


@tool
def match_paired_fastq(directory_path: str) -> str:
    """
    扫描目录，查找并配对双端 FASTQ 文件（R1/R2 或 _1/_2）。

    自动识别 Illumina 命名约定，配对双端文件，找出落单的 FASTQ 文件。
    用于"检查 R1/R2 是否一一对应"、"双端文件配对"、"是否缺少某端文件"等场景。

    Args:
        directory_path: 要扫描的目录绝对路径

    Returns:
        配对报告，列出所有样本及其 R1/R2 文件对
    """
    cache_key = _get_cache_key(directory_path) + ":pair"
    cached = _check_probe_cache(cache_key, "match_paired_fastq")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] match_paired_fastq called: {directory_path}")

    if not os.path.exists(directory_path):
        return _make_probe_result(f"❌ 目录不存在: {directory_path}", {"error": "directory_not_found"})

    if not os.path.isdir(directory_path):
        return _make_probe_result(f"❌ 路径不是目录: {directory_path}", {"error": "not_a_directory"})

    try:
        import re as regex

        # 收集所有 FASTQ 文件
        fastq_files = []
        for root, dirs, files in os.walk(directory_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.startswith('.'):
                    continue
                f_lower = f.lower()
                if any(f_lower.endswith(ext) for ext in ('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
                    full_path = os.path.join(root, f)
                    file_size = os.path.getsize(full_path)
                    fastq_files.append((f, full_path, file_size))

        if not fastq_files:
            return _make_probe_result(f"📂 目录 {directory_path} 中未找到 FASTQ 文件", {"error": "no_fastq_found"})

        # 配对模式
        pair_patterns = [
            # _R1 / _R2 (Illumina 标准)
            regex.compile(r'^(.+?)_R1[_\\.]?(.*\.(?:fastq|fq)(?:\.gz)?)$', regex.IGNORECASE),
            regex.compile(r'^(.+?)_R2[_\\.]?(.*\.(?:fastq|fq)(?:\.gz)?)$', regex.IGNORECASE),
            # _1 / _2 (替代)
            regex.compile(r'^(.+?)_1[_\\.]?(.*\.(?:fastq|fq)(?:\.gz)?)$', regex.IGNORECASE),
            regex.compile(r'^(.+?)_2[_\\.]?(.*\.(?:fastq|fq)(?:\.gz)?)$', regex.IGNORECASE),
            # .R1. / .R2.
            regex.compile(r'^(.+?)\.R1\.(.+)$', regex.IGNORECASE),
            regex.compile(r'^(.+?)\.R2\.(.+)$', regex.IGNORECASE),
        ]

        # 分类：R1 文件、R2 文件
        r1_files = {}  # sample_name -> (filename, full_path, size)
        r2_files = {}
        unmatched = []

        for filename, full_path, size in fastq_files:
            matched = False
            for i, pattern in enumerate(pair_patterns):
                m = pattern.search(filename)
                if m:
                    sample_name = m.group(1).rstrip('_').rstrip('.')
                    if i % 2 == 0:  # R1 patterns (even indices)
                        r1_files[sample_name] = (filename, full_path, size)
                    else:  # R2 patterns (odd indices)
                        r2_files[sample_name] = (filename, full_path, size)
                    matched = True
                    break
            if not matched:
                unmatched.append((filename, full_path, size))

        # 配对分析
        all_samples = set(list(r1_files.keys()) + list(r2_files.keys()))
        paired = []
        r1_only = []
        r2_only = []

        for sample in sorted(all_samples):
            has_r1 = sample in r1_files
            has_r2 = sample in r2_files
            if has_r1 and has_r2:
                _, path1, size1 = r1_files[sample]
                _, path2, size2 = r2_files[sample]
                paired.append((sample, path1, size1, path2, size2))
            elif has_r1:
                fname, path, size = r1_files[sample]
                r1_only.append((sample, fname, path, size))
            elif has_r2:
                fname, path, size = r2_files[sample]
                r2_only.append((sample, fname, path, size))

        # 构建报告
        result = f"""🔗 FASTQ 双端文件配对报告

📂 目录: {directory_path}
📊 总 FASTQ 文件: {len(fastq_files)} 个

✅ 配对成功: {len(paired)} 对 ({len(paired) * 2} 个文件)
"""
        if paired:
            result += "\n📋 配对详情:\n"
            result += f"  {'样本名':<30} {'R1大小':>10} {'R2大小':>10}\n"
            result += f"  {'-'*30} {'-'*10} {'-'*10}\n"
            for sample, _, size1, _, size2 in paired[:20]:
                result += f"  {sample:<30} {_format_size(size1):>10} {_format_size(size2):>10}\n"
            if len(paired) > 20:
                result += f"  ... 共 {len(paired)} 对\n"

        if r1_only:
            result += f"\n⚠️ 仅有 R1 (缺 R2) - {len(r1_only)} 个:\n"
            for sample, fname, _, size in r1_only[:10]:
                result += f"  - {sample}: {fname} ({_format_size(size)})\n"

        if r2_only:
            result += f"\n⚠️ 仅有 R2 (缺 R1) - {len(r2_only)} 个:\n"
            for sample, fname, _, size in r2_only[:10]:
                result += f"  - {sample}: {fname} ({_format_size(size)})\n"

        if unmatched:
            result += f"\n❓ 未识别配对模式 - {len(unmatched)} 个:\n"
            for fname, _, size in unmatched[:10]:
                result += f"  - {fname} ({_format_size(size)})\n"

        # 总体判断
        if not r1_only and not r2_only and not unmatched:
            result += f"\n✅ 所有 {len(paired)} 对文件配对完整，R1/R2 一一对应"
        else:
            issues = []
            if r1_only:
                issues.append(f"{len(r1_only)} 个 R1 缺 R2")
            if r2_only:
                issues.append(f"{len(r2_only)} 个 R2 缺 R1")
            if unmatched:
                issues.append(f"{len(unmatched)} 个无法识别")
            result += f"\n⚠️ 存在问题: {', '.join(issues)}"

        log.info(f"✅ [Probe] match_paired_fastq 完成: {len(paired)} 对, {len(r1_only)} R1-only, {len(r2_only)} R2-only")
        # V2.4: 双模输出
        structured = {
            "n_pairs": len(paired),
            "n_r1_only": len(r1_only),
            "n_r2_only": len(r2_only),
            "n_unmatched": len(unmatched),
            "pairs": [sample for sample, _, _, _, _ in paired],
            "r1_only_samples": [sample for sample, _, _, _ in r1_only],
            "r2_only_samples": [sample for sample, _, _, _ in r2_only],
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] match_paired_fastq 失败: {str(e)}")
        return _make_probe_result(f"❌ FASTQ 配对失败: {str(e)}", {"error": str(e)})


@tool
def detect_file_type(file_path: str) -> str:
    """
    基于文件扩展名、magic bytes 和内容模式综合判断文件类型。

    适用于用户不确定文件类型或文件扩展名缺失的场景。
    检测策略：扩展名（第一优先级）→ magic bytes → 内容模式匹配。

    Args:
        file_path: 文件的绝对路径

    Returns:
        文件类型检测报告（primary_type, confidence, alternative_types）
    """
    cache_key = _get_cache_key(file_path) + ":file_type"
    cached = _check_probe_cache(cache_key, "detect_file_type")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] detect_file_type called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    if not os.path.isfile(file_path):
        return _make_probe_result(f"❌ 路径不是文件: {file_path}", {"error": "not_a_file"})

    try:
        file_size = os.path.getsize(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        if ext.startswith('.'):
            ext = ext[1:]

        # ===== Step 1: 扩展名检测 =====
        EXT_TYPE_MAP = {
            'csv': 'tabular', 'tsv': 'tabular', 'txt': 'tabular',
            'xlsx': 'tabular', 'xls': 'tabular', 'parquet': 'tabular',
            'fastq': 'fastq', 'fq': 'fastq', 'fasta': 'fasta', 'fa': 'fasta',
            'bam': 'bam', 'sam': 'sam', 'cram': 'cram',
            'vcf': 'vcf', 'gvcf': 'vcf',
            'bed': 'bed', 'gff': 'gff', 'gtf': 'gtf',
            'h5ad': 'h5ad', 'h5': 'h5',
            'mtx': 'mtx',
            'gz': 'gzip', 'tar': 'tar', 'zip': 'zip', 'bz2': 'bzip2',
            'py': 'python', 'r': 'r_script', 'sh': 'shell', 'ipynb': 'jupyter',
            'md': 'markdown', 'json': 'json', 'yaml': 'yaml', 'yml': 'yaml',
            'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'svg': 'image',
            'pdf': 'pdf', 'tiff': 'image', 'bmp': 'image',
        }

        # 处理复合扩展名 (.mtx.gz, .fastq.gz 等)
        compound_ext = ext
        base_name = os.path.basename(file_path).lower()
        for comp in ['mtx.gz', 'fastq.gz', 'fa.gz', 'fq.gz', 'csv.gz', 'tsv.gz']:
            if base_name.endswith(comp):
                compound_ext = comp
                break

        primary_from_ext = EXT_TYPE_MAP.get(compound_ext, ext if ext else 'unknown')
        alternative_types = []

        # ===== Step 2: Magic bytes 检测 =====
        magic_primary = None
        magic_confidence = 0.0
        with open(file_path, 'rb') as f:
            magic = f.read(16)

        if magic[:4] == b'\x1f\x8b\x08\x04':
            magic_primary = 'bam'  # BGZF-compressed SAM
            magic_confidence = 0.95
        elif magic[:3] in (b'@HD', b'@SQ', b'@RG', b'@PG'):
            magic_primary = 'sam'
            magic_confidence = 0.95
        elif magic[:2] == b'\x1f\x8b':
            magic_primary = 'gzip'
            magic_confidence = 0.95
        elif magic[:4] == b'\x89HDF':
            magic_primary = 'h5'
            magic_confidence = 0.95
        elif magic[:4] == b'PAR1':
            magic_primary = 'parquet'
            magic_confidence = 0.95
        elif magic[:2] == b'BZ':
            magic_primary = 'bzip2'
            magic_confidence = 0.95
        elif magic[:4] == b'%PDF':
            magic_primary = 'pdf'
            magic_confidence = 0.95

        # ===== Step 3: 内容模式匹配 =====
        content_primary = None
        content_confidence = 0.0
        content_details = {}

        if magic_primary != 'gzip' and file_size < 10 * 1024 * 1024:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    first_lines = ''.join([f.readline() for _ in range(5)])

                # VCF 检测: ##fileformat=VCF 或 #CHROM\tPOS...
                if first_lines.startswith('##fileformat=VCF') or '#CHROM\t' in first_lines:
                    content_primary = 'vcf'
                    content_confidence = 0.95
                # GTF/GFF 检测: 9列 tab 分隔
                elif first_lines.strip():
                    lines = first_lines.strip().split('\n')
                    for line in lines:
                        if line.startswith('##') or line.startswith('#'):
                            continue
                        cols = line.split('\t')
                        if len(cols) == 9 and cols[2] in (
                            'gene', 'exon', 'CDS', 'transcript',
                            'start_codon', 'stop_codon'
                        ):
                            if 'gene_id' in line or 'transcript_id' in line:
                                content_primary = 'gtf'
                            else:
                                content_primary = 'gff'
                            content_confidence = 0.90
                            break

                # FASTA 检测: > 开头
                if any(line.startswith('>') for line in first_lines.strip().split('\n')):
                    if content_primary is None:
                        content_primary = 'fasta'
                        content_confidence = 0.90

                # FASTQ 检测: @ 开头 + + 质量行
                if first_lines.strip():
                    line_list = first_lines.strip().split('\n')
                    if len(line_list) >= 4:
                        if line_list[0].startswith('@') and line_list[2].startswith('+'):
                            if content_primary is None:
                                content_primary = 'fastq'
                                content_confidence = 0.85
                            elif content_primary != 'fastq':
                                alternative_types.append('fastq')

                # MTX Matrix Market 检测: %%MatrixMarket 头
                if first_lines.startswith('%%MatrixMarket'):
                    content_primary = 'mtx'
                    content_confidence = 0.98
                    for line in first_lines.strip().split('\n'):
                        if line.startswith('%%MatrixMarket'):
                            content_details['format_header'] = line.strip()
                        elif not line.startswith('%') and line.strip():
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                try:
                                    content_details['n_rows'] = int(parts[0])
                                    content_details['n_cols'] = int(parts[1])
                                    content_details['n_nonzero'] = int(parts[2]) if len(parts) >= 3 else None
                                except ValueError:
                                    pass
                            break
                # Tabular 检测: 计数分隔符
                elif first_lines and first_lines[0] != '#' and not first_lines[0].startswith('>') and not first_lines[0].startswith('@'):
                    first_line = first_lines.split('\n')[0]
                    if '\t' in first_line:
                        content_details['delimiter'] = 'tab'
                    elif ',' in first_line:
                        content_details['delimiter'] = 'comma'
            except UnicodeDecodeError:
                pass  # 二进制文件，跳过内容检测

        # ===== 综合判定 =====
        if magic_primary and magic_confidence > 0.9:
            primary_type = magic_primary
            confidence = magic_confidence
        elif content_primary and content_confidence > 0.9:
            primary_type = content_primary
            confidence = content_confidence
        else:
            primary_type = primary_from_ext
            confidence = 0.7 if ext else 0.3

        # 收集备选类型
        for alt_type in [primary_from_ext, magic_primary, content_primary]:
            if alt_type and alt_type != primary_type and alt_type not in alternative_types:
                alternative_types.append(alt_type)

        result = f"""🔍 文件类型检测报告

📁 文件路径: {file_path}
📏 文件大小: {file_size / 1024:.1f} KB
📎 扩展名: {ext if ext else '(无)'}
🔬 Magic Bytes: {magic[:8].hex()} (前 8 字节)
✅ 主要类型: {primary_type}
🎯 置信度: {confidence:.0%}
📋 候选类型: {', '.join(alternative_types) if alternative_types else '无'}
"""
        if content_details:
            result += f"\n📝 内容详情:\n{json.dumps(content_details, ensure_ascii=False, indent=2)}"

        structured = {
            "primary_type": primary_type,
            "confidence": round(confidence, 3),
            "alternative_types": alternative_types,
            "extension": ext if ext else None,
            "file_size_kb": round(file_size / 1024, 1),
            "details": content_details if content_details else None,
        }
        result = _make_probe_result(result, structured)
        _cache_result(cache_key, result)
        return result

    except Exception as e:
        log.error(f"❌ [Probe] detect_file_type 失败: {str(e)}")
        return _make_probe_result(f"❌ 文件类型检测失败: {str(e)}", {"error": str(e)})


@tool
def inspect_mtx(file_path: str) -> str:
    """
    轻量级 MTX 矩阵维度探测 —— 仅读文件头，不加载全量数据。

    对 10GB+ 的 Matrix Market 文件同样秒级返回维度信息。
    支持 gzip 压缩的 .mtx.gz 文件和标准 .mtx 文件。

    Args:
        file_path: MTX 文件的绝对路径

    Returns:
        MTX 矩阵维度、格式、稀疏度等结构化报告
    """
    cache_key = _get_cache_key(file_path) + ":mtx"
    cached = _check_probe_cache(cache_key, "inspect_mtx")
    if cached is not None:
        return cached

    log.info(f"🔍 [Probe] inspect_mtx called: {file_path}")

    if not os.path.exists(file_path):
        return _make_probe_result(f"❌ 文件不存在: {file_path}", {"error": "file_not_found"})

    try:
        file_size = os.path.getsize(file_path)
        is_gzip = file_path.endswith('.gz')

        # 打开文件（按需解压 gzip）
        if is_gzip:
            import gzip
            f = gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore')
        else:
            f = open(file_path, 'r', encoding='utf-8', errors='ignore')

        try:
            header_line = None
            dims_line = None
            n_comment_lines = 0

            for line in f:
                line = line.strip()
                if line.startswith('%%MatrixMarket'):
                    header_line = line
                elif line.startswith('%'):
                    n_comment_lines += 1
                elif not line and not header_line:
                    continue
                elif line and not line.startswith('%'):
                    dims_line = line
                    break
                if n_comment_lines > 1000:
                    break

            # 解析 MatrixMarket header
            if header_line:
                header_lower = header_line.lower()
                if 'coordinate' in header_lower:
                    mtx_format = 'coordinate'
                elif 'array' in header_lower:
                    mtx_format = 'array'
                else:
                    mtx_format = 'unknown'

                if 'real' in header_lower:
                    mtx_type = 'real'
                elif 'integer' in header_lower:
                    mtx_type = 'integer'
                elif 'pattern' in header_lower:
                    mtx_type = 'pattern'
                else:
                    mtx_type = 'unknown'
            else:
                mtx_format = 'unknown'
                mtx_type = 'unknown'

            # 解析维度行
            n_rows = 0
            n_cols = 0
            n_nonzero = 0

            if dims_line:
                parts = dims_line.strip().split()
                if len(parts) >= 2:
                    try:
                        n_rows = int(parts[0])
                        n_cols = int(parts[1])
                        if len(parts) >= 3:
                            n_nonzero = int(parts[2])
                    except ValueError:
                        pass

            result = f"""🔬 MTX 矩阵文件探查报告

📁 文件路径: {file_path}
📏 文件大小: {file_size / 1024 / 1024:.2f} MB{" (gzip 压缩)" if is_gzip else ""}
📐 矩阵维度: {n_rows} 行 × {n_cols} 列
🔢 非零元素数: {n_nonzero:,}
📦 存储格式: {mtx_format}
🔤 元素类型: {mtx_type}
💾 备注行数: {n_comment_lines}
"""

            # 计算稀疏度
            if n_rows > 0 and n_cols > 0 and n_nonzero > 0:
                total = n_rows * n_cols
                sparsity = 1.0 - (n_nonzero / total)
                result += f"🕸️ 稀疏度: {sparsity:.4%} ({n_nonzero:,} / {total:,})"
                if sparsity > 0.95:
                    result += " (极度稀疏)"
                elif sparsity > 0.8:
                    result += " (高度稀疏)"

            if mtx_format == "unknown" and not header_line:
                result += "\n\n⚠️ 未检测到 %%MatrixMarket 头部，文件可能不是标准 MTX 格式"

            structured = {
                "n_rows": n_rows,
                "n_cols": n_cols,
                "n_nonzero": n_nonzero,
                "format": mtx_format,
                "element_type": mtx_type,
                "comment_lines": n_comment_lines,
                "file_size_mb": round(file_size / 1024 / 1024, 2),
                "is_gzip": is_gzip,
            }
            if n_rows > 0 and n_cols > 0 and n_nonzero > 0:
                structured["sparsity"] = round(1.0 - (n_nonzero / (n_rows * n_cols)), 4)

            result = _make_probe_result(result, structured)
            _cache_result(cache_key, result)
            return result
        finally:
            f.close()

    except Exception as e:
        log.error(f"❌ [Probe] inspect_mtx 失败: {str(e)}")
        return _make_probe_result(f"❌ MTX 文件探查失败: {str(e)}", {"error": str(e)})


def _get_file_icon(ext: str) -> str:
    """根据扩展名返回对应图标"""
    image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.tiff', '.bmp'}
    data_exts = {'.csv', '.tsv', '.xlsx', '.xls', '.parquet', '.h5', '.h5ad'}
    code_exts = {'.py', '.r', '.sh', '.ipynb', '.md', '.txt', '.json', '.yaml', '.yml'}
    bio_exts = {'.fastq', '.fq', '.fasta', '.fa', '.bam', '.sam', '.vcf', '.bed', '.gtf', '.gff', '.mtx'}

    if ext in image_exts:
        return "🖼️"
    elif ext in data_exts:
        return "📊"
    elif ext in code_exts:
        return "📄"
    elif ext in bio_exts:
        return "🧬"
    else:
        return "📄"


@tool
def sandbox_probe(code: str, workspace_path: str, description: str = "") -> str:
    """
    在 Docker 沙箱中执行 AI 生成的 Python 探查脚本，探查内置工具不支持的文件格式。

    当 13 个内置探针工具均无法处理目标文件格式时，LLM 可自主编写 Python 脚本，
    通过此工具在安全的 Docker 沙箱容器中运行，读取工作区文件并输出探查结果。

    典型场景：
    - 探查非标准格式的生物信息学文件（如 GCT、GPR、SOFT 等）
    - 对自定义二进制格式进行轻量级解析
    - 补充内置探针工具未覆盖的特定文件结构探查

    Args:
        code: 完整的 Python 探查脚本源代码，通过 stdout 输出探查结果
        workspace_path: 项目工作区的绝对路径（供脚本设置文件读取路径）
        description: 脚本探查目的的简短描述（用于日志记录和审计）

    Returns:
        脚本执行的 stdout + stderr 输出
    """
    # 延迟导入以避免循环依赖（probe_tools.py ↔ bio_tools.py）
    from app.tools.bio_tools import run_container_simple

    log.info(f"🔍 [Probe] sandbox_probe called: description='{description[:100]}'")

    if not code or not code.strip():
        return _make_probe_result("❌ 探查脚本代码为空", {"error": "empty_code"})

    # 构建沙箱执行环境：将输出目录设为工作区路径
    # 探针脚本只需读取文件，无需写入结果文件，使用 workspace_path 作为工作目录
    task_out_dir = workspace_path or "/workspace"
    os.makedirs(task_out_dir, exist_ok=True)

    environment = {
        "TASK_OUT_DIR": task_out_dir,
    }

    log.info(
        f"🛡️ [sandbox_probe] 执行探查脚本: "
        f"code_len={len(code)}, workspace={task_out_dir}"
    )

    try:
        # 使用简化的沙箱执行路径（60s 超时，探针应轻量快速）
        result_output, exit_code = run_container_simple(
            image='autonome-tool-env',
            command=code,
            language='python',
            environment=environment,
            timeout=60,  # 探针脚本应快速返回，1分钟硬超时
        )

        if exit_code == 0:
            log.info(f"✅ [sandbox_probe] 探查脚本执行成功, output_len={len(result_output)}")
            summary = f"""🛠️ 自定义探查脚本执行报告

📝 探查目的: {description if description else '(未指定)'}
✅ 执行状态: 成功 (exit_code=0)
📏 输出长度: {len(result_output)} 字符
📁 工作目录: {workspace_path}

=== 探查脚本 ===
{code[:500]}{'...' if len(code) > 500 else ''}

=== 探查输出 ===
{result_output[:3000]}{'...' if len(result_output) > 3000 else ''}
"""
            return _make_probe_result(summary, {
                "exit_code": exit_code,
                "output": result_output,
                "description": description,
                "code_snippet": code[:200],
            })
        else:
            log.warning(f"⚠️ [sandbox_probe] 探查脚本返回非零退出码: {exit_code}")
            summary = f"""🛠️ 自定义探查脚本执行报告

📝 探查目的: {description if description else '(未指定)'}
⚠️ 执行状态: 失败 (exit_code={exit_code})
📁 工作目录: {workspace_path}

=== 探查脚本 ===
{code[:500]}{'...' if len(code) > 500 else ''}

=== 错误输出 ===
{result_output[:3000]}{'...' if len(result_output) > 3000 else ''}
"""
            return _make_probe_result(summary, {
                "exit_code": exit_code,
                "error": result_output,
                "description": description,
                "code_snippet": code[:200],
            })

    except Exception as e:
        log.error(f"❌ [sandbox_probe] 沙箱执行异常: {str(e)}")
        return _make_probe_result(f"❌ 探查脚本执行异常: {str(e)}", {"error": str(e)})


# 导出工具列表（供 data_probe_node.py 导入）
probe_tools_list = [
    peek_tabular_data, scan_workspace, inspect_h5ad, inspect_fastq, inspect_bam,
    detect_na, compute_summary_stats, detect_file_encoding,
    compute_set_operations, inspect_vcf, match_paired_fastq,
    detect_file_type, inspect_mtx, sandbox_probe,
]

# 工具分类：查看类（内容预览，附件注入时可跳过）vs 计算类（深度分析，附件注入时保留）
VIEW_TOOLS = {"scan_workspace", "peek_tabular_data", "inspect_h5ad", "inspect_fastq", "inspect_bam", "inspect_vcf", "inspect_mtx", "detect_file_type", "sandbox_probe"}
COMPUTE_TOOLS = {"detect_na", "compute_summary_stats", "detect_file_encoding", "compute_set_operations", "match_paired_fastq"}

log.info("🔍 环境探针工具模块已加载（含多组学探针）")