# Claude Code Agent 模式 — 升级方案设计 V2

> 基于 `docs/claude_module.md` 进行全面审计后的分阶段升级方案。
> 创建时间: 2026-05-02
> 状态: 待审批

---

## 一、审计总结

### 1.1 设计文档功能达成情况

对照 `docs/claude_module.md` Phase 1-5 规格，全部 22 个文件存在且有实质性实现。

| Phase | 描述 | 状态 |
|-------|------|------|
| Phase 1 | 基础设施（5表、Agent Service、Redis桥接、API路由、前端核心） | 完整 |
| Phase 2 | 工具与能力（技能检索、重型任务API、PlanCard、TaskCard） | 完整 |
| Phase 3 | 任务管理（预览区、工作区文件API、会话管理增强） | 完整 |
| Phase 4 | 容器池（预热/分配/回收、stats API） | 完整 |
| Phase 5 | UX打磨（ToolUseBlock、经验萃取API） | 完整 |

### 1.2 上一轮升级（V1）已完成项

最近 6 次提交（`6e8797c` → `1d8a1c2`）完成了 V1 方案的 Stage 1-3：

- Stage 1（止血）：双重 JSON 解析修复、TypeScript 类型断言修复、容器池 session_id 传递
- Stage 2（韧性加固）：ClaudeErrorBoundary、SSE 断线重连、优雅降级状态、handleSend 前置检查
- Stage 3（测试覆盖）：后端 27 测试用例、前端 store/hook 测试、组件测试

### 1.3 本次审计发现的遗留问题

| # | 严重度 | 问题 | 位置 |
|---|--------|------|------|
| 1 | **致命** | SSE 流接收断裂：`fetchAPI` 总是 `response.json()`，SSE 响应解析失败 | `useClaudeChat.ts:51` |
| 2 | **致命** | DB Schema 不一致：迁移 `message_id NOT NULL` vs API 允许不传 | 迁移 + `routes/claude.py` |
| 3 | **致命** | 容器池 env 注入方案无效：`docker exec ... sh -c "export X=Y"` 无法影响已运行进程 | `container_pool.py:195` |
| 4 | **高** | 任务提交不执行：`submit_heavy_task` 只写 DB 记录，未 dispatch Celery | `routes/claude.py:326` |
| 5 | **高** | PlanEvent 解析逻辑错误：前端在 `event.content` 找 JSON，但 PlanEvent 字段在顶层 | `ClaudeChatStage.tsx:179` |
| 6 | **中** | 无对话管理 UI：侧栏只显示 Session，不显示/切换 Conversations | 前端 |
| 7 | **中** | ClaudeChatStage 401 行：超过 200 行目标，混合多种职责 | `ClaudeChatStage.tsx` |
| 8 | **低** | claude-redis 端口 6380：非标准端口，调试不便 | `docker-compose.yml` |
| 9 | **低** | API 响应格式不统一：17 个端点各不同格式 | `routes/claude.py` |

---

## 二、升级方案：渐进式两阶段

### 总体策略

Stage 1 聚焦致命修复 + 核心链路打通，恢复端到端可用性。Stage 2 聚焦重构 + UI 完善 + 类型安全。

```
Stage 1 (致命修复+核心链路)
  ├── 1.1 SSE 流接收修复
  ├── 1.2 DB Schema 修复
  ├── 1.3 容器池 session 动态分配
  ├── 1.4 Celery 任务 dispatch 集成
  └── 1.5 API 响应格式统一
       │
       ▼
Stage 2 (前端重构+UI完善)
  ├── 2.1 ClaudeChatStage 组件拆分
  ├── 2.2 对话管理 UI
  ├── 2.3 PlanEvent 解析修复
  ├── 2.4 类型安全加固
  └── 2.5 前后端字段命名对齐
```

---

## 三、Stage 1 详细设计

### 3.1 SSE 流接收修复

**根因**：`fetchAPI`（`@/lib/api.ts:246`）对所有响应调用 `response.json()`。SSE 是 `text/event-stream` 而非 JSON，导致 `SyntaxError`。`useClaudeChat.ts` 中的 `.body?.getReader()` 永远无法执行。

**修复**：`sendMessage` 中使用原生 `fetch()` + `createSSEUrl()` 直接获取 SSE 流。保留 `fetchAPI` 用于 CRUD API 调用。

**关键代码变更** (`useClaudeChat.ts`):

```typescript
// 修复前：fetchAPI 返回 JSON，丢失 Response body
const response = await fetchAPI(`/api/claude/sessions/.../messages`, {
  method: 'POST',
  ...
});
const reader = response.body?.getReader(); // response 是 JSON 对象

// 修复后：原生 fetch 获取 SSE 流，通过 Authorization header 认证
import { BASE_URL, getToken } from '@/lib/api';

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
const reader = response.body?.getReader(); // 原生 Response body
```

**影响文件**：`useClaudeChat.ts`

### 3.2 DB Schema 修复

**根因**：迁移 `claude_agent_tables.py:89` 中 `message_id UUID NOT NULL`，`session_id UUID NOT NULL`。但 `POST /tasks/submit` 允许不传这两个字段（由 Claude Code Agent Service 调用时可能不提供）。

**修复**：新建迁移文件，ALTER 两个字段为 nullable。

```sql
ALTER TABLE claude_task ALTER COLUMN message_id DROP NOT NULL;
ALTER TABLE claude_task ALTER COLUMN session_id DROP NOT NULL;
```

同时修复 `submit_heavy_task` 路由，根据 `conversation_id` 反查 `session_id` 并赋值。

**影响文件**：新 Alembic 迁移 + `routes/claude.py`

### 3.3 容器池 session 动态分配

**根因**：预热容器用 `session_id="prewarm"` 启动 agent_service。分配时 `docker exec ... sh -c "export X=Y"` 在 subshell 中执行，不影响 agent_service 进程的环境变量。

**修复**：使用 Redis broadcast 通道实现 session 动态分配。

```
预热阶段：
  container pool → docker run → agent_service 启动
  agent_service → subscribe "claude:pool:broadcast"

分配阶段：
  allocate() → Redis PUBLISH {action: "assign", container_id: "abc123", session_id: "xyz"}
  agent_service 收到消息 → unsubscribe broadcast → subscribe "claude:session:xyz"
```

容器标识：agent_service 启动时通过 Docker hostname（默认 = container_id 前 12 位）或 `/proc/self/cgroup` 获取自己的 container_id。

**新增 Redis 通道**：

| 通道 | 方向 | 用途 |
|------|------|------|
| `claude:pool:broadcast` | Backend → Agent containers | 容器分配广播 |

**影响文件**：
- `agent_service/main.py`：启动时从 hostname 获取 container_id，先 subscribe broadcast
- `agent_service/redis_client.py`：增加 `unsubscribe()` + `subscribe_session()` 方法
- `container_pool.py`：`allocate()` 中 publish 分配消息，删除无效的 `docker exec export`
- `redis_bridge.py`：增加 `publish_allocation()` 方法

### 3.4 Celery 任务 dispatch 集成

**根因**：`submit_heavy_task` 只创建 DB 记录，状态永远停留在 `pending`，没有实际执行。

**修复**：在任务创建后 dispatch Celery 任务：

```python
from app.services.celery_app import execute_skill_task

# 创建记录后
celery_result = execute_skill_task.delay(
    task_id=str(task.id),
    skill_id=req.skill_id,
    code=req.code,
    parameters=req.parameters or {},
)
task.celery_task_id = celery_result.id
task.status = "running"
```

需要确认 `app/services/celery_app.py` 中已有 `execute_skill_task` 任务定义，或新增。

**影响文件**：`routes/claude.py` + `app/services/celery_app.py`

### 3.5 API 响应格式统一

**根因**：Claude API 端点响应格式不一致，与其他模块的 `{success, data, error}` 信封不统一。

**修复**：所有 17 个端点增加统一的响应信封。新增 `success` 字段，原数据移入 `data`。前端同步更新（因 Stage 1 已涉及前端修改，一并调整成本低）。

```python
# 统一前
return {"sessions": [...]}

# 统一后
return {"success": True, "data": {"sessions": [...]}}
```

**注意**：前端 `ClaudeChatStage.tsx` 和 `useClaudeChat.ts` 中所有 `fetchAPI('/api/claude/...')` 的返回值解构需同步更新（如 `data.sessions` 替代 `response.sessions`）。`fetchAPI` 对非 2xx 已抛异常，`success` 字段主要用于 SSE 事件和文档一致性。

**影响文件**：`routes/claude.py` + `ClaudeChatStage.tsx` + `useClaudeChat.ts`

---

## 四、Stage 2 详细设计

### 4.1 ClaudeChatStage 组件拆分

**当前**：`ClaudeChatStage.tsx` 401 行，混合 session CRUD + 消息渲染 + 流式处理 + 输入管理。

**目标结构**：

```
components/chat/claude/
├── ClaudeChatStage.tsx          # 主容器 ~80行（布局编排 + hook 调用）
├── ClaudeSessionSidebar.tsx     # 左栏会话列表 ~100行（新建）
├── ClaudeMessageList.tsx        # 中间消息时间线 ~100行（新建）
├── ClaudeInputArea.tsx          # 底部输入区 ~50行（新建）
├── ClaudePreview.tsx            # 右栏预览（已有）
├── ClaudeErrorBoundary.tsx      # 错误边界（已有）
├── ThinkingBlock.tsx            # 已有
├── PlanCard.tsx                 # 已有
├── TaskCard.tsx                 # 已有
└── ToolUseBlock.tsx             # 已有
```

**各组件职责**：
- **ClaudeSessionSidebar**：接收 `sessions`, `activeSessionId`, `onSelect`, `onCreate`, `onDelete` — 纯展示
- **ClaudeMessageList**：接收 `messages`, `streamEvents`, `isStreaming` — 消息时间线 + 流式渲染
- **ClaudeInputArea**：接收 `onSend`, `onCancel`, `isStreaming` — 输入框 + 发送/停止按钮
- **ClaudeChatStage**：编排子组件，仅保留 hook 调用和事件处理

**新增文件**：`ClaudeSessionSidebar.tsx`、`ClaudeMessageList.tsx`、`ClaudeInputArea.tsx`

### 4.2 对话管理 UI

**需求**：Session 侧栏下方展示 conversations 列表，支持创建和切换。

**UI 布局**：

```
┌──────────────────┐
│ + 新建会话         │
│ [搜索会话...]      │
│                  │
│ ▼ 会话 A  (展开)   │  ← 当前选中 session
│   ├ 对话 1 (选中)  │  ← activeConversation
│   ├ 对话 2        │
│   + 新对话        │
│                  │
│   会话 B  (折叠)   │
│   会话 C  (折叠)   │
└──────────────────┘
```

**API 变更**：
- `GET /api/claude/sessions/{id}` 扩展返回 `conversations` 列表
- `POST .../conversations` 已存在，前端调用即可

**交互**：
- 点击 session 展开/折叠 conversations 列表
- 选中 conversation 时加载其消息历史（已有 `loadMessages`）
- 发送消息前若无 conversation 则自动创建（已有 `handleSend` 前置检查）

**影响文件**：`ClaudeSessionSidebar.tsx` + `routes/claude.py`

### 4.3 PlanEvent 解析修复

**根因**：`extractPlan` 在 `event.content` 中找 JSON 字符串，但 `PlanEvent` 的 title/steps/codeSnapshot 等字段在事件顶层。

**修复**：直接从 event 顶层字段构造 PlanData，移除多余的 `JSON.parse`。

```typescript
const extractPlan = (events: ClaudeEvent[]): PlanData | null => {
  const e = events.find(ev => ev.type === 'plan');
  if (!e) return null;
  return {
    title: String(e.title || ''),
    steps: (e.steps as PlanStep[]) || [],
    codeSnapshot: String(e.codeSnapshot || ''),
    estimatedCost: String(e.estimatedCost || ''),
  };
};
```

同时确认 `PlanEvent.to_json()` 输出字段名与前端 `PlanData` 接口对齐。

**影响文件**：`ClaudeChatStage.tsx`（extractPlan 函数） + `event_types.py`

### 4.4 类型安全加固

**当前问题**：`ClaudeEvent` 只有 `[key: string]: unknown` index signature，缺少按事件类型的 narrowing。

**修复**：在 `types/claude.ts` 中新增 discriminant union 类型：

```typescript
type ClaudeThinkingEvent = { type: 'thinking'; content: string; timestamp: number };
type ClaudeTextDeltaEvent = { type: 'text_delta'; content: string; timestamp: number };
type ClaudePlanEvent = { type: 'plan'; title: string; steps: PlanStep[]; codeSnapshot: string; estimatedCost: string; timestamp: number };
type ClaudeToolUseEvent = { type: 'tool_use'; tool_name: string; tool_input: Record<string, unknown>; tool_use_id: string; timestamp: number };
type ClaudeToolResultEvent = { type: 'tool_result'; tool_name: string; tool_use_id: string; status: string; output: string; timestamp: number };
type ClaudeStatusEvent = { type: 'status'; status: string; message: string; timestamp: number };
type ClaudeErrorEvent = { type: 'error'; message: string; code?: string; timestamp: number };
type ClaudeUsageEvent = { type: 'usage'; input_tokens: number; output_tokens: number; timestamp: number };
type ClaudeTaskSubmittedEvent = { type: 'task_submitted'; task_id: string; celery_queue?: string; skill_id?: string; timestamp: number };
type ClaudeTaskStatusEvent = { type: 'task_status'; task_id: string; status: string; progress?: string; timestamp: number };

type ClaudeStreamEvent =
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

组件中使用 `switch/case` 按事件 type narrowing，消除所有 `as` 强制类型转换。

**影响文件**：`types/claude.ts` + `ClaudeMessageList.tsx`

### 4.5 前后端字段命名对齐

**确认内容**：
- `PlanEvent.to_json()` 输出 camelCase（`codeSnapshot`, `estimatedCost`）— 已确认通过 `asdict()` 序列化
- 前端 `PlanData` 接口使用 camelCase — 已确认对齐
- 其他事件类型的字段命名检查

**影响文件**：`event_types.py`（如需修复）

---

## 五、实施顺序

```
Stage 1 各任务独立可并行：
  ├── 1.1 SSE 流修复（前端）
  ├── 1.2 DB Schema（后端）
  ├── 1.3 容器动态分配（后端 + agent_service）
  ├── 1.4 Celery 集成（后端）
  └── 1.5 API 格式统一（后端）

Stage 2 有依赖关系：
  2.3 PlanEvent 修复 + 2.5 命名对齐（先）
     ↓
  2.1 组件拆分 + 2.2 对话管理 UI（并行）
     ↓
  2.4 类型安全加固（依赖拆分完成）
```

---

## 六、验证标准

### Stage 1 验收

- [ ] 用户可通过 Web UI 发送消息 → SSE 流正常接收并渲染
- [ ] 容器池预热和分配正常，无 env 注入报错
- [ ] 重型任务提交后自动 dispatch Celery，状态正常流转
- [ ] `POST /api/claude/tasks/submit` 不传 message_id 不报 DB 错误
- [ ] 所有 Claude API 端点响应格式统一为 `{success, data}`

### Stage 2 验收

- [ ] `ClaudeChatStage.tsx` ≤ 100 行，每个拆分文件 ≤ 200 行
- [ ] 侧栏可展开/折叠会话，显示 conversations 列表
- [ ] PlanCard 正确显示分析方案（从 plan 事件解析）
- [ ] `types/claude.ts` 含完整 discriminant union 类型
- [ ] 零 `as` 强制类型转换在事件处理代码中
- [ ] 前后端字段命名完全对齐

---

## 七、已知限制与后续增强

### 7.1 PlanEvent 生成链路不完整

`PlanEvent` 类型已定义且序列化正确，但 `ClaudeStreamParser` 当前只解析 Claude Code 原生的 JSONL 事件（system/assistant/user/result），不产出 `PlanEvent`。Claude Code 通过文本输出方案内容（text_delta 事件），前端无法将其解析为结构化 PlanCard。

**建议后续增强**（不纳入本次升级范围）：
- 在系统提示中要求 Claude Code 通过 `tool_use` 输出结构化方案 JSON
- 在 `ClaudeStreamParser` 中识别特定 tool_use（如 `output_plan`），产出 `PlanEvent`
- 或：agent_service 对 text_delta 累积文本进行后处理，用 LLM/正则提取方案结构

### 7.2 claude-redis 端口

`claude-redis` 使用 `--port 6380`（非标准 6379）以避免与主 Redis 冲突。由于 `claude_net` 为 `internal: true`，外部无法直接连接 debug。如需调试，可临时添加端口映射 `"6380:6380"`。

### 7.3 SSE 断线重连的消息去重

当前断线重连恢复后，可能重复收到部分事件（因 Redis pub/sub 无消息持久化）。需在后续版本中增加基于 message_id 的幂等去重。
