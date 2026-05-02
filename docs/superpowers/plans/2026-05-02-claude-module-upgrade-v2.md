# Claude Code Agent 模式 V2 升级 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Claude Agent 模式 3 个致命缺陷 + 2 个功能空缺 + 4 个架构问题，恢复端到端可用性并提升代码可维护性。

**Architecture:** 分两阶段 — Stage 1 聚焦致命修复（SSE 流、DB Schema、容器分配、Celery 集成、API 格式），Stage 2 聚焦重构（组件拆分、对话管理 UI、事件解析、类型安全）。前后端独立可测，每阶段独立可验收。

**Tech Stack:** Python 3.11 / FastAPI / SQLModel / Redis pub-sub / TypeScript / React / Zustand / SSE

---

## File Structure

```
autonome-backend/
├── app/
│   ├── api/routes/claude.py              # MODIFY: 1.2 DB, 1.4 Celery, 1.5 API format, 2.2 conversations list
│   ├── services/
│   │   ├── claude_redis_bridge.py        # MODIFY: 1.3 add publish_allocation()
│   │   ├── claude_container_pool.py      # MODIFY: 1.3 publish allocation, remove docker exec hack
│   │   └── celery_app.py                 # MODIFY: 1.4 ensure execute_skill_task exists
│   ├── sandbox/agent_service/
│   │   ├── main.py                       # MODIFY: 1.3 broadcast sub + dynamic session switch
│   │   ├── redis_client.py               # MODIFY: 1.3 unsubscribe + subscribe_session methods
│   │   └── event_types.py                # MODIFY: 2.5 confirm camelCase output
│   ├── models/claude.py                  # MODIFY: 1.2 model constraint alignment
│   └── alembic/versions/
│       └── claude_task_nullable.py       # CREATE: 1.2 migration
│
├── tests/
│    ├── test_claude_models.py            # MODIFY: add nullable task test
│    └── test_claude_api.py               # MODIFY: un-skip task tests, add format tests

autonome-studio/src/
├── types/claude.ts                       # MODIFY: 2.4 discriminant union types
├── hooks/useClaudeChat.ts                # MODIFY: 1.1 raw fetch for SSE, 1.5 API format
├── store/useClaudeStore.ts               # MODIFY: add conversations state
├── components/chat/
│   ├── ClaudeChatStage.tsx               # MODIFY: 2.1 split into orchestrator, 1.5 format, 2.3 plan fix
│   ├── ClaudeSessionSidebar.tsx          # CREATE: 2.1 + 2.2 session+conversation sidebar
│   ├── ClaudeMessageList.tsx             # CREATE: 2.1 message timeline + streaming
│   ├── ClaudeInputArea.tsx               # CREATE: 2.1 input + send/cancel buttons
│   ├── ClaudePreview.tsx                 # UNCHANGED
│   ├── ClaudeErrorBoundary.tsx           # UNCHANGED
│   ├── ThinkingBlock.tsx                 # UNCHANGED
│   ├── PlanCard.tsx                      # UNCHANGED
│   ├── TaskCard.tsx                      # UNCHANGED
│   └── ToolUseBlock.tsx                  # UNCHANGED
```

---

## Stage 1: 致命修复 + 核心链路打通

### Task 1.1: SSE 流接收修复（前端）

**Files:**
- Modify: `autonome-studio/src/hooks/useClaudeChat.ts`

- [ ] **Step 1: Write the failing test for SSE fetch**

Create test file at `autonome-studio/src/__tests__/useClaudeChat.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react';
import { useClaudeChat } from '@/hooks/useClaudeChat';

// Mock useClaudeStore
jest.mock('@/store/useClaudeStore', () => ({
  useClaudeStore: () => ({
    activeSessionId: 'test-sid',
    activeConversationId: 'test-cid',
    isStreaming: false,
    streamEvents: [],
    addMessage: jest.fn(),
    appendStreamContent: jest.fn(),
    setStreaming: jest.fn(),
    resetStream: jest.fn(),
    messages: [],
    setMessages: jest.fn(),
  }),
}));

describe('useClaudeChat sendMessage', () => {
  it('uses raw fetch (not fetchAPI) for SSE endpoint to preserve response.body', async () => {
    const mockReader = {
      read: jest.fn()
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('event: session_info\ndata: {"type":"session_info"}\n\n') })
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('event: status\ndata: {"type":"status","status":"idle"}\n\n') })
        .mockResolvedValueOnce({ done: true }),
      cancel: jest.fn(),
    };

    const mockResponse = {
      ok: true,
      body: { getReader: () => mockReader },
    };

    global.fetch = jest.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('test message');
    });

    // Verify raw fetch was called (fetchAPI would have returned .json() — this verifies body.getReader was used)
    expect(global.fetch).toHaveBeenCalled();
    const callUrl = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(callUrl).toContain('/api/claude/sessions/test-sid/conversations/test-cid/messages');
  });

  it('does not use fetchAPI (which calls .json()) for SSE', async () => {
    // If fetchAPI were used, response.body.getReader() would fail because
    // fetchAPI returns parsed JSON. This test verifies native fetch is used.
    const fetchAPIModule = await import('@/lib/api');
    // fetchAPI should NOT be called during sendMessage
    const fetchAPISpy = jest.spyOn(fetchAPIModule, 'fetchAPI');

    const mockReader = { read: jest.fn().mockResolvedValue({ done: true }), cancel: jest.fn() };
    global.fetch = jest.fn().mockResolvedValue({ ok: true, body: { getReader: () => mockReader } });

    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('hello');
    });

    // fetchAPI should not be called for the SSE POST
    const sseCallArgs = fetchAPISpy.mock.calls.filter(
      args => typeof args[0] === 'string' && args[0].includes('/messages')
    );
    expect(sseCallArgs).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autonome-studio && npx jest src/__tests__/useClaudeChat.test.ts --no-coverage`
Expected: FAIL — mock assertions fail because real code still uses `fetchAPI`

- [ ] **Step 3: Modify useClaudeChat.ts to use raw fetch for SSE**

In `autonome-studio/src/hooks/useClaudeChat.ts`, change the SSE POST from `fetchAPI` to native `fetch`:

```typescript
// Line 5: Add getToken import
import { useCallback, useRef } from 'react';
import { useClaudeStore } from '@/store/useClaudeStore';
import type { ClaudeEvent } from '@/types/claude';
import { BASE_URL, getToken } from '@/lib/api';
// REMOVE: import { fetchAPI } from '@/lib/api';

export function useClaudeChat() {
  // ... existing store destructuring ...

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeSessionId || !activeConversationId) return;
      if (isStreaming) return;

      const userMsg = {
        id: `temp-${Date.now()}`,
        role: 'user' as const,
        content,
        createdAt: new Date().toISOString(),
      };
      addMessage(userMsg);

      resetStream();
      setStreaming(true);

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      const MAX_RETRIES = 5;
      const BASE_DELAY = 1000;
      const assistantEvents: ClaudeEvent[] = [];

      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          // Use raw fetch to preserve Response.body for SSE streaming
          // fetchAPI calls response.json() which fails on text/event-stream
          const url = `${BASE_URL}/api/claude/sessions/${activeSessionId}/conversations/${activeConversationId}/messages`;
          const headers: Record<string, string> = {
            'Content-Type': 'application/json',
          };
          const token = getToken();
          if (token) headers['Authorization'] = `Bearer ${token}`;

          const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify({ content }),
            signal: abortController.signal,
            credentials: 'include',
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const reader = response.body?.getReader();
          if (!reader) throw new Error('No response body');

          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let currentEvent = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                const data = line.slice(6);
                try {
                  const parsed = JSON.parse(data);
                  if (currentEvent !== 'end' && currentEvent !== 'session_info') {
                    appendStreamContent(parsed);
                    assistantEvents.push(parsed);
                  }
                } catch {
                  // 跳过非 JSON 数据
                }
              }
            }
          }

          break;
        } catch (err: unknown) {
          if (err instanceof Error && err.name === 'AbortError') {
            return;
          }

          if (attempt < MAX_RETRIES) {
            const delay = BASE_DELAY * Math.pow(2, attempt);
            console.warn(`Claude SSE 中断，${delay / 1000}s 后重连 (${attempt + 1}/${MAX_RETRIES})`);
            appendStreamContent({
              type: 'status',
              status: 'reconnecting',
              message: `连接中断，${delay / 1000}s 后重连 (${attempt + 1}/${MAX_RETRIES})`,
              timestamp: Date.now(),
            });
            await new Promise((r) => setTimeout(r, delay));
          } else {
            console.error('Claude chat error after max retries:', err);
            appendStreamContent({
              type: 'error',
              message: '连接失败，已达最大重试次数。请检查网络后重试。',
              timestamp: Date.now(),
            });
            break;
          }
        }
      }

      const assistantMsg = {
        id: `msg-${Date.now()}`,
        role: 'assistant' as const,
        content: '',
        events: assistantEvents,
        createdAt: new Date().toISOString(),
      };
      addMessage(assistantMsg);
      setStreaming(false);
      abortControllerRef.current = null;
    },
    [
      activeSessionId,
      activeConversationId,
      isStreaming,
      addMessage,
      appendStreamContent,
      setStreaming,
      resetStream,
    ]
  );

  // ... rest unchanged (cancelStream, loadMessages, return) ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autonome-studio && npx jest src/__tests__/useClaudeChat.test.ts --no-coverage`
Expected: PASS (both test cases)

- [ ] **Step 5: Commit**

```bash
git add autonome-studio/src/hooks/useClaudeChat.ts
git commit -m "fix: SSE 流接收改为原生 fetch，修复 fetchAPI 导致 response.json() 解析失败"
```

---

### Task 1.2: DB Schema 修复 — message_id / session_id nullable

**Files:**
- Create: `autonome-backend/alembic/versions/claude_task_nullable.py`
- Modify: `autonome-backend/app/api/routes/claude.py:326-366`
- Modify: `autonome-backend/tests/test_claude_api.py:383-410` (un-skip tests)

- [ ] **Step 1: Create migration**

Create `autonome-backend/alembic/versions/claude_task_nullable.py`:

```python
"""
claude_task 表 message_id 和 session_id 改为 nullable

ClaudeTask 模型中这两个字段已是 Optional，但迁移中错误设为 NOT NULL。
Agent Service 调用 POST /tasks/submit 时不传 message_id，导致 DB 约束错误。
"""

from typing import Union, Sequence
from alembic import op

revision: str = 'claude_task_nullable'
down_revision: Union[str, Sequence[str], None] = 'claude_agent_001'


def upgrade() -> None:
    op.execute("ALTER TABLE claude_task ALTER COLUMN message_id DROP NOT NULL")
    op.execute("ALTER TABLE claude_task ALTER COLUMN session_id DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE claude_task ALTER COLUMN message_id SET NOT NULL")
    op.execute("ALTER TABLE claude_task ALTER COLUMN session_id SET NOT NULL")
```

- [ ] **Step 2: Write test to verify migration**

Add to `autonome-backend/tests/test_claude_models.py`:

```python
class TestClaudeTaskNullable:
    def test_task_without_message_id(self):
        """ClaudeTask 允许不关联 message （修复 NOT NULL constraint）"""
        task = ClaudeTask(
            skill_id="test_skill",
            status="pending",
        )
        assert task.message_id is None
        assert task.session_id is None
        assert task.status == "pending"
```

- [ ] **Step 3: Run migration test**

Run: `cd autonome-backend && docker exec autonome-api pytest /app/tests/test_claude_models.py::TestClaudeTaskNullable -v`
Expected: PASS

- [ ] **Step 4: Fix submit_heavy_task to set session_id from conversation**

In `autonome-backend/app/api/routes/claude.py`, modify `submit_heavy_task`:

```python
@router.post("/tasks/submit")
async def submit_heavy_task(
    req: SubmitTaskRequest,
    user: User = Depends(get_current_user),
):
    with Session(engine) as db:
        # 提取 session_id：从 conversation_id 反查
        task_session_id = None
        if req.conversation_id:
            conv = db.get(ClaudeConversation, UUID(req.conversation_id))
            if conv:
                task_session_id = conv.session_id

        task = ClaudeTask(
            message_id=UUID(req.message_id) if req.message_id else None,
            session_id=task_session_id,
            skill_id=req.skill_id,
            status="pending",
            code=req.code,
            parameters=req.parameters or {},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # ... rest unchanged (message task_ids update, return) ...
```

- [ ] **Step 5: Un-skip the previously skipped tests**

In `autonome-backend/tests/test_claude_api.py`, remove `pytest.skip` from `test_submit_task_no_message` and `test_submit_task_empty_body`:

```python
class TestTaskSubmit:
    def test_submit_task_no_message(self, client):
        """POST /api/claude/tasks/submit — 提交任务（不关联消息）"""
        resp = client.post("/api/claude/tasks/submit", json={
            "skill_id": "test_skill",
            "parameters": {"arg1": "value1"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_submit_task_empty_body(self, client):
        """POST /api/claude/tasks/submit — 空 body 可接受"""
        resp = client.post("/api/claude/tasks/submit", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
```

- [ ] **Step 6: Run API tests**

Run: `docker exec autonome-api pytest /app/tests/test_claude_api.py::TestTaskSubmit -v`
Expected: 2 PASS (was 2 SKIP before)

- [ ] **Step 7: Run migration in container**

Run: `docker exec autonome-api alembic upgrade head`
Expected: "Running upgrade claude_agent_001 -> claude_task_nullable"

- [ ] **Step 8: Commit**

```bash
git add autonome-backend/alembic/versions/claude_task_nullable.py \
        autonome-backend/app/api/routes/claude.py \
        autonome-backend/tests/test_claude_models.py \
        autonome-backend/tests/test_claude_api.py
git commit -m "fix: ClaudeTask message_id/session_id 改为 nullable，修复 NOT NULL 约束冲突"
```

---

### Task 1.3: 容器池 session 动态分配

**Files:**
- Modify: `autonome-backend/app/sandbox/agent_service/main.py`
- Modify: `autonome-backend/app/sandbox/agent_service/redis_client.py`
- Modify: `autonome-backend/app/services/claude_container_pool.py:194-206`
- Modify: `autonome-backend/app/services/claude_redis_bridge.py`

- [ ] **Step 1: Add unsubscribe + subscribe_session to AgentRedisClient**

In `autonome-backend/app/sandbox/agent_service/redis_client.py`, add methods to AgentRedisClient:

```python
class AgentRedisClient:
    # ... existing code ...

    def unsubscribe_current(self) -> None:
        """取消当前 pub/sub 订阅"""
        if self._pubsub:
            try:
                self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

    def subscribe_session(self, session_id: str, message_handler: Callable) -> None:
        """订阅指定 session 的消息通道（非阻塞模式）"""
        self._message_handler = message_handler
        self._pubsub = self._client.pubsub()
        self._pubsub.subscribe(f"claude:session:{session_id}")
```

- [ ] **Step 2: Modify agent_service main.py for dynamic session switching**

In `autonome-backend/app/sandbox/agent_service/main.py`:

```python
import socket

def get_container_id() -> str:
    """从 Docker hostname 获取 container_id"""
    return socket.gethostname()

def main() -> None:
    global redis_client, claude_manager, running, SESSION_ID

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    redis_client = AgentRedisClient(REDIS_URL)
    if not redis_client.connect():
        print("ERROR: Cannot connect to Redis, exiting")
        sys.exit(1)

    claude_manager = ClaudeManager(
        api_key=API_KEY,
        api_base_url=API_BASE_URL or None,
        model=CLAUDE_MODEL or None,
    )

    container_id = get_container_id()
    print(f"[AgentService] Container ID: {container_id}")

    # 如果已有 SESSION_ID（非预热容器），直接订阅
    if SESSION_ID and SESSION_ID != "prewarm":
        redis_client.start_heartbeat(SESSION_ID)
        redis_client.publish_event(
            SESSION_ID,
            StatusEvent(status=AgentStatus.IDLE.value, message="Agent Service 已就绪"),
        )
        print(f"[AgentService] 已就绪, session={SESSION_ID}")
        redis_client.subscribe(SESSION_ID, handle_message)
    else:
        # 预热容器：等待分配
        redis_client.start_heartbeat(f"prewarm-{container_id}")
        print(f"[AgentService] 预热模式, 等待容器分配 broadcast...")

        # 订阅 broadcast 通道等待分配
        pubsub = redis_client._client.pubsub()
        pubsub.subscribe("claude:pool:broadcast")

        for message in pubsub.listen():
            if not running:
                break
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
            except json.JSONDecodeError:
                continue

            if data.get("action") == "assign" and data.get("container_id") == container_id:
                SESSION_ID = data["session_id"]
                print(f"[AgentService] 分配到 session={SESSION_ID}")

                # 取消 broadcast 订阅
                pubsub.close()

                # 开始心跳和消息处理
                redis_client.stop()  # 停止旧 heartbeat
                redis_client = AgentRedisClient(REDIS_URL)
                redis_client.connect()
                redis_client.start_heartbeat(SESSION_ID)
                redis_client.publish_event(
                    SESSION_ID,
                    StatusEvent(status=AgentStatus.IDLE.value, message="Agent Service 已就绪"),
                )
                redis_client.subscribe(SESSION_ID, handle_message)
                break

    print("[AgentService] 已退出")
```

- [ ] **Step 3: Add publish_allocation to redis_bridge**

In `autonome-backend/app/services/claude_redis_bridge.py`, add method:

```python
class ClaudeRedisBridge:
    # ... existing code ...

    async def publish_allocation(self, container_id: str, session_id: str) -> None:
        """发布容器分配消息到 broadcast 通道"""
        await self._redis.publish(
            "claude:pool:broadcast",
            json.dumps({
                "action": "assign",
                "container_id": container_id,
                "session_id": session_id,
            }),
        )
```

- [ ] **Step 4: Modify container_pool allocate() to use broadcast**

In `autonome-backend/app/services/claude_container_pool.py`, modify `allocate()` — replace the ineffective `docker exec export` block (lines 193-201) with Redis broadcast:

```python
# REPLACE lines 193-201:
# OLD: docker exec export hack (doesn't work — subshell doesn't persist)
# try:
#     subprocess.run(
#         ["docker", "exec", idle_container.container_id,
#          "sh", "-c",
#          f"export CLAUDE_SESSION_ID={session_id}"],
#         capture_output=True, timeout=5,
#     )
# except Exception:
#     pass

# NEW: publish allocation via Redis broadcast
from app.services.claude_redis_bridge import get_claude_bridge

bridge = await get_claude_bridge()
await bridge.publish_allocation(
    container_id=idle_container.container_id,
    session_id=session_id,
)
log.info(f"已发布分配: container={idle_container.container_id[:12]} → session={session_id}")
```

Also update `_create_container` — when creating prewarm containers, use `prewarm-{container_id}` as the session identifier:

```python
def _create_container(self, session_id: str, user_id: int) -> Optional[str]:
    # ... existing code ...
    env_session_id = session_id
    if session_id == "prewarm":
        # 预热容器使用占位符，等待 broadcast 分配
        env_session_id = "prewarm"
    
    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", f"claude-sandbox-{session_id[:8]}",
            "--network", "autonome_claude_net",
            "--memory", "2g",
            "--memory-swap", "4g",
            "--cpus", "2",
            "-e", f"CLAUDE_SESSION_ID={env_session_id}",
            # ... rest unchanged ...
        ],
        # ...
    )
```

- [ ] **Step 5: Write unit test for AgentRedisClient dynamic subscription**

Add to `autonome-backend/tests/test_claude_models.py`:

```python
from unittest.mock import patch, MagicMock
from app.sandbox.agent_service.redis_client import AgentRedisClient

class TestAgentRedisClientDynamicSub:
    @patch('app.sandbox.agent_service.redis_client.redis.Redis')
    def test_unsubscribe_current(self, mock_redis):
        """AgentRedisClient.unsubscribe_current 关闭 pubsub"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis.from_url.return_value = mock_client

        client = AgentRedisClient("redis://localhost:6379/0")
        client.connect()
        client._pubsub = mock_pubsub

        client.unsubscribe_current()
        mock_pubsub.close.assert_called_once()
        assert client._pubsub is None
```

- [ ] **Step 6: Run tests**

Run: `docker exec autonome-api pytest /app/tests/test_claude_models.py -v`
Expected: All running tests PASS

- [ ] **Step 7: Commit**

```bash
git add autonome-backend/app/sandbox/agent_service/main.py \
        autonome-backend/app/sandbox/agent_service/redis_client.py \
        autonome-backend/app/services/claude_container_pool.py \
        autonome-backend/app/services/claude_redis_bridge.py \
        autonome-backend/tests/test_claude_models.py
git commit -m "fix: 容器池使用 Redis broadcast 实现 session 动态分配，替代无效的 docker exec export"
```

---

### Task 1.4: Celery 任务 dispatch 集成

**Files:**
- Modify: `autonome-backend/app/api/routes/claude.py:326-366`
- Verify: `autonome-backend/app/services/celery_app.py`

- [ ] **Step 1: Verify celery_app has execute_skill_task**

Run: `grep -n "execute_skill_task" autonome-backend/app/services/celery_app.py`

If NOT found, add the task definition:

```python
@celery.task(name="execute_skill_task", bind=True, max_retries=3)
def execute_skill_task(self, task_id: str, skill_id: str = None, code: str = None, parameters: dict = None):
    """
    通过 SkillExecutor 执行技能任务
    
    Args:
        task_id: ClaudeTask UUID（用于 DB 状态更新）
        skill_id: 技能 ID
        code: 直接执行的代码
        parameters: 任务参数字典
    """
    from sqlmodel import Session
    from app.core.database import engine
    from app.models.claude import ClaudeTask
    
    with Session(engine) as db:
        task = db.get(ClaudeTask, task_id)
        if not task:
            return {"status": "error", "detail": "Task not found"}
        
        task.status = "running"
        db.add(task)
        db.commit()
    
    try:
        # 执行技能代码
        result = execute_skill(skill_id=skill_id, code=code, parameters=parameters or {})
        
        with Session(engine) as db:
            task = db.get(ClaudeTask, task_id)
            task.status = "completed"
            task.output_files = result.get("output_files", [])
            task.completed_at = datetime.now(timezone.utc)
            db.add(task)
            db.commit()
        
        return {"status": "completed"}
    except Exception as exc:
        with Session(engine) as db:
            task = db.get(ClaudeTask, task_id)
            task.status = "failed"
            task.error_text = str(exc)[:1000]
            task.completed_at = datetime.now(timezone.utc)
            db.add(task)
            db.commit()
        
        raise self.retry(exc=exc)
```

- [ ] **Step 2: Modify submit_heavy_task to dispatch Celery task**

In `autonome-backend/app/api/routes/claude.py` `submit_heavy_task`:

```python
# After db.commit() + db.refresh(task):

# Dispatch Celery task for execution
from app.services.celery_app import execute_skill_task

celery_result = execute_skill_task.delay(
    task_id=str(task.id),
    skill_id=req.skill_id,
    code=req.code,
    parameters=req.parameters or {},
)
task.celery_task_id = celery_result.id
task.status = "running"
db.add(task)
db.commit()

return {
    "task_id": str(task.id),
    "status": task.status,
    "celery_task_id": celery_result.id,
    "created_at": task.created_at.isoformat(),
}
```

- [ ] **Step 3: Update test for task with Celery dispatch**

In `autonome-backend/tests/test_claude_api.py`, update `TestTaskSubmit` — add mock for Celery:

```python
class TestTaskSubmit:
    @patch("app.api.routes.claude.execute_skill_task")
    def test_submit_task_dispatches_celery(self, mock_celery_task, client):
        """POST /api/claude/tasks/submit — dispatch Celery task"""
        mock_result = MagicMock()
        mock_result.id = "celery-task-123"
        mock_celery_task.delay.return_value = mock_result
        
        resp = client.post("/api/claude/tasks/submit", json={
            "skill_id": "test_skill",
            "code": "print('hello')",
            "parameters": {"arg1": "value1"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["celery_task_id"] == "celery-task-123"
        assert data["status"] == "running"
        mock_celery_task.delay.assert_called_once()
```

- [ ] **Step 4: Run tests**

Run: `docker exec autonome-api pytest /app/tests/test_claude_api.py::TestTaskSubmit -v`
Expected: PASS (with Celery mock)

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/claude.py \
        autonome-backend/app/services/celery_app.py \
        autonome-backend/tests/test_claude_api.py
git commit -m "feat: 重型任务提交后自动 dispatch Celery 异步执行"
```

---

### Task 1.5: API 响应格式统一

**Files:**
- Modify: `autonome-backend/app/api/routes/claude.py` (all 17 endpoints)
- Modify: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`
- Modify: `autonome-studio/src/hooks/useClaudeChat.ts`

- [ ] **Step 1: Write test for new API response format**

Add to `autonome-backend/tests/test_claude_api.py`:

```python
class TestApiResponseFormat:
    def test_session_list_returns_success_envelope(self, client, monkeypatch):
        """所有 Claude API 端点返回 {success, data} 信封"""
        mock_mgr, mock_sess = setup_session_manager_mock(monkeypatch)
        resp = client.get("/api/claude/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "sessions" in data["data"]

    def test_container_stats_returns_success_envelope(self, client):
        """GET /containers/stats 返回 {success, data} 信封"""
        resp = client.get("/api/claude/containers/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "total" in data["data"]
```

- [ ] **Step 2: Wrap all route responses in {success, data}**

In `autonome-backend/app/api/routes/claude.py`, add a helper and wrap all returns:

```python
def _ok(data: dict) -> dict:
    """统一成功响应信封"""
    return {"success": True, "data": data}
```

Apply to ALL 17 endpoints. Example for `create_session`:

```python
@router.post("/sessions")
async def create_session(req: CreateSessionRequest, user: User = Depends(get_current_user)):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.create_session(req.title)
    return _ok({
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
    })
```

Same pattern for `list_sessions`, `get_session`, `update_session`, `delete_session`, `create_conversation`, `get_messages`, `search_skills`, `submit_heavy_task`, `get_task_status`, `list_tasks`, `list_workspace_files`, `save_experience`, `get_container_pool_stats`.

- [ ] **Step 3: Update frontend to read from data envelope**

In `autonome-studio/src/hooks/useClaudeChat.ts`, `loadMessages`:

```typescript
const loadMessages = useCallback(
  async (sessionId: string, conversationId: string) => {
    try {
      const res = await fetchAPI(
        `/api/claude/sessions/${sessionId}/conversations/${conversationId}/messages`
      );
      if (res.ok) {
        const data = await res.json();
        setMessages(data.data?.messages || data.messages || []);
      }
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  },
  [setMessages]
);
```

Note: `fetchAPI` already returns parsed JSON. The response is `{success: true, data: {messages: [...]}}`.

Actually, `loadMessages` uses `fetchAPI` which returns parsed JSON. So the code should be:

```typescript
const data = await fetchAPI(`/api/claude/sessions/${sessionId}/conversations/${conversationId}/messages`);
setMessages(data?.data?.messages || data?.messages || []);
```

In `autonome-studio/src/components/chat/ClaudeChatStage.tsx`, update all `fetchAPI` consumers:

```typescript
// refreshSessions
const data = await fetchAPI('/api/claude/sessions');
if (data?.success && data?.data?.sessions?.length > 0) {
  setSessions(data.data.sessions as ClaudeSession[]);
  setPageState('ready');
}

// handleCreateSession
const session = await fetchAPI('/api/claude/sessions', {...});
addSession(session.data as ClaudeSession);

// handleDeleteSession - unchanged (DELETE returns {success, data: {status: "closed"}})

// handleSend auto-create session
const res = await fetchAPI('/api/claude/sessions', {...});
sid = res.data.id;

// handleSend auto-create conversation
const res = await fetchAPI(`/api/claude/sessions/${sid}/conversations`, {...});
cid = res.data.id;
```

- [ ] **Step 4: Run backend + frontend tests**

Run backend: `docker exec autonome-api pytest /app/tests/test_claude_api.py::TestApiResponseFormat -v`
Expected: PASS

Run frontend: `cd autonome-studio && npx tsc --noEmit`
Expected: No TypeScript errors

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/claude.py \
        autonome-backend/tests/test_claude_api.py \
        autonome-studio/src/components/chat/ClaudeChatStage.tsx \
        autonome-studio/src/hooks/useClaudeChat.ts
git commit -m "refactor: Claude API 响应格式统一为 {success, data} 信封"
```

---

## Stage 2: 前端重构 + UI 完善 + 类型安全

### Task 2.1: ClaudeChatStage 组件拆分

**Files:**
- Create: `autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx`
- Create: `autonome-studio/src/components/chat/ClaudeMessageList.tsx`
- Create: `autonome-studio/src/components/chat/ClaudeInputArea.tsx`
- Modify: `autonome-studio/src/components/chat/ClaudeChatStage.tsx` (reduce to ~80 lines)

- [ ] **Step 1: Create ClaudeInputArea component**

Create `autonome-studio/src/components/chat/ClaudeInputArea.tsx`:

```tsx
'use client';

interface ClaudeInputAreaProps {
  isStreaming: boolean;
  onSend: (content: string) => void;
  onCancel: () => void;
}

export function ClaudeInputArea({ isStreaming, onSend, onCancel }: ClaudeInputAreaProps) {
  const [input, setInput] = useState('');
  
  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    onSend(input.trim());
    setInput('');
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };
  
  return (
    <div className="border-t border-gray-700 p-3">
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送)"
          rows={2}
          className="flex-1 bg-gray-800 text-gray-200 rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          onClick={isStreaming ? onCancel : handleSend}
          className={`px-4 py-2 rounded text-sm ${
            isStreaming
              ? 'bg-red-600 hover:bg-red-700 text-white'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
          }`}
        >
          {isStreaming ? '停止' : '发送'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ClaudeMessageList component**

Create `autonome-studio/src/components/chat/ClaudeMessageList.tsx`:

```tsx
'use client';

import { useRef, useEffect } from 'react';
import { ThinkingBlock } from './ThinkingBlock';
import { PlanCard } from './PlanCard';
import { TaskCard } from './TaskCard';
import { ToolUseBlock } from './ToolUseBlock';
import type { ClaudeMessage, ClaudeEvent, PlanData, PlanStep } from '@/types/claude';

interface ClaudeMessageListProps {
  messages: ClaudeMessage[];
  streamEvents: ClaudeEvent[];
  isStreaming: boolean;
  onPlanConfirm: () => void;
}

function buildTextContent(events: ClaudeEvent[]): string {
  return events
    .filter((e) => e.type === 'text_delta')
    .map((e) => (e.content as string) || '')
    .join('');
}

function extractPlan(events: ClaudeEvent[]): PlanData | null {
  const e = events.find(ev => ev.type === 'plan');
  if (!e) return null;
  return {
    title: String(e.title || ''),
    steps: (e.steps as PlanStep[]) || [],
    codeSnapshot: String(e.codeSnapshot || ''),
    estimatedCost: String(e.estimatedCost || ''),
  };
}

function extractTaskIds(events: ClaudeEvent[]): string[] {
  return events
    .filter((e) => e.type === 'task_submitted' && e.task_id)
    .map((e) => e.task_id as string);
}

function renderEvents(events: ClaudeEvent[]) {
  return events.map((event, i) => {
    if (event.type === 'thinking') {
      return <ThinkingBlock key={i} content={(event.content as string) || ''} />;
    }
    if (event.type === 'tool_use' || event.type === 'tool_result') {
      return <ToolUseBlock key={i} event={event} />;
    }
    return null;
  });
}

export function ClaudeMessageList({
  messages,
  streamEvents,
  isStreaming,
  onPlanConfirm,
}: ClaudeMessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamEvents]);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.map((msg) => (
        <div key={msg.id} className="mb-4">
          {msg.role === 'user' ? (
            <div className="flex justify-end">
              <div className="bg-blue-600 text-white px-4 py-2 rounded-lg max-w-[80%]">
                {msg.content}
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {msg.events && extractPlan(msg.events) && (
                <PlanCard
                  plan={extractPlan(msg.events)!}
                  onConfirm={onPlanConfirm}
                  disabled={true}
                />
              )}
              {msg.events && renderEvents(msg.events)}
              {msg.events && msg.events.length > 0 && (
                <div className="text-gray-200 whitespace-pre-wrap">
                  {buildTextContent(msg.events)}
                </div>
              )}
              {msg.events && extractTaskIds(msg.events).map((tid) => (
                <TaskCard key={tid} taskId={tid} />
              ))}
            </div>
          )}
        </div>
      ))}

      {/* 流式渲染 */}
      {isStreaming && (
        <div className="mb-4">
          {extractPlan(streamEvents) && (
            <PlanCard plan={extractPlan(streamEvents)!} onConfirm={onPlanConfirm} />
          )}
          {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
            <ThinkingBlock key={`stream-thinking-${i}`} content={(e.content as string) || ''} />
          ))}
          {streamEvents.filter((e) => e.type === 'tool_use' || e.type === 'tool_result').map((e, i) => (
            <ToolUseBlock key={`stream-tool-${i}`} event={e} />
          ))}
          <div className="text-gray-200 whitespace-pre-wrap">
            {streamEvents.filter((e) => e.type === 'text_delta').map((e) => (e.content as string) || '').join('')}
            {streamEvents.some((e) => e.type === 'status' && e.status === 'thinking') && (
              <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-1" />
            )}
          </div>
          {extractTaskIds(streamEvents).map((tid) => (
            <TaskCard key={tid} taskId={tid} />
          ))}
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
```

- [ ] **Step 3: Create ClaudeSessionSidebar component**

Create `autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx`:

```tsx
'use client';

import { useState } from 'react';
import type { ClaudeSession } from '@/types/claude';

interface ClaudeSessionSidebarProps {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (id: string) => void;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function ClaudeSessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
}: ClaudeSessionSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredSessions = sessions.filter((s) =>
    !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleDeleteClick = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('确定要删除此会话吗？关联的对话和消息将被永久删除。')) return;
    onDeleteSession(sessionId);
  };

  return (
    <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
      <button
        onClick={onCreateSession}
        className="w-full px-3 py-2 mb-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
      >
        + 新建会话
      </button>
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="搜索会话..."
        className="w-full mb-2 px-2 py-1.5 bg-gray-800 text-gray-300 text-xs rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <div className="flex-1 overflow-y-auto space-y-1">
        {filteredSessions.length === 0 ? (
          <div className="text-xs text-gray-500 text-center py-4">
            {searchQuery ? '无匹配会话' : '暂无会话'}
          </div>
        ) : (
          filteredSessions.map((s) => (
            <div
              key={s.id}
              className={`group flex items-center rounded ${
                s.id === activeSessionId ? 'bg-gray-700' : 'hover:bg-gray-800'
              }`}
            >
              <button
                onClick={() => onSelectSession(s.id)}
                className="flex-1 text-left px-3 py-2 rounded text-sm truncate min-w-0"
              >
                <div className={`truncate ${
                  s.id === activeSessionId ? 'text-white' : 'text-gray-400'
                }`}>
                  {s.title}
                </div>
                {s.updatedAt && (
                  <div className="text-xs text-gray-600 mt-0.5">
                    {formatDate(s.updatedAt)}
                  </div>
                )}
              </button>
              <button
                onClick={(e) => handleDeleteClick(e, s.id)}
                className="px-2 py-1 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all text-xs shrink-0"
                title="删除会话"
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite ClaudeChatStage as thin orchestrator**

Rewrite `autonome-studio/src/components/chat/ClaudeChatStage.tsx`:

```tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import { useClaudeChat } from '@/hooks/useClaudeChat';
import { useClaudeStore } from '@/store/useClaudeStore';
import type { ClaudeSession } from '@/types/claude';
import { ClaudeSessionSidebar } from './ClaudeSessionSidebar';
import { ClaudeMessageList } from './ClaudeMessageList';
import { ClaudeInputArea } from './ClaudeInputArea';
import { ClaudePreview } from './ClaudePreview';
import { fetchAPI } from '@/lib/api';

export function ClaudeChatStage() {
  const {
    activeSessionId,
    activeConversationId,
    sessions,
    setSessions,
    setActiveSession,
    addSession,
    removeSession,
  } = useClaudeStore();

  const { messages, isStreaming, streamEvents, sendMessage, cancelStream, loadMessages } =
    useClaudeChat();

  const [pageState, setPageState] = useState<'loading' | 'empty' | 'error' | 'ready'>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  const refreshSessions = useCallback(async () => {
    try {
      setPageState('loading');
      const data = await fetchAPI('/api/claude/sessions');
      if (data?.success && data?.data?.sessions?.length > 0) {
        setSessions(data.data.sessions as ClaudeSession[]);
        setPageState('ready');
      } else {
        setPageState('empty');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '连接失败');
      setPageState('error');
    }
  }, [setSessions]);

  useEffect(() => { refreshSessions(); }, []);
  useEffect(() => {
    if (activeSessionId && activeConversationId) {
      loadMessages(activeSessionId, activeConversationId);
    }
  }, [activeSessionId, activeConversationId, loadMessages]);

  const handleCreateSession = async () => {
    try {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新会话' }),
      });
      addSession(res.data as ClaudeSession);
      setActiveSession(res.data.id);
      setPageState('ready');
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    await fetchAPI(`/api/claude/sessions/${sessionId}`, { method: 'DELETE' });
    removeSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSession(sessions[0]?.id || '');
    }
  };

  const handleSend = async (content: string) => {
    let sid = activeSessionId;
    let cid = activeConversationId;

    if (!sid) {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: content.slice(0, 30) }),
      });
      sid = res.data.id;
      addSession(res.data as ClaudeSession);
      setActiveSession(sid!);
    }

    if (!cid && sid) {
      const res = await fetchAPI(`/api/claude/sessions/${sid}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: content.slice(0, 30) }),
      });
      cid = res.data.id;
    }

    sendMessage(content);
  };

  const handlePlanConfirm = useCallback(() => {
    sendMessage('确认执行方案，请开始执行。');
  }, [sendMessage]);

  if (pageState === 'loading') {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
          <div className="text-gray-400 text-sm">正在连接 Claude Agent...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <ClaudeSessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSession}
        onCreateSession={handleCreateSession}
        onDeleteSession={handleDeleteSession}
      />
      <div className="flex-1 flex flex-col min-w-0">
        {pageState === 'error' ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-red-400 text-sm mb-2">{errorMessage}</div>
              <button onClick={refreshSessions} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm">
                重试
              </button>
            </div>
          </div>
        ) : pageState === 'empty' ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-gray-400 text-lg mb-3">开始你的分析之旅</div>
              <button onClick={handleCreateSession} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm">
                创建新会话
              </button>
            </div>
          </div>
        ) : (
          <ClaudeMessageList
            messages={messages}
            streamEvents={streamEvents}
            isStreaming={isStreaming}
            onPlanConfirm={handlePlanConfirm}
          />
        )}
        <ClaudeInputArea isStreaming={isStreaming} onSend={handleSend} onCancel={cancelStream} />
      </div>
      <div className="w-64 border-l border-gray-700">
        <ClaudePreview />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verify TypeScript compiles and component renders**

Run: `cd autonome-studio && npx tsc --noEmit`
Expected: No errors

Run: `cd autonome-studio && npx jest src/__tests__/ClaudeChatStage.test.tsx --no-coverage` (if test exists)
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx \
        autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx \
        autonome-studio/src/components/chat/ClaudeMessageList.tsx \
        autonome-studio/src/components/chat/ClaudeInputArea.tsx
git commit -m "refactor: ClaudeChatStage 拆分为 4 个组件（Sidebar + MessageList + InputArea + 主容器）"
```

---

### Task 2.2: 对话管理 UI

**Files:**
- Modify: `autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx`
- Modify: `autonome-backend/app/api/routes/claude.py` (extend session detail)

- [ ] **Step 1: Extend GET /sessions/{id} to return conversations**

In `autonome-backend/app/api/routes/claude.py` `get_session`:

```python
@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID, user: User = Depends(get_current_user)):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 同时返回 conversations 列表
    with Session(engine) as db:
        conversations = db.exec(
            select(ClaudeConversation)
            .where(ClaudeConversation.session_id == session_id)
            .order_by(ClaudeConversation.created_at.desc())
        ).all()
    
    return _ok({
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "container_id": session.container_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat(),
            }
            for c in conversations
        ],
    })
```

- [ ] **Step 2: Add conversations display to ClaudeSessionSidebar**

In `autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx`, extend the session item to show conversations when selected:

```tsx
import { useState, useEffect } from 'react';
import type { ClaudeSession, ClaudeConversation } from '@/types/claude';
import { fetchAPI } from '@/lib/api';

interface ClaudeSessionSidebarProps {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  activeConversationId: string | null;
  onSelectSession: (id: string) => void;
  onSelectConversation: (id: string) => void;
  onCreateSession: () => void;
  onCreateConversation: (sessionId: string) => void;
  onDeleteSession: (id: string) => void;
}

export function ClaudeSessionSidebar({
  sessions,
  activeSessionId,
  activeConversationId,
  onSelectSession,
  onSelectConversation,
  onCreateSession,
  onCreateConversation,
  onDeleteSession,
}: ClaudeSessionSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [conversationsMap, setConversationsMap] = useState<Record<string, ClaudeConversation[]>>({});

  // 当选中的 session 改变时，加载其 conversations
  useEffect(() => {
    if (!activeSessionId) return;
    fetchAPI(`/api/claude/sessions/${activeSessionId}`).then((res) => {
      if (res?.data?.conversations) {
        setConversationsMap((prev) => ({
          ...prev,
          [activeSessionId]: res.data.conversations,
        }));
      }
    }).catch(() => {});
  }, [activeSessionId]);

  const filteredSessions = sessions.filter((s) =>
    !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
      {/* ... create button + search input unchanged ... */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {filteredSessions.map((s) => {
          const isActive = s.id === activeSessionId;
          const conversations = conversationsMap[s.id] || [];
          return (
            <div key={s.id}>
              {/* Session item */}
              <div className={`group flex items-center rounded ${
                isActive ? 'bg-gray-700' : 'hover:bg-gray-800'
              }`}>
                <button
                  onClick={() => onSelectSession(s.id)}
                  className="flex-1 text-left px-3 py-2 rounded text-sm truncate min-w-0"
                >
                  <div className={`truncate ${isActive ? 'text-white' : 'text-gray-400'}`}>
                    {isActive ? '▼' : '▶'} {s.title}
                  </div>
                  {s.updatedAt && (
                    <div className="text-xs text-gray-600 mt-0.5">{formatDate(s.updatedAt)}</div>
                  )}
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
                  className="px-2 py-1 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all text-xs"
                >✕</button>
              </div>

              {/* Conversations list (shown when session is active) */}
              {isActive && (
                <div className="ml-3 space-y-0.5">
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => onSelectConversation(conv.id)}
                      className={`w-full text-left px-3 py-1.5 rounded text-xs ${
                        conv.id === activeConversationId
                          ? 'bg-blue-600/30 text-blue-300'
                          : 'text-gray-400 hover:bg-gray-800'
                      }`}
                    >
                      {conv.title}
                    </button>
                  ))}
                  <button
                    onClick={() => onCreateConversation(s.id)}
                    className="w-full text-left px-3 py-1.5 rounded text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                  >
                    + 新对话
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update ClaudeChatStage for conversation management**

Update `ClaudeChatStage.tsx` to pass `activeConversationId` and conversation handlers to sidebar:

```tsx
// Add to store destructuring:
const { ..., activeConversationId, setActiveConversation } = useClaudeStore();

// Add handler:
const handleCreateConversation = async (sessionId: string) => {
  const res = await fetchAPI(`/api/claude/sessions/${sessionId}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: `对话 ${Date.now()}` }),
  });
  if (res?.data?.id) {
    setActiveConversation(res.data.id);
  }
};

// Update ClaudeSessionSidebar props:
<ClaudeSessionSidebar
  ...
  activeConversationId={activeConversationId}
  onSelectConversation={setActiveConversation}
  onCreateConversation={handleCreateConversation}
/>
```

- [ ] **Step 4: Update useClaudeStore for conversation state**

In `autonome-studio/src/store/useClaudeStore.ts`, ensure `activeConversationId` and `setActiveConversation` are exported (already defined in interface):

```typescript
// No code changes needed — activeConversationId is already in the interface
// Just verify: the store has setActiveConversation
```

- [ ] **Step 5: Verify**

Run: `cd autonome-studio && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add autonome-studio/src/components/chat/ClaudeSessionSidebar.tsx \
        autonome-studio/src/components/chat/ClaudeChatStage.tsx \
        autonome-backend/app/api/routes/claude.py
git commit -m "feat: 侧栏增加对话管理，支持多 conversation 创建与切换"
```

---

### Task 2.3: PlanEvent 解析修复

**Files:**
- Modify: `autonome-studio/src/components/chat/ClaudeMessageList.tsx` (extractPlan function)
- Modify: `autonome-backend/app/sandbox/agent_service/event_types.py` (verify PlanEvent.to_json)

- [ ] **Step 1: Fix extractPlan in ClaudeMessageList**

In `autonome-studio/src/components/chat/ClaudeMessageList.tsx`, the `extractPlan` function already has the correct implementation from Task 2.1 (reads fields from event top level, not from `event.content`). Verify:

```typescript
// extractPlan in ClaudeMessageList is correct:
function extractPlan(events: ClaudeEvent[]): PlanData | null {
  const e = events.find(ev => ev.type === 'plan');
  if (!e) return null;
  return {
    title: String(e.title || ''),
    steps: (e.steps as PlanStep[]) || [],
    codeSnapshot: String(e.codeSnapshot || ''),
    estimatedCost: String(e.estimatedCost || ''),
  };
}
```

- [ ] **Step 2: Confirm PlanEvent.to_json() camelCase output**

In `autonome-backend/app/sandbox/agent_service/event_types.py`, verify PlanEvent field names are camelCase (already confirmed — `codeSnapshot`, `estimatedCost`):

The test `test_plan_data_serialization_camelcase` in `test_claude_models.py` already validates this.

Run: `docker exec autonome-api pytest /app/tests/test_claude_models.py::TestEventTypes::test_plan_data_serialization_camelcase -v`
Expected: PASS

- [ ] **Step 3: Update test to verify PlanEvent parsing**

Add to `autonome-backend/tests/test_claude_models.py`:

```python
def test_plan_event_fields_in_top_level(self):
    """PlanEvent.to_json() 字段在顶层（非嵌套在 content 下）"""
    event = PlanEvent(
        title="QC方案",
        steps=[{"title": "FastQC", "description": "质量检查"}],
        codeSnapshot="fastqc input.fq",
        estimatedCost="2min",
    )
    json_str = event.to_json()
    data = json.loads(json_str)
    # 前端 extractPlan 直接从 data 顶层读取这些字段
    assert data["title"] == "QC方案"
    assert data["steps"][0]["title"] == "FastQC"
    assert data["codeSnapshot"] == "fastqc input.fq"
    # Content 字段不应存在（旧 Bug：前端误在此字段中找 JSON）
    assert "content" not in data or data.get("content") == ""
```

- [ ] **Step 4: Run tests**

Run: `docker exec autonome-api pytest /app/tests/test_claude_models.py -v -k plan`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add autonome-studio/src/components/chat/ClaudeMessageList.tsx \
        autonome-backend/app/sandbox/agent_service/event_types.py \
        autonome-backend/tests/test_claude_models.py
git commit -m "fix: PlanEvent 解析从事件顶层字段读取，修复 content 嵌套错误"
```

---

### Task 2.4: 类型安全加固

**Files:**
- Modify: `autonome-studio/src/types/claude.ts`
- Modify: `autonome-studio/src/components/chat/ClaudeMessageList.tsx`

- [ ] **Step 1: Define discriminant union types**

In `autonome-studio/src/types/claude.ts`, add specific event types:

```typescript
// Add after existing ClaudeEvent interface:

/** Discriminant union: 按 type 字段窄化的事件类型 */
export interface ClaudeThinkingEvent { type: 'thinking'; content: string; timestamp: number; }
export interface ClaudeTextDeltaEvent { type: 'text_delta'; content: string; timestamp: number; }
export interface ClaudePlanEvent { type: 'plan'; title: string; steps: PlanStep[]; codeSnapshot: string; estimatedCost: string; timestamp: number; }
export interface ClaudeToolUseEvent { type: 'tool_use'; tool_name: string; tool_input: Record<string, unknown>; tool_use_id: string; timestamp: number; }
export interface ClaudeToolResultEvent { type: 'tool_result'; tool_name: string; tool_use_id: string; status: string; output: string; timestamp: number; }
export interface ClaudeStatusEvent { type: 'status'; status: string; message: string; timestamp: number; }
export interface ClaudeErrorEvent { type: 'error'; message: string; code?: string; timestamp: number; }
export interface ClaudeUsageEvent { type: 'usage'; input_tokens: number; output_tokens: number; timestamp: number; }
export interface ClaudeTaskSubmittedEvent { type: 'task_submitted'; task_id: string; celery_queue?: string; skill_id?: string; timestamp: number; }
export interface ClaudeTaskStatusEvent { type: 'task_status'; task_id: string; status: string; progress?: string; timestamp: number; }

export type ClaudeStreamEvent =
  | ClaudeThinkingEvent
  | ClaudeTextDeltaEvent
  | ClaudePlanEvent
  | ClaudeToolUseEvent
  | ClaudeToolResultEvent
  | ClaudeStatusEvent
  | ClaudeErrorEvent
  | ClaudeUsageEvent
  | ClaudeTaskSubmittedEvent
  | ClaudeTaskStatusEvent;
```

- [ ] **Step 2: Use ClaudeStreamEvent in ClaudeMessageList**

In `autonome-studio/src/components/chat/ClaudeMessageList.tsx`, replace `ClaudeEvent` with `ClaudeStreamEvent` and remove `as` casts:

```typescript
import type { ClaudeMessage, ClaudeStreamEvent, PlanData, PlanStep } from '@/types/claude';

// In extractPlan — use type narrowing
function extractPlan(events: ClaudeStreamEvent[]): PlanData | null {
  const e = events.find((ev): ev is ClaudeStreamEvent & { type: 'plan' } => ev.type === 'plan');
  if (!e) return null;
  return {
    title: e.title,
    steps: e.steps,
    codeSnapshot: e.codeSnapshot,
    estimatedCost: e.estimatedCost,
  };
}

// In extractTaskIds — type narrowing
function extractTaskIds(events: ClaudeStreamEvent[]): string[] {
  return events
    .filter((ev): ev is ClaudeStreamEvent & { type: 'task_submitted' } => 
      ev.type === 'task_submitted' && !!ev.task_id
    )
    .map((e) => e.task_id);
}

// In buildTextContent
function buildTextContent(events: ClaudeStreamEvent[]): string {
  return events
    .filter((ev): ev is ClaudeStreamEvent & { type: 'text_delta' } => ev.type === 'text_delta')
    .map((e) => e.content)
    .join('');
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd autonome-studio && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add autonome-studio/src/types/claude.ts \
        autonome-studio/src/components/chat/ClaudeMessageList.tsx
git commit -m "refactor: 新增 ClaudeStreamEvent discriminant union 类型，消除 as 强制转换"
```

---

### Task 2.5: 前后端字段命名对齐确认

**Files:**
- Verify: `autonome-backend/app/sandbox/agent_service/event_types.py`

- [ ] **Step 1: Audit all event types for camelCase consistency**

For each event type, verify the dataclass field names match frontend expectations:

| Event Type | Backend field | Frontend expected | Aligned? |
|-----------|---------------|-------------------|----------|
| PlanEvent | title, steps, codeSnapshot, estimatedCost | title, steps, codeSnapshot, estimatedCost | ✅ |
| ThinkingEvent | content | content | ✅ |
| TextDeltaEvent | content | content | ✅ |
| ToolUseEvent | tool_name, tool_input, tool_use_id | tool_name, tool_input, tool_use_id | ✅ |
| ToolResultEvent | tool_name, tool_use_id, status, output | tool_name, tool_use_id, status, output | ✅ |
| StatusEvent | status, message | status, message | ✅ |
| ErrorEvent | message, code | message, code | ✅ |
| UsageEvent | input_tokens, output_tokens | input_tokens, output_tokens | ✅ |
| TaskSubmittedEvent | task_id, celery_queue, skill_id | task_id, celery_queue, skill_id | ✅ |
| TaskStatusEvent | task_id, status, progress | task_id, status, progress | ✅ |

- [ ] **Step 2: Run the camelCase verification test**

Run: `docker exec autonome-api pytest /app/tests/test_claude_models.py::TestEventTypes::test_plan_data_serialization_camelcase -v`
Expected: PASS

- [ ] **Step 3: Confirm no changes needed**

All field names are already aligned. No code changes required for this task.

- [ ] **Step 4: Final verification**

Run backend tests: `docker exec autonome-api pytest /app/tests/test_claude_models.py /app/tests/test_claude_api.py -v`
Expected: All PASS

Run frontend type check: `cd autonome-studio && npx tsc --noEmit`
Expected: No errors

---

## Stage 1 验收总览

Stage 1 所有 5 个任务完成后的验证：

- [ ] 用户可通过 Web UI 发送消息 → SSE 流正常接收并渲染
- [ ] 容器池预热和分配正常，无 env 注入报错
- [ ] 重型任务提交后自动 dispatch Celery，状态正常流转
- [ ] `POST /api/claude/tasks/submit` 不传 message_id 不报 DB 错误
- [ ] 所有 Claude API 端点响应格式统一为 `{success, data}`

## Stage 2 验收总览

- [ ] `ClaudeChatStage.tsx` ≤ 100 行，每个拆分文件 ≤ 200 行
- [ ] 侧栏可展开/折叠会话，显示 conversations 列表
- [ ] PlanCard 正确显示分析方案（从 plan 事件解析）
- [ ] `types/claude.ts` 含完整 discriminant union 类型
- [ ] 零 `as` 强制类型转换在事件处理代码中
- [ ] 前后端字段命名完全对齐
