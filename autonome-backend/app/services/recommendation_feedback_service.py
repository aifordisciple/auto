"""
推荐反馈闭环服务

功能：
1. 用户行为埋点 - 记录查询、点击、执行、成功/失败
2. 实时反馈聚合 - 每5分钟聚合统计
3. 动态权重调整 - skill_score = base_score × click_rate × success_rate

使用场景：
- 用户点击推荐技能时记录 click 事件
- 技能执行完成时记录 execute 和 success/fail 事件
- 定期计算技能热度分数并更新
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, func, and_
from pydantic import BaseModel

from app.core.logger import log
from app.models.domain import (
    SkillAsset,
    SkillExecutionHistory,
    SkillMatchingFeedback,
    SkillRecommendationLog,
    get_utc_now,
)


# ==========================================
# 行为埋点事件类型
# ==========================================

class EventType:
    """埋点事件类型"""
    RECOMMEND = "recommend"      # 技能被推荐
    CLICK = "click"              # 用户点击技能
    EXECUTE = "execute"          # 技能被执行
    SUCCESS = "success"          # 执行成功
    FAILURE = "failure"          # 执行失败
    DISMISS = "dismiss"          # 用户忽略推荐


# ==========================================
# 埋点数据模型
# ==========================================

class BehaviorEvent(BaseModel):
    """行为埋点事件"""
    user_id: int
    session_id: str
    event_type: str
    skill_id: str
    query: Optional[str] = None
    match_source: Optional[str] = None
    confidence: float = 0.0
    parameters: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None


class FeedbackStats(BaseModel):
    """反馈统计数据"""
    skill_id: str
    recommend_count: int = 0      # 被推荐次数
    click_count: int = 0          # 被点击次数
    execute_count: int = 0        # 被执行次数
    success_count: int = 0        # 成功次数
    failure_count: int = 0        # 失败次数

    click_rate: float = 0.0       # 点击率
    success_rate: float = 0.0     # 成功率
    dynamic_score: float = 0.0    # 动态分数


# ==========================================
# 推荐反馈闭环服务
# ==========================================

class RecommendationFeedbackService:
    """
    推荐反馈闭环服务

    负责：
    1. 记录用户行为埋点
    2. 聚合反馈统计
    3. 计算动态权重
    """

    def __init__(self, session: Session):
        self.session = session
        self._stats_cache: Dict[str, FeedbackStats] = {}
        self._last_aggregation: Optional[datetime] = None

    # ==========================================
    # 用户行为埋点
    # ==========================================

    def record_event(self, event: BehaviorEvent) -> bool:
        """
        记录用户行为埋点事件

        Args:
            event: 行为事件

        Returns:
            是否记录成功
        """
        try:
            if event.event_type == EventType.RECOMMEND:
                return self._record_recommend(event)
            elif event.event_type == EventType.CLICK:
                return self._record_click(event)
            elif event.event_type == EventType.EXECUTE:
                return self._record_execute(event)
            elif event.event_type == EventType.SUCCESS:
                return self._record_success(event)
            elif event.event_type == EventType.FAILURE:
                return self._record_failure(event)
            elif event.event_type == EventType.DISMISS:
                return self._record_dismiss(event)
            else:
                log.warning(f"[Feedback] 未知事件类型: {event.event_type}")
                return False
        except Exception as e:
            log.error(f"[Feedback] 记录事件失败: {e}")
            return False

    def _record_recommend(self, event: BehaviorEvent) -> bool:
        """记录技能被推荐"""
        # 创建或更新推荐日志
        log_entry = SkillRecommendationLog(
            user_id=event.user_id,
            session_id=event.session_id,
            query=event.query or "",
            intent_type="skill_match",
            recommended_skills=[event.skill_id],
            confidence=event.confidence,
            accepted_skill=None,
        )
        self.session.add(log_entry)
        self.session.commit()

        log.info(f"[Feedback] 技能被推荐: {event.skill_id}, 查询: {event.query}")
        return True

    def _record_click(self, event: BehaviorEvent) -> bool:
        """记录用户点击技能"""
        # 更新推荐日志
        log_entry = self.session.exec(
            select(SkillRecommendationLog)
            .where(
                SkillRecommendationLog.user_id == event.user_id,
                SkillRecommendationLog.session_id == event.session_id,
                SkillRecommendationLog.accepted_skill.is_(None)
            )
            .order_by(SkillRecommendationLog.created_at.desc())
        ).first()

        if log_entry:
            log_entry.accepted_skill = event.skill_id
            self.session.add(log_entry)
            self.session.commit()

        # 更新匹配反馈
        feedback = self.session.exec(
            select(SkillMatchingFeedback)
            .where(
                SkillMatchingFeedback.user_id == event.user_id,
                SkillMatchingFeedback.session_id == event.session_id
            )
            .order_by(SkillMatchingFeedback.created_at.desc())
        ).first()

        if feedback:
            feedback.accepted = True
            feedback.accepted_skill_id = event.skill_id
            feedback.updated_at = get_utc_now()
            self.session.add(feedback)
            self.session.commit()

        log.info(f"[Feedback] 用户点击技能: {event.skill_id}")
        return True

    def _record_execute(self, event: BehaviorEvent) -> bool:
        """记录技能被执行"""
        # 执行历史已在 SkillExecutionHistory 中记录
        log.info(f"[Feedback] 技能被执行: {event.skill_id}, 参数: {event.parameters}")
        return True

    def _record_success(self, event: BehaviorEvent) -> bool:
        """记录执行成功"""
        log.info(f"[Feedback] 执行成功: {event.skill_id}, 耗时: {event.execution_time}s")
        return True

    def _record_failure(self, event: BehaviorEvent) -> bool:
        """记录执行失败"""
        log.info(f"[Feedback] 执行失败: {event.skill_id}")
        return True

    def _record_dismiss(self, event: BehaviorEvent) -> bool:
        """记录用户忽略推荐"""
        feedback = self.session.exec(
            select(SkillMatchingFeedback)
            .where(
                SkillMatchingFeedback.user_id == event.user_id,
                SkillMatchingFeedback.session_id == event.session_id
            )
            .order_by(SkillMatchingFeedback.created_at.desc())
        ).first()

        if feedback:
            feedback.accepted = False
            if event.skill_id and event.skill_id not in feedback.rejected_skills:
                feedback.rejected_skills = list(feedback.rejected_skills) + [event.skill_id]
            feedback.updated_at = get_utc_now()
            self.session.add(feedback)
            self.session.commit()

        log.info(f"[Feedback] 用户忽略推荐: {event.skill_id}")
        return True

    # ==========================================
    # 实时反馈聚合
    # ==========================================

    def aggregate_feedback(self, time_window_hours: int = 24) -> Dict[str, FeedbackStats]:
        """
        聚合反馈统计

        Args:
            time_window_hours: 统计时间窗口（小时）

        Returns:
            技能ID -> 反馈统计
        """
        now = get_utc_now()
        start_time = now - timedelta(hours=time_window_hours)

        stats: Dict[str, FeedbackStats] = {}

        # 1. 统计推荐次数
        recommend_logs = self.session.exec(
            select(SkillRecommendationLog)
            .where(SkillRecommendationLog.created_at >= start_time)
        ).all()

        for log_entry in recommend_logs:
            for skill_id in (log_entry.recommended_skills or []):
                if skill_id not in stats:
                    stats[skill_id] = FeedbackStats(skill_id=skill_id)
                stats[skill_id].recommend_count += 1

        # 2. 统计点击次数
        for log_entry in recommend_logs:
            if log_entry.accepted_skill:
                skill_id = log_entry.accepted_skill
                if skill_id not in stats:
                    stats[skill_id] = FeedbackStats(skill_id=skill_id)
                stats[skill_id].click_count += 1

        # 3. 统计执行次数和成功/失败
        executions = self.session.exec(
            select(SkillExecutionHistory)
            .where(SkillExecutionHistory.created_at >= start_time)
        ).all()

        for execution in executions:
            skill_id = execution.skill_id
            if skill_id not in stats:
                stats[skill_id] = FeedbackStats(skill_id=skill_id)

            stats[skill_id].execute_count += 1

            if execution.status == "SUCCESS":
                stats[skill_id].success_count += 1
            elif execution.status == "FAILURE":
                stats[skill_id].failure_count += 1

        # 4. 计算点击率和成功率
        for skill_id, stat in stats.items():
            if stat.recommend_count > 0:
                stat.click_rate = stat.click_count / stat.recommend_count

            if stat.execute_count > 0:
                stat.success_rate = stat.success_count / stat.execute_count

            # 计算动态分数
            # dynamic_score = base_score (1.0) × click_rate × success_rate
            base_score = 1.0
            stat.dynamic_score = base_score * max(stat.click_rate, 0.1) * max(stat.success_rate, 0.1)

        self._stats_cache = stats
        self._last_aggregation = now

        log.info(f"[Feedback] 聚合完成: {len(stats)} 个技能, 时间窗口: {time_window_hours}h")

        return stats

    # ==========================================
    # 动态权重调整
    # ==========================================

    def get_dynamic_score(self, skill_id: str) -> float:
        """
        获取技能的动态分数

        如果缓存过期或不存在，返回默认分数 1.0
        """
        # 检查缓存是否需要更新
        if self._last_aggregation is None or \
           (get_utc_now() - self._last_aggregation) > timedelta(minutes=5):
            self.aggregate_feedback()

        if skill_id in self._stats_cache:
            return self._stats_cache[skill_id].dynamic_score
        return 1.0

    def get_top_skills_by_feedback(self, limit: int = 10) -> List[FeedbackStats]:
        """
        获取反馈表现最好的技能

        Args:
            limit: 返回数量

        Returns:
            按动态分数排序的技能统计列表
        """
        if self._last_aggregation is None or \
           (get_utc_now() - self._last_aggregation) > timedelta(minutes=5):
            self.aggregate_feedback()

        sorted_stats = sorted(
            self._stats_cache.values(),
            key=lambda x: x.dynamic_score,
            reverse=True
        )

        return sorted_stats[:limit]

    def get_skill_recommendation_boost(self, skill_id: str) -> float:
        """
        获取技能推荐加成因子

        基于历史表现计算推荐时的加成因子：
        - 高成功率 → 加成
        - 高点击率 → 加成
        - 低成功率 → 降权

        Returns:
            加成因子 (0.5 - 2.0)
        """
        stats = self._stats_cache.get(skill_id)

        if not stats or stats.execute_count < 3:
            # 样本太少，使用默认加成
            return 1.0

        # 基于成功率和点击率计算加成
        # 成功率权重 0.6，点击率权重 0.4
        success_factor = stats.success_rate * 1.5  # 0 - 1.5
        click_factor = stats.click_rate * 1.0     # 0 - 1.0

        boost = success_factor * 0.6 + click_factor * 0.4

        # 限制范围在 0.5 - 2.0
        return max(0.5, min(2.0, boost))

    # ==========================================
    # 周期性任务
    # ==========================================

    def run_periodic_aggregation(self) -> Dict[str, Any]:
        """
        运行周期性聚合任务

        Returns:
            聚合结果摘要
        """
        stats = self.aggregate_feedback(time_window_hours=24)

        # 计算总体指标
        total_recommend = sum(s.recommend_count for s in stats.values())
        total_click = sum(s.click_count for s in stats.values())
        total_execute = sum(s.execute_count for s in stats.values())
        total_success = sum(s.success_count for s in stats.values())

        overall_click_rate = total_click / total_recommend if total_recommend > 0 else 0
        overall_success_rate = total_success / total_execute if total_execute > 0 else 0

        # 获取表现最好的技能
        top_skills = self.get_top_skills_by_feedback(limit=5)

        result = {
            "aggregation_time": get_utc_now().isoformat(),
            "total_skills": len(stats),
            "total_recommendations": total_recommend,
            "total_clicks": total_click,
            "total_executions": total_execute,
            "total_successes": total_success,
            "overall_click_rate": round(overall_click_rate, 3),
            "overall_success_rate": round(overall_success_rate, 3),
            "top_performing_skills": [
                {
                    "skill_id": s.skill_id,
                    "dynamic_score": round(s.dynamic_score, 3),
                    "click_rate": round(s.click_rate, 3),
                    "success_rate": round(s.success_rate, 3),
                }
                for s in top_skills
            ],
        }

        log.info(f"[Feedback] 周期聚合完成: 推荐率={overall_click_rate:.1%}, 成功率={overall_success_rate:.1%}")

        return result


# ==========================================
# 便捷函数
# ==========================================

def record_user_behavior(
    session: Session,
    user_id: int,
    session_id: str,
    event_type: str,
    skill_id: str,
    **kwargs
) -> bool:
    """
    记录用户行为的便捷函数

    Args:
        session: 数据库会话
        user_id: 用户ID
        session_id: 会话ID
        event_type: 事件类型
        skill_id: 技能ID
        **kwargs: 其他参数

    Returns:
        是否记录成功
    """
    service = RecommendationFeedbackService(session)
    event = BehaviorEvent(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        skill_id=skill_id,
        **kwargs
    )
    return service.record_event(event)


log.info("✅ 推荐反馈闭环服务已加载")