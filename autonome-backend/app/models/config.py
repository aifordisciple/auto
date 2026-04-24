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
    openai_base_url: str = Field(default="https://api.openai.com/v1")  # 默认值与 config.settings.OPENAI_BASE_URL 保持一致
    default_model: str = Field(default="gpt-3.5-turbo")

    # ✨ 视觉模型配置（用于图像识别）
    # 当 use_shared_vision_config=True 时，使用主模型配置处理图片
    # 当 use_shared_vision_config=False 时，使用独立的视觉模型配置
    vision_api_key: Optional[str] = Field(default=None, description="视觉模型API密钥，None表示与主模型共用")
    vision_base_url: Optional[str] = Field(default=None, description="视觉模型API端点，None表示与主模型共用")
    vision_model: str = Field(default="qwen3.5-plus", description="视觉模型名称，默认使用qwen3.5-plus")
    use_shared_vision_config: bool = Field(default=True, description="是否与主模型共用配置")

    # ✨ 意图识别模型配置（用于 L1 意图解构）
    # 未配置时回退到主模型配置，保持向后兼容
    intent_api_key: Optional[str] = Field(default=None, description="意图识别模型API密钥，None表示回退到主模型")
    intent_base_url: Optional[str] = Field(default=None, description="意图识别模型API端点，None表示回退到主模型")
    intent_model: str = Field(default="gpt-4o-mini", description="意图识别模型名称，默认使用轻量模型")

    # 其他设置
    theme: str = Field(default="dark")

    updated_at: datetime = Field(default_factory=get_utc_now)
