"""
偏好学习引擎服务

功能：
1. 从用户行为记录学习偏好
2. 计算常用技能列表
3. 计算分类偏好权重
4. 提取参数使用模式
5. 推断用户专家水平
6. 生成个性化推荐加成

设计原则：
- 学习维度：常用技能、偏好分类、参数模式、活跃时段、专家水平
- 更新策略：每日定时更新 + 用户触发更新
- 数据来源：BehaviorRecord + SkillExecutionHistory
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import Counter
from sqlmodel import Session, select, and_

from app.core.logger import log
from app.services.behavior_tracker import BehaviorRecord, BehaviorType
from app.models.user_preference import (
    ExpertiseLevel,
    FrequentSkill,
    CategoryPreference,
    ParameterPattern,
    UserPreferenceProfile,
    UserPreferenceRecord,
)


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 偏好学习引擎
# ==========================================

class PreferenceEngine:
    """
    偏好学习引擎

    负责：
    1. 分析用户行为数据
    2. 计算偏好画像
    3. 提供个性化加成
    """

    # 时间窗口配置（天）
    DEFAULT_TIME_WINDOW = 30  # 默认分析最近 30 天的行为
    LONG_TERM_WINDOW = 90     # 长期偏好分析 90 天

    # 专家水平阈值
    BEGINNER_EXECUTION_THRESHOLD = 10
    INTERMEDIATE_EXECUTION_THRESHOLD = 50
    ADVANCED_EXECUTION_THRESHOLD = 100

    BEGINNER_SUCCESS_THRESHOLD = 0.5
    INTERMEDIATE_SUCCESS_THRESHOLD = 0.8
    ADVANCED_SUCCESS_THRESHOLD = 0.95

    # 最大保存数量
    MAX_FREQUENT_SKILLS = 10
    MAX_PREFERRED_CATEGORIES = 10
    MAX_COMMON_VALUES = 5

    def __init__(self, session: Session):
        """
        初始化偏好学习引擎

        Args:
            session: 数据库会话
        """
        self.session = session

    # ==========================================
    # 主要接口
    # ==========================================

    def compute_user_profile(
        self,
        user_id: int,
        time_window_days: int = DEFAULT_TIME_WINDOW,
    ) -> UserPreferenceProfile:
        """
        计算用户偏好画像

        Args:
            user_id: 用户 ID
            time_window_days: 分析时间窗口（天）

        Returns:
            用户偏好画像
        """
        log.info(f"[PreferenceEngine] 开始计算用户偏好: user_id={user_id}, window={time_window_days}d")

        # 获取时间窗口内的行为数据
        behaviors = self._fetch_user_behaviors(user_id, time_window_days)

        if not behaviors:
            log.info(f"[PreferenceEngine] 用户无行为数据: user_id={user_id}")
            return UserPreferenceProfile(user_id=user_id)

        # 计算各个偏好维度
        frequent_skills = self._compute_frequent_skills(behaviors)
        preferred_categories = self._compute_category_preferences(behaviors)
        parameter_patterns = self._extract_parameter_patterns(behaviors)
        active_hours = self._compute_active_hours(behaviors)
        expertise_level = self._infer_expertise_level(behaviors)

        # 计算统计信息
        total_executions = sum(s.execute_count for s in frequent_skills)
        total_successes = sum(s.success_count for s in frequent_skills)
        total_failures = sum(s.failure_count for s in frequent_skills)

        profile = UserPreferenceProfile(
            user_id=user_id,
            frequent_skills=frequent_skills,
            preferred_categories=preferred_categories,
            parameter_patterns=parameter_patterns,
            active_hours=active_hours,
            expertise_level=expertise_level,
            total_executions=total_executions,
            total_successes=total_successes,
            total_failures=total_failures,
            updated_at=get_utc_now(),
        )

        log.info(
            f"[PreferenceEngine] 偏好计算完成: "
            f"skills={len(frequent_skills)}, "
            f"categories={len(preferred_categories)}, "
            f"level={expertise_level.value}"
        )

        return profile

    def update_user_profile(self, user_id: int) -> UserPreferenceRecord:
        """
        更新用户偏好画像（持久化）

        Args:
            user_id: 用户 ID

        Returns:
            更新后的偏好记录
        """
        # 计算新画像
        profile = self.compute_user_profile(user_id)

        # 查找现有记录
        existing = self.session.exec(
            select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
        ).first()

        if existing:
            # 更新现有记录
            record = UserPreferenceRecord.from_profile(profile)
            record.id = existing.id
            record.created_at = existing.created_at
            record.version = existing.version + 1

            self.session.add(record)
            self.session.commit()
            log.info(f"[PreferenceEngine] 更新偏好记录: user_id={user_id}, version={record.version}")
        else:
            # 创建新记录
            record = UserPreferenceRecord.from_profile(profile)
            self.session.add(record)
            self.session.commit()
            log.info(f"[PreferenceEngine] 创建偏好记录: user_id={user_id}")

        return record

    def get_user_profile(self, user_id: int) -> Optional[UserPreferenceProfile]:
        """
        获取用户偏好画像

        Args:
            user_id: 用户 ID

        Returns:
            用户偏好画像，不存在则返回 None
        """
        record = self.session.exec(
            select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
        ).first()

        if record:
            return record.to_profile()
        return None

    # ==========================================
    # 个性化推荐加成
    # ==========================================

    def get_skill_recommendation_boost(
        self,
        user_id: int,
        skill_id: str,
        skill_category: str = None,
    ) -> float:
        """
        获取技能推荐加成因子

        Args:
            user_id: 用户 ID
            skill_id: 技能 ID
            skill_category: 技能分类

        Returns:
            推荐加成因子（1.0 - 3.0）
        """
        profile = self.get_user_profile(user_id)
        if not profile:
            return 1.0

        boost = 1.0

        # 1. 常用技能加成
        frequent_skill_ids = [s.skill_id for s in profile.frequent_skills]
        if skill_id in frequent_skill_ids:
            # 根据排名给予不同加成
            rank = frequent_skill_ids.index(skill_id) + 1
            skill_boost = 1.5 - (rank - 1) * 0.1  # 第一名 1.5，第二名 1.4，依此类推
            boost *= max(1.1, skill_boost)

        # 2. 分类偏好加成
        if skill_category:
            category_weights = {c.category: c.weight for c in profile.preferred_categories}
            if skill_category in category_weights:
                category_boost = 1.0 + category_weights[skill_category] * 0.3
                boost *= category_boost

        # 3. 成功率加成（如果技能在常用列表中）
        for skill in profile.frequent_skills:
            if skill.skill_id == skill_id:
                if skill.success_rate > 0.8:
                    boost *= 1.1
                elif skill.success_rate < 0.5:
                    boost *= 0.9  # 降低低成功率技能的推荐
                break

        # 限制最大加成
        return min(3.0, max(0.5, boost))

    def get_parameter_suggestion(
        self,
        user_id: int,
        skill_id: str,
        parameter_name: str,
    ) -> Optional[Any]:
        """
        获取参数建议值

        Args:
            user_id: 用户 ID
            skill_id: 技能 ID
            parameter_name: 参数名

        Returns:
            建议的参数值，无历史数据则返回 None
        """
        profile = self.get_user_profile(user_id)
        if not profile:
            return None

        skill_patterns = profile.parameter_patterns.get(skill_id)
        if not skill_patterns:
            return None

        pattern = skill_patterns.get(parameter_name)
        if not pattern or not pattern.common_values:
            return None

        # 返回最常用的值
        return pattern.common_values[0]

    # ==========================================
    # 内部方法 - 数据获取
    # ==========================================

    def _fetch_user_behaviors(
        self,
        user_id: int,
        time_window_days: int,
    ) -> List[BehaviorRecord]:
        """
        获取用户行为记录

        Args:
            user_id: 用户 ID
            time_window_days: 时间窗口（天）

        Returns:
            行为记录列表
        """
        cutoff = get_utc_now() - timedelta(days=time_window_days)

        behaviors = self.session.exec(
            select(BehaviorRecord)
            .where(
                BehaviorRecord.user_id == user_id,
                BehaviorRecord.created_at >= cutoff
            )
            .order_by(BehaviorRecord.created_at.desc())
        ).all()

        return list(behaviors)

    # ==========================================
    # 内部方法 - 偏好计算
    # ==========================================

    def _compute_frequent_skills(
        self,
        behaviors: List[BehaviorRecord],
    ) -> List[FrequentSkill]:
        """
        计算常用技能列表

        Args:
            behaviors: 行为记录列表

        Returns:
            常用技能列表（按执行次数排序）
        """
        # 统计技能执行数据
        skill_stats: Dict[str, Dict[str, Any]] = {}

        for behavior in behaviors:
            if not behavior.skill_id:
                continue

            skill_id = behavior.skill_id
            if skill_id not in skill_stats:
                skill_stats[skill_id] = {
                    "skill_name": behavior.skill_name or skill_id,
                    "execute_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "execution_times": [],
                    "last_executed_at": None,
                }

            stats = skill_stats[skill_id]

            if behavior.event_type == BehaviorType.EXECUTE.value:
                stats["execute_count"] += 1
                stats["last_executed_at"] = behavior.created_at
            elif behavior.event_type == BehaviorType.SUCCESS.value:
                stats["success_count"] += 1
                if behavior.execution_time:
                    stats["execution_times"].append(behavior.execution_time)
            elif behavior.event_type == BehaviorType.FAILURE.value:
                stats["failure_count"] += 1

        # 转换为 FrequentSkill 并排序
        frequent_skills = []
        for skill_id, stats in skill_stats.items():
            avg_time = None
            if stats["execution_times"]:
                avg_time = sum(stats["execution_times"]) / len(stats["execution_times"])

            frequent_skills.append(FrequentSkill(
                skill_id=skill_id,
                skill_name=stats["skill_name"],
                execute_count=stats["execute_count"],
                success_count=stats["success_count"],
                failure_count=stats["failure_count"],
                last_executed_at=stats["last_executed_at"],
                avg_execution_time=avg_time,
            ))

        # 按执行次数排序，取 Top N
        frequent_skills.sort(key=lambda x: x.execute_count, reverse=True)
        return frequent_skills[:self.MAX_FREQUENT_SKILLS]

    def _compute_category_preferences(
        self,
        behaviors: List[BehaviorRecord],
    ) -> List[CategoryPreference]:
        """
        计算分类偏好权重

        Args:
            behaviors: 行为记录列表

        Returns:
            分类偏好列表
        """
        # 需要从技能表获取分类信息
        # 这里简化处理，从元数据中获取
        category_stats: Dict[str, Dict[str, Any]] = {}

        for behavior in behaviors:
            if behavior.event_type not in [BehaviorType.EXECUTE.value, BehaviorType.SUCCESS.value]:
                continue

            # 从 event_metadata 中获取分类（如果有的话）
            metadata = behavior.event_metadata or {}
            category = metadata.get("category", "general")
            category_name = metadata.get("category_name", "通用")

            if category not in category_stats:
                category_stats[category] = {
                    "category_name": category_name,
                    "execute_count": 0,
                    "last_executed_at": None,
                }

            category_stats[category]["execute_count"] += 1
            category_stats[category]["last_executed_at"] = behavior.created_at

        if not category_stats:
            return []

        # 计算权重
        total = sum(s["execute_count"] for s in category_stats.values())
        preferences = []

        for category, stats in category_stats.items():
            weight = stats["execute_count"] / total if total > 0 else 0
            preferences.append(CategoryPreference(
                category=category,
                category_name=stats["category_name"],
                weight=weight,
                execute_count=stats["execute_count"],
                last_executed_at=stats["last_executed_at"],
            ))

        # 按权重排序
        preferences.sort(key=lambda x: x.weight, reverse=True)
        return preferences[:self.MAX_PREFERRED_CATEGORIES]

    def _extract_parameter_patterns(
        self,
        behaviors: List[BehaviorRecord],
    ) -> Dict[str, Dict[str, ParameterPattern]]:
        """
        提取参数使用模式

        Args:
            behaviors: 行为记录列表

        Returns:
            参数模式（skill_id -> {param_name -> ParameterPattern}）
        """
        # 收集每个技能的参数值
        skill_params: Dict[str, Dict[str, List[Any]]] = {}

        for behavior in behaviors:
            if behavior.event_type != BehaviorType.EXECUTE.value:
                continue
            if not behavior.skill_id or not behavior.parameters:
                continue

            skill_id = behavior.skill_id
            if skill_id not in skill_params:
                skill_params[skill_id] = {}

            for param_name, param_value in behavior.parameters.items():
                if param_name not in skill_params[skill_id]:
                    skill_params[skill_id][param_name] = []
                skill_params[skill_id][param_name].append(param_value)

        # 转换为 ParameterPattern
        patterns: Dict[str, Dict[str, ParameterPattern]] = {}

        for skill_id, params in skill_params.items():
            patterns[skill_id] = {}

            for param_name, values in params.items():
                # 统计值频率
                value_counts = Counter(str(v) for v in values)
                common_values = [v for v, _ in value_counts.most_common(self.MAX_COMMON_VALUES)]

                # 推断默认值（最常用的值）
                default_value = common_values[0] if common_values else None

                # 计算自定义率（假设技能有默认参数）
                # 这里简化处理，假设第一个值之后都是自定义
                custom_rate = 0.0
                if len(values) > 1:
                    unique_values = len(set(str(v) for v in values))
                    custom_rate = min(1.0, unique_values / len(values))

                patterns[skill_id][param_name] = ParameterPattern(
                    parameter_name=param_name,
                    common_values=common_values,
                    value_counts=dict(value_counts),
                    default_value=default_value,
                    custom_rate=custom_rate,
                    sample_count=len(values),
                )

        return patterns

    def _compute_active_hours(self, behaviors: List[BehaviorRecord]) -> List[int]:
        """
        计算用户活跃时段

        Args:
            behaviors: 行为记录列表

        Returns:
            活跃时段列表（小时 0-23，按活跃度排序）
        """
        hour_counts = Counter()

        for behavior in behaviors:
            if behavior.created_at:
                hour = behavior.created_at.hour
                hour_counts[hour] += 1

        # 按活跃度排序
        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        return [hour for hour, _ in sorted_hours[:10]]

    def _infer_expertise_level(self, behaviors: List[BehaviorRecord]) -> ExpertiseLevel:
        """
        推断用户专家水平

        Args:
            behaviors: 行为记录列表

        Returns:
            专家水平
        """
        # 统计执行和成功次数
        execute_count = sum(1 for b in behaviors if b.event_type == BehaviorType.EXECUTE.value)
        success_count = sum(1 for b in behaviors if b.event_type == BehaviorType.SUCCESS.value)

        # 计算成功率
        success_rate = success_count / execute_count if execute_count > 0 else 0

        # 根据执行次数和成功率推断
        if execute_count < self.BEGINNER_EXECUTION_THRESHOLD or success_rate < self.BEGINNER_SUCCESS_THRESHOLD:
            return ExpertiseLevel.BEGINNER
        elif execute_count < self.INTERMEDIATE_EXECUTION_THRESHOLD or success_rate < self.INTERMEDIATE_SUCCESS_THRESHOLD:
            return ExpertiseLevel.INTERMEDIATE
        elif execute_count < self.ADVANCED_EXECUTION_THRESHOLD or success_rate < self.ADVANCED_SUCCESS_THRESHOLD:
            return ExpertiseLevel.ADVANCED
        else:
            return ExpertiseLevel.EXPERT


# ==========================================
# 便捷函数
# ==========================================

def update_user_preference(session: Session, user_id: int) -> UserPreferenceRecord:
    """
    更新用户偏好的便捷函数

    Args:
        session: 数据库会话
        user_id: 用户 ID

    Returns:
        更新后的偏好记录
    """
    engine = PreferenceEngine(session)
    return engine.update_user_profile(user_id)


def get_user_preference(session: Session, user_id: int) -> Optional[UserPreferenceProfile]:
    """
    获取用户偏好的便捷函数

    Args:
        session: 数据库会话
        user_id: 用户 ID

    Returns:
        用户偏好画像
    """
    engine = PreferenceEngine(session)
    return engine.get_user_profile(user_id)


log.info("✅ 偏好学习引擎已加载")