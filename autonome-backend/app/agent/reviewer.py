"""
Visual Reviewer Agent 模块

负责对生成的图表进行视觉审查，确保图表质量符合学术标准。
"""

import os
import base64
from typing import Optional, Tuple
from openai import AsyncOpenAI

from app.core.logger import log


async def review_plot(
    image_path: str,
    task_instruction: str,
    api_key: str,
    base_url: str,
    model_name: str = "gpt-4o"
) -> str:
    """
    视觉审稿：评估生信图表质量

    Args:
        image_path: 图片文件的绝对路径
        task_instruction: 原始任务指令（用于评估图表是否符合要求）
        api_key: LLM API Key
        base_url: LLM Base URL
        model_name: 多模态模型名称（默认 gpt-4o）

    Returns:
        'PASS' 或 'REJECT: 修改建议'
    """
    if not os.path.exists(image_path):
        log.error(f"❌ [Reviewer] 图片不存在: {image_path}")
        return f"REJECT: 图片文件不存在 {image_path}"

    # 检查文件扩展名
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        log.warning(f"⚠️ [Reviewer] 不支持的图片格式: {ext}")
        return "PASS"  # 非图片文件直接通过

    try:
        # 读取图片并编码为 base64
        with open(image_path, 'rb') as f:
            image_data = f.read()

        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # 构建 review prompt
        review_prompt = f"""你是一位资深的生物信息学图表审稿专家，请对以下图表进行质量审查。

## 原始任务要求
{task_instruction}

## 审查标准

请从以下几个维度评估图表质量：

### 1. 内容完整性（Content Completeness）
- 图表是否完整展示了任务要求的内容？
- 是否遗漏了关键信息？

### 2. 标签清晰度（Label Clarity）
- 标题、坐标轴标签是否清晰可读？
- 图例是否完整且易于理解？
- 是否有标签重叠或遮挡问题？

### 3. 数据呈现（Data Presentation）
- 数据点是否清晰可见？
- 颜色搭配是否合理？
- 是否存在误导性的视觉呈现？

### 4. 学术规范性（Academic Standards）
- 图表是否符合学术出版标准？
- 字体大小是否合适？
- 分辨率是否足够？

### 5. 常见问题检测（Common Issues）
- 标签重叠
- 坐标轴范围不合理
- 图例缺失或不清晰
- 颜色难以区分
- 标题缺失
- 字体过小

## 输出格式

如果图表质量合格，请输出：
PASS

如果图表存在问题需要修改，请输出：
REJECT: [具体问题描述和修改建议]

例如：
REJECT: 图例标签重叠严重，建议调整图例位置或减小字体大小。坐标轴标题缺失，请添加 x 轴标题 "Gene Expression" 和 y 轴标题 "Sample"。

请仔细审查这张图片：
"""

        # 调用多模态模型
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": review_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{ext[1:]};base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3
        )

        review_result = response.choices[0].message.content.strip()

        log.info(f"🔍 [Reviewer] 审稿结果: {review_result[:100]}...")

        return review_result

    except Exception as e:
        log.error(f"❌ [Reviewer] 审稿失败: {str(e)}")
        return f"REJECT: 审稿过程出错 - {str(e)}"


async def batch_review_plots(
    image_paths: list,
    task_instruction: str,
    api_key: str,
    base_url: str,
    model_name: str = "gpt-4o"
) -> Tuple[list, list]:
    """
    批量审稿多张图片

    Args:
        image_paths: 图片路径列表
        task_instruction: 任务指令
        api_key: API Key
        base_url: Base URL
        model_name: 模型名称

    Returns:
        (passed_paths, failed_results) - 通过的图片路径列表和失败的审稿结果列表
    """
    passed = []
    failed = []

    for path in image_paths:
        result = await review_plot(
            image_path=path,
            task_instruction=task_instruction,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name
        )

        if result.startswith("PASS"):
            passed.append(path)
        else:
            failed.append({
                "path": path,
                "review": result
            })

    return passed, failed


def extract_images_from_result(result_text: str, project_id: str) -> list:
    """
    从执行结果中提取图片路径

    Args:
        result_text: 执行结果文本
        project_id: 项目 ID

    Returns:
        图片路径列表
    """
    import re

    images = []

    # 匹配常见的图片路径格式
    patterns = [
        r'/app/uploads/project_\w+/results/[^\s"\']+\.(png|jpg|jpeg|pdf|svg)',
        r'/app/uploads/project_\w+/[^\s"\']+\.(png|jpg|jpeg|pdf|svg)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, result_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                path = match[0]
            else:
                path = match
            if path not in images:
                images.append(path)

    return images


log.info("🎨 Visual Reviewer Agent 模块已加载")