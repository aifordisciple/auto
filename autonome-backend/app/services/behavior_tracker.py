"""
行为埋点服务

功能：
1. 全面的用户行为追踪 - 覆盖完整用户旅程
2. 行为数据存储 - 持久化到数据库
3. 批量事件处理 - 支持高效批量上报
4. 聚合统计分析 - 提供行为统计能力

设计原则：
- 不可变事件：事件一旦记录不可修改
- 完整追踪：覆盖从查询到执行的全流程
- 高效批量：支持前端批量上报
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum
from sqlmodel import Session, select, and_, SQLModel
from pydantic import BaseModel, Field

from app.core.logger import log
from app.models.domain import (
    SkillMatchingFeedback,
    SkillRecommendationLog,
    SkillExecutionHistory,
    get_utc_now,
)


# ==========================================
# 行为类型枚举
# ==========================================

class BehaviorType(str, Enum):
    """
    用户行为类型枚举

    覆盖完整的用户旅程：
    1. 查询阶段: QUERY
    2. 推荐阶段: RECOMMEND
    3. 浏览阶段: CLICK, VIEW_DETAIL
    4. 执行阶段: EXECUTE, MODIFY_PARAM, RETRY, ABORT
    5. 结果阶段: SUCCESS, FAILURE
    6. 反馈阶段: FEEDBACK, FAVORITE, SHARE
    """

    # 查询阶段
    QUERY = "query"                    # 用户发起查询

    # 推荐阶段
    RECOMMEND = "recommend"            # 系统推荐技能

    # 浏览阶段
    CLICK = "click"                    # 用户点击技能
    VIEW_DETAIL = "view_detail"        # 查看技能详情

    # 执行阶段
    EXECUTE = "execute"                # 技能被执行
    MODIFY_PARAM = "modify_param"      # 用户修改参数
    RETRY = "retry"                    # 重试执行
    ABORT = "abort"                    # 中断执行

    # 结果阶段
    SUCCESS = "success"                # 执行成功
    FAILURE = "failure"                # 执行失败

    # 反馈阶段
    FEEDBACK = "feedback"              # 用户反馈
    FAVORITE = "favorite"              # 收藏技能
    SHARE = "share"                    # 分享结果


# ==========================================
# 行为事件模型
# ==========================================

class BehaviorEvent(BaseModel):
    """
    行为埋点事件模型

    用于记录用户在系统中的所有行为，支持：
    - 技能推荐和选择
    - 技能执行和结果
    - 用户反馈和互动
    """

    # 必填字段
    user_id: int = Field(description="用户 ID")
    session_id: str = Field(description="会话 ID")
    event_type: BehaviorType = Field(description="事件类型")

    # 可选字段 - 技能相关
    skill_id: Optional[str] = Field(default=None, description="技能 ID")
    skill_name: Optional[str] = Field(default=None, description="技能名称")

    # 可选字段 - 查询相关
    query: Optional[str] = Field(default=None, description="用户查询")

    # 可选字段 - 匹配相关
    match_source: Optional[str] = Field(
        default=None,
        description="匹配来源: rule | vector | llm | hybrid"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="匹配置信度")

    # 可选字段 - 执行相关
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="执行参数")
    execution_time: Optional[float] = Field(default=None, description="执行耗时（秒）")
    error_message: Optional[str] = Field(default=None, description="错误信息")

    # 可选字段 - 元数据
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元数据")


class BehaviorAggregation(BaseModel):
    """
    行为聚合统计模型

    用于统计技能或用户的行为数据
    """

    # 技能统计
    recommend_count: int = Field(default=0, description="被推荐次数")
    click_count: int = Field(default=0, description="被点击次数")
    view_detail_count: int = Field(default=0, description="查看详情次数")
    execute_count: int = Field(default=0, description="被执行次数")
    success_count: int = Field(default=0, description="成功次数")
    failure_count: int = Field(default=0, description="失败次数")
    retry_count: int = Field(default=0, description="重试次数")
    abort_count: int = Field(default=0, description="中断次数")
    favorite_count: int = Field(default=0, description="收藏次数")
    share_count: int = Field(default=0, description="分享次数")

    # 用户统计
    query_count: int = Field(default=0, description="查询次数")

    # 计算字段
    click_rate: float = Field(default=0.0, description="点击率")
    success_rate: float = Field(default=0.0, description="成功率")


# ==========================================
# 行为记录模型（数据库表）
# ==========================================

from sqlalchemy import Column, String, Float, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField


class BehaviorRecord(SQLModel, table=True):
    """
    行为记录表

    存储所有用户行为事件的原始数据
    """
    __tablename__ = "behaviorrecord"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(index=True, description="用户 ID")
    session_id: str = SQLField(index=True, description="会话 ID")
    event_type: str = SQLField(max_length=50, index=True, description="事件类型")

    # 技能相关
    skill_id: Optional[str] = SQLField(default=None, index=True, description="技能 ID")
    skill_name: Optional[str] = SQLField(default=None, description="技能名称")

    # 查询相关
    query: Optional[str] = SQLField(default=None, description="用户查询")

    # 匹配相关
    match_source: Optional[str] = SQLField(default=None, max_length=20, description="匹配来源")
    confidence: float = SQLField(default=0.0, description="置信度")

    # 执行相关
    parameters: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column(JSONB),
        description="执行参数"
    )
    execution_time: Optional[float] = SQLField(default=None, description="执行耗时")
    error_message: Optional[str] = SQLField(default=None, description="错误信息")

    # 元数据
    event_metadata: Optional[Dict[str, Any]] = SQLField(
        default=None,
        sa_column=Column("metadata", JSONB),
        description="额外元数据"
    )

    # 时间戳
    created_at: datetime = SQLField(default_factory=get_utc_now, description="创建时间")


# ==========================================
# 行为埋点服务
# ==========================================

class BehaviorTracker:
    """
    行为埋点服务

    负责：
    1. 记录用户行为事件
    2. 查询行为历史
    3. 聚合行为统计
    """

    def __init__(self, session: Session):
        """
        初始化行为埋点服务

        Args:
            session: 数据库会话
        """
        self.session = session

    # ==========================================
    # 事件记录
    # ==========================================

    def track(self, event: BehaviorEvent) -> bool:
        """
        记录单个行为事件

        Args:
            event: 行为事件

        Returns:
            是否记录成功
        """
        try:
            record = BehaviorRecord(
                user_id=event.user_id,
                session_id=event.session_id,
                event_type=event.event_type.value,
                skill_id=event.skill_id,
                skill_name=event.skill_name,
                query=event.query,
                match_source=event.match_source,
                confidence=event.confidence,
                parameters=event.parameters,
                execution_time=event.execution_time,
                error_message=event.error_message,
                event_metadata=event.metadata,
            )

            self.session.add(record)
            self.session.commit()

            log.info(
                f"[BehaviorTracker] 事件已记录: "
                f"type={event.event_type.value}, "
                f"user={event.user_id}, "
                f"skill={event.skill_id}"
            )

            return True

        except Exception as e:
            log.error(f"[BehaviorTracker] 记录事件失败: {e}")
            self.session.rollback()
            return False

    def batch_track(self, events: List[BehaviorEvent]) -> List[bool]:
        """
        批量记录行为事件

        Args:
            events: 行为事件列表

        Returns:
            每个事件的记录结果
        """
        results = []
        for event in events:
            results.append(self.track(event))
        return results

    # ==========================================
    # 历史查询
    # ==========================================

    def get_user_behaviors(
        self,
        user_id: int,
        event_types: Optional[List[BehaviorType]] = None,
        limit: int = 100,
    ) -> List[BehaviorRecord]:
        """
        获取用户行为历史

        Args:
            user_id: 用户 ID
            event_types: 可选的事件类型过滤
            limit: 返回数量限制

        Returns:
            行为记录列表
        """
        query = select(BehaviorRecord).where(BehaviorRecord.user_id == user_id)

        if event_types:
            type_values = [t.value for t in event_types]
            query = query.where(BehaviorRecord.event_type.in_(type_values))

        query = query.order_by(BehaviorRecord.created_at.desc()).limit(limit)

        return list(self.session.exec(query).all())

    def get_session_behaviors(
        self,
        session_id: str,
    ) -> List[BehaviorRecord]:
        """
        获取会话内的所有行为

        Args:
            session_id: 会话 ID

        Returns:
            行为记录列表
        """
        query = (
            select(BehaviorRecord)
            .where(BehaviorRecord.session_id == session_id)
            .order_by(BehaviorRecord.created_at.asc())
        )

        return list(self.session.exec(query).all())

    def get_skill_behaviors(
        self,
        skill_id: str,
        event_types: Optional[List[BehaviorType]] = None,
        limit: int = 100,
    ) -> List[BehaviorRecord]:
        """
        获取技能相关的行为历史

        Args:
            skill_id: 技能 ID
            event_types: 可选的事件类型过滤
            limit: 返回数量限制

        Returns:
            行为记录列表
        """
        query = select(BehaviorRecord).where(BehaviorRecord.skill_id == skill_id)

        if event_types:
            type_values = [t.value for t in event_types]
            query = query.where(BehaviorRecord.event_type.in_(type_values))

        query = query.order_by(BehaviorRecord.created_at.desc()).limit(limit)

        return list(self.session.exec(query).all())

    # ==========================================
    # 聚合统计
    # ==========================================

    def aggregate_skill_behaviors(
        self,
        skill_id: str,
        time_window_hours: int = 24 * 7,  # 默认一周
    ) -> BehaviorAggregation:
        """
        聚合技能的行为统计

        Args:
            skill_id: 技能 ID
            time_window_hours: 统计时间窗口（小时）

        Returns:
            行为聚合统计
        """
        now = get_utc_now()
        start_time = now - timedelta(hours=time_window_hours)

        records = self.session.exec(
            select(BehaviorRecord)
            .where(
                BehaviorRecord.skill_id == skill_id,
                BehaviorRecord.created_at >= start_time
            )
        ).all()

        aggregation = BehaviorAggregation(skill_id=skill_id)

        for record in records:
            event_type = record.event_type

            if event_type == BehaviorType.RECOMMEND.value:
                aggregation.recommend_count += 1
            elif event_type == BehaviorType.CLICK.value:
                aggregation.click_count += 1
            elif event_type == BehaviorType.VIEW_DETAIL.value:
                aggregation.view_detail_count += 1
            elif event_type == BehaviorType.EXECUTE.value:
                aggregation.execute_count += 1
            elif event_type == BehaviorType.SUCCESS.value:
                aggregation.success_count += 1
            elif event_type == BehaviorType.FAILURE.value:
                aggregation.failure_count += 1
            elif event_type == BehaviorType.RETRY.value:
                aggregation.retry_count += 1
            elif event_type == BehaviorType.ABORT.value:
                aggregation.abort_count += 1
            elif event_type == BehaviorType.FAVORITE.value:
                aggregation.favorite_count += 1
            elif event_type == BehaviorType.SHARE.value:
                aggregation.share_count += 1

        # 计算比率
        if aggregation.recommend_count > 0:
            aggregation.click_rate = aggregation.click_count / aggregation.recommend_count

        if aggregation.execute_count > 0:
            aggregation.success_rate = aggregation.success_count / aggregation.execute_count

        return aggregation

    def aggregate_user_behaviors(
        self,
        user_id: int,
        time_window_hours: int = 24 * 7,
    ) -> BehaviorAggregation:
        """
        聚合用户的行为统计

        Args:
            user_id: 用户 ID
            time_window_hours: 统计时间窗口（小时）

        Returns:
            行为聚合统计
        """
        now = get_utc_now()
        start_time = now - timedelta(hours=time_window_hours)

        records = self.session.exec(
            select(BehaviorRecord)
            .where(
                BehaviorRecord.user_id == user_id,
                BehaviorRecord.created_at >= start_time
            )
        ).all()

        aggregation = BehaviorAggregation()

        for record in records:
            if record.event_type == BehaviorType.QUERY.value:
                aggregation.query_count += 1
            elif record.event_type == BehaviorType.EXECUTE.value:
                aggregation.execute_count += 1
            elif record.event_type == BehaviorType.SUCCESS.value:
                aggregation.success_count += 1
            elif record.event_type == BehaviorType.FAILURE.value:
                aggregation.failure_count += 1

        # 计算成功率
        if aggregation.execute_count > 0:
            aggregation.success_rate = aggregation.success_count / aggregation.execute_count

        return aggregation


# ==========================================
# 便捷函数
# ==========================================

def track_behavior(
    session: Session,
    user_id: int,
    session_id: str,
    event_type: BehaviorType,
    **kwargs,
) -> bool:
    """
    记录用户行为的便捷函数

    Args:
        session: 数据库会话
        user_id: 用户 ID
        session_id: 会话 ID
        event_type: 事件类型
        **kwargs: 其他参数

    Returns:
        是否记录成功
    """
    tracker = BehaviorTracker(session)
    event = BehaviorEvent(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        **kwargs,
    )
    return tracker.track(event)


log.info("✅ 行为埋点服务已加载")