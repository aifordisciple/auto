"""
多模态消息构建服务

支持图片和PDF内容输入，构建多模态消息
"""

import base64
from langchain_core.messages import HumanMessage

from app.core.logger import log


def build_multimodal_message(
    text: str,
    image_paths: list[str],
    pdf_context: str = ""
) -> HumanMessage:
    """
    构建多模态消息，支持图片和PDF内容输入

    工作流程：
    1. 如果有PDF内容，将其注入到用户消息前面
    2. 如果有图片，将图片转换为 base64 格式
    3. 构建 content 列表：[text_with_pdf, image1, image2, ...]

    Args:
        text: 用户消息文本
        image_paths: 图片文件的绝对路径列表
        pdf_context: PDF文档内容上下文（可选）

    Returns:
        HumanMessage: LangChain 消息对象，包含文本、PDF内容和图片
    """
    # 构建完整文本：如果有PDF内容，注入到用户消息前面
    full_text = text
    if pdf_context:
        full_text = pdf_context + "\n\n" + text

    if not image_paths:
        return HumanMessage(content=full_text)

    content = [{"type": "text", "text": full_text}]

    for img_path in image_paths:
        try:
            # 读取图片文件并转换为 base64
            with open(img_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # 根据扩展名检测 MIME 类型
            ext = img_path.lower().split('.')[-1]
            mime_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'webp': 'image/webp'
            }
            mime_type = mime_map.get(ext, 'image/png')

            # 添加图片内容
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
            })
            log.info(f"🖼️ [Chat] 已添加图片到消息: {img_path}")
        except Exception as e:
            log.warning(f"⚠️ [Chat] 读取图片失败 {img_path}: {e}")

    return HumanMessage(content=content)