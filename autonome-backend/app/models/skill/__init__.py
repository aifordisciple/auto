"""
技能模型模块

包含技能资产、版本、执行历史、收藏、评价、草稿等模型
"""

# 导入所有技能相关模型
from app.models.skill.asset import (
    SkillAssetBase,
    SkillAsset,
    SkillAssetCreate,
    SkillAssetUpdate,
    SkillAssetPublic,
)
from app.models.skill.version import SkillVersion
from app.models.skill.history import SkillExecutionHistory
from app.models.skill.favorite import SkillFavorite
from app.models.skill.review import SkillReview
from app.models.skill.recommendation import (
    SkillRecommendationLog,
    SkillMatchingFeedback,
)
from app.models.skill.share import (
    ResultShare,
)
from app.models.skill.draft import (
    DraftStatus,
    TriggerSource,
    PendingSkillDraft,
    PendingSkillDraftCreate,
    PendingSkillDraftPublic,
    PendingSkillDraftUpdate,
)

__all__ = [
    # 资产模型
    "SkillAssetBase",
    "SkillAsset",
    "SkillAssetCreate",
    "SkillAssetUpdate",
    "SkillAssetPublic",
    # 版本模型
    "SkillVersion",
    # 执行历史
    "SkillExecutionHistory",
    # 收藏
    "SkillFavorite",
    # 评价
    "SkillReview",
    # 推荐
    "SkillRecommendationLog",
    "SkillMatchingFeedback",
    # 分享
    "ResultShare",
    # 草稿模型
    "DraftStatus",
    "TriggerSource",
    "PendingSkillDraft",
    "PendingSkillDraftCreate",
    "PendingSkillDraftPublic",
    "PendingSkillDraftUpdate",
]