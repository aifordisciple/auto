"""
成功评估器 - 评估会话是否成功并值得提取为经验资产
"""

from typing import Dict, List, Optional
from sqlmodel import Session, select
from datetime import datetime, timedelta

from app.models.domain import ChatSession, ChatMessage, RoleEnum, SkillExecutionHistory
from app.core.logger import log


class SuccessEvaluator:
    """
    评估会话成功度的服务类

    通过分析会话消息、技能执行历史等来判断一个会话是否成功完成，
    从而决定是否将其提取为可复用的经验资产。
    """

    # 成功信号词（用户最后几条消息中）
    SUCCESS_INDICATORS = [
        "成功", "完成", "解决了", "可以了", "谢谢", "感谢", "完美",
        "好的", "太好了", "很棒", "问题解决了", "搞定了", "没问题了"
    ]

    # 失败信号词
    FAILURE_INDICATORS = [
        "报错", "失败", "不行", "还是有问题", "错误", "出错了",
        "失败了", "不行了", "没解决", "还是有错误", "不管用"
    ]

    # 用户确认询问词（需要再确认）
    CONFIRMATION_QUESTIONS = [
        "是对的吗", "正确吗", "合适吗", "这样可以吗"
    ]

    def __init__(self, db: Session):
        self.db = db

    def evaluate_session(self, session_id: str) -> Dict:
        """
        评估会话成功度

        Args:
            session_id: 会话 ID

        Returns:
            {
                "is_successful": bool,          # 是否成功
                "confidence": float,            # 置信度 (0-1)
                "success_criteria": str,        # 成功判定依据
                "debug_iterations": int,        # 调试迭代次数
                "skill_executions": int,        # 技能执行次数
                "successful_skills": int,       # 成功的技能数
                "signals_detected": List[str]   # 检测到的信号词
            }
        """
        result = {
            "is_successful": False,
            "confidence": 0.0,
            "success_criteria": "",
            "debug_iterations": 0,
            "skill_executions": 0,
            "successful_skills": 0,
            "signals_detected": []
        }

        try:
            # 1. 获取会话消息
            messages = self._get_session_messages(session_id)
            if not messages:
                result["success_criteria"] = "会话无消息"
                return result

            # 2. 分析用户最后几条消息的成功/失败信号
            user_messages = [m for m in messages if m.role == RoleEnum.user]
            if not user_messages:
                result["success_criteria"] = "无用户消息"
                return result

            last_user_messages = user_messages[-3:] if len(user_messages) >= 3 else user_messages
            signal_result = self._analyze_user_signals(last_user_messages)
            result["signals_detected"] = signal_result["signals"]

            # 3. 获取技能执行历史
            skill_result = self._analyze_skill_executions(session_id)
            result["skill_executions"] = skill_result["total"]
            result["successful_skills"] = skill_result["successful"]
            result["debug_iterations"] = skill_result["debug_iterations"]

            # 4. 综合评分
            score = self._calculate_success_score(
                signal_result, skill_result, len(messages)
            )
            result["confidence"] = score["confidence"]
            result["success_criteria"] = score["criteria"]

            # 5. 判定成功（置信度阈值 0.7）
            result["is_successful"] = score["confidence"] >= 0.7

            log.info(
                f"📊 [SuccessEvaluator] 会话 {session_id} 评估结果: "
                f"成功={result['is_successful']}, 置信度={result['confidence']:.2f}, "
                f"依据={result['success_criteria']}"
            )

        except Exception as e:
            log.error(f"❌ [SuccessEvaluator] 评估会话失败: {e}")
            result["success_criteria"] = f"评估异常: {str(e)}"

        return result

    def _get_session_messages(self, session_id: str) -> List[ChatMessage]:
        """获取会话所有消息"""
        return self.db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).all()

    def _analyze_user_signals(self, messages: List[ChatMessage]) -> Dict:
        """分析用户消息中的成功/失败信号"""
        result = {
            "signals": [],
            "success_count": 0,
            "failure_count": 0,
            "confirmation_count": 0
        }

        for msg in messages:
            content = msg.content.lower() if msg.content else ""

            # 检测成功信号
            for indicator in self.SUCCESS_INDICATORS:
                if indicator in content:
                    result["signals"].append(f"成功信号: {indicator}")
                    result["success_count"] += 1
                    break

            # 检测失败信号
            for indicator in self.FAILURE_INDICATORS:
                if indicator in content:
                    result["signals"].append(f"失败信号: {indicator}")
                    result["failure_count"] += 1
                    break

            # 检测确认询问
            for question in self.CONFIRMATION_QUESTIONS:
                if question in content:
                    result["signals"].append(f"确认询问: {question}")
                    result["confirmation_count"] += 1
                    break

        return result

    def _analyze_skill_executions(self, session_id: str) -> Dict:
        """分析技能执行历史"""
        result = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "debug_iterations": 0
        }

        # 查询该会话的技能执行记录
        executions = self.db.exec(
            select(SkillExecutionHistory)
            .where(SkillExecutionHistory.session_id == session_id)
            .order_by(SkillExecutionHistory.created_at)
        ).all()

        result["total"] = len(executions)
        if not executions:
            return result

        # 统计成功/失败
        for exec_record in executions:
            if exec_record.status == "SUCCESS":
                result["successful"] += 1
            elif exec_record.status == "FAILURE":
                result["failed"] += 1

        # 估算调试迭代次数：连续失败后成功的组合
        consecutive_failures = 0
        for exec_record in executions:
            if exec_record.status == "FAILURE":
                consecutive_failures += 1
            elif exec_record.status == "SUCCESS" and consecutive_failures > 0:
                # 一次调试循环结束
                result["debug_iterations"] += consecutive_failures
                consecutive_failures = 0

        return result

    def _calculate_success_score(
        self,
        signal_result: Dict,
        skill_result: Dict,
        message_count: int
    ) -> Dict:
        """
        计算成功评分

        综合考虑：
        1. 用户消息信号（权重 0.5）
        2. 技能执行成功率（权重 0.3）
        3. 调试情况（权重 0.2）
        """
        confidence = 0.0
        criteria_parts = []

        # 1. 用户信号评分（权重 0.5）
        signal_score = 0.0
        if signal_result["success_count"] > 0:
            # 有成功信号
            signal_score = min(signal_result["success_count"] * 0.4, 1.0)
            if signal_result["failure_count"] == 0:
                signal_score = min(signal_score + 0.2, 1.0)
            criteria_parts.append(f"成功信号×{signal_result['success_count']}")

        if signal_result["failure_count"] > signal_result["success_count"]:
            # 失败信号多于成功信号
            signal_score = max(0, signal_score - 0.3)
            criteria_parts.append(f"失败信号×{signal_result['failure_count']}")

        confidence += signal_score * 0.5

        # 2. 技能执行评分（权重 0.3）
        skill_score = 0.0
        if skill_result["total"] > 0:
            success_rate = skill_result["successful"] / skill_result["total"]
            skill_score = success_rate
            if skill_result["successful"] > 0:
                criteria_parts.append(f"技能成功{skill_result['successful']}/{skill_result['total']}")

        confidence += skill_score * 0.3

        # 3. 调试评分（权重 0.2）
        debug_score = 0.0
        if skill_result["debug_iterations"] == 0:
            # 没有调试，直接成功
            debug_score = 1.0
        elif skill_result["successful"] > 0:
            # 有调试但最终成功，说明问题解决了
            debug_score = 0.7
            criteria_parts.append(f"调试×{skill_result['debug_iterations']}后成功")
        else:
            debug_score = 0.3

        confidence += debug_score * 0.2

        # 构建判定依据描述
        if not criteria_parts:
            criteria = "无明确信号，默认评分较低"
        else:
            criteria = " | ".join(criteria_parts)

        return {
            "confidence": round(confidence, 2),
            "criteria": criteria
        }

    def quick_check_success(self, session_id: str) -> bool:
        """
        快速检查会话是否成功（用于快速筛选）

        只检查最后一条用户消息是否包含成功信号
        """
        messages = self._get_session_messages(session_id)
        user_messages = [m for m in messages if m.role == RoleEnum.user]

        if not user_messages:
            return False

        last_msg = user_messages[-1].content.lower() if user_messages[-1].content else ""

        # 检查最后消息是否包含成功信号且不包含失败信号
        has_success = any(ind in last_msg for ind in self.SUCCESS_INDICATORS)
        has_failure = any(ind in last_msg for ind in self.FAILURE_INDICATORS)

        return has_success and not has_failure