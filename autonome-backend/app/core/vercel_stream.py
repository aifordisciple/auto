"""
Vercel AI SDK Data Stream Protocol 编码器

将内部 SSE 事件转换为 Vercel AI SDK 的 Data Stream Protocol 格式。
协议规范：每行格式为 `type:json\n`，类型标识符 + JSON 载荷。

类型映射：
  - 0: 文本流式块   → 0:"chunk"\n
  - 9: 工具调用     → 9:{tool_call}\n
  - b: 工具结果     → b:{tool_result}\n
  - e: 流结束+用量  → e:{finish_reason,usage}\n
  - 3: 错误         → 3:"message"\n
  - data: 自定义数据 → data:[{...}]\n

所有 JSON 输出使用 ensure_ascii=False 以保留中文字符。
"""

from __future__ import annotations

import json
from typing import Any


class VercelDataStreamEncoder:
    """Vercel AI SDK Data Stream Protocol 编码器

    负责将内部事件（消息、思考、计费等）转换为 Vercel Data Stream Protocol
    的行格式。每个方法返回一个以 \\n 结尾的字符串，可直接写入 SSE 响应流。
    """

    # ── 核心方法 ──────────────────────────────────────────────

    def text_chunk(self, text: str) -> str:
        """文本流式块 — 类型 0

        对应 Vercel AI SDK 的 text-delta 事件，前端逐块渲染文本。
        """
        return f"0:{json.dumps(text, ensure_ascii=False)}\n"

    def tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """工具调用 — 类型 9

        当 Agent 调用工具（如代码执行、数据探针）时发送。
        前端收到后展示工具调用状态。
        """
        payload = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "args": args,
        }
        return f"9:{json.dumps(payload, ensure_ascii=False)}\n"

    def tool_result(
        self,
        tool_call_id: str,
        result: Any,
    ) -> str:
        """工具结果 — 类型 b

        工具执行完成后返回结果。result 可以是字符串或结构化数据。
        """
        payload = {
            "toolCallId": tool_call_id,
            "result": result,
        }
        return f"b:{json.dumps(payload, ensure_ascii=False)}\n"

    def finish(
        self,
        finish_reason: str = "stop",
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> str:
        """流结束 + 用量统计 — 类型 e

        流式响应结束时发送，携带结束原因和 token 用量。
        """
        payload = {
            "finishReason": finish_reason,
            "usage": {
                "promptTokens": prompt_tokens,
                "completionTokens": completion_tokens,
                "totalTokens": total_tokens,
            },
        }
        return f"e:{json.dumps(payload, ensure_ascii=False)}\n"

    def error(self, message: str) -> str:
        """错误 — 类型 3

        流式过程中发生错误时发送。前端展示错误提示。
        """
        return f"3:{json.dumps(message, ensure_ascii=False)}\n"

    def data_event(self, data: list[dict[str, Any]]) -> str:
        """自定义数据事件 — data: 前缀

        用于传输非标准协议的自定义数据，前端通过 useChat 的
        onToolCall 或 onFinish 回调处理。

        data 必须是字典列表，符合 Vercel AI SDK 的 data 消息格式。
        """
        return f"data:{json.dumps(data, ensure_ascii=False)}\n"

    # ── 便捷映射方法 ──────────────────────────────────────────
    # 将内部 SSE 事件映射为 Vercel Data Stream Protocol 行格式

    def from_thinking(self, content: str) -> str:
        """思考过程 → 自定义 data 事件

        内部 thinking 事件携带 AI 的思考过程内容。
        映射为 data 事件以便前端在思考框中渲染，
        同时保持与 Vercel AI SDK 协议的兼容性。
        """
        return self.data_event([{"type": "thinking", "content": content}])

    def from_session_info(self, session_id: str, is_new: bool) -> str:
        """会话信息 → 自定义 data 事件

        SSE 连接建立后首先推送会话标识，前端用于绑定消息。
        """
        return self.data_event([{
            "type": "session_info",
            "session_id": session_id,
            "is_new": is_new,
        }])

    def from_billing(self, cost: float, balance: float) -> str:
        """计费信息 → 自定义 data 事件

        LLM 调用完成后推送扣费金额和余额。
        """
        return self.data_event([{
            "type": "billing",
            "cost": cost,
            "balance": balance,
        }])

    def from_ai_message_id(self, message_id: str) -> str:
        """AI 消息 ID → 自定义 data 事件

        消息持久化后推送数据库 ID，前端用于关联和更新。
        """
        return self.data_event([{
            "type": "ai_message_id",
            "message_id": message_id,
        }])

    def from_ai_message_content(self, content: str) -> str:
        """AI 消息完整内容 → 自定义 data 事件

        流式结束后推送完整的消息内容（已过滤思考标签），
        前端可用于最终确认或替换流式累积的内容。
        """
        return self.data_event([{
            "type": "ai_message_content",
            "content": content,
        }])

    def from_queue_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """队列事件 → 对应的 Vercel 流事件

        将 Celery 队列处理的 SSE 事件映射为 Vercel 协议格式。
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
        return self.data_event([enriched_payload])

    def from_custom_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """自定义事件 → data 事件

        通用方法，将任意事件类型和载荷映射为 Vercel data 事件。
        用于意图识别结果等非标准协议数据的传输。
        """
        return self.data_event([{**payload, "type": event_type}])
