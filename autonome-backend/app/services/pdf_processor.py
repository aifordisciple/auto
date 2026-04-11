"""
PDF 内容提取服务

支持 PDF 文档文本和表格提取，将内容注入 AI 上下文

设计要点：
- 分页处理避免内存溢出
- 表格提取为 Markdown 格式，便于 AI 理解
- 内容截断保护，防止单文件占用过多上下文
"""

import os
from typing import Optional
from typing import TypedDict
import pdfplumber

from app.core.logger import log


class PDFExtractResult(TypedDict):
    """PDF提取结果结构"""
    file_path: str
    file_name: str
    total_pages: int
    text_content: str
    tables: list[dict]
    extraction_status: str  # "success" | "partial" | "failed"
    error_message: Optional[str]
    char_count: int
    table_count: int


def extract_pdf_content(
    file_path: str,
    max_pages: int = 50,
    max_chars: int = 100000
) -> PDFExtractResult:
    """
    提取PDF文件的文本内容和表格数据

    设计说明：
    - 支持大文件分页处理，避免内存溢出
    - 表格提取为结构化数据，便于AI理解
    - 内容截断保护，防止单个文件占用过多上下文

    Args:
        file_path: PDF文件的绝对路径
        max_pages: 最大处理页数限制，默认50页
        max_chars: 最大字符数限制，默认10万字符

    Returns:
        PDFExtractResult: 包含提取结果和元数据的字典
    """
    log.info(f"📄 [PDF] 开始解析: {file_path}")

    result: PDFExtractResult = {
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "total_pages": 0,
        "text_content": "",
        "tables": [],
        "extraction_status": "success",
        "error_message": None,
        "char_count": 0,
        "table_count": 0
    }

    try:
        with pdfplumber.open(file_path) as pdf:
            result["total_pages"] = len(pdf.pages)
            pages_to_process = pdf.pages[:max_pages]

            all_text = []
            all_tables = []

            for page_num, page in enumerate(pages_to_process, 1):
                # 提取文本
                page_text = page.extract_text() or ""
                if page_text.strip():
                    all_text.append(f"--- 第 {page_num} 页 ---\n{page_text}")

                # 提取表格
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables, 1):
                    if table and len(table) > 0:
                        table_md = _format_table_to_markdown(table, page_num, table_idx)
                        all_tables.append({
                            "page": page_num,
                            "table_index": table_idx,
                            "rows": len(table),
                            "markdown": table_md
                        })

                # 检查字符限制
                current_chars = sum(len(t) for t in all_text)
                if current_chars > max_chars:
                    log.warning(f"📄 [PDF] 内容超过 {max_chars} 字符，截断处理")
                    result["extraction_status"] = "partial"
                    break

            result["text_content"] = "\n\n".join(all_text)[:max_chars]
            result["tables"] = all_tables
            result["char_count"] = len(result["text_content"])
            result["table_count"] = len(all_tables)

            log.info(f"📄 [PDF] 解析完成: {result['total_pages']} 页, "
                     f"{result['char_count']} 字符, {result['table_count']} 个表格")

    except Exception as e:
        log.error(f"📄 [PDF] 解析失败: {e}")
        result["extraction_status"] = "failed"
        result["error_message"] = str(e)

    return result


def _format_table_to_markdown(table: list, page_num: int, table_idx: int) -> str:
    """
    将PDF表格转换为Markdown格式

    Args:
        table: pdfplumber 提取的表格数据（二维列表）
        page_num: 页码
        table_idx: 表格序号

    Returns:
        str: Markdown 格式的表格字符串
    """
    if not table or len(table) == 0:
        return ""

    lines = [f"\n**表 {table_idx} (第 {page_num} 页)**\n"]

    # 处理表头
    header = table[0] if table else []
    header = [str(cell) if cell else "" for cell in header]

    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    # 处理数据行
    for row in table[1:]:
        cells = [str(cell).replace("\n", " ") if cell else "" for cell in row]
        # 补齐列数
        while len(cells) < len(header):
            cells.append("")
        cells = cells[:len(header)]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def build_pdf_context_message(pdf_results: list[PDFExtractResult]) -> str:
    """
    构建PDF内容上下文消息，注入到AI提示词中

    将提取的PDF文本和表格组织为结构化的上下文消息，
    帮助 AI 理解用户上传的PDF文档内容。

    Args:
        pdf_results: PDF提取结果列表

    Returns:
        str: 格式化的上下文消息字符串
    """
    if not pdf_results:
        return ""

    context_parts = ["\n\n📚 **用户上传的PDF文档内容**：\n"]

    for idx, pdf in enumerate(pdf_results, 1):
        context_parts.append(f"\n---\n### 📄 PDF {idx}: {pdf['file_name']}\n")
        context_parts.append(f"- 总页数: {pdf['total_pages']}\n")
        context_parts.append(f"- 提取字符: {pdf['char_count']:,}\n")
        context_parts.append(f"- 表格数量: {pdf['table_count']}\n")

        if pdf['extraction_status'] == 'failed':
            context_parts.append(f"\n⚠️ **解析失败**: {pdf['error_message']}\n")
            continue
        elif pdf['extraction_status'] == 'partial':
            context_parts.append("\n⚠️ **内容已截断** (超过限制)\n")

        if pdf['text_content']:
            context_parts.append(f"\n**文档正文**:\n```\n{pdf['text_content']}\n```\n")

        if pdf['tables']:
            context_parts.append("\n**提取的表格**:\n")
            # 限制表格数量避免上下文过长
            for table in pdf['tables'][:10]:
                context_parts.append(table['markdown'])

    context_parts.append("\n---\n")
    return "".join(context_parts)