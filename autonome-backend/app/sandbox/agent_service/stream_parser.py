"""
Claude Code JSONL Stream 解析器

解析 Claude Code --output-format stream-json 输出:
- 将 JSONL 行映射为统一的 AgentEvent 类型
- 支持增量解析 (逐行读取)
- 容错处理: 跳过非法 JSON 行
"""

import json
from typing import Iterator, Optional

from app.sandbox.agent_service.event_types import (
    AgentEvent,
    TextDeltaEvent,
    TextEndEvent,
    ThinkingEvent,
    ToolUseEvent,
    ToolResultEvent,
    StatusEvent,
    ErrorEvent,
    UsageEvent,
    AgentStatus,
)


class ClaudeStreamParser:
    """
    Claude Code stream-json 解析器

    Claude Code --output-format stream-json 的 JSONL 结构:
    - {"type":"system","subtype":"init",...}
    - {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
    - {"type":"user","message":{"content":[{"type":"tool_result",...}]}}
    - {"type":"result","usage":{...}}
    """

    def __init__(self):
        self._buffer = ""

    def feed_line(self, line: str) -> Optional[AgentEvent]:
        """喂入一行 JSONL，返回解析后的事件 (可能为 None)"""
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        return self._parse_object(data)

    def _parse_object(self, obj: dict) -> Optional[AgentEvent]:
        """解析单个 JSONL 对象"""
        obj_type = obj.get("type", "")

        if obj_type == "system":
            return self._parse_system(obj)
        elif obj_type == "assistant":
            return self._parse_assistant(obj)
        elif obj_type == "user":
            return self._parse_user(obj)
        elif obj_type == "result":
            return self._parse_result(obj)

        return None

    def _parse_system(self, obj: dict) -> Optional[AgentEvent]:
        """解析系统事件 (init, status)"""
        subtype = obj.get("subtype", "")
        if subtype == "status":
            status_str = obj.get("status", "")
            mapping = {
                "compressing": AgentStatus.THINKING,
                "idle": AgentStatus.IDLE,
            }
            return StatusEvent(status=mapping.get(status_str, AgentStatus.THINKING.value))
        return None

    def _parse_assistant(self, obj: dict) -> Optional[AgentEvent]:
        """解析 assistant 消息 — 包含文本、思考、工具调用"""
        message = obj.get("message", {})
        content = message.get("content", [])

        if not isinstance(content, list) or len(content) == 0:
            return None

        events = []
        for block in content:
            if isinstance(block, str):
                return TextDeltaEvent(content=block)

            block_type = block.get("type", "")
            if block_type == "text":
                return TextDeltaEvent(content=block.get("text", ""))
            elif block_type == "thinking":
                return ThinkingEvent(content=block.get("thinking", ""))
            elif block_type == "tool_use":
                return ToolUseEvent(
                    tool_name=block.get("name", ""),
                    tool_input=block.get("input", {}),
                    tool_use_id=block.get("id", ""),
                )

        return None

    def _parse_user(self, obj: dict) -> Optional[AgentEvent]:
        """解析 user 消息 — 通常包含 tool_result"""
        message = obj.get("message", {})
        content = message.get("content", [])

        if isinstance(content, list) and len(content) > 0:
            block = content[0]
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return ToolResultEvent(
                    tool_use_id=block.get("tool_use_id", ""),
                    tool_name="",
                    status="success" if not block.get("is_error") else "failed",
                    output=json.dumps(block.get("content", ""), ensure_ascii=False),
                )

        return None

    def _parse_result(self, obj: dict) -> Optional[AgentEvent]:
        """解析 result — 包含 usage 信息"""
        usage = obj.get("usage", {})
        if usage:
            return UsageEvent(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        return None


def parse_claude_output(stdout_lines: Iterator[str]) -> Iterator[AgentEvent]:
    """便捷函数: 逐行解析 Claude Code stdout, 产出事件流"""
    parser = ClaudeStreamParser()
    for line in stdout_lines:
        event = parser.feed_line(line)
        if event is not None:
            yield event
