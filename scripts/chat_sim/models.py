"""模拟对话测试 - 数据模型"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Category(str, Enum):
    KNOWLEDGE_BASE = "knowledge_base"
    GENERAL_QA = "general_qa"
    SMALL_TALK = "small_talk"
    TASK = "task"
    CONTENT_FILTER = "content_filter"
    EDGE_CASE = "edge_case"


class Verdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class SimQuestion:
    """测试问题"""
    id: int
    message: str
    category: str
    difficulty: str
    expected_intent: str
    description: str


@dataclass
class APIResult:
    """API 调用结果"""
    question_id: int
    status_code: int
    elapsed_ms: float
    response_text: str = ""
    actual_intent: str = ""
    session_id: str = ""
    ai_message_id: str = ""
    error: str = ""
    # 流式事件原始记录，用于调试定位
    raw_events: list = field(default_factory=list)


@dataclass
class JudgeResult:
    """评判结果"""
    question_id: int
    verdict: str  # PASS / WARN / FAIL
    relevance: int = 0       # 1-5
    accuracy: int = 0        # 1-5
    completeness: int = 0    # 1-5
    intent_match: bool = True
    reason: str = ""
    issue_location: str = ""  # intent_router / knowledge_base_node / content_filter / llm_service / performance


@dataclass
class TestItem:
    """单条测试完整记录"""
    question: SimQuestion
    api_result: Optional[APIResult] = None
    judge_result: Optional[JudgeResult] = None


@dataclass
class TestReport:
    """测试报告"""
    timestamp: str
    total: int = 0
    passed: int = 0
    warned: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    items: list = field(default_factory=list)
    category_stats: dict = field(default_factory=dict)
