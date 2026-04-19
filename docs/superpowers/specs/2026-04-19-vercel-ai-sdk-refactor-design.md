# Vercel AI SDK Full Refactor Design

> Date: 2026-04-19
> Status: Approved
> Scope: Frontend streaming + state management + BFF proxy + Generative UI + Backend protocol adaptation

---

## 1. Overview

Replace the custom streaming architecture (`useChatStream` + `useImmediateStream` + `@microsoft/fetch-event-source`) with Vercel AI SDK's `useChat` hook and Data Stream Protocol. This is a full-stack refactor covering backend protocol adaptation, Next.js BFF proxy layer, frontend state management simplification, and Generative UI introduction.

### Goals

1. **Simplify streaming code**: Replace ~800 lines of custom SSE parsing with Vercel AI SDK's built-in streaming
2. **Generative UI**: Enable Tool Calling so the AI can render interactive React components inline
3. **Unified state management**: `useChat` as single source of truth, Zustand as global mirror
4. **BFF proxy**: Next.js API Routes as proxy layer for JWT injection, context assembly, and protocol handling
5. **Backend protocol alignment**: FastAPI outputs Vercel Data Stream Protocol natively

### Non-Goals

- Rewriting the Celery/Redis queue core logic
- Changing the LangGraph agent orchestration
- Replacing `StreamingMarkdown` rendering (simplify, not replace)
- Modifying `StreamContentFilter` (protocol-agnostic, keep as-is)

---

## 2. Backend Protocol Adaptation

### 2.1 Vercel Data Stream Protocol

Vercel AI SDK uses a line-delimited protocol where each line is `type:json\n`:

| Type | Format | Purpose |
|------|--------|---------|
| `0` | `0:"text chunk"\n` | Text streaming |
| `9` | `9:{tool_call}\n` | Tool call invocation |
| `b` | `b:{tool_result}\n` | Tool result |
| `e` | `e:{finish_reason,usage}\n` | Stream finish + token usage |
| `data:` | `data:[{...}]\n` | Custom data events (for non-standard payloads) |

### 2.2 Event Mapping

| Existing SSE Event | Vercel Mapping | Notes |
|---|---|---|
| `message` (text chunk) | `0:"chunk"\n` | Standard text stream |
| `thinking` | `data:[{"type":"thinking","content":"..."}]\n` | Custom data event |
| `session_info` | `data:[{"type":"session_info","session_id":"...","is_new":bool}]\n` | Custom data event |
| `billing` | `data:[{"type":"billing","cost":N,"balance":N}]\n` | Custom data event |
| `ai_message_id` | `data:[{"type":"ai_message_id","message_id":"..."}]\n` | Custom data event |
| `ai_message_content` | `data:[{"type":"ai_message_content","content":"..."}]\n` + `e:` finish event | Backend sends final cleaned content as data event, then finish event. Frontend uses data event to update message in store. |
| `done` | `e:{"finishReason":"stop","usage":{...}}\n` | Standard finish |
| `queue_start` | `data:[{"type":"queue_start",...}]\n` | Custom data event |
| `queue_progress` | `data:[{"type":"queue_progress",...}]\n` | Custom data event |
| `queue_complete` | `data:[{"type":"queue_complete",...}]\n` | Custom data event |
| `queue_error` | `data:[{"type":"queue_error",...}]\n` | Custom data event |
| `queue_done` | `data:[{"type":"queue_done"}]\n` | Custom data event |

### 2.3 New Backend Files

**`app/core/vercel_stream.py`** — Vercel Data Stream encoder:

```python
class VercelDataStreamEncoder:
    """Encodes events into Vercel AI SDK Data Stream Protocol format."""

    def text_chunk(self, content: str) -> str:
        """Type 0: Text chunk"""
        return f"0:{json.dumps(content)}\n"

    def data_event(self, data: dict) -> str:
        """Custom data event"""
        return f"data:{json.dumps([data])}\n"

    def finish(self, reason: str = "stop", usage: dict | None = None) -> str:
        """Type e: Stream finish"""
        payload = {"finishReason": reason}
        if usage:
            payload["usage"] = usage
        return f"e:{json.dumps(payload)}\n"

    def error(self, message: str) -> str:
        """Type 3: Error"""
        return f"3:{json.dumps(message)}\n"
```

### 2.4 Modified Backend Files

| File | Change |
|------|--------|
| `app/api/routes/chat.py` | `event_generator()` uses `VercelDataStreamEncoder` instead of raw SSE events |
| `app/tasks/chat_queue_task.py` | `publish_sse_event()` publishes Vercel-format events to Redis |
| `app/api/routes/chat.py` | `queue_event_generator()` parses Vercel-format events from Redis |

### 2.5 Unchanged Backend Components

- `StreamContentFilter` — Protocol-agnostic, continues to handle thinking tag splitting
- Celery task routing, Redis lock, queue logic — No changes
- LangGraph agent system — No changes
- Skill matching, intent classification — No changes

---

## 3. Next.js BFF Proxy Layer

### 3.1 Architecture

```
Frontend useChat ──POST──> /api/chat (Next.js) ──POST──> FastAPI /api/chat/stream
                               │                              │
                         JWT injection                   Vercel Data Stream
                         Context assembly                 (already converted)
                         Queue routing
                               │                              │
                               └─────── Stream forward ◄──────┘
```

### 3.2 API Routes

**`src/app/api/chat/route.ts`** — Main chat proxy:

- Receives `useChat` standard payload (messages + body)
- Extracts JWT from httpOnly cookie
- Assembles FastAPI request body: `{ project_id, message, context_files, session_id, skill_id, images }`
- Forwards to FastAPI `/api/chat/stream`
- Transparently proxies Vercel Data Stream response
- Error handling: 402 → error event, 422 → 400, network → retry

**`src/app/api/chat/queue/route.ts`** — Queue stream proxy:

- Forwards to FastAPI `/api/chat/stream/queue`
- Proxies queue SSE events (already in Vercel format from backend)

**`src/app/api/chat/queue-actions/route.ts`** — Queue CRUD proxy:

- Proxies queue operations (add/status/update/delete/clear/reorder)
- REST API passthrough with JWT injection

### 3.3 Key Decisions

- **Node.js runtime** (not Edge): Needs access to FastAPI internal network address
- **JWT from cookie**: BFF reads from httpOnly cookie, more secure than localStorage
- **No Edge Runtime**: Avoid Edge API limitations for streaming proxying

---

## 4. Frontend State Management Refactoring

### 4.1 Core Principle: useChat as Single Source of Truth

Vercel AI SDK's `useChat` provides an `onFinish` callback and exposes `data` array for custom `data:` events. We use `experimental_onToolCall` for Generative UI and process custom data events via `onFinish` and middleware.

```
useChat (component-level)
  ├── messages[]        ──sync──>  useChatStore.mirroredMessages
  ├── isLoading                   useChatStore.isTyping
  ├── error                       useChatStore.lastError
  └── data (custom events)       useChatStore.sessionInfo / billing / thinking
```

Custom data events (thinking, session_info, billing, ai_message_id, ai_message_content) are extracted from the `data` array returned by `useChat` and synced to Zustand via `useChatSync`. The `data` array accumulates all `data:` events from the stream; `useChatSync` processes new entries on each render.

### 4.2 useChatStore Slim-down

**DELETE (taken over by useChat):**
- `streamingMessageId` / `streamingContent` / `streamingContentVersion` / `committedContentVersion`
- `appendStreamingContent` / `setStreamingContent` / `commitStreamingContent` / `clearStreamingContent`
- `isTyping` (synced from `useChat.isLoading`)
- `addMessage` / `appendLastMessage` / `updateMessage` / `updateLastMessageId` / `deleteMessagesAfter`

**KEEP (global state):**
- `mirroredMessages: Message[]` — Message mirror synced from useChat, for non-parent-child components
- `thinkingContent: string` — Thinking process content (extracted from data events)
- `isThinking: boolean` — Whether AI is thinking
- `currentSessionId: string | null` — Current session ID
- `queueItems: ChatQueueItem[]` — Queue state
- `isQueueActive: boolean`
- Bookmarks / tags / search UI state

**ADD:**
- `syncFromUseChat(messages: Message[], isLoading: boolean)` — One-way sync action
- `sessionInfo: { sessionId: string; isNew: boolean } | null`
- `lastBilling: { cost: number; balance: number } | null`

### 4.3 Hooks to Delete

| Hook | Reason |
|------|--------|
| `useImmediateStream` | SDK built-in streaming replaces typewriter effect |
| `useChatStream` | Core logic replaced by `useChat` + BFF; queue logic extracted to `useChatQueue` |
| `useMessageActions.handleInterpret` | Replaced by `useChat.append()` method |

### 4.4 Hooks to Add

| Hook | Purpose |
|------|---------|
| `useChatQueue` | Queue management: SSE stream + CRUD operations |
| `useChatSync` | Bridge hook: syncs useChat state to Zustand store |

### 4.5 Hooks to Keep (with modifications)

| Hook | Modification |
|------|------|
| `useSmartScroll` | No changes |
| `useFilePreview` | No changes |
| `usePasteUpload` | No changes |
| `useChatEventListeners` | Simplify: remove chat-specific events, keep global ones |
| `useMessageActions` | Simplify: `handleRetry` uses `useChat.setMessages`, `handleEditResend` uses `useChat` |

---

## 5. Component Layer Refactoring

### 5.1 ChatStage

**Before:** 7 hooks + complex ref dependency chain
**After:** 3 core hooks + clean data flow

```
ChatStage
  ├── useChat({ api: '/api/chat', onChunk, onFinish, tools })  ← Core
  ├── useChatSync()                                              ← Zustand sync
  ├── useChatQueue()                                             ← Queue management
  ├── useSmartScroll()                                           ← Keep
  ├── useFilePreview()                                           ← Keep
  ├── usePasteUpload()                                           ← Keep
  └── useChatEventListeners()                                    ← Keep (simplified)
```

### 5.2 MemoizedMessageItem Simplification

- No more `streamingContent` vs `msg.content` dual-path logic
- `useChat` messages already contain real-time streaming content
- Streaming messages read `msg.content` directly (SDK auto-appends)

### 5.3 StreamingMarkdown

- **Keep**: Thinking box, unclosed structure handling, interactive plot placeholders
- **Keep**: Performance optimization (plain text path when no code blocks)
- **Remove**: Typewriter cursor (SDK built-in streaming provides visual feedback)
- **Simplify**: Remove `isStreaming` prop complexity — content is always complete from SDK perspective

### 5.4 ChatInputBox

- Bind to `useChat`'s `input` / `handleInputChange` / `handleSubmit`
- Stop button binds to `useChat`'s `stop`
- Keep attachment/skill/code import UI features

### 5.5 QueueIndicator

- Data source changes from `useChatStore.queueItems` to `useChatQueue`
- Component structure and UI remain the same

---

## 6. Generative UI Architecture

### 6.1 Tool Calling Integration

```tsx
const { messages, input, handleSubmit, ... } = useChat({
  api: '/api/chat',
  tools: {
    execute_code: {
      description: 'Execute code in sandbox',
      parameters: z.object({
        code: z.string(),
        language: z.enum(['python', 'r']),
      }),
      generate: async ({ code, language }) => {
        return <ExecutionResultCard code={code} language={language} />
      }
    },
    show_plot: {
      description: 'Display interactive plot',
      parameters: z.object({
        plot_id: z.string(),
        title: z.string(),
        preview_url: z.string(),
        pdf_url: z.string(),
        png_url: z.string(),
        tsv_url: z.string(),
      }),
      generate: async (params) => {
        return <InteractivePlotCard data={params} />
      }
    },
    show_data_preview: {
      description: 'Show data preview table',
      parameters: z.object({
        file_path: z.string(),
        rows: z.number(),
        columns: z.array(z.string()),
      }),
      generate: async (params) => {
        return <DataPreviewCard {...params} />
      }
    },
    show_skill_draft: {
      description: 'Show skill draft card',
      parameters: z.object({
        draft_id: z.string(),
        skill_name: z.string(),
        code: z.string(),
      }),
      generate: async (params) => {
        return <SkillDraftCard {...params} />
      }
    },
  }
})
```

### 6.2 Initial Tool Set

| Tool | Component | Purpose |
|------|-----------|---------|
| `execute_code` | `ExecutionResultCard` | Code execution result with sandbox test button |
| `show_plot` | `InteractivePlotCard` | Interactive plot with PDF/PNG/TSV download |
| `show_data_preview` | `DataPreviewCard` | Data file preview table |
| `show_skill_draft` | `SkillDraftCard` | Skill draft with edit/test/publish actions |

### 6.3 Backend Tool Calling

The backend LangGraph agent needs to output tool calls in Vercel format:

- When agent decides to execute code: emit `9:{tool_call}` event
- When sandbox returns results: emit `b:{tool_result}` event
- The tool call/response cycle is handled by the agent, not the frontend

---

## 7. Queue System Adaptation

### 7.1 Architecture Preservation

The queue system core (Redis pub/sub + Celery worker + ChatQueueItem DB model) remains unchanged.

### 7.2 Frontend Adaptation

**`useChatQueue` hook:**

```typescript
interface UseChatQueueReturn {
  queueItems: ChatQueueItem[]
  isQueueActive: boolean
  addToQueue: (message: string, contextFiles?: string[]) => Promise<void>
  removeFromQueue: (itemId: string) => Promise<void>
  reorderQueue: (itemIds: string[]) => Promise<void>
  clearQueue: () => Promise<void>
}
```

**Queue flow:**
1. When `useChat.isLoading` is true, new messages go to queue via `addToQueue`
2. Queue SSE stream proxied through BFF `/api/chat/queue`
3. Queue events delivered as `data:` custom events in Vercel format
4. On `queue_complete`, AI reply is appended to `useChat.messages` via `append` or `setMessages`

### 7.3 Key Changes

- Extract `_startQueueStream` logic from `useChatStream` into `useChatQueue`
- Adapt queue SSE event parsing to Vercel Data Stream protocol
- On queue completion, merge results via `useChat`'s `append` or `setMessages`

---

## 8. Error Handling

| Scenario | Handling |
|----------|----------|
| FastAPI returns 402 (insufficient credits) | BFF converts to Vercel error event, frontend toast |
| FastAPI returns 422 (validation) | BFF returns 400, `useChat.onError` callback |
| Network disconnect | useChat built-in retry + `onError` callback |
| Mid-stream abort | useChat `stop()` cleans up state |
| Thinking tags split across chunks | Backend `StreamContentFilter` handles (unchanged) |
| Queue item failure | `queue_error` data event → toast + queue status update |

---

## 9. Migration Phases

Each phase is independently verifiable. No phase depends on a later phase to function.

### Phase 1: Backend Protocol Adapter + BFF Proxy

**Goal:** Basic streaming works end-to-end with Vercel protocol

- Create `app/core/vercel_stream.py` encoder
- Modify `app/api/routes/chat.py` to use encoder
- Modify `app/tasks/chat_queue_task.py` to publish Vercel-format events
- Create `src/app/api/chat/route.ts` BFF proxy
- Verify: curl to BFF returns Vercel Data Stream format

### Phase 2: Frontend useChat Replacement + Zustand Slim-down

**Goal:** Core chat functionality parity with new architecture

- Install `ai` package
- Create `useChatSync` hook
- Refactor `ChatStage` to use `useChat`
- Slim down `useChatStore`
- Refactor `ChatInputBox` to bind to `useChat`
- Simplify `MemoizedMessageItem` (remove dual-path logic)
- Delete `useImmediateStream`
- Delete old `useChatStream`
- Verify: Send message, receive streaming response, thinking box works

### Phase 3: Queue System Adaptation

**Goal:** Queue functionality parity

- Create `useChatQueue` hook
- Create BFF queue proxy routes
- Adapt `QueueIndicator` to new data source
- Delete queue logic from old `useChatStream`
- Verify: Queue messages while AI is busy, process queue items

### Phase 4: Generative UI + Tool Calling

**Goal:** New capability — AI renders interactive components

- Configure `tools` in `useChat`
- Implement `ExecutionResultCard` as Generative UI component
- Implement `InteractivePlotCard` as Generative UI component
- Implement `DataPreviewCard` as Generative UI component
- Implement `SkillDraftCard` as Generative UI component
- Backend: Agent outputs tool calls in Vercel format
- Verify: AI triggers tool calls, interactive components render inline

### Phase 5: Cleanup

**Goal:** Remove all deprecated code

- Delete `useImmediateStream.ts`
- Delete old `useChatStream.ts`
- Remove `@microsoft/fetch-event-source` dependency
- Remove unused Zustand store fields
- Clean up SSE adapter if no longer needed
- Verify: Full regression test

---

## 10. Files Changed Summary

### New Files

| File | Purpose |
|------|---------|
| `autonome-backend/app/core/vercel_stream.py` | Vercel Data Stream encoder |
| `autonome-studio/src/app/api/chat/route.ts` | BFF main chat proxy |
| `autonome-studio/src/app/api/chat/queue/route.ts` | BFF queue stream proxy |
| `autonome-studio/src/app/api/chat/queue-actions/route.ts` | BFF queue CRUD proxy |
| `autonome-studio/src/hooks/useChatSync.ts` | useChat → Zustand sync bridge |
| `autonome-studio/src/hooks/useChatQueue.ts` | Queue management hook |
| `autonome-studio/src/components/chat/InteractivePlotCard/index.tsx` | Generative UI plot card |
| `autonome-studio/src/components/chat/ExecutionResultCard/index.tsx` | Generative UI execution card |
| `autonome-studio/src/components/chat/DataPreviewCard/index.tsx` | Generative UI data preview |
| `autonome-studio/src/components/chat/SkillDraftCard/index.tsx` | Generative UI skill draft |

### Modified Files

| File | Change |
|------|--------|
| `autonome-backend/app/api/routes/chat.py` | Use VercelDataStreamEncoder |
| `autonome-backend/app/tasks/chat_queue_task.py` | Publish Vercel-format events |
| `autonome-studio/src/store/useChatStore.ts` | Slim down: remove streaming state, add sync actions |
| `autonome-studio/src/components/chat/ChatStage.tsx` | Refactor to useChat + useChatSync + useChatQueue |
| `autonome-studio/src/components/chat/ChatInputBox.tsx` | Bind to useChat state |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | Simplify: remove dual-path logic |
| `autonome-studio/src/components/chat/StreamingMarkdown.tsx` | Simplify: remove typewriter cursor |
| `autonome-studio/src/components/chat/QueueIndicator.tsx` | Data source change |
| `autonome-studio/src/hooks/useMessageActions.ts` | Simplify: use useChat methods |
| `autonome-studio/src/hooks/useChatEventListeners.ts` | Simplify |
| `autonome-studio/package.json` | Add `ai`, remove `@microsoft/fetch-event-source` |

### Deleted Files

| File | Reason |
|------|--------|
| `autonome-studio/src/hooks/useImmediateStream.ts` | Replaced by SDK built-in streaming |
| `autonome-studio/src/hooks/useChatStream.ts` | Replaced by useChat + BFF |

---

## 11. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Vercel Data Stream protocol version mismatch | Pin `ai` package version, test protocol compatibility |
| Thinking content lost in protocol conversion | Custom `data:` events preserve thinking; test with DeepSeek R1 |
| Queue system regression | Phase 3 dedicated to queue; keep old queue API as fallback during migration |
| Generative UI SSR issues | Use `'use client'` directives; test with Next.js SSR |
| Zustand sync race conditions | `useChatSync` uses `useEffect` with stable references; test concurrent updates |
| BFF proxy latency | Measure end-to-end latency before/after; BFF adds ~5ms overhead |
