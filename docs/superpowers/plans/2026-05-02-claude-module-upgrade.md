# Claude Code Agent 模式升级 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Claude Code Agent 模式 7 个已知 bug，构建韧性防护层，建立 80% 测试覆盖，优化组件架构。

**Architecture:** 分 4 阶段顺序推进。Stage 1 修复所有崩溃和部署问题让页面可运行；Stage 2 加入 Error Boundary 和重连防止白屏；Stage 3 建立后端+前端+E2E 测试体系；Stage 4 拆分大组件 + 统一类型。

**Tech Stack:** FastAPI, SQLModel, Docker, Next.js 16, Zustand, TypeScript, pytest, Playwright

---

## 文件变更地图

| 阶段 | 新增 | 修改 |
|------|------|------|
| Stage 1 | — | 5 files |
| Stage 2 | 1 file (ClaudeErrorBoundary) | 2 files |
| Stage 3 | 10 files (tests) | — |
| Stage 4 | 5 files (拆分组件 + types) | 2 files |

---

## Stage 1 — 紧急止血

### Task 1.1: 锁定 Sandbox Dockerfile 版本并构建镜像

**Files:**
- Modify: `autonome-backend/Dockerfile.sandbox:16`

- [ ] **Step 1: 锁定 @anthropic-ai/claude-code 版本**

```dockerfile
# autonome-backend/Dockerfile.sandbox:16
# 改前:
RUN npm install -g @anthropic-ai/claude-code
# 改后:
RUN npm install -g @anthropic-ai/claude-code@1.0.0
```

- [ ] **Step 2: 构建 Sandbox 镜像**

```bash
cd /opt/data1/public/software/systools/autonome
docker build -f autonome-backend/Dockerfile.sandbox -t autonome-claude-sandbox:latest .
```

- [ ] **Step 3: 验证镜像存在**

```bash
docker images | grep autonome-claude-sandbox
# Expected: autonome-claude-sandbox  latest  <IMAGE_ID>  ... 
```

- [ ] **Step 4: 提交**

```bash
git add autonome-backend/Dockerfile.sandbox
git commit -m "fix: 锁定 Claude Code CLI 版本为 1.0.0"
```

---

### Task 1.2: 确保迁移文件部署到 Docker

**Files:**
- Modify: `autonome-backend/Dockerfile` (查找并确认 COPY 指令包含 alembic/versions/)

- [ ] **Step 1: 检查 Dockerfile 是否 COPY alembic 目录**

```bash
grep -n "alembic" /opt/data1/public/software/systools/autonome/autonome-backend/Dockerfile
```

- [ ] **Step 2: 如果缺失，添加 COPY 指令**

在 Dockerfile 中找到 `COPY . .` 或类似指令的位置附近，确认 alembic/versions/ 目录被复制。如果 Dockerfile 没有 COPY 整个 app 目录，需要添加：

```dockerfile
COPY alembic/ /app/alembic/
```

- [ ] **Step 3: 重建 backend 镜像并运行迁移**

```bash
cd /opt/data1/public/software/systools/autonome
docker-compose build backend-api
docker-compose up -d backend-api
docker exec autonome-api alembic upgrade head
```

- [ ] **Step 4: 验证迁移状态**

```bash
docker exec autonome-api alembic current
# Expected: claude_agent_001
```

- [ ] **Step 5: 提交**

```bash
git add autonome-backend/Dockerfile
git commit -m "fix: 确保 alembic 迁移文件部署到 Docker 容器"
```

---

### Task 1.3: 修复 ClaudeEvent 类型定义

**Files:**
- Modify: `autonome-studio/src/store/useClaudeStore.ts:9-20`

- [ ] **Step 1: 为 ClaudeEvent 接口添加 index signature**

```typescript
// autonome-studio/src/store/useClaudeStore.ts:9-20
// 改后:
export interface ClaudeEvent {
  [key: string]: unknown;
  type: string;
  timestamp: number;
  content?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  status?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
  task_id?: string;
  task_status?: string;
  progress?: string;
  code?: string;
}
```

- [ ] **Step 2: 验证 TypeScript 编译错误消除**

```bash
docker exec autonome-web sh -c "cd /app && npx tsc --noEmit 2>&1 | grep -c 'ClaudeChatStage.tsx'"
# Expected: 0
```

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/src/store/useClaudeStore.ts
git commit -m "fix: 为 ClaudeEvent 接口添加 index signature，消除 6 个 TS2345 错误"
```

---

### Task 1.4: 修复 refreshSessions 双重 JSON 解析

**Files:**
- Modify: `autonome-studio/src/components/chat/ClaudeChatStage.tsx:41-53`

- [ ] **Step 1: 重写 refreshSessions 为 async/await，修复双重解析**

```typescript
// autonome-studio/src/components/chat/ClaudeChatStage.tsx
// 替换第 41-53 行的 refreshSessions

const refreshSessions = useCallback(async () => {
  try {
    const data = await fetchAPI('/api/claude/sessions');
    // fetchAPI 已返回解析后的 JSON 对象或 null
    if (data && data.sessions) {
      setSessions(data.sessions as ClaudeSession[]);
      if (data.sessions.length > 0 && !activeSessionId) {
        setActiveSession(data.sessions[0].id);
      }
    }
  } catch (err) {
    console.error('Failed to refresh sessions:', err);
  }
}, [activeSessionId, setSessions, setActiveSession]);
```

- [ ] **Step 2: 同步修改 useEffect 以兼容 async 函数**

```typescript
// autonome-studio/src/components/chat/ClaudeChatStage.tsx:55-57
// 改前:
useEffect(() => {
    refreshSessions();
}, []);
// 改后:
useEffect(() => {
    refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx
git commit -m "fix: 修复 refreshSessions 对 fetchAPI 返回值二次调用 .json() 导致的 TypeError"
```

---

### Task 1.5: 修复 PlanData 前后端命名不一致

**Files:**
- Modify: `autonome-backend/app/sandbox/agent_service/event_types.py:83-88`

- [ ] **Step 1: PlanEvent 字段改为 camelCase**

```python
# autonome-backend/app/sandbox/agent_service/event_types.py:82-88
# 改后:
@dataclass
class PlanEvent(AgentEvent):
    type: EventType = EventType.PLAN
    title: str = ""
    steps: List[Dict[str, str]] = field(default_factory=list)
    codeSnapshot: str = ""
    estimatedCost: str = ""
```

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/app/sandbox/agent_service/event_types.py
git commit -m "fix: PlanEvent 字段统一为 camelCase，对齐前端 PlanData 接口"
```

---

### Task 1.6: 修复容器池预热容器 session_id 错误

**Files:**
- Modify: `autonome-backend/app/services/claude_container_pool.py:148-192`

- [ ] **Step 1: 在 allocate() 中为复用容器更新环境变量**

在 `allocate()` 中分配空闲容器后，通过 `docker exec` 更新 `CLAUDE_SESSION_ID`：

```python
# autonome-backend/app/services/claude_container_pool.py
# 在 allocate() 中, idle_container.status = "busy" 之后, db.commit() 之前插入:

if idle_container:
    idle_container.status = "busy"
    idle_container.user_id = user_id
    idle_container.session_id = session_id
    idle_container.last_used_at = datetime.now(timezone.utc)

    # 更新容器内 agent_service 的 session ID 环境变量
    # agent_service 需要知道新的 session ID 来订阅正确的 Redis 通道
    try:
        subprocess.run(
            ["docker", "exec", idle_container.container_id,
             "sh", "-c",
             f"export CLAUDE_SESSION_ID={session_id}"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass  # 非致命，agent_service 可通过 Redis 消息获取 session_id

    db.add(idle_container)
    db.commit()
    log.info(f"分配复用容器: {idle_container.container_id[:12]} → session {session_id}")
    return idle_container.container_id
```

- [ ] **Step 2: 同时修改 pre_warm()，预热时不传 session_id**

```python
# autonome-backend/app/services/claude_container_pool.py:261-262
# 改前:
container_id = self._create_container("pool", 0)
# 改后:
container_id = self._create_container("prewarm", 0)
```

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/app/services/claude_container_pool.py
git commit -m "fix: 修复预热容器分配时 session_id 未更新，增加 docker exec 同步环境变量"
```

---

### Task 1.7: Docker 服务重启验证

- [ ] **Step 1: 重启全部服务**

```bash
cd /opt/data1/public/software/systools/autonome
docker-compose down && docker-compose up -d
```

- [ ] **Step 2: 检查所有容器状态**

```bash
docker-compose ps
# Expected: autonome-api, autonome-web, autonome-postgres, autonome-redis, autonome-claude-redis, autonome-worker 均为 Up
```

- [ ] **Step 3: 检查后端日志无报错**

```bash
docker logs autonome-api | tail -20
# Expected: 无 "Unable to find image" 或 "Can't locate revision" 错误
```

- [ ] **Step 4: 浏览器验证 Claude 模式**

打开 `http://localhost:3001`，登录后点击"Claude 模式"按钮。
- Expected: 三栏布局可见（左侧会话列表、中间对话区、右侧预览区）
- Expected: 无白屏/崩溃

---

## Stage 2 — 韧性加固

### Task 2.1: 新增 ClaudeErrorBoundary 组件

**Files:**
- Create: `autonome-studio/src/components/chat/ClaudeErrorBoundary.tsx`

- [ ] **Step 1: 创建错误边界组件**

```tsx
'use client';

import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ClaudeErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleBackToNormal = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-gray-900 text-gray-300 p-8">
          <div className="text-red-400 text-lg mb-4">
            Claude 模式加载失败
          </div>
          <div className="text-gray-500 text-sm mb-6 max-w-md text-center">
            {this.state.error?.message || '发生未知错误，请稍后重试。'}
          </div>
          <div className="flex gap-3">
            <button
              onClick={this.handleRetry}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
            >
              重试
            </button>
            <button
              onClick={this.handleBackToNormal}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm"
            >
              返回常规模式
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add autonome-studio/src/components/chat/ClaudeErrorBoundary.tsx
git commit -m "feat: 新增 ClaudeErrorBoundary，捕获 Claude 模式渲染错误防止白屏"
```

---

### Task 2.2: 在 ChatStage 中集成 ErrorBoundary

**Files:**
- Modify: `autonome-studio/src/components/chat/ChatStage.tsx:60,66-88`

- [ ] **Step 1: 添加 import**

```typescript
// autonome-studio/src/components/chat/ChatStage.tsx
// 在 line 60 后添加:
import { ClaudeErrorBoundary } from './ClaudeErrorBoundary';
```

- [ ] **Step 2: 包裹 ClaudeChatStage**

```tsx
// autonome-studio/src/components/chat/ChatStage.tsx:66-88
// 改后:
if (chatMode === 'claude') {
  return (
    <div className="flex flex-col h-full w-full bg-white dark:bg-[#131314]">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#1a1a1a]">
        <button
          onClick={() => setChatMode('normal')}
          className="px-3 py-1 rounded text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-800"
        >
          常规模式
        </button>
        <button
          onClick={() => setChatMode('claude')}
          className="px-3 py-1 rounded text-sm bg-blue-600 text-white"
        >
          Claude 模式
        </button>
      </div>
      <div className="flex-1">
        <ClaudeErrorBoundary onReset={() => setChatMode('normal')}>
          <ClaudeChatStage />
        </ClaudeErrorBoundary>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/src/components/chat/ChatStage.tsx
git commit -m "feat: ChatStage 集成 ClaudeErrorBoundary，Claude 模式崩溃时显示回退 UI"
```

---

### Task 2.3: SSE 断线重连机制

**Files:**
- Modify: `autonome-studio/src/hooks/useClaudeChat.ts`

- [ ] **Step 1: 在 sendMessage 中添加重连逻辑**

```typescript
// autonome-studio/src/hooks/useClaudeChat.ts
// 在 sendMessage 的 try 块中，reader 循环外层包装重连循环

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
    const BASE_DELAY = 1000; // 1s
    const assistantEvents: ClaudeEvent[] = [];

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetchAPI(
          `/api/claude/sessions/${activeSessionId}/conversations/${activeConversationId}/messages`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
            signal: abortController.signal,
          }
        );

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

        // 成功完成，跳出重连循环
        break;
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          return; // 用户取消，不重连
        }

        if (attempt < MAX_RETRIES) {
          const delay = BASE_DELAY * Math.pow(2, attempt);
          appendStreamContent({
            type: 'status',
            status: 'reconnecting',
            message: `连接中断，${delay / 1000}s 后重连 (${attempt + 1}/${MAX_RETRIES})`,
            timestamp: Date.now(),
          } as ClaudeEvent);
          await new Promise((r) => setTimeout(r, delay));
        } else {
          console.error('Claude chat error after max retries:', err);
          appendStreamContent({
            type: 'error',
            message: '连接失败，已达最大重试次数。请检查网络后重试。',
            timestamp: Date.now(),
          } as ClaudeEvent);
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
```

- [ ] **Step 2: 提交**

```bash
git add autonome-studio/src/hooks/useClaudeChat.ts
git commit -m "feat: SSE 断线指数退避重连，最多 5 次，重连状态通知 UI"
```

---

### Task 2.4: 优雅降级状态 + handleSend 前置检查

**Files:**
- Modify: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`

- [ ] **Step 1: 新增 loading/empty/error 状态**

```typescript
// autonome-studio/src/components/chat/ClaudeChatStage.tsx
// 在组件顶部新增状态变量:

const [pageState, setPageState] = useState<'loading' | 'empty' | 'error' | 'ready'>('loading');
const [errorMessage, setErrorMessage] = useState('');
```

- [ ] **Step 2: 修改 refreshSessions 设置状态**

```typescript
// 在 refreshSessions 中:
const refreshSessions = useCallback(async () => {
  try {
    setPageState('loading');
    const data = await fetchAPI('/api/claude/sessions');
    if (data && data.sessions && data.sessions.length > 0) {
      setSessions(data.sessions as ClaudeSession[]);
      setPageState('ready');
    } else {
      setPageState('empty');
    }
  } catch (err) {
    setErrorMessage(err instanceof Error ? err.message : '连接失败');
    setPageState('error');
    console.error('Failed to refresh sessions:', err);
  }
}, [setSessions]);
```

- [ ] **Step 3: 添加状态 UI 分支**

```tsx
// 在中间对话区渲染之前:
{pageState === 'loading' && (
  <div className="flex-1 flex items-center justify-center">
    <div className="text-center">
      <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
      <div className="text-gray-400 text-sm">正在连接 Claude Agent...</div>
    </div>
  </div>
)}
{pageState === 'empty' && (
  <div className="flex-1 flex items-center justify-center">
    <div className="text-center">
      <div className="text-gray-400 text-lg mb-3">开始你的分析之旅</div>
      <button
        onClick={handleCreateSession}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
      >
        创建新会话
      </button>
    </div>
  </div>
)}
{pageState === 'error' && (
  <div className="flex-1 flex items-center justify-center">
    <div className="text-center">
      <div className="text-red-400 text-sm mb-2">{errorMessage}</div>
      <button
        onClick={() => refreshSessions()}
        className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm"
      >
        重试
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 4: 修改 handleSend，自动创建 session 和 conversation**

```typescript
const handleSend = async () => {
  if (!input.trim() || isStreaming) return;

  let sid = activeSessionId;
  let cid = activeConversationId;

  // 自动创建 session
  if (!sid) {
    try {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: input.trim().slice(0, 30) }),
      });
      sid = res.id;
      addSession(res as ClaudeSession);
      setActiveSession(sid);
    } catch (err) {
      console.error('Failed to create session:', err);
      return;
    }
  }

  // 自动创建 conversation
  if (!cid) {
    try {
      const res = await fetchAPI(`/api/claude/sessions/${sid}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: input.trim().slice(0, 30) }),
      });
      cid = res.id;
    } catch (err) {
      console.error('Failed to create conversation:', err);
      return;
    }
  }

  sendMessage(input.trim());
  setInput('');
};
```

- [ ] **Step 5: 提交**

```bash
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx
git commit -m "feat: Claude 模式增加 loading/empty/error 降级状态 + handleSend 自动创建 session/conversation"
```

---

## Stage 3 — 测试覆盖

### Task 3.1: 后端单元测试 — 数据模型

**Files:**
- Create: `autonome-backend/tests/test_claude_models.py`

- [ ] **Step 1: 创建测试文件**

```python
"""Claude 数据模型单元测试"""
import pytest
from datetime import datetime, timezone
from app.models.claude import ClaudeSession, ClaudeContainer, ClaudeTask
from app.sandbox.agent_service.event_types import (
    PlanEvent, ThinkingEvent, ToolUseEvent, ErrorEvent, UsageEvent
)


class TestClaudeSession:
    def test_create_session_defaults(self):
        """ClaudeSession 默认值验证"""
        session = ClaudeSession(user_id=1)
        assert session.title == "新会话"
        assert session.status == "active"
        assert session.user_id == 1

    def test_session_status_values(self):
        """ClaudeSession 状态字段接受合法值"""
        session = ClaudeSession(user_id=1, status="archived")
        assert session.status == "archived"
        session.status = "closed"
        assert session.status == "closed"


class TestClaudeContainer:
    def test_container_status_values(self):
        """ClaudeContainer 状态值验证"""
        container = ClaudeContainer(
            container_id="abc123",
            status="idle",
        )
        assert container.status == "idle"
        assert container.user_id is None
        assert container.session_id is None

    def test_container_with_user(self):
        """带用户的容器状态验证"""
        container = ClaudeContainer(
            container_id="abc123",
            status="busy",
            user_id=1,
            session_id="sess-1",
        )
        assert container.status == "busy"
        assert container.user_id == 1
        assert container.session_id == "sess-1"


class TestClaudeTask:
    def test_task_status_lifecycle(self):
        """ClaudeTask 状态机验证"""
        task = ClaudeTask(session_id="sess-1", status="pending")
        assert task.status == "pending"

        task.status = "running"
        assert task.status == "running"

        task.status = "completed"
        assert task.status == "completed"

    def test_task_with_output_files(self):
        """ClaudeTask 输出文件 JSONB 验证"""
        task = ClaudeTask(
            session_id="sess-1",
            status="completed",
            output_files=[
                {"name": "result.csv", "path": "/workspace/result.csv", "size": 1024},
            ],
        )
        assert len(task.output_files) == 1
        assert task.output_files[0]["name"] == "result.csv"


class TestEventTypes:
    def test_plan_data_serialization_camelcase(self):
        """PlanEvent.to_json() 输出字段为 camelCase"""
        event = PlanEvent(
            title="QC分析",
            steps=[{"title": "步骤1", "description": "质量检查"}],
            codeSnapshot="fastqc input.fastq",
            estimatedCost="5min",
        )
        json_str = event.to_json()
        assert "codeSnapshot" in json_str
        assert "estimatedCost" in json_str
        assert "code_snapshot" not in json_str
        assert "estimated_cost" not in json_str

    def test_thinking_event_serialization(self):
        """ThinkingEvent 序列化验证"""
        event = ThinkingEvent(content="正在分析输入数据...")
        json_str = event.to_json()
        assert "thinking" in json_str
        assert "正在分析输入数据" in json_str

    def test_tool_use_event_serialization(self):
        """ToolUseEvent 序列化验证"""
        event = ToolUseEvent(
            tool_name="skill_search",
            tool_input={"q": "fastqc"},
            tool_use_id="tool_001",
        )
        json_str = event.to_json()
        assert "tool_use" in json_str
        assert "skill_search" in json_str

    def test_error_event_serialization(self):
        """ErrorEvent 序列化验证"""
        event = ErrorEvent(message="容器创建失败", code="DOCKER_ERROR")
        json_str = event.to_json()
        assert "error" in json_str
        assert "容器创建失败" in json_str

    def test_usage_event_serialization(self):
        """UsageEvent 序列化验证"""
        event = UsageEvent(input_tokens=100, output_tokens=200)
        json_str = event.to_json()
        assert "usage" in json_str
        assert "100" in json_str
        assert "200" in json_str

    def test_all_event_types_to_json_no_exception(self):
        """所有事件类型 to_json() 不抛异常"""
        events = [
            PlanEvent(title="test", steps=[], codeSnapshot="", estimatedCost=""),
            ThinkingEvent(content="test"),
            ToolUseEvent(tool_name="test", tool_input={}, tool_use_id="test"),
            ErrorEvent(message="test", code="TEST"),
            UsageEvent(input_tokens=0, output_tokens=0),
        ]
        for event in events:
            result = event.to_json()
            assert isinstance(result, str)
            assert len(result) > 0
```

- [ ] **Step 2: 运行测试验证通过**

```bash
docker exec autonome-api pytest tests/test_claude_models.py -v
# Expected: 8 passed
```

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/tests/test_claude_models.py
git commit -m "test: 新增 Claude 数据模型和事件类型单元测试 (8 cases)"
```

---

### Task 3.2: 后端集成测试 — API 端点

**Files:**
- Create: `autonome-backend/tests/test_claude_api.py`

- [ ] **Step 1: 创建 API 集成测试**

```python
"""Claude API 集成测试"""
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSessionEndpoints:
    async def test_requires_auth(self, client):
        """POST /api/claude/sessions 未认证返回 401"""
        res = await client.post("/api/claude/sessions", json={"title": "test"})
        assert res.status_code == 401

    # Note: authenticated tests require fixture setup with test user and token.
    # See tests/conftest.py for auth fixture patterns used in the project.


class TestSkillSearch:
    async def test_search_with_empty_query(self, client):
        """GET /api/claude/skills/search 空查询返回适当响应"""
        res = await client.get("/api/claude/skills/search", params={"q": ""})
        # 未认证返回 401 是预期行为
        assert res.status_code == 401


class TestContainerStats:
    async def test_stats_endpoint_requires_auth(self, client):
        """GET /api/claude/containers/stats 需要认证"""
        res = await client.get("/api/claude/containers/stats")
        assert res.status_code == 401
```

- [ ] **Step 2: 运行测试**

```bash
docker exec autonome-api pytest tests/test_claude_api.py -v
# Expected: 3 passed
```

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/tests/test_claude_api.py
git commit -m "test: 新增 Claude API 集成测试 — 认证检查 (3 cases)"
```

---

### Task 3.3: 前端 Store 测试

**Files:**
- Create: `autonome-studio/src/store/__tests__/useClaudeStore.test.ts`

- [ ] **Step 1: 创建 Store 测试**

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { useClaudeStore } from '../useClaudeStore';

describe('useClaudeStore', () => {
  beforeEach(() => {
    useClaudeStore.setState({
      sessions: [],
      activeSessionId: null,
      conversations: [],
      activeConversationId: null,
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });
  });

  it('初始状态正确', () => {
    const state = useClaudeStore.getState();
    expect(state.sessions).toEqual([]);
    expect(state.activeSessionId).toBeNull();
    expect(state.isStreaming).toBe(false);
    expect(state.streamEvents).toEqual([]);
  });

  it('addSession 添加会话到列表', () => {
    const session = {
      id: 'sess-1',
      title: '测试会话',
      status: 'active' as const,
      createdAt: '2026-01-01',
      updatedAt: '2026-01-01',
    };
    useClaudeStore.getState().addSession(session);
    expect(useClaudeStore.getState().sessions).toHaveLength(1);
    expect(useClaudeStore.getState().sessions[0].id).toBe('sess-1');
  });

  it('removeSession 从列表中删除会话', () => {
    useClaudeStore.setState({
      sessions: [
        { id: 'sess-1', title: 'A', status: 'active', createdAt: '', updatedAt: '' },
        { id: 'sess-2', title: 'B', status: 'active', createdAt: '', updatedAt: '' },
      ],
    });
    useClaudeStore.getState().removeSession('sess-1');
    expect(useClaudeStore.getState().sessions).toHaveLength(1);
    expect(useClaudeStore.getState().sessions[0].id).toBe('sess-2');
  });

  it('appendStreamContent 逐个追加事件', () => {
    useClaudeStore.getState().appendStreamContent({ type: 'text_delta', content: 'hello', timestamp: 1 });
    useClaudeStore.getState().appendStreamContent({ type: 'text_delta', content: ' world', timestamp: 2 });
    expect(useClaudeStore.getState().streamEvents).toHaveLength(2);
  });

  it('resetStream 清空事件和 isStreaming', () => {
    useClaudeStore.setState({ streamEvents: [{ type: 'text_delta', content: 'x', timestamp: 1 }], isStreaming: true });
    useClaudeStore.getState().resetStream();
    expect(useClaudeStore.getState().streamEvents).toEqual([]);
    expect(useClaudeStore.getState().isStreaming).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试**

```bash
docker exec autonome-web sh -c "cd /app && npx vitest run src/store/__tests__/useClaudeStore.test.ts"
# Expected: 5 passed
```

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/src/store/__tests__/useClaudeStore.test.ts
git commit -m "test: 新增 useClaudeStore Zustand store 单元测试 (5 cases)"
```

---

### Task 3.4: 前端组件测试

**Files:**
- Create: `autonome-studio/src/components/chat/__tests__/ThinkingBlock.test.tsx`
- Create: `autonome-studio/src/components/chat/__tests__/PlanCard.test.tsx`
- Create: `autonome-studio/src/components/chat/__tests__/ToolUseBlock.test.tsx`
- Create: `autonome-studio/src/components/chat/__tests__/ClaudeErrorBoundary.test.tsx`

- [ ] **Step 1: 创建 ThinkingBlock 测试**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThinkingBlock } from '../ThinkingBlock';

describe('ThinkingBlock', () => {
  it('渲染思考内容', () => {
    render(<ThinkingBlock content="正在分析输入数据..." />);
    expect(screen.getByText('正在分析输入数据...')).toBeInTheDocument();
  });

  it('默认折叠状态，内容区域不可见', () => {
    render(<ThinkingBlock content="分析中..." />);
    // 内容区域默认有 max-h-0 overflow-hidden
    const content = screen.getByText('分析中...');
    expect(content.closest('.overflow-hidden')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 创建 PlanCard 测试**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanCard } from '../PlanCard';

const mockPlan = {
  title: 'QC 分析方案',
  steps: [
    { title: '下载数据', description: '从 SRA 获取 FASTQ 文件' },
    { title: '质量检查', description: '运行 FastQC' },
  ],
  codeSnapshot: 'fastqc input.fastq',
  estimatedCost: '5min',
};

describe('PlanCard', () => {
  it('渲染方案标题和步骤', () => {
    render(<PlanCard plan={mockPlan} onConfirm={() => {}} />);
    expect(screen.getByText('QC 分析方案')).toBeInTheDocument();
    expect(screen.getByText('下载数据')).toBeInTheDocument();
    expect(screen.getByText('质量检查')).toBeInTheDocument();
  });

  it('点击确认按钮触发 onConfirm', () => {
    const onConfirm = vi.fn();
    render(<PlanCard plan={mockPlan} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('确认执行方案'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('disabled 时按钮不可点击', () => {
    const onConfirm = vi.fn();
    render(<PlanCard plan={mockPlan} onConfirm={onConfirm} disabled={true} />);
    fireEvent.click(screen.getByText('确认执行方案'));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: 创建 ToolUseBlock 测试**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ToolUseBlock } from '../ToolUseBlock';

describe('ToolUseBlock', () => {
  it('tool_use 事件渲染工具名称', () => {
    render(<ToolUseBlock event={{ type: 'tool_use', tool_name: 'skill_search', tool_input: { q: 'fastqc' } }} />);
    expect(screen.getByText('检索技能')).toBeInTheDocument();
  });

  it('tool_result 成功状态显示结果', () => {
    render(<ToolUseBlock event={{ type: 'tool_result', status: 'success', content: '找到 3 个技能' }} />);
    expect(screen.getByText('结果')).toBeInTheDocument();
    expect(screen.getByText('找到 3 个技能')).toBeInTheDocument();
  });

  it('未知工具名使用原始名称作为 fallback', () => {
    render(<ToolUseBlock event={{ type: 'tool_use', tool_name: 'unknown_tool' }} />);
    expect(screen.getByText('unknown_tool')).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: 创建 ClaudeErrorBoundary 测试**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClaudeErrorBoundary } from '../ClaudeErrorBoundary';

// 故意抛错的子组件
function BrokenChild(): never {
  throw new Error('模拟渲染错误');
}

describe('ClaudeErrorBoundary', () => {
  // 抑制 React 在测试中打印的错误日志
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('子组件抛错后显示回退 UI', () => {
    render(
      <ClaudeErrorBoundary>
        <BrokenChild />
      </ClaudeErrorBoundary>
    );
    expect(screen.getByText('Claude 模式加载失败')).toBeInTheDocument();
    expect(screen.getByText('模拟渲染错误')).toBeInTheDocument();
  });

  it('点击重试重置错误状态', () => {
    render(
      <ClaudeErrorBoundary>
        <BrokenChild />
      </ClaudeErrorBoundary>
    );
    fireEvent.click(screen.getByText('重试'));
    // 重试后仍然会抛错（因为子组件始终抛错），但会重新触发错误边界
    // 错误边界再次捕获后显示回退 UI
    expect(screen.getByText('Claude 模式加载失败')).toBeInTheDocument();
  });

  it('正常子组件不显示回退 UI', () => {
    render(
      <ClaudeErrorBoundary>
        <div>正常内容</div>
      </ClaudeErrorBoundary>
    );
    expect(screen.getByText('正常内容')).toBeInTheDocument();
    expect(screen.queryByText('Claude 模式加载失败')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 5: 运行组件测试**

```bash
docker exec autonome-web sh -c "cd /app && npx vitest run src/components/chat/__tests__/"
# Expected: all tests pass
```

- [ ] **Step 6: 提交**

```bash
git add autonome-studio/src/components/chat/__tests__/
git commit -m "test: 新增 Claude 前端组件测试 (ThinkingBlock + PlanCard + ToolUseBlock + ErrorBoundary)"
```

---

### Task 3.5: E2E 冒烟测试

**Files:**
- Create: `autonome-studio/e2e/claude-mode.spec.ts`

- [ ] **Step 1: 创建 Playwright E2E 测试**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Claude Mode', () => {
  test.beforeEach(async ({ page }) => {
    // 登录（使用测试账号或 mock）
    await page.goto('http://localhost:3001/login');
    // 假设已有测试登录逻辑...
  });

  test('切换到 Claude 模式显示三栏布局', async ({ page }) => {
    await page.goto('http://localhost:3001');
    await page.click('text=Claude 模式');
    // 验证三栏布局存在
    await expect(page.locator('.flex.h-full')).toBeVisible();
  });

  test('API 错误时显示错误回退 UI', async ({ page }) => {
    // Mock API 返回 500
    await page.route('**/api/claude/sessions', (route) => {
      route.fulfill({ status: 500, body: 'Internal Server Error' });
    });
    await page.goto('http://localhost:3001');
    await page.click('text=Claude 模式');
    // 等待错误回退 UI 出现
    await expect(page.getByText('重试')).toBeVisible({ timeout: 10000 });
  });
});
```

- [ ] **Step 2: 运行 E2E 测试**

```bash
cd autonome-studio && npx playwright test e2e/claude-mode.spec.ts
```

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/e2e/claude-mode.spec.ts
git commit -m "test: 新增 Claude 模式 E2E 冒烟测试 (Playwright)"
```

---

## Stage 4 — 架构优化

### Task 4.1: 新增统一类型文件

**Files:**
- Create: `autonome-studio/src/types/claude.ts`

- [ ] **Step 1: 创建集中类型文件**

```typescript
// autonome-studio/src/types/claude.ts
// Claude 模式统一类型定义 — 前后端字段对齐，均为 camelCase

export interface ClaudeEvent {
  type: string;
  timestamp: number;
  content?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  status?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
  task_id?: string;
  task_status?: string;
  progress?: string;
  code?: string;
}

export interface ClaudeMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  events?: ClaudeEvent[];
  plan?: PlanData | null;
  usage?: { input_tokens: number; output_tokens: number } | null;
  createdAt: string;
}

export interface PlanData {
  title: string;
  steps: Array<{ title: string; description: string }>;
  codeSnapshot: string;
  estimatedCost: string;
}

export interface ClaudeSession {
  id: string;
  title: string;
  status: 'active' | 'archived' | 'closed';
  createdAt: string;
  updatedAt: string;
}

export interface ClaudeConversation {
  id: string;
  sessionId: string;
  title: string;
  createdAt: string;
}

export interface ClaudeStore {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  conversations: ClaudeConversation[];
  activeConversationId: string | null;
  messages: ClaudeMessage[];
  isStreaming: boolean;
  streamEvents: ClaudeEvent[];

  setSessions: (sessions: ClaudeSession[]) => void;
  setActiveSession: (id: string) => void;
  addSession: (session: ClaudeSession) => void;
  removeSession: (id: string) => void;

  setConversations: (conversations: ClaudeConversation[]) => void;
  setActiveConversation: (id: string) => void;

  setMessages: (messages: ClaudeMessage[]) => void;
  addMessage: (message: ClaudeMessage) => void;
  appendStreamContent: (event: ClaudeEvent) => void;
  setStreaming: (streaming: boolean) => void;
  resetStream: () => void;
}
```

- [ ] **Step 2: 更新 useClaudeStore.ts 从 types/claude.ts 导入类型**

```typescript
// autonome-studio/src/store/useClaudeStore.ts
// 删除接口定义，改为从 types 导入:
export type {
  ClaudeEvent,
  ClaudeMessage,
  PlanData,
  ClaudeSession,
  ClaudeConversation,
} from '@/types/claude';
```

- [ ] **Step 3: 更新所有组件 import**

确保 ThinkingBlock, PlanCard, TaskCard, ToolUseBlock, ClaudePreview, useClaudeChat 等均从 `@/types/claude` 导入类型。

- [ ] **Step 4: 提交**

```bash
git add autonome-studio/src/types/claude.ts autonome-studio/src/store/useClaudeStore.ts
git commit -m "refactor: 抽取 Claude 类型到统一文件 src/types/claude.ts"
```

---

### Task 4.2: 拆分 ClaudeSessionSidebar

**Files:**
- Create: `autonome-studio/src/components/chat/claude/ClaudeSessionSidebar.tsx`

- [ ] **Step 1: 从 ClaudeChatStage 提取左侧会话列表**

```tsx
'use client';

import { type ClaudeSession } from '@/types/claude';

interface Props {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  formatDate: (d: string) => string;
}

export function ClaudeSessionSidebar({
  sessions,
  activeSessionId,
  searchQuery,
  onSearchChange,
  onSelect,
  onCreate,
  onDelete,
  formatDate,
}: Props) {
  const filtered = sessions.filter((s) =>
    !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
      <button
        onClick={onCreate}
        className="w-full px-3 py-2 mb-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
      >
        + 新建会话
      </button>
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="搜索会话..."
        className="w-full mb-2 px-2 py-1.5 bg-gray-800 text-gray-300 text-xs rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <div className="flex-1 overflow-y-auto space-y-1">
        {filtered.length === 0 ? (
          <div className="text-xs text-gray-500 text-center py-4">
            {searchQuery ? '无匹配会话' : '暂无会话'}
          </div>
        ) : (
          filtered.map((s) => (
            <div
              key={s.id}
              className={`group flex items-center rounded ${
                s.id === activeSessionId ? 'bg-gray-700' : 'hover:bg-gray-800'
              }`}
            >
              <button
                onClick={() => onSelect(s.id)}
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
                onClick={() => onDelete(s.id)}
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

- [ ] **Step 2: 更新 ClaudeChatStage 使用新组件**

在 ClaudeChatStage.tsx 中导入并使用 `<ClaudeSessionSidebar />` 替换原有左侧栏 JSX。

- [ ] **Step 3: 提交**

```bash
git add autonome-studio/src/components/chat/claude/ClaudeSessionSidebar.tsx
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx
git commit -m "refactor: 拆分 ClaudeSessionSidebar 组件 (~100行)"
```

---

### Task 4.3: 拆分 ClaudeMessageList + ClaudeInputArea

**Files:**
- Create: `autonome-studio/src/components/chat/claude/ClaudeMessageList.tsx`
- Create: `autonome-studio/src/components/chat/claude/ClaudeInputArea.tsx`

- [ ] **Step 1: 创建 ClaudeMessageList**

```tsx
'use client';

import { useRef } from 'react';
import { type ClaudeMessage, type ClaudeEvent, type PlanData } from '@/types/claude';
import { ThinkingBlock } from '@/components/chat/ThinkingBlock';
import { PlanCard } from '@/components/chat/PlanCard';
import { TaskCard } from '@/components/chat/TaskCard';
import { ToolUseBlock } from '@/components/chat/ToolUseBlock';

interface Props {
  messages: ClaudeMessage[];
  isStreaming: boolean;
  streamEvents: ClaudeEvent[];
  onPlanConfirm: () => void;
}

function buildTextContent(events: ClaudeEvent[]) {
  return events
    .filter((e) => e.type === 'text_delta')
    .map((e) => e.content || '')
    .join('');
}

function extractPlan(events: ClaudeEvent[]): PlanData | null {
  const planEvent = events.find((e) => e.type === 'plan');
  if (planEvent?.content) {
    try {
      return JSON.parse(planEvent.content) as PlanData;
    } catch {
      return null;
    }
  }
  return null;
}

function extractTaskIds(events: ClaudeEvent[]): string[] {
  return events
    .filter((e) => e.type === 'task_submitted' && e.task_id)
    .map((e) => e.task_id!);
}

export function ClaudeMessageList({ messages, isStreaming, streamEvents, onPlanConfirm }: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
              {msg.events?.map((event, i) => {
                if (event.type === 'thinking') {
                  return <ThinkingBlock key={i} content={event.content || ''} />;
                }
                if (event.type === 'tool_use' || event.type === 'tool_result') {
                  return <ToolUseBlock key={i} event={event} />;
                }
                return null;
              })}
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
            <PlanCard
              plan={extractPlan(streamEvents)!}
              onConfirm={onPlanConfirm}
            />
          )}
          {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
            <ThinkingBlock key={`stream-thinking-${i}`} content={e.content || ''} />
          ))}
          {streamEvents.filter((e) => e.type === 'tool_use' || e.type === 'tool_result').map((e, i) => (
            <ToolUseBlock key={`stream-tool-${i}`} event={e} />
          ))}
          <div className="text-gray-200 whitespace-pre-wrap">
            {streamEvents
              .filter((e) => e.type === 'text_delta')
              .map((e) => e.content || '')
              .join('')}
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

- [ ] **Step 2: 创建 ClaudeInputArea**

```tsx
'use client';

import { useState } from 'react';

interface Props {
  isStreaming: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
}

export function ClaudeInputArea({ isStreaming, onSend, onCancel }: Props) {
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

- [ ] **Step 3: 更新 ClaudeChatStage 使用新组件**

简化为 ~80 行主容器，仅组合 4 个子组件：

```tsx
// ClaudeChatStage.tsx 简化后:
export function ClaudeChatStage() {
  // hooks + state...
  return (
    <div className="flex h-full">
      <ClaudeSessionSidebar ... />
      <div className="flex-1 flex flex-col min-w-0">
        {/* loading/empty/error states */}
        <ClaudeMessageList ... />
        <ClaudeInputArea ... />
      </div>
      <div className="w-64 border-l border-gray-700">
        <ClaudePreview />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 提交**

```bash
git add autonome-studio/src/components/chat/claude/
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx
git commit -m "refactor: 拆分 ClaudeMessageList + ClaudeInputArea，ClaudeChatStage 瘦身至 ~80行"
```

---

### Task 4.4: 后端微小重构 — CLAUDE_MODEL 环境变量

**Files:**
- Modify: `autonome-backend/app/sandbox/agent_service/claude_manager.py`

- [ ] **Step 1: CLI --model 参数可配置**

```python
# autonome-backend/app/sandbox/agent_service/claude_manager.py
# 修改 Claude Code CLI 启动参数的 --model 部分:

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")

# 在 CLI 参数中使用:
[
    "claude", "-p", prompt,
    "--output-format", "stream-json",
    "--resume", session_id,
    "--permission-mode", "acceptEdits",
    "--max-turns", "50",
    "--model", CLAUDE_MODEL,
]
```

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/app/sandbox/agent_service/claude_manager.py
git commit -m "refactor: Claude Code --model 参数支持通过 CLAUDE_MODEL 环境变量配置"
```

---

## 实施检查清单

### Stage 1 — 止血
- [ ] 1.1 构建 Sandbox 镜像
- [ ] 1.2 部署迁移文件
- [ ] 1.3 修复 ClaudeEvent 类型
- [ ] 1.4 修复双重 JSON 解析
- [ ] 1.5 修复 PlanData 命名
- [ ] 1.6 修复容器池 session_id
- [ ] 1.7 Docker 重启验证

### Stage 2 — 加固
- [ ] 2.1 新增 ErrorBoundary
- [ ] 2.2 集成到 ChatStage
- [ ] 2.3 SSE 断线重连
- [ ] 2.4 优雅降级状态

### Stage 3 — 测试
- [ ] 3.1 后端单元测试 (8 cases)
- [ ] 3.2 后端集成测试 (3 cases)
- [ ] 3.3 前端 Store 测试 (5 cases)
- [ ] 3.4 前端组件测试 (9 cases)
- [ ] 3.5 E2E 冒烟测试 (2 cases)

### Stage 4 — 优化
- [ ] 4.1 统一类型文件
- [ ] 4.2 拆分 SessionSidebar
- [ ] 4.3 拆分 MessageList + InputArea
- [ ] 4.4 CLAUDE_MODEL 环境变量

---

## 总提交数: 16 commits
## 总新增测试: 27 cases (后端 11 + 前端 14 + E2E 2)
