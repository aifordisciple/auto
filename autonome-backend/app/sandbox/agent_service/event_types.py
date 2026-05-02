"""
Agent Service 事件类型定义

Claude Code stream-json 输出 → 统一事件类型的映射。
每种事件对应一个 dataclass，用于序列化/反序列化 Redis 通道传输。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from enum import Enum
import json
import time


class EventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    PLAN = "plan"
    TASK_SUBMITTED = "task_submitted"
    TASK_STATUS = "task_status"
    STATUS = "status"
    ERROR = "error"
    USAGE = "usage"


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_USER = "waiting_user"


@dataclass
class AgentEvent:
    """Agent 事件基类"""
    type: EventType
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type.value
        return json.dumps(data, ensure_ascii=False)


@dataclass
class TextDeltaEvent(AgentEvent):
    type: EventType = EventType.TEXT_DELTA
    content: str = ""


@dataclass
class TextEndEvent(AgentEvent):
    type: EventType = EventType.TEXT_END


@dataclass
class ThinkingEvent(AgentEvent):
    type: EventType = EventType.THINKING
    content: str = ""


@dataclass
class ToolUseEvent(AgentEvent):
    type: EventType = EventType.TOOL_USE
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""


@dataclass
class ToolResultEvent(AgentEvent):
    type: EventType = EventType.TOOL_RESULT
    tool_name: str = ""
    tool_use_id: str = ""
    status: str = "success"
    output: str = ""


@dataclass
class PlanEvent(AgentEvent):
    type: EventType = EventType.PLAN
    title: str = ""
    steps: List[Dict[str, str]] = field(default_factory=list)
    codeSnapshot: str = ""
    estimatedCost: str = ""


@dataclass
class TaskSubmittedEvent(AgentEvent):
    type: EventType = EventType.TASK_SUBMITTED
    task_id: str = ""
    celery_queue: str = ""
    skill_id: str = ""


@dataclass
class TaskStatusEvent(AgentEvent):
    type: EventType = EventType.TASK_STATUS
    task_id: str = ""
    status: str = "pending"
    progress: str = ""


@dataclass
class StatusEvent(AgentEvent):
    type: EventType = EventType.STATUS
    status: str = AgentStatus.IDLE.value
    message: str = ""


@dataclass
class ErrorEvent(AgentEvent):
    type: EventType = EventType.ERROR
    message: str = ""
    code: str = ""


@dataclass
class UsageEvent(AgentEvent):
    type: EventType = EventType.USAGE
    input_tokens: int = 0
    output_tokens: int = 0
