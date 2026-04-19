# Vercel AI SDK Full Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace custom streaming architecture with Vercel AI SDK `useChat` + Data Stream Protocol, add Generative UI via Tool Calling, and establish Next.js BFF proxy layer.

**Architecture:** Backend outputs Vercel Data Stream Protocol natively. Next.js API Routes proxy requests with JWT injection. Frontend uses `useChat` as single source of truth, Zustand as global mirror. Generative UI via `tools` config in `useChat`.

**Tech Stack:** Vercel AI SDK (`ai` package), Next.js 16 App Router API Routes, FastAPI + sse-starlette, Zustand, Zod

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `autonome-backend/app/core/vercel_stream.py` | Vercel Data Stream Protocol encoder |
| `autonome-studio/src/app/api/chat/route.ts` | BFF main chat proxy (JWT + context + stream forward) |
| `autonome-studio/src/app/api/chat/queue/route.ts` | BFF queue stream proxy |
| `autonome-studio/src/app/api/chat/queue-actions/route.ts` | BFF queue CRUD proxy |
| `autonome-studio/src/hooks/useChatSync.ts` | Bridge: useChat state → Zustand store |
| `autonome-studio/src/hooks/useChatQueue.ts` | Queue management: SSE stream + CRUD |
| `autonome-studio/src/components/chat/InteractivePlotCard/index.tsx` | Generative UI: interactive plot |
| `autonome-studio/src/components/chat/ExecutionResultCard/index.tsx` | Generative UI: code execution result |
| `autonome-studio/src/components/chat/DataPreviewCard/index.tsx` | Generative UI: data preview table |
| `autonome-studio/src/components/chat/SkillDraftCard/index.tsx` | Generative UI: skill draft |

### Modified Files

| File | Change |
|------|--------|
| `autonome-backend/app/api/routes/chat.py` | `event_generator()` and `queue_event_generator()` use VercelDataStreamEncoder |
| `autonome-backend/app/tasks/chat_queue_task.py` | `publish_sse_event()` calls → `publish_vercel_event()` |
| `autonome-backend/app/services/chat_queue_service.py` | Add `publish_vercel_event()` alongside existing `publish_sse_event()` |
| `autonome-studio/src/store/useChatStore.ts` | Remove streaming state, add mirror sync actions |
| `autonome-studio/src/components/chat/ChatStage.tsx` | Replace hooks with useChat + useChatSync + useChatQueue |
| `autonome-studio/src/components/chat/ChatInputBox.tsx` | Bind to useChat input/submit/stop |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | Remove dual-path streaming logic |
| `autonome-studio/src/components/chat/StreamingMarkdown.tsx` | Remove typewriter cursor, simplify isStreaming |
| `autonome-studio/src/components/chat/QueueIndicator.tsx` | Data source from useChatQueue |
| `autonome-studio/src/hooks/useMessageActions.ts` | Simplify: use useChat methods |
| `autonome-studio/src/hooks/useChatEventListeners.ts` | Simplify |
| `autonome-studio/package.json` | Add `ai` + `@ai-sdk/openai`, remove `@microsoft/fetch-event-source` |

### Deleted Files

| File | Reason |
|------|--------|
| `autonome-studio/src/hooks/useImmediateStream.ts` | SDK built-in streaming replaces typewriter |
| `autonome-studio/src/hooks/useChatStream.ts` | Replaced by useChat + BFF |

---

## Task 1: Backend — Vercel Data Stream Encoder

**Files:**
- Create: `autonome-backend/app/core/vercel_stream.py`

- [ ] **Step 1: Create the VercelDataStreamEncoder class**

```python
"""
Vercel AI SDK Data Stream Protocol 编码器

将内部事件转换为 Vercel AI SDK 的 Data Stream Protocol 格式。
协议格式为行分隔，每行 type:json\\n

类型说明：
- 0: 文本流式块 (0:"chunk"\\n)
- 9: Tool Call (9:{tool_call}\\n)
- b: Tool Result (b:{tool_result}\\n)
- e: 流结束 + 用量 (e:{finish_reason,usage}\\n)
- 3: 错误 (3:"message"\\n)
- data: 自定义数据事件 (data:[{...}]\\n)
"""

import json
from typing import Any, Optional


class VercelDataStreamEncoder:
    """将内部事件编码为 Vercel AI SDK Data Stream Protocol 格式"""

    def text_chunk(self, content: str) -> str:
        """类型 0: 文本流式块"""
        return f"0:{json.dumps(content, ensure_ascii=False)}\n"

    def tool_call(self, tool_call_id: str, tool_name: str, args: dict[str, Any]) -> str:
        """类型 9: Tool Call 调用"""
        payload = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "args": args,
        }
        return f"9:{json.dumps(payload, ensure_ascii=False)}\n"

    def tool_result(self, tool_call_id: str, result: Any) -> str:
        """类型 b: Tool Result 结果"""
        payload = {
            "toolCallId": tool_call_id,
            "result": result,
        }
        return f"b:{json.dumps(payload, ensure_ascii=False)}\n"

    def finish(self, reason: str = "stop", usage: Optional[dict[str, Any]] = None) -> str:
        """类型 e: 流结束"""
        payload: dict[str, Any] = {"finishReason": reason}
        if usage:
            payload["usage"] = usage
        return f"e:{json.dumps(payload, ensure_ascii=False)}\n"

    def error(self, message: str) -> str:
        """类型 3: 错误"""
        return f"3:{json.dumps(message, ensure_ascii=False)}\n"

    def data_event(self, data: dict[str, Any]) -> str:
        """自定义 data 事件（用于非标准载荷如 thinking/billing/session_info）"""
        return f"data:{json.dumps([data], ensure_ascii=False)}\n"

    # ==========================================
    # 便捷方法：从现有 SSE 事件映射
    # ==========================================

    def from_thinking(self, content: str) -> str:
        """从 thinking SSE 事件转换"""
        return self.data_event({"type": "thinking", "content": content})

    def from_session_info(self, session_id: str, is_new: bool) -> str:
        """从 session_info SSE 事件转换"""
        return self.data_event({
            "type": "session_info",
            "session_id": session_id,
            "is_new": is_new,
        })

    def from_billing(self, cost: float, balance: float) -> str:
        """从 billing SSE 事件转换"""
        return self.data_event({"type": "billing", "cost": cost, "balance": balance})

    def from_ai_message_id(self, message_id: str) -> str:
        """从 ai_message_id SSE 事件转换"""
        return self.data_event({"type": "ai_message_id", "message_id": message_id})

    def from_ai_message_content(self, content: str) -> str:
        """从 ai_message_content SSE 事件转换"""
        return self.data_event({"type": "ai_message_content", "content": content})

    def from_queue_event(self, event_type: str, data: dict[str, Any]) -> str:
        """从队列事件（queue_start/progress/complete/error/done）转换"""
        return self.data_event({"type": event_type, **data})
```

- [ ] **Step 2: Verify the file is importable**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.core.vercel_stream import VercelDataStreamEncoder; e = VercelDataStreamEncoder(); print(e.text_chunk('hello')); print(e.from_thinking('thinking...')); print(e.finish())"`
Expected: Output shows `0:"hello"\n`, `data:[{"type":"thinking","content":"thinking..."}]\n`, `e:{"finishReason":"stop"}\n`

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/core/vercel_stream.py
git commit -m "feat: add Vercel Data Stream Protocol encoder for AI SDK compatibility"
```

---

## Task 2: Backend — Modify chat.py to Use Vercel Encoder

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py:192-304` (event_generator)
- Modify: `autonome-backend/app/api/routes/chat.py:340-412` (queue_event_generator)

- [ ] **Step 1: Add import and change event_generator to output Vercel Data Stream**

In `autonome-backend/app/api/routes/chat.py`, add import at top:

```python
from app.core.vercel_stream import VercelDataStreamEncoder
```

Replace the `event_generator()` function (lines 192-293) with a version that uses `VercelDataStreamEncoder`. The key changes:

1. Replace `EventSourceResponse` with a standard `StreamingResponse` using `text/plain` content type (Vercel Data Stream is NOT SSE format — it's plain text with line-delimited protocol)
2. Each `yield {"event": ..., "data": ...}` becomes `yield encoder.method(...)`

```python
    # 8. Vercel Data Stream 流式响应
    async def vercel_event_generator():
        encoder = VercelDataStreamEncoder()

        # 推送 session_info
        yield encoder.from_session_info(session_id_for_ai, is_new_session)

        # 检查 API Key
        if not is_local_model and not api_key:
            yield encoder.text_chunk("⚠️ 您尚未配置大模型 API Key。请在左侧设置中心配置。")
            yield encoder.finish()
            return

        # 直接 LLM 流式调用
        from langchain_openai import ChatOpenAI

        ai_full_response = ""
        cost_credits = 1.0
        content_filter = StreamContentFilter()

        try:
            direct_llm = ChatOpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                model=model_name,
                streaming=True,
            )

            async for chunk in direct_llm.astream(lc_messages):
                content = chunk.content
                if content:
                    filtered_content, content_type = content_filter.filter_chunk(content)
                    if filtered_content:
                        if content_type == "thinking":
                            yield encoder.from_thinking(filtered_content)
                        else:
                            ai_full_response += filtered_content
                            yield encoder.text_chunk(filtered_content)

        except StopAsyncIteration:
            raise
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Chat] LLM 调用失败: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **AI 引擎异常**: {str(e)}\n请查看后台日志。"
            ai_full_response += err_msg
            yield encoder.text_chunk(err_msg)

        finally:
            # 持久化助手消息 + 扣费
            with Session(engine) as final_db_session:
                cleaned_response = filter_thinking_content(ai_full_response, model_name=model_name)
                ai_msg = ChatMessage(
                    session_id=session_id_for_ai,
                    role=RoleEnum.assistant,
                    content=cleaned_response,
                )
                final_db_session.add(ai_msg)

                final_balance = 0
                db_user = final_db_session.get(User, user_id)
                if db_user:
                    try:
                        from app.services.billing_service import BillingService
                        bs = BillingService(final_db_session)
                        bs.deduct_credits(
                            wallet_id=wallet.wallet_id,
                            amount=cost_credits,
                            transaction_type="consume_chat",
                            description="聊天消息消费",
                        )
                        final_db_session.refresh(wallet)
                        final_balance = wallet.credits_balance
                    except Exception as e:
                        log.warning(f"扣费失败: {e}")
                        if db_user.billing:
                            db_user.billing.credits_balance -= cost_credits
                            if db_user.billing.credits_balance < 0:
                                db_user.billing.credits_balance = 0
                            final_balance = db_user.billing.credits_balance if db_user.billing else 0

                final_db_session.commit()

                yield encoder.from_ai_message_id(str(ai_msg.id))
                yield encoder.from_ai_message_content(cleaned_response)
                yield encoder.from_billing(cost_credits, final_balance)

            yield encoder.finish()

    # Vercel Data Stream 使用 text/plain 响应（非 SSE）
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        vercel_event_generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Modify queue_event_generator to forward Vercel-format events from Redis**

Replace `queue_event_generator()` (lines 340-401). The Redis pub/sub now carries Vercel-format events (after Task 3 modifies `publish_sse_event`). The generator reads raw Vercel protocol lines and forwards them as-is:

```python
    async def vercel_queue_event_generator():
        """
        订阅 Redis pub/sub channel，转发 Celery worker 的 Vercel Data Stream 事件给前端

        Redis 消息格式已改为 Vercel Data Stream 协议行（如 0:"chunk"\\n 或 data:[...]\\n）
        直接透传给前端。
        """
        # 推送 session_info 确认连接
        encoder = VercelDataStreamEncoder()
        yield encoder.from_session_info(session_id, False)

        # 订阅 Redis pub/sub
        import redis.asyncio as aioredis
        from app.core.config import settings

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        channel = f"chat_stream:{session_id}"

        try:
            await pubsub.subscribe(channel)
            log.info(f"队列 Vercel 流订阅已建立: session_id={session_id}")

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=300,
                )
                if message and message["type"] == "message":
                    try:
                        # Redis 消息现在是 Vercel 协议行，直接透传
                        vercel_line = message["data"]
                        yield vercel_line

                        # 检查是否是 finish 事件（表示队列处理完毕）
                        if vercel_line.startswith("data:") and '"type":"queue_done"' in vercel_line:
                            yield encoder.finish()
                            break

                    except Exception as e:
                        log.warning(f"Redis 消息转发失败: {e}")
                        continue

        except asyncio.CancelledError:
            log.info(f"队列 Vercel 流连接被取消: session_id={session_id}")
        except Exception as e:
            log.error(f"队列 Vercel 流异常: session_id={session_id}, error={e}")
        finally:
            await pubsub.unsubscribe(channel)
            await r.close()
            log.info(f"队列 Vercel 流订阅已关闭: session_id={session_id}")

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        vercel_queue_event_generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 3: Verify backend starts without import errors**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.api.routes.chat import router; print('chat router OK')"`
Expected: `chat router OK`

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py
git commit -m "refactor: chat stream endpoint outputs Vercel Data Stream Protocol"
```

---

## Task 3: Backend — Modify Celery Task and Queue Service for Vercel Protocol

**Files:**
- Modify: `autonome-backend/app/services/chat_queue_service.py:400-413` (add `publish_vercel_event`)
- Modify: `autonome-backend/app/tasks/chat_queue_task.py` (replace `publish_sse_event` calls)

- [ ] **Step 1: Add `publish_vercel_event` to chat_queue_service.py**

Add after the existing `publish_sse_event` function (line 413):

```python
def publish_vercel_event(session_id: str, vercel_line: str):
    """
    通过 Redis pub/sub 推送 Vercel Data Stream 协议行

    与 publish_sse_event 不同，此方法直接推送 Vercel 协议格式字符串
    （如 0:"chunk"\\n 或 data:[{"type":"thinking",...}]\\n），
    而非 SSE 事件字典。queue_event_generator 直接透传这些行。
    """
    r = get_redis()
    r.publish(stream_key(session_id), vercel_line)
    log.debug(f"Vercel 事件已推送: session_id={session_id}, line_prefix={vercel_line[:50]}")
```

- [ ] **Step 2: Modify chat_queue_task.py to use VercelDataStreamEncoder**

Add import at top:

```python
from app.core.vercel_stream import VercelDataStreamEncoder
```

Replace all `chat_queue_service.publish_sse_event(session_id, event_type, data)` calls with equivalent `chat_queue_service.publish_vercel_event(session_id, encoder.method(...))` calls. Key replacements in `_process_item_with_llm`:

| Old call | New call |
|----------|----------|
| `publish_sse_event(sid, "queue_start", {"queue_item_id": id, "user_message": msg})` | `publish_vercel_event(sid, encoder.from_queue_event("queue_start", {"queue_item_id": id, "user_message": msg}))` |
| `publish_sse_event(sid, "queue_progress", {...})` | `publish_vercel_event(sid, encoder.from_queue_event("queue_progress", {...}))` |
| `publish_sse_event(sid, "thinking", {"type":"thinking","content":c})` | `publish_vercel_event(sid, encoder.from_thinking(c))` |
| `publish_sse_event(sid, "message", {"type":"text","content":c})` | `publish_vercel_event(sid, encoder.text_chunk(c))` |
| `publish_sse_event(sid, "ai_message_id", {"message_id": id})` | `publish_vercel_event(sid, encoder.from_ai_message_id(str(id)))` |
| `publish_sse_event(sid, "ai_message_content", {"content": c})` | `publish_vercel_event(sid, encoder.from_ai_message_content(c))` |
| `publish_sse_event(sid, "billing", {"cost":c,"balance":b})` | `publish_vercel_event(sid, encoder.from_billing(c, b))` |
| `publish_sse_event(sid, "queue_complete", {...})` | `publish_vercel_event(sid, encoder.from_queue_event("queue_complete", {...}))` |
| `publish_sse_event(sid, "queue_error", {...})` | `publish_vercel_event(sid, encoder.from_queue_event("queue_error", {...}))` |
| `publish_sse_event(sid, "queue_done", {})` | `publish_vercel_event(sid, encoder.from_queue_event("queue_done", {}))` |

Also replace the API key check error message:
```python
# Old:
chat_queue_service.publish_sse_event(session_id, "message", {"type": "text", "content": "⚠️ ..."})
# New:
chat_queue_service.publish_vercel_event(session_id, encoder.text_chunk("⚠️ ..."))
```

And the LLM error:
```python
# Old:
chat_queue_service.publish_sse_event(session_id, "message", {"type": "text", "content": err_msg})
# New:
chat_queue_service.publish_vercel_event(session_id, encoder.text_chunk(err_msg))
```

Create the encoder instance at the start of `_process_item_with_llm`:
```python
encoder = VercelDataStreamEncoder()
```

- [ ] **Step 3: Verify import**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.tasks.chat_queue_task import process_chat_queue_item; print('task OK')"`
Expected: `task OK`

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/services/chat_queue_service.py autonome-backend/app/tasks/chat_queue_task.py
git commit -m "refactor: Celery worker publishes Vercel Data Stream events to Redis"
```

---

## Task 4: Frontend — Install Vercel AI SDK and Create BFF Proxy

**Files:**
- Create: `autonome-studio/src/app/api/chat/route.ts`
- Create: `autonome-studio/src/app/api/chat/queue/route.ts`
- Create: `autonome-studio/src/app/api/chat/queue-actions/route.ts`
- Modify: `autonome-studio/package.json`

- [ ] **Step 1: Install Vercel AI SDK**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-studio && pnpm add ai @ai-sdk/openai zod`

- [ ] **Step 2: Create BFF main chat proxy**

Create `autonome-studio/src/app/api/chat/route.ts`:

```typescript
/**
 * BFF 代理：主聊天流
 *
 * 接收前端 useChat 的标准 payload，注入 JWT 和上下文，
 * 转发到 FastAPI 后端，透传 Vercel Data Stream 响应。
 */
import { NextRequest } from 'next/server';

// FastAPI 后端地址（Docker 内部网络或 localhost）
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    // 1. 解析前端 useChat 发送的标准 payload
    const body = await req.json();
    const { messages, data: contextData } = body;

    // 2. 从 cookie 或 Authorization header 提取 JWT
    const authHeader = req.headers.get('authorization');
    const token = authHeader?.replace('Bearer ', '') ||
      req.cookies.get('autonome_access_token')?.value || '';

    // 3. 从 contextData 提取上下文信息
    // useChat 的 body 字段会被合并到请求中
    const projectId = contextData?.projectId || '';
    const sessionId = contextData?.sessionId || null;
    const contextFiles = contextData?.contextFiles || [];
    const skillId = contextData?.skillId || null;
    const images = contextData?.images || [];

    // 4. 提取最新用户消息（useChat 发送完整 messages 数组，取最后一条 user 消息）
    const lastUserMessage = messages
      ?.filter((m: { role: string }) => m.role === 'user')
      ?.pop()?.content || '';

    // 5. 转发至 FastAPI 后端
    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        project_id: projectId,
        message: lastUserMessage,
        context_files: contextFiles,
        session_id: sessionId,
        skill_id: skillId,
        images,
      }),
    });

    // 6. 错误处理
    if (!backendResponse.ok) {
      if (backendResponse.status === 402) {
        // 余额不足：返回 Vercel error 事件
        const errorText = await backendResponse.text();
        return new Response(`3:${JSON.stringify(errorText)}\n`, {
          status: 200, // 返回 200 让 useChat 正常解析
          headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        });
      }
      const errorText = await backendResponse.text();
      return new Response(JSON.stringify({ error: errorText }), {
        status: backendResponse.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 7. 透传 Vercel Data Stream 响应
    return new Response(backendResponse.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
      },
    });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
```

- [ ] **Step 3: Create BFF queue stream proxy**

Create `autonome-studio/src/app/api/chat/queue/route.ts`:

```typescript
/**
 * BFF 代理：队列流
 *
 * 订阅 FastAPI 后端的队列 SSE 流，透传 Vercel Data Stream 事件。
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { sessionId, projectId } = body;

    const authHeader = req.headers.get('authorization');
    const token = authHeader?.replace('Bearer ', '') ||
      req.cookies.get('autonome_access_token')?.value || '';

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/stream/queue`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        session_id: sessionId,
        project_id: projectId,
      }),
    });

    if (!backendResponse.ok) {
      return new Response(await backendResponse.text(), { status: backendResponse.status });
    }

    return new Response(backendResponse.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
      },
    });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
```

- [ ] **Step 4: Create BFF queue actions proxy**

Create `autonome-studio/src/app/api/chat/queue-actions/route.ts`:

```typescript
/**
 * BFF 代理：队列 CRUD 操作
 *
 * 代理队列的 add/status/update/delete/clear/reorder REST API。
 * 通过 URL query 参数指定操作类型。
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { action, sessionId, projectId, ...payload } = body;

    const token = req.cookies.get('autonome_access_token')?.value || '';

    // 根据 action 类型路由到不同的后端端点
    let endpoint = '';
    let method = 'POST';
    let reqBody: unknown = null;

    switch (action) {
      case 'add':
        endpoint = `/api/chat/queue`;
        reqBody = { session_id: sessionId, project_id: projectId, ...payload };
        break;
      case 'status':
        endpoint = `/api/chat/queue/${sessionId}`;
        method = 'GET';
        break;
      case 'update':
        endpoint = `/api/chat/queue/${payload.itemId}`;
        method = 'PATCH';
        reqBody = payload.updates;
        break;
      case 'delete':
        endpoint = `/api/chat/queue/${payload.itemId}`;
        method = 'DELETE';
        break;
      case 'clear':
        endpoint = `/api/chat/queue/session/${sessionId}`;
        method = 'DELETE';
        break;
      case 'reorder':
        endpoint = `/api/chat/queue/reorder`;
        reqBody = { session_id: sessionId, item_ids: payload.itemIds };
        break;
      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };

    const backendResponse = await fetch(`${BACKEND_URL}${endpoint}`, {
      method,
      headers,
      ...(reqBody ? { body: JSON.stringify(reqBody) } : {}),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-studio && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors in the new files (existing errors may exist)

- [ ] **Step 6: Commit**

```bash
git add autonome-studio/package.json autonome-studio/pnpm-lock.yaml autonome-studio/src/app/api/
git commit -m "feat: add Vercel AI SDK + BFF proxy routes for chat, queue stream, and queue actions"
```

---

## Task 5: Frontend — Create useChatSync Bridge Hook

**Files:**
- Create: `autonome-studio/src/hooks/useChatSync.ts`

- [ ] **Step 1: Create the useChatSync hook**

Create `autonome-studio/src/hooks/useChatSync.ts`:

```typescript
/**
 * useChatSync — useChat 状态到 Zustand store 的单向同步桥接
 *
 * 核心原则：useChat 是单一事实来源，Zustand 是全局镜像。
 * 非父子关系的组件（如 Sidebar、TopHeader）通过 Zustand 读取状态，
 * 但永远不直接修改 useChat 管理的状态。
 */
import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import type { Message } from 'ai';

/** 自定义 data 事件类型（从 Vercel data: 行解析） */
interface ChatDataEvent {
  type: string;
  [key: string]: unknown;
}

interface UseChatSyncOptions {
  /** useChat 的 messages 数组 */
  messages: Message[];
  /** useChat 的 isLoading 状态 */
  isLoading: boolean;
  /** useChat 的 data 数组（自定义 data: 事件累积） */
  data?: ChatDataEvent[] | undefined;
}

export function useChatSync({ messages, isLoading, data }: UseChatSyncOptions) {
  const syncFromUseChat = useChatStore(state => state.syncFromUseChat);
  const setThinkingContent = useChatStore(state => state.setThinkingContent);
  const setIsThinking = useChatStore(state => state.setIsThinking);
  const setCurrentSessionId = useChatStore(state => state.setCurrentSessionId);

  // 跟踪已处理的 data 事件索引，避免重复处理
  const lastProcessedDataIndex = useRef(0);

  // 同步 messages 和 isLoading 到 Zustand
  useEffect(() => {
    syncFromUseChat(messages, isLoading);
  }, [messages, isLoading, syncFromUseChat]);

  // 处理自定义 data 事件（thinking, session_info, billing, ai_message_id, ai_message_content）
  useEffect(() => {
    if (!data || data.length === 0) return;

    // 只处理新增的 data 事件
    for (let i = lastProcessedDataIndex.current; i < data.length; i++) {
      const event = data[i];
      if (!event) continue;

      switch (event.type) {
        case 'thinking':
          // 累积思考内容
          const thinkingContent = useChatStore.getState().thinkingContent;
          setThinkingContent(thinkingContent + (event.content as string));
          setIsThinking(true);
          break;

        case 'session_info':
          setCurrentSessionId(event.session_id as string);
          break;

        case 'billing':
          useChatStore.getState().setLastBilling({
            cost: event.cost as number,
            balance: event.balance as number,
          });
          break;

        case 'ai_message_id':
          // 更新最后一条 assistant 消息的 ID
          useChatStore.getState().updateMirroredMessageId(event.message_id as string);
          break;

        case 'ai_message_content':
          // 后端发送的最终内容，可用于修正显示
          break;

        // 队列事件由 useChatQueue 单独处理
        case 'queue_start':
        case 'queue_progress':
        case 'queue_complete':
        case 'queue_error':
        case 'queue_done':
          break;
      }
    }

    lastProcessedDataIndex.current = data.length;
  }, [data, setThinkingContent, setIsThinking, setCurrentSessionId]);

  // 当 isLoading 变为 false 时，结束思考状态
  useEffect(() => {
    if (!isLoading) {
      setIsThinking(false);
    }
  }, [isLoading, setIsThinking]);
}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/hooks/useChatSync.ts
git commit -m "feat: add useChatSync bridge hook for useChat → Zustand state sync"
```

---

## Task 6: Frontend — Slim Down useChatStore

**Files:**
- Modify: `autonome-studio/src/store/useChatStore.ts`

- [ ] **Step 1: Remove streaming state fields and add mirror sync actions**

Key changes to `useChatStore.ts`:

1. **Remove** from `ChatState` interface and implementation:
   - `streamingMessageId`, `streamingContent`, `streamingContentVersion`, `committedContentVersion`
   - `setStreamingMessageId`, `appendStreamingContent`, `setStreamingContent`, `commitStreamingContent`, `clearStreamingContent`, `getCurrentStreamingContent`
   - `isTyping`, `setIsTyping` (replaced by `mirroredIsTyping` synced from useChat)
   - `addMessage`, `appendLastMessage`, `updateMessage`, `updateLastMessageId`, `deleteMessagesAfter`

2. **Add** to `ChatState` interface:
   ```typescript
   /** 从 useChat 同步的消息镜像（供非父子组件读取） */
   mirroredMessages: Message[];
   /** 从 useChat 同步的 typing 状态 */
   mirroredIsTyping: boolean;
   /** 最后一次计费信息 */
   lastBilling: { cost: number; balance: number } | null;
   /** 同步动作：从 useChat 推送状态 */
   syncFromUseChat: (messages: Message[], isLoading: boolean) => void;
   /** 更新镜像消息中最后一条 assistant 消息的 ID */
   updateMirroredMessageId: (newId: string) => void;
   /** 设置计费信息 */
   setLastBilling: (billing: { cost: number; balance: number } | null) => void;
   ```

3. **Add** implementation:
   ```typescript
   mirroredMessages: [initialMessage],
   mirroredIsTyping: false,
   lastBilling: null,
   syncFromUseChat: (messages: Message[], isLoading: boolean) =>
     set({ mirroredMessages: messages, mirroredIsTyping: isLoading }),
   updateMirroredMessageId: (newId: string) =>
     set((state) => {
       const newMessages = [...state.mirroredMessages];
       const lastAssistantIndex = newMessages.map(m => m.role).lastIndexOf('assistant');
       if (lastAssistantIndex !== -1) {
         newMessages[lastAssistantIndex] = { ...newMessages[lastAssistantIndex], id: newId };
       }
       return { mirroredMessages: newMessages };
     }),
   setLastBilling: (billing) => set({ lastBilling: billing }),
   ```

4. **Keep** `messages` and `setMessages` for session message fetching (used when switching sessions), but mark as "session loading only — not for streaming"

5. **Keep** `thinkingContent`, `isThinking`, `setThinkingContent`, `setIsThinking`
6. **Keep** all queue state (`queueItems`, `isQueueActive`, etc.)
7. **Keep** all search/bookmark/tag state

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-studio && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: Errors will appear in files that reference deleted fields — that's expected, will fix in subsequent tasks

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/store/useChatStore.ts
git commit -m "refactor: slim down useChatStore — remove streaming state, add mirror sync"
```

---

## Task 7: Frontend — Refactor ChatStage to useChat

**Files:**
- Modify: `autonome-studio/src/components/chat/ChatStage.tsx`

- [ ] **Step 1: Rewrite ChatStage to use Vercel AI SDK useChat**

Replace the entire `ChatStage` component. Key changes:

1. Replace `useChatStream` + `useImmediateStream` with `useChat` from `ai/react`
2. Add `useChatSync` bridge
3. Remove all streaming content refs and handlers
4. `handleSend` becomes a wrapper around `useChat.handleSubmit` with context assembly
5. `handleStop` becomes `useChat.stop`
6. Message list reads from `useChat.messages` directly
7. `isTyping` reads from `useChat.isLoading`

```tsx
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowDown, X, Eye, Download, Loader2, Code } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useChat } from 'ai/react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

// 状态管理
import { useChatStore } from "@/store/useChatStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useUIStore } from "@/store/useUIStore";

// Hooks
import { useSmartScroll } from "@/hooks/useSmartScroll";
import { useFilePreview } from "@/hooks/useFilePreview";
import { usePasteUpload } from "@/hooks/usePasteUpload";
import { useChatEventListeners } from "@/hooks/useChatEventListeners";
import { useChatSync } from "@/hooks/useChatSync";

// 子组件
import { ChatInputBox } from "./ChatInputBox";
import { QueueIndicator } from "./QueueIndicator";
import { MemoizedMessageItem } from "./MemoizedMessageItem";
import { VirtualizedMessageList } from "./VirtualizedMessageList";
import { TablePreview, AttachmentPicker } from "./components";
import { BASE_URL, getToken } from "@/lib/api";

export function ChatStage() {
  // ==========================================
  // 状态订阅
  // ==========================================
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setCurrentSessionId = useWorkspaceStore(state => state.setCurrentSessionId);
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  const setPendingChatAttachments = useWorkspaceStore(state => state.setPendingChatAttachments);
  const openSkillCenter = useUIStore(state => state.openSkillCenter);
  const setSkillFilterMode = useUIStore(state => state.setSkillFilterMode);

  // ==========================================
  // 核心：Vercel AI SDK useChat
  // ==========================================
  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    stop,
    data,
    setMessages,
    append,
  } = useChat({
    api: '/api/chat',
    body: {
      projectId: currentProjectId,
      sessionId: currentSessionId,
      contextFiles: pendingChatAttachments,
    },
    onError: (error) => {
      console.error('Chat stream error:', error);
    },
  });

  // ==========================================
  // useChat → Zustand 同步
  // ==========================================
  useChatSync({ messages, isLoading, data });

  // 从 Zustand 读取思考状态（由 useChatSync 维护）
  const thinkingContent = useChatStore(state => state.thinkingContent);
  const isThinking = useChatStore(state => state.isThinking);

  // ==========================================
  // Refs
  // ==========================================
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // 本地 UI 状态
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);
  const [isAttachmentPickerOpen, setIsAttachmentPickerOpen] = useState(false);
  const [isCodeImportOpen, setIsCodeImportOpen] = useState(false);
  const [importedCode, setImportedCode] = useState("");

  // ==========================================
  // 智能滚动 Hook
  // ==========================================
  const { isAtBottom, isPaused, isAtBottomRef, isPausedRef, scrollToBottom, resumeAutoScroll } =
    useSmartScroll(scrollContainerRef, {
      bottomThreshold: 150,
      smoothScroll: true,
      scrollDuration: 100,
    });

  // ==========================================
  // 文件预览 + 粘贴上传 Hooks
  // ==========================================
  const { previewData, previewType, previewContent, previewLanguage, isPreviewLoading,
    handlePreviewAsset, handleDownloadAsset, closePreview } = useFilePreview();
  const { pastedAttachments, handlePaste, cleanupPastedAttachments } = usePasteUpload();

  // ==========================================
  // 事件监听器
  // ==========================================
  useChatEventListeners({ messagesEndRef });

  // ==========================================
  // 自动滚动
  // ==========================================
  useEffect(() => {
    if (messages.length > 0 && isAtBottomRef.current && !isPausedRef.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [messages.length, scrollToBottom, isAtBottomRef, isPausedRef]);

  // ==========================================
  // Session 切换时加载消息
  // ==========================================
  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) { setMessages([]); return; }
      const token = getToken();
      try {
        const res = await fetch(`${BASE_URL}/api/chat/sessions/${currentSessionId}/messages`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.data && data.data.length > 0) {
          setMessages(data.data.map((msg: { role: string; content: string; id: number; attachments?: unknown }) => ({
            id: String(msg.id),
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
          })));
        } else {
          setMessages([]);
        }
      } catch (e) {
        console.error('Failed to fetch messages:', e);
        setMessages([]);
      }
    };
    fetchMessages();
  }, [currentSessionId, setMessages]);

  // ==========================================
  // 发送消息包装
  // ==========================================
  const handleOpenBasicAnalysis = useCallback(() => {
    setSkillFilterMode('basic');
    openSkillCenter();
  }, [setSkillFilterMode, openSkillCenter]);

  // useChat 的 handleSubmit 需要一个 form event，我们包装一层
  const handleSendWrapper = useCallback((messageText: string) => {
    // 使用 append 直接发送消息（绕过 form submit）
    append({
      role: 'user',
      content: messageText,
    });
    cleanupPastedAttachments();
  }, [append, cleanupPastedAttachments]);

  // ==========================================
  // 渲染
  // ==========================================
  const isChatEmpty = messages.length === 0;

  // ... (保留现有渲染逻辑，但将 isTyping 替换为 isLoading，
  //      streamingContent 替换为直接读取 messages，
  //      handleStop 替换为 stop)
  // 注意：完整的 JSX 渲染部分与现有代码基本相同，
  // 只需要替换变量引用即可。此处省略重复的 JSX。
}
```

The rendering JSX stays largely the same. Key substitutions in the JSX:
- `isTyping` → `isLoading`
- `handleStop` → `stop`
- `streamingContent` → removed (MemoizedMessageItem reads from `messages` directly)
- `handleSend` → `handleSendWrapper`
- Remove `useImmediateStream` / `useChatStream` / `useMessageActions` hook compositions
- Remove `handleTypewriterUpdate`, `appendStream`, `resetStream`, `getCurrentContent`

- [ ] **Step 2: Verify component compiles**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-studio && npx tsc --noEmit --pretty 2>&1 | grep -i "ChatStage" | head -10`
Expected: No ChatStage-specific errors

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/components/chat/ChatStage.tsx
git commit -m "refactor: ChatStage uses Vercel AI SDK useChat + useChatSync"
```

---

## Task 8: Frontend — Refactor ChatInputBox

**Files:**
- Modify: `autonome-studio/src/components/chat/ChatInputBox.tsx`

- [ ] **Step 1: Update ChatInputBox props and bind to useChat**

The `ChatInputBox` currently manages its own `inputValue` state. With `useChat`, we have two options:

**Option: Keep local inputValue (recommended for performance)** — Keystrokes only re-render ChatInputBox, not the parent. On send, pass the value to parent which calls `append()`.

This means **no changes to ChatInputBox internals**. The `onSend` / `onStop` / `isTyping` props remain the same. The parent (ChatStage) passes `isLoading` as `isTyping` and `stop` as `onStop`.

The only change is ensuring the prop interface matches what ChatStage now provides:
- `onSend: (messageText: string) => void` — unchanged
- `onStop: () => void` — unchanged
- `isTyping: boolean` — now receives `isLoading` from useChat

**No code changes needed in ChatInputBox.tsx** — the prop interface is already compatible.

- [ ] **Step 2: Commit (if any changes were needed)**

Only commit if actual changes were made.

---

## Task 9: Frontend — Simplify MemoizedMessageItem

**Files:**
- Modify: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`

- [ ] **Step 1: Remove dual-path streaming logic**

Key changes:
1. Remove `streamingContent` prop — no longer needed
2. For the last assistant message during streaming, read `msg.content` directly (useChat auto-appends)
3. Remove `isTyping` prop — parent passes `isLoading` from useChat
4. The `isLast && isTyping` check that switches between `streamingContent` and `msg.content` is no longer needed

The component reads `msg.content` in all cases. During streaming, `useChat` updates `msg.content` in real-time.

- [ ] **Step 2: Update VirtualizedMessageList props accordingly**

Remove `streamingContent` prop from `VirtualizedMessageList`. Pass `isLoading` (from useChat) instead of `isTyping`.

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/components/chat/MemoizedMessageItem.tsx autonome-studio/src/components/chat/VirtualizedMessageList.tsx
git commit -m "refactor: remove dual-path streaming logic from MemoizedMessageItem"
```

---

## Task 10: Frontend — Simplify StreamingMarkdown

**Files:**
- Modify: `autonome-studio/src/components/chat/StreamingMarkdown.tsx`

- [ ] **Step 1: Remove typewriter cursor and simplify isStreaming**

Key changes:
1. Remove the animated streaming cursor (SDK built-in streaming provides visual feedback via content updates)
2. Simplify `isStreaming` prop — during streaming, content is already partial and being updated by useChat
3. Keep thinking box, unclosed structure handling, interactive plot placeholders
4. Keep performance optimization (plain text path when no code blocks)

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/components/chat/StreamingMarkdown.tsx
git commit -m "refactor: simplify StreamingMarkdown — remove typewriter cursor"
```

---

## Task 11: Frontend — Create useChatQueue Hook

**Files:**
- Create: `autonome-studio/src/hooks/useChatQueue.ts`

- [ ] **Step 1: Create the useChatQueue hook**

```typescript
/**
 * useChatQueue — 消息队列管理 Hook
 *
 * 当 AI 正在流式输出时，新消息进入后端队列。
 * 此 Hook 管理队列状态和 SSE 流连接。
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { useChatStore } from '@/store/useChatStore';

interface UseChatQueueOptions {
  /** 当前会话 ID */
  sessionId: string | null;
  /** 当前项目 ID */
  projectId: string | null;
  /** useChat 的 isLoading 状态 */
  isLoading: boolean;
}

export function useChatQueue({ sessionId, projectId, isLoading }: UseChatQueueOptions) {
  const queueItems = useChatStore(state => state.queueItems);
  const isQueueActive = useChatStore(state => state.isQueueActive);
  const addQueueItem = useChatStore(state => state.addQueueItem);
  const updateQueueItemStatus = useChatStore(state => state.updateQueueItemStatus);
  const removeQueueItem = useChatStore(state => state.removeQueueItem);
  const clearQueueItems = useChatStore(state => state.clearQueueItems);
  const setIsQueueActive = useChatStore(state => state.setIsQueueActive);

  const [isQueueStreaming, setIsQueueStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 添加消息到队列
  const addToQueue = useCallback(async (message: string, contextFiles?: string[]) => {
    if (!sessionId || !projectId) return;

    try {
      const res = await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'add',
          sessionId,
          projectId,
          message,
          context_files: contextFiles,
        }),
      });
      const data = await res.json();
      if (data.data) {
        addQueueItem({
          id: String(data.data.id),
          session_id: sessionId,
          project_id: projectId,
          status: 'pending',
          message,
          position: queueItems.length + 1,
          created_at: new Date().toISOString(),
        });
      }
    } catch (e) {
      console.error('Failed to add to queue:', e);
    }
  }, [sessionId, projectId, addQueueItem, queueItems.length]);

  // 从队列移除
  const removeFromQueue = useCallback(async (itemId: string) => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', sessionId, itemId }),
      });
      removeQueueItem(itemId);
    } catch (e) {
      console.error('Failed to remove from queue:', e);
    }
  }, [sessionId, removeQueueItem]);

  // 清空队列
  const clearQueue = useCallback(async () => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'clear', sessionId }),
      });
      clearQueueItems();
    } catch (e) {
      console.error('Failed to clear queue:', e);
    }
  }, [sessionId, clearQueueItems]);

  // 重排队列
  const reorderQueue = useCallback(async (itemIds: string[]) => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reorder', sessionId, itemIds }),
      });
    } catch (e) {
      console.error('Failed to reorder queue:', e);
    }
  }, [sessionId]);

  return {
    queueItems,
    isQueueActive,
    isQueueStreaming,
    addToQueue,
    removeFromQueue,
    clearQueue,
    reorderQueue,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/hooks/useChatQueue.ts
git commit -m "feat: add useChatQueue hook for message queue management"
```

---

## Task 12: Frontend — Generative UI Components

**Files:**
- Create: `autonome-studio/src/components/chat/InteractivePlotCard/index.tsx`
- Create: `autonome-studio/src/components/chat/ExecutionResultCard/index.tsx`
- Create: `autonome-studio/src/components/chat/DataPreviewCard/index.tsx`
- Create: `autonome-studio/src/components/chat/SkillDraftCard/index.tsx`

- [ ] **Step 1: Create InteractivePlotCard**

```tsx
"use client";

import { BarChart2, Download, Maximize2, FileText, CheckCircle2 } from 'lucide-react';

interface PlotData {
  plot_id: string;
  title: string;
  description?: string;
  preview_url: string;
  pdf_url: string;
  png_url: string;
  tsv_url: string;
}

export default function InteractivePlotCard({ data }: { data: PlotData }) {
  return (
    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl overflow-hidden shadow-sm my-3">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-emerald-500" />
          <h3 className="font-medium text-sm text-slate-800 dark:text-slate-200">{data.title}</h3>
        </div>
        <button className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* 图像预览 */}
      <div className="p-4 bg-slate-100 dark:bg-slate-900/50 flex justify-center">
        <img src={data.preview_url} alt={data.title}
          className="max-h-[300px] object-contain rounded border border-slate-200 dark:border-slate-800 shadow-sm" />
      </div>

      {/* 下载区 */}
      <div className="p-4">
        {data.description && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">{data.description}</p>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <a href={data.pdf_url} target="_blank" rel="noreferrer"
            className="flex items-center justify-center gap-1 py-1.5 bg-slate-100 dark:bg-slate-700 text-xs font-medium rounded hover:bg-slate-200 transition-colors">
            <Download className="w-3 h-3" /> PDF
          </a>
          <a href={data.png_url} target="_blank" rel="noreferrer"
            className="flex items-center justify-center gap-1 py-1.5 bg-slate-100 dark:bg-slate-700 text-xs font-medium rounded hover:bg-slate-200 transition-colors">
            <Download className="w-3 h-3" /> PNG
          </a>
          <a href={data.tsv_url} target="_blank" rel="noreferrer"
            className="flex items-center justify-center gap-1 py-1.5 bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400 text-xs font-medium rounded border border-blue-200 dark:border-blue-800/50 hover:bg-blue-100 transition-colors">
            <FileText className="w-3 h-3" /> TSV
          </a>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ExecutionResultCard**

```tsx
"use client";

import { Play, Code, Loader2 } from 'lucide-react';
import { useState } from 'react';

interface ExecutionResultProps {
  code: string;
  language: 'python' | 'r';
}

export default function ExecutionResultCard({ code, language }: ExecutionResultProps) {
  const [isExecuting, setIsExecuting] = useState(false);

  return (
    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl overflow-hidden shadow-sm my-3">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          <Code className="w-4 h-4 text-blue-500" />
          <h3 className="font-medium text-sm text-slate-800 dark:text-slate-200">
            {language === 'python' ? 'Python' : 'R'} 代码执行
          </h3>
        </div>
        <button
          onClick={() => setIsExecuting(true)}
          disabled={isExecuting}
          className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:bg-slate-400 transition-colors"
        >
          {isExecuting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          {isExecuting ? '执行中...' : '在沙箱中执行'}
        </button>
      </div>
      <div className="p-4 bg-slate-900 overflow-x-auto">
        <pre className="text-sm text-slate-200 font-mono whitespace-pre-wrap">{code}</pre>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create DataPreviewCard**

```tsx
"use client";

import { Table } from 'lucide-react';

interface DataPreviewProps {
  file_path: string;
  rows: number;
  columns: string[];
}

export default function DataPreviewCard({ file_path, rows, columns }: DataPreviewProps) {
  return (
    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl overflow-hidden shadow-sm my-3">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <Table className="w-4 h-4 text-emerald-500" />
        <h3 className="font-medium text-sm text-slate-800 dark:text-slate-200">
          数据预览: {file_path.split('/').pop()}
        </h3>
        <span className="text-xs text-slate-500 ml-auto">{rows} 行 × {columns.length} 列</span>
      </div>
      <div className="p-4 overflow-x-auto">
        <div className="flex gap-2 flex-wrap">
          {columns.slice(0, 10).map((col, i) => (
            <span key={i} className="px-2 py-1 bg-slate-100 dark:bg-slate-700 text-xs rounded text-slate-600 dark:text-slate-300">
              {col}
            </span>
          ))}
          {columns.length > 10 && (
            <span className="px-2 py-1 text-xs text-slate-400">+{columns.length - 10} more</span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create SkillDraftCard**

```tsx
"use client";

import { Wrench, Play, Save } from 'lucide-react';

interface SkillDraftProps {
  draft_id: string;
  skill_name: string;
  code: string;
}

export default function SkillDraftCard({ draft_id, skill_name, code }: SkillDraftProps) {
  return (
    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl overflow-hidden shadow-sm my-3">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          <Wrench className="w-4 h-4 text-purple-500" />
          <h3 className="font-medium text-sm text-slate-800 dark:text-slate-200">{skill_name}</h3>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 transition-colors">
            <Play className="w-3 h-3" /> 测试
          </button>
          <button className="flex items-center gap-1 px-2 py-1 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700 transition-colors">
            <Save className="w-3 h-3" /> 发布
          </button>
        </div>
      </div>
      <div className="p-4 bg-slate-900 overflow-x-auto max-h-[200px] overflow-y-auto">
        <pre className="text-sm text-slate-200 font-mono whitespace-pre-wrap">{code}</pre>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add autonome-studio/src/components/chat/InteractivePlotCard/ autonome-studio/src/components/chat/ExecutionResultCard/ autonome-studio/src/components/chat/DataPreviewCard/ autonome-studio/src/components/chat/SkillDraftCard/
git commit -m "feat: add Generative UI components — InteractivePlotCard, ExecutionResultCard, DataPreviewCard, SkillDraftCard"
```

---

## Task 13: Frontend — Delete Old Hooks and Cleanup

**Files:**
- Delete: `autonome-studio/src/hooks/useImmediateStream.ts`
- Delete: `autonome-studio/src/hooks/useChatStream.ts`
- Modify: `autonome-studio/src/hooks/useChat.ts` (remove re-exports of deleted hooks)
- Modify: `autonome-studio/src/hooks/useMessageActions.ts` (simplify)
- Modify: `autonome-studio/package.json` (remove `@microsoft/fetch-event-source`)

- [ ] **Step 1: Delete useImmediateStream.ts**

Run: `rm autonome-studio/src/hooks/useImmediateStream.ts`

- [ ] **Step 2: Delete useChatStream.ts**

Run: `rm autonome-studio/src/hooks/useChatStream.ts`

- [ ] **Step 3: Update useChat.ts barrel file**

Remove re-exports of `useChatStream` and `useImmediateStream`. Keep other exports.

- [ ] **Step 4: Simplify useMessageActions.ts**

Remove `handleInterpret` (replaced by `useChat.append`). Simplify `handleRetry` and `handleEditResend` to work with `useChat.setMessages` instead of store methods. Remove dependencies on deleted store fields (`streamingMessageId`, `streamingContent`, etc.).

- [ ] **Step 5: Remove @microsoft/fetch-event-source from package.json**

Run: `cd autonome-studio && pnpm remove @microsoft/fetch-event-source`

- [ ] **Step 6: Verify build**

Run: `cd autonome-studio && pnpm build 2>&1 | tail -20`
Expected: Build succeeds (or only has pre-existing warnings)

- [ ] **Step 7: Commit**

```bash
git add -A autonome-studio/src/hooks/ autonome-studio/package.json autonome-studio/pnpm-lock.yaml
git commit -m "refactor: delete useImmediateStream and useChatStream, remove fetch-event-source"
```

---

## Task 14: Integration Test — End-to-End Streaming

**Files:** None (manual verification)

- [ ] **Step 1: Restart Docker services**

Run: `cd /opt/data1/public/software/systools/autonome && docker-compose down && docker-compose up -d`

- [ ] **Step 2: Verify backend health**

Run: `curl -s http://localhost:8000/docs | head -5`
Expected: HTML response (FastAPI docs page)

- [ ] **Step 3: Verify frontend health**

Run: `curl -s http://localhost:3001 | head -5`
Expected: HTML response (Next.js page)

- [ ] **Step 4: Test chat stream via BFF**

Run: `curl -s -X POST http://localhost:3001/api/chat -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"hello"}],"data":{"projectId":"test","sessionId":null}}' | head -20`
Expected: Vercel Data Stream format output (lines starting with `0:`, `data:`, `e:`)

- [ ] **Step 5: Test in browser**

Open http://localhost:3001, log in, send a message in chat. Verify:
- Streaming text appears character by character
- Thinking box shows and collapses
- Stop button works
- Session ID updates in sidebar

- [ ] **Step 6: Commit verification status**

If all tests pass, proceed to auto_deploy. If issues found, fix and re-test.

---

## Task 15: Deploy

**Files:** None

- [ ] **Step 1: Run auto_deploy**

Run: `cd /opt/data1/public/software/systools/autonome && ./auto_deploy.sh -s "feat: Vercel AI SDK full refactor — useChat + BFF + Generative UI" -d "重构前端流式架构：用 Vercel AI SDK useChat 替换自定义 useChatStream + useImmediateStream，建立 Next.js BFF 代理层，后端输出 Vercel Data Stream Protocol，Zustand 瘦身为全局镜像，新增 Generative UI 组件（InteractivePlotCard/ExecutionResultCard/DataPreviewCard/SkillDraftCard），删除 @microsoft/fetch-event-source 依赖。"`
