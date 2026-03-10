"""
环境探针工具模块

提供两个核心探针工具，让 AI Agent 能够"感知"数据环境，不再盲目写代码。
"""

import os
import json
from typing import Optional
from langchain_core.tools import tool
from app.core.logger import log


@tool
def peek_tabular_data(file_path: str, n_rows: int = 5) -> str:
    """
    预览表格文件（CSV/TSV/TXT）的结构：表头、维度和前几行数据。

    在处理任何表格数据前，强制先调用此工具了解表头和维度，绝不盲目瞎猜列名！

    Args:
        file_path: 表格文件的绝对路径（如 /app/uploads/project_1/raw_data/counts.tsv）
        n_rows: 预览行数，默认 5 行

    Returns:
        包含表头、维度、前 n_rows 行数据的结构化信息字符串
    """
    log.info(f"🔍 [Probe] peek_tabular_data called: {file_path}")

    if not os.path.exists(file_path):
        return f"❌ 文件不存在: {file_path}"

    if not os.path.isfile(file_path):
        return f"❌ 路径不是文件: {file_path}"

    # 检测文件大小，避免读取超大文件
    file_size = os.path.getsize(file_path)
    if file_size > 100 * 1024 * 1024:  # 100MB
        return f"⚠️ 文件过大 ({file_size / 1024 / 1024:.1f} MB)，建议使用分块读取方式处理"

    try:
        # 尝试检测分隔符
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()

        if not first_line.strip():
            return "❌ 文件为空"

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

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 读取第一行作为表头
            first_line = f.readline()
            if not first_line.strip():
                return "❌ 文件为空"

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
{json.dumps(headers, ensure_ascii=False, indent=2)}

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
        return result

    except Exception as e:
        log.error(f"❌ [Probe] 读取文件失败: {str(e)}")
        return f"❌ 读取文件失败: {str(e)}"


@tool
def scan_workspace(directory_path: str, max_depth: int = 3) -> str:
    """
    扫描指定目录下的所有文件和文件夹，返回结构化的目录树。

    当需要找文件但不确定位置时，调用此工具获取目录结构。

    Args:
        directory_path: 要扫描的目录绝对路径（如 /app/uploads/project_1）
        max_depth: 最大扫描深度，默认 3 层

    Returns:
        结构化的目录树字符串
    """
    log.info(f"🔍 [Probe] scan_workspace called: {directory_path}")

    if not os.path.exists(directory_path):
        return f"❌ 目录不存在: {directory_path}"

    if not os.path.isdir(directory_path):
        return f"❌ 路径不是目录: {directory_path}"

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

            # 渲染文件
            for i, file in enumerate(files):
                is_last = (i == len(files) - 1)
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

                # 统计文件类型
                file_counts["total"] += 1
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
        return result

    except Exception as e:
        log.error(f"❌ [Probe] 扫描目录失败: {str(e)}")
        return f"❌ 扫描目录失败: {str(e)}"


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
        return f"❌ 文件不存在: {file_path}"

    if not file_path.endswith('.h5ad'):
        return f"⚠️ 文件扩展名不是 .h5ad，可能不是有效的 AnnData 文件"

    try:
        # 尝试导入 scanpy
        try:
            import scanpy as sc
        except ImportError:
            return "❌ scanpy 未安装，无法解析 .h5ad 文件。请在沙箱环境中安装 scanpy。"

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
        return result

    except Exception as e:
        log.error(f"❌ [Probe] h5ad 解析失败: {str(e)}")
        return f"❌ 解析 .h5ad 文件失败: {str(e)}"


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
        return f"❌ 文件不存在: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.fastq', '.fq', '.gz']:
        return f"⚠️ 文件扩展名 {ext} 不是标准的 FASTQ 格式"

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
        return result

    except Exception as e:
        log.error(f"❌ [Probe] FASTQ 解析失败: {str(e)}")
        return f"❌ 解析 FASTQ 文件失败: {str(e)}"


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
        return f"❌ 文件不存在: {file_path}"

    if not file_path.endswith('.bam'):
        return f"⚠️ 文件扩展名不是 .bam"

    try:
        # 检查 pysam 是否可用
        try:
            import pysam
        except ImportError:
            return "❌ pysam 未安装，无法解析 BAM 文件。请在沙箱环境中安装 pysam。"

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

        log.info(f"✅ [Probe] BAM 预览完成: {total_reads} reads, 比对率 {mapping_rate:.1f}%")
        return result

    except Exception as e:
        log.error(f"❌ [Probe] BAM 解析失败: {str(e)}")
        return f"❌ 解析 BAM 文件失败: {str(e)}"


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


# 导出工具列表（供 bio_tools.py 导入）
probe_tools_list = [peek_tabular_data, scan_workspace, inspect_h5ad, inspect_fastq, inspect_bam]

log.info("🔍 环境探针工具模块已加载（含多组学探针）")