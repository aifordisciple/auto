"""
学习中心文献摄入服务

协调 PDF 处理流水线：
1. PyMuPDF 文本提取 + 图表截取
2. 智能分块（按章节/段落/图表边界切分）
3. Vision LLM 图表理解（结构化 JSON 提取）
4. Embedding 生成
5. 入库

设计要点：
- 分块目标 200-500 字符
- 图注对齐（"As shown in Fig 1A" 关联到对应图表）
- Vision LLM 失败时降级为文本 LLM
"""

import os
import re
import hashlib
from typing import Optional, List, Dict, Any, TypedDict

from app.core.logger import log
from app.core.config import settings


# ==========================================
# 数据结构定义
# ==========================================

class FigureRegion(TypedDict):
    """图表区域信息"""
    page_number: int
    figure_number: str        # 如 "Figure 1A"
    image_path: str           # 裁剪后的图片路径
    caption: str              # 图注文本
    bbox: tuple               # (x0, y0, x1, y1) 边界框


class ChunkData(TypedDict):
    """知识块数据"""
    chunk_index: int
    chunk_type: str           # text/figure/table/equation
    content: str
    page_number: int
    section_title: str
    figure_caption: Optional[str]
    metadata_: Optional[Dict[str, Any]]


class ExtractedKnowledge(TypedDict):
    """Vision LLM 提取的结构化知识"""
    methodology: str
    tool_stack: Dict[str, List[str]]
    parameters: Dict[str, Any]
    analysis_type: str


# ==========================================
# PDF 解析与分块
# ==========================================

def extract_pdf_with_figures(
    file_path: str,
    output_dir: str,
    max_pages: int = 100,
) -> Dict[str, Any]:
    """
    使用 PyMuPDF 提取 PDF 文本和图表

    Args:
        file_path: PDF 文件路径
        output_dir: 图表输出目录
        max_pages: 最大处理页数

    Returns:
        包含文本、图表、页数等信息的字典
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.error("📚 [Ingestion] PyMuPDF 未安装，请运行: pip install PyMuPDF")
        return {"text_by_page": [], "figures": [], "page_count": 0, "error": "PyMuPDF not installed"}

    log.info(f"📚 [Ingestion] 开始解析 PDF: {file_path}")

    os.makedirs(output_dir, exist_ok=True)
    result = {"text_by_page": [], "figures": [], "page_count": 0, "error": None}

    try:
        doc = fitz.open(file_path)
        result["page_count"] = len(doc)

        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]

            # 提取文本
            text = page.get_text("text")
            result["text_by_page"].append({
                "page_number": page_num + 1,
                "text": text,
            })

            # 提取图片
            images = page.get_images(full=True)
            for img_idx, img_info in enumerate(images):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if base_image:
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # 过滤太小的图片（可能是图标、logo）
                        if len(image_bytes) < 5000:
                            continue

                        img_filename = f"page{page_num + 1}_img{img_idx + 1}.{image_ext}"
                        img_path = os.path.join(output_dir, img_filename)

                        with open(img_path, "wb") as f:
                            f.write(image_bytes)

                        result["figures"].append({
                            "page_number": page_num + 1,
                            "figure_number": f"Figure P{page_num + 1}-{img_idx + 1}",
                            "image_path": img_path,
                            "caption": "",  # 图注稍后对齐
                            "bbox": (0, 0, 0, 0),
                        })
                except Exception as e:
                    log.warning(f"📚 [Ingestion] 提取图片失败 (page={page_num + 1}, img={img_idx}): {e}")

        doc.close()
        log.info(f"📚 [Ingestion] PDF 解析完成: {result['page_count']} 页, {len(result['figures'])} 张图片")

    except Exception as e:
        log.error(f"📚 [Ingestion] PDF 解析失败: {e}")
        result["error"] = str(e)

    return result


def smart_chunking(
    text_by_page: List[Dict[str, Any]],
    figures: List[FigureRegion],
    target_chunk_size: int = 300,
    max_chunk_size: int = 500,
) -> List[ChunkData]:
    """
    智能分块：按章节/段落/图表边界切分

    策略：
    1. 识别章节标题（如 "1. Introduction", "Methods" 等）
    2. 按段落边界切分
    3. 合并过短段落，切分过长段落
    4. 图表独立成块

    Args:
        text_by_page: 按页提取的文本列表
        figures: 图表区域列表
        target_chunk_size: 目标块大小（字符数）
        max_chunk_size: 最大块大小

    Returns:
        知识块列表
    """
    chunks: List[ChunkData] = []
    chunk_index = 0
    current_section = ""

    # 章节标题正则模式（匹配常见学术论文章节格式）
    section_patterns = [
        re.compile(r"^(\d+\.?\s+\w+)", re.MULTILINE),           # "1. Introduction"
        re.compile(r"^(\d+\.\d+\.?\s+\w+)", re.MULTILINE),      # "1.1. Sub Section"
        re.compile(r"^(Abstract|Introduction|Methods|Results|Discussion|Conclusion|References|Supplementary)", re.IGNORECASE),
    ]

    for page_data in text_by_page:
        page_num = page_data["page_number"]
        page_text = page_data["text"]

        if not page_text.strip():
            continue

        # 按段落分割
        paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]

        buffer = ""
        for para in paragraphs:
            # 检测章节标题
            is_section = False
            for pattern in section_patterns:
                match = pattern.match(para)
                if match:
                    # 保存当前缓冲区
                    if buffer.strip():
                        chunks.append(_make_chunk(
                            chunk_index, "text", buffer.strip(),
                            page_num, current_section, None, None
                        ))
                        chunk_index += 1
                        buffer = ""
                    current_section = para[:100]  # 截取作为章节标题
                    is_section = True
                    break

            if is_section:
                continue

            # 累积到缓冲区
            if len(buffer) + len(para) > max_chunk_size:
                # 缓冲区已满，先保存
                if buffer.strip():
                    chunks.append(_make_chunk(
                        chunk_index, "text", buffer.strip(),
                        page_num, current_section, None, None
                    ))
                    chunk_index += 1
                buffer = para
            else:
                buffer = buffer + "\n\n" + para if buffer else para

            # 如果缓冲区达到目标大小，保存
            if len(buffer) >= target_chunk_size:
                chunks.append(_make_chunk(
                    chunk_index, "text", buffer.strip(),
                    page_num, current_section, None, None
                ))
                chunk_index += 1
                buffer = ""

        # 保存剩余缓冲区
        if buffer.strip():
            chunks.append(_make_chunk(
                chunk_index, "text", buffer.strip(),
                page_num, current_section, None, None
            ))
            chunk_index += 1

    # 图表独立成块
    for fig in figures:
        caption = fig.get("caption", "")
        content = f"[Figure: {fig['figure_number']}]"
        if caption:
            content += f"\nCaption: {caption}"

        chunks.append(_make_chunk(
            chunk_index, "figure", content,
            fig["page_number"], current_section, caption,
            {"image_path": fig["image_path"], "figure_number": fig["figure_number"]}
        ))
        chunk_index += 1

    log.info(f"📚 [Ingestion] 智能分块完成: {len(chunks)} 个知识块")
    return chunks


def _make_chunk(
    index: int,
    chunk_type: str,
    content: str,
    page_number: int,
    section_title: str,
    figure_caption: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> ChunkData:
    """构造知识块数据"""
    return ChunkData(
        chunk_index=index,
        chunk_type=chunk_type,
        content=content,
        page_number=page_number,
        section_title=section_title,
        figure_caption=figure_caption,
        metadata_=metadata,
    )


# ==========================================
# 图注对齐
# ==========================================

def align_captions(
    text_by_page: List[Dict[str, Any]],
    figures: List[FigureRegion],
) -> List[FigureRegion]:
    """
    图注对齐：将正文中的图注与提取的图表关联

    策略：搜索 "Figure X" / "Fig. X" 模式，将后续段落作为图注

    Args:
        text_by_page: 按页提取的文本
        figures: 图表区域列表

    Returns:
        更新了 caption 的图表列表
    """
    caption_pattern = re.compile(
        r"(?:Figure|Fig\.?)\s+(\d+[A-Za-z]?)[:\.\s]+(.+?)(?=\n\n|\Z)",
        re.DOTALL | re.IGNORECASE
    )

    # 从文本中提取所有图注
    found_captions: Dict[str, str] = {}
    for page_data in text_by_page:
        for match in caption_pattern.finditer(page_data["text"]):
            fig_num = f"Figure {match.group(1)}"
            caption_text = match.group(2).strip()[:500]  # 截取前 500 字符
            found_captions[fig_num] = caption_text

    # 将图注与图表关联
    for fig in figures:
        fig_num = fig.get("figure_number", "")
        # 尝试匹配 "Figure 1A" 格式
        for key, caption in found_captions.items():
            if key.lower() in fig_num.lower() or fig_num.lower() in key.lower():
                fig["caption"] = caption
                break

    return figures


# ==========================================
# Vision LLM 图表理解
# ==========================================

VISION_LLM_PROMPT = """你是一个严谨的计算生物学专家。分析提供的文献图表及其图注，提取生信分析方法。

绝对规则：
1. 保持科学客观，禁用夸大其词或主观推断
2. 重点关注：数据降维、聚类、差异分析、轨迹推断等统计算法
3. 准确识别开源软件（Seurat, Scanpy, DESeq2 等）及参数设置
4. 必须输出 JSON，结构：{"methodology": "...", "tool_stack": {"R": [...], "Python": [...]}, "parameters": {...}, "analysis_type": "..."}
5. 信息缺失时填 "Not specified"，严禁编造"""


async def analyze_figure_with_vision_llm(
    image_path: str,
    caption: str,
) -> Optional[ExtractedKnowledge]:
    """
    使用 Vision LLM 分析图表

    Args:
        image_path: 图表图片路径
        caption: 图注文本

    Returns:
        结构化知识提取结果，或 None（失败时）
    """
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        # 读取图片并编码为 base64
        import base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # 推断图片格式
        ext = os.path.splitext(image_path)[1].lower().strip(".")
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            ext = "png"
        mime_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"

        # 构建消息
        text_content = f"图注：{caption}\n\n请分析此图表，提取生信分析方法。"
        messages = [
            {"role": "system", "content": VISION_LLM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": text_content},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
            ]},
        ]

        # 调用 Vision LLM
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL_NAME or "gpt-4o",
            messages=messages,
            max_tokens=1000,
            temperature=0.1,
        )

        # 解析 JSON 响应
        import json
        content = response.choices[0].message.content
        # 提取 JSON（可能包裹在 ```json ``` 中）
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            log.info(f"📚 [Ingestion] Vision LLM 提取成功: {result.get('analysis_type', 'unknown')}")
            return result
        else:
            log.warning(f"📚 [Ingestion] Vision LLM 返回非 JSON 格式，降级处理")
            return None

    except Exception as e:
        log.error(f"📚 [Ingestion] Vision LLM 分析失败: {e}")
        return None


async def analyze_figure_with_text_llm(caption: str) -> Optional[ExtractedKnowledge]:
    """
    降级方案：仅用文本 LLM 从图注提取信息

    当 Vision LLM 不可用时使用
    """
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        messages = [
            {"role": "system", "content": VISION_LLM_PROMPT},
            {"role": "user", "content": f"仅根据以下图注文本提取生信分析方法（无法看到图片）：\n\n{caption}"},
        ]

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL_NAME or "gpt-4o",
            messages=messages,
            max_tokens=800,
            temperature=0.1,
        )

        import json
        content = response.choices[0].message.content
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        return None

    except Exception as e:
        log.error(f"📚 [Ingestion] 文本 LLM 降级分析失败: {e}")
        return None


# ==========================================
# Embedding 生成
# ==========================================

def generate_embedding(text: str) -> Optional[List[float]]:
    """
    生成文本的 Embedding 向量

    使用 text-embedding-3-large（1536 维）

    Args:
        text: 待向量化的文本

    Returns:
        1536 维浮点数列表，或 None（失败时）
    """
    try:
        import openai
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=text[:8000],  # 截断过长文本
        )
        return response.data[0].embedding

    except Exception as e:
        log.error(f"📚 [Ingestion] Embedding 生成失败: {e}")
        return None


# ==========================================
# 文件哈希计算
# ==========================================

def compute_file_hash(file_path: str) -> str:
    """计算文件的 SHA256 哈希值"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
