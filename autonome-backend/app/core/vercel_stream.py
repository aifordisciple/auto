"""
Vercel AI SDK UIMessage Stream Protocol 编码器 (v5)

将内部 SSE 事件转换为 Vercel AI SDK v5 的 UIMessage Stream Protocol 格式。
传输层使用 SSE 格式：每行 `data: {JSON}\n\n`，
前端 DefaultChatTransport 通过 EventSourceParserStream 解析。

UIMessage Stream Protocol 事件类型：
  - text-start:       文本块开始  → data: {"type":"text-start","id":"msg_xxx"}
  - text-delta:       文本增量    → data: {"type":"text-delta","id":"msg_xxx","delta":"chunk"}
  - text-end:         文本块结束  → data: {"type":"text-end","id":"msg_xxx"}
  - data-{name}:      自定义数据 → data: {"type":"data-{name}","data":{...}}
  - finish:           流结束     → data: {"type":"finish","finishReason":"stop","usage":{...}}
  - error:            错误       → data: {"type":"error","error":"message"}
  - step-start:       步骤开始

⚠️ v5 要求自定义数据事件的 type 必须以 "data-" 开头（如 "data-thinking"），
   不能使用裸 "data" 类型，否则 Zod 校验会报 invalid_union 错误。

所有 JSON 输出使用 ensure_ascii=False 以保留中文字符。
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def _sse_line(payload: dict[str, Any]) -> str:
    """将 JSON payload 编码为 SSE 格式行：data: {json}\n\n"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class VercelDataStreamEncoder:
    """Vercel AI SDK UIMessage Stream Protocol 编码器 (v5)

    负责将内部事件（消息、思考、计费等）转换为 UIMessage Stream Protocol
    的 SSE 格式。每个方法返回 `data: {JSON}\\n\\n` 格式的字符串。
    """

    def __init__(self) -> None:
        # 为当前流式消息生成固定 ID，text-start/text-delta/text-end 共用
        self._message_id: str = f"msg_{uuid.uuid4().hex[:12]}"

    # ── 核心方法 ──────────────────────────────────────────────

    def text_chunk(self, text: str) -> str:
        """文本增量 — text-delta 事件"""
        return _sse_line({"type": "text-delta", "id": self._message_id, "delta": text})

    def text_start(self) -> str:
        """文本块开始 — text-start 事件"""
        return _sse_line({"type": "text-start", "id": self._message_id})

    def text_end(self) -> str:
        """文本块结束 — text-end 事件"""
        return _sse_line({"type": "text-end", "id": self._message_id})

    def tool_call(self, tool_call_id: str, tool_name: str, args: dict[str, Any]) -> str:
        """工具调用 — tool-call 事件（AI SDK v5 规范：使用 toolCallId 非 id）"""
        return _sse_line({"type": "tool-call", "toolCallId": tool_call_id, "toolName": tool_name, "args": args})

    def tool_result(self, tool_call_id: str, result: Any) -> str:
        """工具结果 — tool-result 事件"""
        return _sse_line({"type": "tool-result", "id": tool_call_id, "result": result})

    def finish(self, finish_reason: str = "stop") -> str:
        """流结束 — finish 事件 (v5 strictObject: only type + finishReason)

        v5 Zod schema 为 strictObject，仅接受 type/finishReason/messageMetadata，
        任何额外字段（如 usage）会导致 AI_TypeValidationError。
        """
        return _sse_line({
            "type": "finish",
            "finishReason": finish_reason,
        })

    def error(self, message: str) -> str:
        """错误 — error 事件"""
        return _sse_line({"type": "error", "error": message})

    def data_event(self, data: dict[str, Any], *, event_name: str = "custom") -> str:
        """自定义数据事件 — data-{name} 事件

        v5 UIMessage Stream Protocol 要求自定义数据事件的 type 必须以 "data-" 开头，
        例如 "data-thinking"、"data-billing" 等。
        前端通过 message.parts 中 type="data-{name}" 的项提取数据。
        """
        return _sse_line({"type": f"data-{event_name}", "data": data})

    def step_start(self) -> str:
        """步骤开始 — step-start 事件"""
        return _sse_line({"type": "step-start"})

    # ── 便捷映射方法 ──────────────────────────────────────────

    def from_thinking(self, content: str) -> str:
        """思考过程 → data-thinking 事件"""
        return self.data_event({"content": content}, event_name="thinking")

    def from_session_info(self, session_id: str, is_new: bool) -> str:
        """会话信息 → data-session_info 事件"""
        return self.data_event({"session_id": session_id, "is_new": is_new}, event_name="session_info")

    def from_billing(self, cost: float, balance: float) -> str:
        """计费信息 → data-billing 事件"""
        return self.data_event({"cost": cost, "balance": balance}, event_name="billing")

    def from_ai_message_id(self, message_id: str) -> str:
        """AI 消息 ID → data-ai_message_id 事件"""
        return self.data_event({"message_id": message_id}, event_name="ai_message_id")

    def from_ai_message_content(self, content: str) -> str:
        """AI 消息完整内容 → data-ai_message_content 事件"""
        return self.data_event({"content": content}, event_name="ai_message_content")

    def from_queue_event(self, event_type: str, payload: dict[str, Any]) -> str:
        """队列事件 → 对应的 UIMessage 流事件"""
        if event_type == "queue_done":
            return self.finish(finish_reason="stop")
        return self.data_event({**payload, "queue_event": event_type}, event_name=f"queue_{event_type}")

    def from_custom_event(self, event_type: str, payload: dict[str, Any]) -> str:
        """自定义事件 → data-{event_type} 事件"""
        return self.data_event(payload, event_name=event_type)
