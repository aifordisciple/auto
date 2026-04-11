"""
系统配置模型模块

包含系统全局配置模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 系统全局配置表 (System Settings)
# ==========================================
class SystemConfig(SQLModel, table=True):
    """
    系统全局配置表 - 存储AI模型配置、主题设置等

    架构说明：
    - 主模型配置：openai_api_key, openai_base_url, default_model 用于主要对话
    - 视觉模型配置：vision_api_key, vision_base_url, vision_model 用于图像识别
    - 视觉模型可以独立配置（当主模型不支持多模态时）或与主模型共用配置
    """
    id: Optional[int] = Field(default=1, primary_key=True)

    # 主模型配置（用于文本对话和主要推理）
    openai_api_key: Optional[str] = None
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    default_model: str = Field(default="gpt-3.5-turbo")

    # ✨ 视觉模型配置（用于图像识别）
    # 当 use_shared_vision_config=True 时，使用主模型配置处理图片
    # 当 use_shared_vision_config=False 时，使用独立的视觉模型配置
    vision_api_key: Optional[str] = Field(default=None, description="视觉模型API密钥，None表示与主模型共用")
    vision_base_url: Optional[str] = Field(default=None, description="视觉模型API端点，None表示与主模型共用")
    vision_model: str = Field(default="qwen3.5-plus", description="视觉模型名称，默认使用qwen3.5-plus")
    use_shared_vision_config: bool = Field(default=True, description="是否与主模型共用配置")

    # 其他设置
    theme: str = Field(default="dark")

    # ✨ 嵌入模型配置（用于技能向量检索）
    # 支持本地 Ollama (bge-m3) 或云端嵌入模型
    embedding_api_base: Optional[str] = Field(
        default=None,
        description="嵌入模型 API 端点，如 http://host.docker.internal:11434"
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description="嵌入模型名称，如 bge-m3:latest, text-embedding-3-small"
    )
    embedding_api_key: Optional[str] = Field(
        default=None,
        description="嵌入模型 API Key，本地模型可留空或填 'EMPTY'"
    )
    embedding_dimension: int = Field(
        default=1024,
        description="嵌入向量维度：bge-m3=1024, OpenAI text-embedding-3-small=1536"
    )

    # ✨ 消息分类器配置（用于判断是否需要技能推荐）
    # 为空时使用主模型配置，建议使用快速模型如 qwen2.5:7b 或 gpt-4o-mini
    classifier_model: Optional[str] = Field(
        default=None,
        description="消息分类模型，如 qwen2.5:7b，为空则使用主模型配置"
    )
    classifier_base_url: Optional[str] = Field(
        default=None,
        description="消息分类器 API 端点，为空则使用主模型端点"
    )
    classifier_api_key: Optional[str] = Field(
        default=None,
        description="消息分类器 API Key，为空则使用主模型 API Key"
    )

    updated_at: datetime = Field(default_factory=get_utc_now)