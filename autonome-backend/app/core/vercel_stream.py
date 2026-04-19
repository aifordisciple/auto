"""
Vercel AI SDK UIMessage Stream Protocol 编码器 (v5)

将内部 SSE 事件转换为 Vercel AI SDK v5 的 UIMessage Stream Protocol 格式。
协议规范：每行是一个 JSON 对象，包含 type 字段标识事件类型。

UIMessage Stream Protocol 事件类型：
  - text-start:  文本块开始  → {"type":"text-start","id":"msg_xxx"}
  - text-delta:  文本增量    → {"type":"text-delta","id":"msg_xxx","delta":"chunk"}
  - text-end:    文本块结束  → {"type":"text-end","id":"msg_xxx"}
  - reasoning-start: 推理开始
  - reasoning-delta: 推理增量
  - reasoning-end:   推理结束
  - tool-call:   工具调用
  - tool-result: 工具结果
  - data:        自定义数据 → {"type":"data","data":{...}}
  - finish:      流结束     → {"type":"finish","finishReason":"stop","usage":{...}}
  - error:       错误       → {"type":"error","error":"message"}
  - step-start:  步骤开始

所有 JSON 输出使用 ensure_ascii=False 以保留中文字符。
"""

from __future__ import annotations

import json
import uuid
from typing import Any


class VercelDataStreamEncoder:
    """Vercel AI SDK UIMessage Stream Protocol 编码器 (v5)

    负责将内部事件（消息、思考、计费等）转换为 UIMessage Stream Protocol
    的 JSON 行格式。每个方法返回一个以 \\n 结尾的字符串，可直接写入响应流。
    """

    def __init__(self) -> None:
        # 为当前流式消息生成固定 ID，text-start/text-delta/text-end 共用
        self._message_id: str = f"msg_{uuid.uuid4().hex[:12]}"

    # ── 核心方法 ──────────────────────────────────────────────

    def text_chunk(self, text: str) -> str:
        """文本增量 — text-delta 事件

        对应 Vercel AI SDK v5 的 text-delta 事件，前端逐块渲染文本。
        注意：首次调用时应先发送 text_start()，流结束时应发送 text_end()。
        这里仅发送增量，start/end 由调用方控制。
        """
        payload = {"type": "text-delta", "id": self._message_id, "delta": text}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def text_start(self) -> str:
        """文本块开始 — text-start 事件

        在第一个 text-delta 之前发送，标记文本块的开始。
        """
        payload = {"type": "text-start", "id": self._message_id}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def text_end(self) -> str:
        """文本块结束 — text-end 事件

        在最后一个 text-delta 之后发送，标记文本块的结束。
        """
        payload = {"type": "text-end", "id": self._message_id}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """工具调用 — tool-call 事件

        当 Agent 调用工具（如代码执行、数据探针）时发送。
        """
        payload = {
            "type": "tool-call",
            "id": tool_call_id,
            "toolName": tool_name,
            "args": args,
        }
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def tool_result(
        self,
        tool_call_id: str,
        result: Any,
    ) -> str:
        """工具结果 — tool-result 事件

        工具执行完成后返回结果。
        """
        payload = {
            "type": "tool-result",
            "id": tool_call_id,
            "result": result,
        }
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def finish(
        self,
        finish_reason: str = "stop",
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> str:
        """流结束 + 用量统计 — finish 事件

        流式响应结束时发送，携带结束原因和 token 用量。
        """
        payload = {
            "type": "finish",
            "finishReason": finish_reason,
            "usage": {
                "promptTokens": prompt_tokens,
                "completionTokens": completion_tokens,
                "totalTokens": total_tokens,
            },
        }
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def error(self, message: str) -> str:
        """错误 — error 事件

        流式过程中发生错误时发送。
        """
        payload = {"type": "error", "error": message}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def data_event(self, data: dict[str, Any]) -> str:
        """自定义数据事件 — data 事件

        用于传输非标准协议的自定义数据，前端通过消息 parts 中的
        DataUIPart 接收。
        """
        payload = {"type": "data", "data": data}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    def step_start(self) -> str:
        """步骤开始 — step-start 事件

        多步骤 Agent 执行时标记新步骤的开始。
        """
        payload = {"type": "step-start"}
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    # ── 便捷映射方法 ──────────────────────────────────────────
    # 将内部 SSE 事件映射为 UIMessage Stream Protocol 行格式

    def from_thinking(self, content: str) -> str:
        """思考过程 → 自定义 data 事件

        内部 thinking 事件携带 AI 的思考过程内容。
        映射为 data 事件以便前端在思考框中渲染。
        """
        return self.data_event({"type": "thinking", "content": content})

    def from_session_info(self, session_id: str, is_new: bool) -> str:
        """会话信息 → 自定义 data 事件

        SSE 连接建立后首先推送会话标识，前端用于绑定消息。
        """
        return self.data_event({
            "type": "session_info",
            "session_id": session_id,
            "is_new": is_new,
        })

    def from_billing(self, cost: float, balance: float) -> str:
        """计费信息 → 自定义 data 事件

        LLM 调用完成后推送扣费金额和余额。
        """
        return self.data_event({
            "type": "billing",
            "cost": cost,
            "balance": balance,
        })

    def from_ai_message_id(self, message_id: str) -> str:
        """AI 消息 ID → 自定义 data 事件

        消息持久化后推送数据库 ID，前端用于关联和更新。
        """
        return self.data_event({
            "type": "ai_message_id",
            "message_id": message_id,
        })

    def from_ai_message_content(self, content: str) -> str:
        """AI 消息完整内容 → 自定义 data 事件

        流式结束后推送完整的消息内容（已过滤思考标签），
        前端可用于最终确认或替换流式累积的内容。
        """
        return self.data_event({
            "type": "ai_message_content",
            "content": content,
        })

    def from_queue_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """队列事件 → 对应的 UIMessage 流事件

        将 Celery 队列处理的 SSE 事件映射为 UIMessage 协议格式。
        队列事件类型包括：queue_start, queue_progress, queue_complete,
        queue_done, queue_error 等。

        特殊处理：
        - queue_done → 映射为 finish 事件（流结束信号）
        - 其他队列事件 → 映射为 data 事件保留完整信息
        """
        if event_type == "queue_done":
            # 队列全部处理完毕，等同于流结束
            return self.finish(finish_reason="stop")

        # 其他队列事件作为自定义数据传输
        enriched_payload = {**payload, "queue_event": event_type}
        return self.data_event(enriched_payload)

    def from_custom_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """自定义事件 → data 事件

        通用方法，将任意事件类型和载荷映射为 data 事件。
        用于意图识别结果等非标准协议数据的传输。
        """
        return self.data_event({**payload, "type": event_type})
