"""
专家解读报告生成服务

调用视觉模型生成生信图表的专业解读报告
"""

import os
import base64
import asyncio
import concurrent.futures

from openai import AsyncOpenAI
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.logger import log
from app.models.domain import SystemConfig


# ==========================================
# 专家解读 Prompt 模板
# ==========================================

INTERPRETER_PROMPT = """你现在是一位顶尖的计算生物学家和高分 SCI 论文撰稿人。
用户刚刚成功运行了一段生信分析代码，生成了对应的图表。

【输入信息】
1. 用户的原始意图: {user_prompt}
2. 用于生成图表的源码:
{source_code}
3. 数据的基本特征摘要:
{data_summary}

【任务要求】
请你根据上述信息和图表图像，为这幅生成的图表撰写一份专业报告。请严格按照以下 Markdown 结构输出。如果有些数据你无法确定，请用泛用的专业学术词汇描述，绝对不要编造具体数字：

### 📝 图注与方法 (Legends & Methods)
- **中文图注**：用一句话概括图表内容。
- **English Legend**：Translate the Chinese legend into standard academic English.
- **材料与方法**：根据源码，用学术语言描述该图是如何分析，使用什么软件/包生成的。
- **English Methods**：Translate the Chinese Methods into standard academic English.

### 🔬 图表深度解读 (Interpretation)
- **技术解读**：解释图表中的视觉元素（例如：横轴代表样本，纵轴代表基因，颜色的深浅代表表达量高低）。
- **科学洞察**：结合【数据的基本特征摘要】和图像内容，指出图表中呈现出的生物学趋势或结论（例如哪些基因高表达）。

### 💡 专家启发与建议 (Suggestions)
- **图形优化**：提出 1-2 个可以让这张图更适合发表的改进建议（如：调整配色、添加样本注释条、Z-score 标准化）。
- **下游分析**：基于当前的分析，建议用户接下来可以做什么深度分析（如：进行差异基因提取、GO/KEGG 富集分析）。
"""

INTERPRETER_TEXT_ONLY_PROMPT = """你现在是一位顶尖的计算生物学家和高分 SCI 论文撰稿人。
用户刚刚成功运行了一段生信分析代码，生成了对应的图表。

【输入信息】
1. 用户的原始意图: {user_prompt}
2. 用于生成图表的源码:
{source_code}
3. 数据的基本特征摘要:
{data_summary}

【任务要求】
请你根据上述信息，为这段分析生成一份专业解读报告。请严格按照以下 Markdown 结构输出：

### 📝 分析方法 (Methods)
- **分析方法**：根据源码，用学术语言描述分析流程，使用什么软件/包。
- **English Methods**：Translate the Methods into standard academic English.

### 🔬 结果解读 (Interpretation)
- **技术解读**：解释分析的原理和关键指标。
- **科学洞察**：结合【数据的基本特征摘要】，指出可能存在的生物学趋势或结论。

### 💡 专家启发与建议 (Suggestions)
- **后续优化**：提出 1-2 个可以进一步优化的建议。
- **下游分析**：基于当前的分析，建议用户接下来可以做什么深度分析。
"""


async def generate_expert_report_async(
    user_prompt: str,
    source_code: str,
    data_summary: str,
    image_paths: list = None
) -> str:
    """
    调用视觉模型生成解读报告（支持图像输入）

    优化：
    1. 使用视觉模型（Vision Model）直接分析图表图像
    2. 如果没有图像，则退回到纯文本分析
    3. 支持多张图像同时分析

    Args:
        user_prompt: 用户的原始意图
        source_code: 生成图表的源代码
        data_summary: 数据特征摘要
        image_paths: 图像文件路径列表（可选）

    Returns:
        专家解读报告（Markdown 格式）
    """
    try:
        # 1. 从数据库获取视觉模型配置
        with Session(engine) as db:
            config = db.get(SystemConfig, 1)
            if config:
                # 优先使用视觉模型配置
                if config.use_shared_vision_config or not config.vision_api_key:
                    # 与主模型共用配置
                    api_key = config.openai_api_key or settings.OPENAI_API_KEY
                    base_url = config.openai_base_url or settings.OPENAI_BASE_URL
                    model_name = config.vision_model or config.default_model or settings.DEFAULT_MODEL
                else:
                    # 使用独立的视觉模型配置
                    api_key = config.vision_api_key
                    base_url = config.vision_base_url or settings.OPENAI_BASE_URL
                    model_name = config.vision_model or settings.DEFAULT_MODEL
            else:
                api_key = settings.OPENAI_API_KEY
                base_url = settings.OPENAI_BASE_URL
                model_name = settings.DEFAULT_MODEL

        # 2. 处理空 API Key
        actual_api_key = api_key if (api_key and api_key.strip() != "") else "sk-dummy"

        # 3. 检查是否有图像
        has_images = image_paths and len(image_paths) > 0

        if has_images:
            log.info(f"🧠 [ExpertReport] 使用视觉模型: {model_name} @ {base_url}，图像数量: {len(image_paths)}")
        else:
            log.info(f"🧠 [ExpertReport] 使用文本模型: {model_name} @ {base_url}")

        # 4. 创建 OpenAI 客户端
        client = AsyncOpenAI(api_key=actual_api_key, base_url=base_url)

        # 5. 构建消息内容
        if has_images:
            # 带图像的消息
            prompt = INTERPRETER_PROMPT.format(
                user_prompt=user_prompt,
                source_code=source_code,
                data_summary=data_summary
            )

            content = [{"type": "text", "text": prompt}]

            # 添加图像
            for img_path in image_paths[:3]:  # 最多处理 3 张图像
                if os.path.exists(img_path):
                    ext = os.path.splitext(img_path)[1].lower().lstrip('.')
                    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                        with open(img_path, 'rb') as f:
                            image_data = f.read()
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{ext};base64,{image_base64}"
                            }
                        })
                        log.info(f"📸 [ExpertReport] 已加载图像: {os.path.basename(img_path)}")

            messages = [
                {"role": "system", "content": "你是一位资深的生物信息学专家和 SCI 论文撰稿人，擅长解读各类生信分析图表。请直接分析图像并给出专业的学术解读。"},
                {"role": "user", "content": content}
            ]
        else:
            # 纯文本消息
            prompt = INTERPRETER_TEXT_ONLY_PROMPT.format(
                user_prompt=user_prompt,
                source_code=source_code,
                data_summary=data_summary
            )

            messages = [
                {"role": "system", "content": "你是一位资深的生物信息学专家和 SCI 论文撰稿人。"},
                {"role": "user", "content": prompt}
            ]

        # 6. 调用模型
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )

        result = response.choices[0].message.content

        log.info(f"✅ [ExpertReport] 解读报告生成成功，长度: {len(result)}")
        return f"\n---\n\n### 🧬 AI 专家解读\n\n{result}"

    except Exception as e:
        log.error(f"[ExpertReport] AI 模型调用失败: {e}")
        return ""


def generate_expert_report(user_prompt: str, source_code: str, data_summary: str, image_paths: list = None) -> str:
    """
    同步包装函数：调用异步的专家解读生成

    Args:
        user_prompt: 用户的原始意图
        source_code: 生成图表的源代码
        data_summary: 数据特征摘要
        image_paths: 图像文件路径列表（可选）

    Returns:
        专家解读报告（Markdown 格式）
    """
    try:
        # 尝试在现有事件循环中运行
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，创建新的
        loop = None

    if loop and loop.is_running():
        # 在已有事件循环中，创建任务
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                generate_expert_report_async(user_prompt, source_code, data_summary, image_paths)
            )
            return future.result(timeout=120)
    else:
        # 直接运行
        return asyncio.run(generate_expert_report_async(user_prompt, source_code, data_summary, image_paths))