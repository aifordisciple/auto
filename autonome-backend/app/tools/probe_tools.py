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

        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()

        # 解析表头
        if delimiter:
            headers = [h.strip() for h in all_lines[0].strip().split(delimiter)]
        else:
            headers = all_lines[0].strip().split()

        n_cols = len(headers)
        n_total_rows = len(all_lines) - 1  # 减去表头

        # 预览数据行
        preview_lines = all_lines[1:n_rows + 1]
        preview_data = []
        for i, line in enumerate(preview_lines, 1):
            if delimiter:
                cells = [c.strip() for c in line.strip().split(delimiter)]
            else:
                cells = line.strip().split()
            preview_data.append(cells)

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
probe_tools_list = [peek_tabular_data, scan_workspace]

log.info("🔍 环境探针工具模块已加载")