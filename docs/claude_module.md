# Claude Code Agent 模式 — 模块文档

> AUTONOME 平台 Claude Code 自主 Agent 模式完整实现文档。
> 更新时间: 2026-05-02

---

## 目录

1. [架构概览](#架构概览)
2. [数据模型](#数据模型)
3. [API 路由](#api-路由)
4. [Agent Service](#agent-service)
5. [Redis 通信桥接](#redis-通信桥接)
6. [前端组件](#前端组件)
7. [容器池管理](#容器池管理)
8. [Docker 基础设施](#docker-基础设施)
9. [通信流程](#通信流程)
10. [文件清单](#文件清单)

---

## 实施阶段

### Phase 1: Infrastructure (Minimum Viable Loop)
- 数据库迁移: `claude_agent_tables.py` — 5 张表 (claude_session, claude_conversation, claude_message, claude_task, claude_container)
- 数据模型: `app/models/claude.py` — SQLModel 定义 + UUID 主键 + JSONB 字段
- Docker 基础设施: docker-compose.yml 新增 `claude-redis` 服务 + `claude_net` 隔离网络
- Agent Service 核心: event_types.py (10 种事件) + redis_client.py (pub/sub) + stream_parser.py + claude_manager.py + main.py
- Backend 桥接: claude_redis_bridge.py + claude_session_manager.py
- API 路由: claude.py (Session CRUD + Message SSE)
- 前端核心: useClaudeStore.ts + useClaudeChat.ts + ClaudeChatStage.tsx + ThinkingBlock.tsx + ChatStage.tsx 模式切换
- **产出**: 用户可在 Web UI 发送消息 → Redis → Agent Service → Claude Code CLI → SSE 流返回前端

### Phase 2: Tools & Capabilities
- 技能检索 API: `GET /api/claude/skills/search` — 搜索 SkillAsset 表 (name/description/tags/skill_id)
- 重型任务 API: `POST /api/claude/tasks/submit` + `GET /api/claude/tasks/{id}` + `GET /api/claude/tasks`
- Agent Service 系统提示更新: 注入实际 API 端点 URL、沙箱执行能力、任务类型判断标准
- PlanCard 组件: 分析方案展示 + 确认按钮 → 自动发送确认指令
- TaskCard 组件: 任务状态显示 + 5s 自动轮询 (pending/running)
- **产出**: Claude Code 可检索技能、提交重型任务，前端可展示方案和任务状态

### Phase 3: Task Management & Preview
- ClaudePreview 组件: 右侧预览区，文件列表 (10s 自动刷新) + 图片预览 + CSV 表格 (前100行) + HTML iframe
- Workspace 文件 API: `GET /api/claude/workspace/files` + `GET /api/claude/workspace/files/content`
- 会话管理增强: 搜索过滤 + 删除按钮 (hover 显示 + 确认对话框) + 相对时间显示
- **产出**: 三栏布局完整可用，右侧预览区可浏览沙箱输出文件

### Phase 4: Container Pool & Fault Tolerance
- ClaudeContainerPool: 预热池 (POOL_MIN=1) + 动态分配 + 空闲超时回收 (30min) + 每用户并发限制 (3)
- Pool stats API: `GET /api/claude/containers/stats`
- main.py 集成: 启动预热 + 后台回收循环 (asyncio task)，关闭优雅清理
- **产出**: 容器资源受控管理，防止资源泄漏

### Phase 5: UX Polish
- ToolUseBlock 组件: 工具调用可视化 (tool_use 绿色展开 + tool_result 成功/失败状态)
- 经验萃取 API: `POST /api/claude/experiences` — Claude Code 分析经验写入 ExperienceAsset 表 (标题合并去重)
- **产出**: 工具调用过程可视化，分析经验沉淀到共享经验库

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                 │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ 会话列表  │  │  对话时间线 (SSE)  │  │  预览区 (文件/图表)   │  │
│  │ 侧边栏    │  │  - ThinkingBlock  │  │  - ClaudePreview     │  │
│  │           │  │  - PlanCard       │  │  - 图片/CSV/HTML     │  │
│  │           │  │  - TaskCard       │  │                      │  │
│  │           │  │  - ToolUseBlock   │  │                      │  │
│  └──────────┘  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SSE (text/event-stream)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (8000)                         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ /api/claude/*    │  │ ClaudeSessionMgr │  │ ClaudeRedisBridge│ │
│  │ - sessions CRUD  │  │ - 会话生命周期    │  │ - pub/sub 桥接  │  │
│  │ - skills/search  │  │ - 容器分配       │  │ - 心跳检测      │  │
│  │ - tasks/submit   │  │ - 消息持久化      │  │ - 消息路由      │  │
│  │ - workspace/files│  └──────────────────┘  └────────┬───────┘  │
│  │ - experiences    │                                  │          │
│  └─────────────────┘                                  │          │
│                                                       │          │
│  ┌──────────────────────────────────────────────────┐ │          │
│  │ PostgreSQL                                        │ │          │
│  │ - claude_session / claude_conversation            │ │          │
│  │ - claude_message / claude_task / claude_container │ │          │
│  └──────────────────────────────────────────────────┘ │          │
└───────────────────────────────────────────────────────┼──────────┘
                          ┌─────────────────────────────┘
                          │ Redis pub/sub
                          ▼
┌──────────────────────────────────┐    ┌──────────────────────────┐
│     Redis (claude-redis:6380)    │    │  Docker Network          │
│  ┌────────────────────────────┐  │    │  claude_net (internal)   │
│  │ claude:session:{sid}       │  │    └──────────────────────────┘
│  │ claude:session:{sid}:events│  │
│  │ claude:heartbeat:{sid}     │  │
│  └────────────────────────────┘  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│               Claude Sandbox Container                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Agent Service (main.py)                                     │  │
│  │  ├─ AgentRedisClient (订阅 Redis 消息通道)                   │  │
│  │  ├─ ClaudeManager (spawn Claude Code CLI)                   │  │
│  │  └─ ClaudeStreamParser (解析 JSONL → 事件)                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Claude Code CLI                                              │  │
│  │  claude -p "$system_prompt + $user_message"                  │  │
│  │         --output-format stream-json                           │  │
│  │         --resume $session_id                                  │  │
│  │         --max-turns 50                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ /workspace (读写)    /app/skills (只读)    /opt/conda (只读) │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 设计原则

- **双轨并行**: Claude Code Agent Mode 与现有 LangGraph Agent 独立运行，互不干扰
- **BYOK**: 用户自带 API Key (AES-256-GCM 加密存储)
- **长连接会话**: 基于 Redis pub/sub 的实时双向通信，支持 `--resume` 上下文保持
- **分布式执行**: 轻量任务沙箱直接执行，重型任务提交 Celery 异步队列
- **混合容器池**: 预热池 + 动态分配 + 空闲回收

---

## 数据模型

### 表结构

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `claude_session` | Claude 会话 (对应 Project) | id(UUID), user_id(int), title, status, container_id, metadata(JSONB) |
| `claude_conversation` | 会话下的对话轮次 | id(UUID), session_id(FK), title, claude_session_id, status |
| `claude_message` | 消息 (含完整事件流) | id(UUID), conversation_id(FK), role, content, events_json(JSONB), plan_json(JSONB), task_ids(UUID[]), usage_json(JSONB) |
| `claude_task` | 重型任务追踪 | id(UUID), message_id(FK), session_id(FK), celery_task_id, skill_id, status, code, parameters(JSONB), output_files(JSONB) |
| `claude_container` | 容器池管理 | id(UUID), container_id, status(idle/busy), user_id(FK), session_id(FK) |

### 模型文件

`autonome-backend/app/models/claude.py`

```python
class ClaudeSession(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key='"user".id', index=True)
    title: str = Field(default="新会话", max_length=500)
    status: str = Field(default="active", max_length=20)  # active/archived/closed
    container_id: Optional[str] = None
    meta_info: Optional[Dict] = Field(sa_column=Column(JSONB, name="metadata"))

class ClaudeConversation(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    session_id: Optional[UUID] = Field(foreign_key="claude_session.id", index=True)
    claude_session_id: Optional[str] = None  # Claude Code --resume id
    status: str = Field(default="active", max_length=20)

class ClaudeMessage(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    conversation_id: Optional[UUID] = Field(foreign_key="claude_conversation.id", index=True)
    role: str  # user / assistant / system
    events_json: Optional[List[Dict]] = Field(sa_column=Column(JSONB))  # 完整事件流
    plan_json: Optional[Dict] = Field(sa_column=Column(JSONB))  # 分析方案
    task_ids: Optional[List[UUID]] = Field(sa_column=Column(ARRAY(SA_UUID)))

class ClaudeTask(SQLModel, table=True):
    id: Optional[UUID] = Field(default=None, primary_key=True)
    celery_task_id: Optional[str] = None
    status: str = "pending"  # pending/running/completed/failed
    output_files: Optional[List[Dict]] = Field(sa_column=Column(JSONB))
```

---

## API 路由

所有路由挂载在 `/api/claude` 下，定义在 `autonome-backend/app/api/routes/claude.py`。

### Session CRUD

| Method | Path | 说明 |
|--------|------|------|
| POST | `/sessions` | 创建新 Claude 会话 |
| GET | `/sessions` | 列出用户的所有会话 |
| GET | `/sessions/{id}` | 获取会话详情 |
| PATCH | `/sessions/{id}` | 更新会话 (标题/状态) |
| DELETE | `/sessions/{id}` | 关闭会话 |

### Conversation & Message

| Method | Path | 说明 |
|--------|------|------|
| POST | `/sessions/{sid}/conversations` | 创建新对话 |
| POST | `/sessions/{sid}/conversations/{cid}/messages` | **发送消息 (SSE 流响应)** |
| GET | `/sessions/{sid}/conversations/{cid}/messages` | 获取对话历史消息 |

### Skill Search

| Method | Path | 说明 |
|--------|------|------|
| GET | `/skills/search?q=...&limit=10` | 搜索技能 (按名称/描述/标签/skill_id) |

返回:
```json
{
  "skills": [{
    "skill_id": "...",
    "name": "...",
    "description": "...",
    "executor_type": "Python_env",
    "category": "qc",
    "tags": ["fastqc", "quality"],
    "parameters_schema": {...}
  }],
  "total": 5
}
```

### Heavy Task

| Method | Path | 说明 |
|--------|------|------|
| POST | `/tasks/submit` | 提交重型任务到 Celery 队列 |
| GET | `/tasks/{id}` | 查询任务状态 |
| GET | `/tasks?status=running` | 列出任务 |

### Workspace Files

| Method | Path | 说明 |
|--------|------|------|
| GET | `/workspace/files?path=` | 列出沙箱 /workspace 文件 |
| GET | `/workspace/files/content?path=` | 获取文件内容 (图片/CSV/HTML/文本) |

### Experience

| Method | Path | 说明 |
|--------|------|------|
| POST | `/experiences` | 保存 Claude 分析经验到 ExperienceAsset |

### Container Pool

| Method | Path | 说明 |
|--------|------|------|
| GET | `/containers/stats` | 容器池状态统计 |

### SSE 事件类型

发送消息 (`POST .../messages`) 返回 `text/event-stream`，包含以下事件类型:

| 事件类型 | 说明 | 前端渲染 |
|---------|------|---------|
| `session_info` | 会话元信息 | - |
| `thinking` | Claude Code 思考过程 | ThinkingBlock |
| `text_delta` | 文本增量 | 直接显示 |
| `plan` | 分析方案 | PlanCard |
| `tool_use` | 工具调用开始 | ToolUseBlock |
| `tool_result` | 工具调用结果 | ToolUseBlock |
| `task_submitted` | 重型任务已提交 | TaskCard |
| `status` | Agent 状态变更 | 状态指示器 |
| `error` | 错误 | 错误提示 |
| `usage` | Token 用量 | 用量统计 |
| `end` | 本轮对话结束 | - |

---

## Agent Service

位于 `autonome-backend/app/sandbox/agent_service/`，在 Docker 沙箱容器中运行。

### 文件结构

```
sandbox/agent_service/
├── __init__.py
├── main.py              # 入口 (守护进程)
├── redis_client.py      # Redis pub/sub 客户端
├── claude_manager.py    # Claude Code CLI 进程管理
├── stream_parser.py     # JSONL 输出解析
└── event_types.py       # 事件类型定义 (10 种 dataclass)
```

### ClaudeManager — 系统提示

Claude Code 的系统提示定义了 AI Agent 的身份、工作流程和可用工具:

```
角色: 生物信息学数据分析专家
工作流程:
  1. 理解需求 → 2. 检索技能 → 3. 制定方案 → 4. 等待确认 → 5. 执行
工具:
  - /api/claude/skills/search     → 技能检索
  - /api/claude/tasks/submit      → 提交重型任务
  - /api/claude/tasks/{id}        → 查询任务状态
  - Sandbox shell 执行            → 轻量任务
关键行为准则:
  - 方案必须确认后执行
  - 优先复用已有技能
  - 中文沟通，中文注释
  - 轻量任务(<2min)沙箱执行，重型任务(>2min)Celery 执行
```

### Claude Code CLI 启动参数

```bash
claude -p "$SYSTEM_PROMPT\n\n---\n\n用户消息:\n$prompt" \
       --output-format stream-json \
       --resume $session_id \
       --permission-mode acceptEdits \
       --max-turns 50 \
       --model $model
```

### 事件类型定义

```python
class EventType(str, Enum):
    TEXT_DELTA = "text_delta"        # 文本增量
    TEXT_END = "text_end"            # 文本响应结束
    THINKING = "thinking"            # 思考过程
    TOOL_USE = "tool_use"            # 工具调用
    TOOL_RESULT = "tool_result"      # 工具结果
    PLAN = "plan"                    # 分析方案
    TASK_SUBMITTED = "task_submitted"  # 任务已提交
    TASK_STATUS = "task_status"      # 任务状态更新
    STATUS = "status"                # Agent 状态
    ERROR = "error"                  # 错误
    USAGE = "usage"                  # Token 用量
```

---

## Redis 通信桥接

### 通道设计

| 通道 | 方向 | 用途 |
|------|------|------|
| `claude:session:{sid}` | Backend → Agent | 用户消息、取消指令 |
| `claude:session:{sid}:events` | Agent → Backend | Claude Code 输出事件流 |
| `claude:heartbeat:{sid}` | Agent → Backend | 心跳 (10s 间隔，20s TTL) |

### 文件

- **Backend 侧**: `autonome-backend/app/services/claude_redis_bridge.py`
  - `get_claude_bridge()` — 获取全局 bridge 单例
  - `send_message()` — 发送消息到 Agent
  - `send_cancel()` — 发送取消指令
  - `subscribe_events()` — 异步迭代器，订阅事件流
  - `check_heartbeat()` — 检查 Agent 存活状态

- **Agent 侧**: `autonome-backend/app/sandbox/agent_service/redis_client.py`
  - `AgentRedisClient` — 连接、心跳、pub/sub 全封装
  - 指数退避自动重连 (最多 5 次)

---

## 前端组件

位于 `autonome-studio/src/`。

### 文件结构

```
src/
├── components/chat/
│   ├── ClaudeChatStage.tsx    # 主容器 (三栏布局)
│   ├── ThinkingBlock.tsx      # 可折叠思考过程
│   ├── PlanCard.tsx           # 分析方案卡片 + 确认按钮
│   ├── TaskCard.tsx           # 重型任务状态卡片 (5s 轮询)
│   ├── ToolUseBlock.tsx       # 工具调用可视化
│   └── ClaudePreview.tsx      # 右侧预览区 (文件/图表)
├── hooks/
│   └── useClaudeChat.ts       # SSE 通信 Hook
└── store/
    └── useClaudeStore.ts      # Zustand 状态管理
```

### Zustand Store

```typescript
interface ClaudeStore {
  sessions: ClaudeSession[]         // 会话列表
  activeSessionId: string | null    // 当前活跃会话
  conversations: ClaudeConversation[]
  activeConversationId: string | null
  messages: ClaudeMessage[]         // 消息历史
  isStreaming: boolean              // 是否正在流式接收
  streamEvents: ClaudeEvent[]       // 流式事件缓冲

  // Actions
  setSessions / setActiveSession / addSession / removeSession
  setConversations / setActiveConversation
  setMessages / addMessage / appendStreamContent
  setStreaming / resetStream
}
```

### useClaudeChat Hook

核心 SSE 通信逻辑:
- `sendMessage(content)` — 发送消息，消费 SSE 流
- `cancelStream()` — 取消当前流 (AbortController)
- `loadMessages(sid, cid)` — 加载历史消息

SSE 解析: 使用 `fetchAPI` + `ReadableStream` reader，解析 `event:` / `data:` 行。

### 组件交互

```
用户输入 → sendMessage()
         → POST /api/claude/.../messages (SSE)
         → appendStreamContent() 逐事件追加
         → streamEvents 驱动 React 渲染
         → 事件结束 → addMessage() 持久化到 messages
                        → resetStream()
```

### PlanCard 交互

1. Claude Code 生成分析方案 → plan 事件
2. PlanCard 展示步骤列表 + 代码预览 + 确认按钮
3. 用户点击"确认执行" → 发送 "确认执行方案，请开始执行。"
4. Claude Code 收到确认 → 开始执行任务

### TaskCard 轮询

- pending/running 状态: 每 5 秒轮询 `GET /api/claude/tasks/{id}`
- completed/failed 状态: 停止轮询，显示最终结果
- 显示: 任务ID、技能名、开始/完成时间、输出文件、错误信息

---

## 容器池管理

`autonome-backend/app/services/claude_container_pool.py`

### 配置 (环境变量)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_POOL_MIN` | 1 | 预热池最小容器数 |
| `CLAUDE_POOL_MAX` | 5 | 最大容器总数 |
| `CLAUDE_USER_MAX_CONCURRENT` | 3 | 每用户并发上限 |
| `CLAUDE_IDLE_TIMEOUT` | 1800s (30min) | 空闲超时回收 |
| `CLAUDE_RECLAIM_INTERVAL` | 300s (5min) | 回收检查间隔 |

### 容器分配策略

1. 检查用户是否已达并发上限
2. 从池中查找空闲容器 (优先复用)
3. 池中无可用且未达上限 → docker run 创建新容器
4. 容器使用完毕 → release() 标记为 idle
5. 后台定时任务回收超时空闲容器 (保留 POOL_MIN 个)

### Docker 网络

容器创建在 `autonome_claude_net` (internal bridge)，与主机和其他服务的网络隔离。Agent Service 通过 `claude-redis:6380` 与 Backend 通信。

---

## Docker 基础设施

### docker-compose.yml 新增

```yaml
networks:
  claude_net:
    driver: bridge
    internal: true  # 无外网访问

services:
  claude-redis:
    image: redis:7-alpine
    container_name: autonome-claude-redis
    ports:
      - "6380:6379"
    networks:
      - claude_net
    volumes:
      - claude_redis_data:/data
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

  backend-api:
    networks:
      - default
      - claude_net    # 允许访问 claude-redis
    environment:
      - CLAUDE_REDIS_URL=redis://claude-redis:6380/0

volumes:
  claude_redis_data:
```

### Dockerfile.claude-sandbox

`autonome-backend/Dockerfile.sandbox` 已安装 Claude Code CLI:
```dockerfile
RUN npm install -g @anthropic-ai/claude-code
```

---

## 通信流程

### 完整消息往返

```
1. 用户在 Web UI 输入消息
2. ClaudeChatStage.handleSend() → useClaudeChat.sendMessage(text)
3. Backend: POST /api/claude/.../messages (SSE)
4. ClaudeSessionManager.send_user_message():
   a. 持久化用户消息到 claude_message 表
   b. 通过 Redis Bridge 发送到 claude:session:{sid}
5. Agent Service AgentRedisClient 收到消息
6. ClaudeManager.run_with_prompt():
   a. 拼接系统提示 + 用户消息
   b. spawn Claude Code CLI
   c. stdout 逐行解析 → AgentEvent
   d. 每解析一个事件 → AgentRedisClient.publish_event()
   e. 发布到 claude:session:{sid}:events
7. Backend ClaudeRedisBridge.subscribe_events() 异步迭代
8. SSE event_stream 推送到前端
9. useClaudeChat SSE reader 解析事件 → appendStreamContent()
10. React 实时渲染: ThinkingBlock, PlanCard, ToolUseBlock, TaskCard 等
11. status=idle/waiting_user → 本轮结束，持久化 assistant 消息
```

### 取消流

```
用户点击"停止" → cancelStream() → Backend 发送 cancel 消息到 Redis
→ Agent Service 收到 cancel → ClaudeManager.kill() → SIGTERM
→ Backend 收到 AbortError → 关闭 SSE 流
```

---

## 文件清单

### Backend (autonome-backend/)

| 文件 | 用途 |
|------|------|
| `app/models/claude.py` | 5 个 SQLModel 数据模型 |
| `app/api/routes/claude.py` | 17 个 API 端点 |
| `app/services/claude_session_manager.py` | 会话 CRUD + 消息持久化 |
| `app/services/claude_redis_bridge.py` | Backend 侧 Redis pub/sub |
| `app/services/claude_container_pool.py` | 容器池分配/回收/统计 |
| `app/sandbox/agent_service/main.py` | Agent Service 入口 |
| `app/sandbox/agent_service/claude_manager.py` | Claude Code CLI 管理 |
| `app/sandbox/agent_service/redis_client.py` | Agent 侧 Redis 客户端 |
| `app/sandbox/agent_service/stream_parser.py` | JSONL 流解析 |
| `app/sandbox/agent_service/event_types.py` | 10 种事件 dataclass |
| `alembic/versions/claude_agent_tables.py` | 数据库迁移 (5 张表) |
| `Dockerfile.sandbox` | Claude Code CLI 已安装 |

### Frontend (autonome-studio/)

| 文件 | 用途 |
|------|------|
| `src/store/useClaudeStore.ts` | Zustand 状态管理 |
| `src/hooks/useClaudeChat.ts` | SSE 通信 Hook |
| `src/components/chat/ClaudeChatStage.tsx` | 主容器 (三栏布局) |
| `src/components/chat/ThinkingBlock.tsx` | 可折叠思考过程 |
| `src/components/chat/PlanCard.tsx` | 分析方案卡片 |
| `src/components/chat/TaskCard.tsx` | 任务状态卡片 |
| `src/components/chat/ToolUseBlock.tsx` | 工具调用可视化 |
| `src/components/chat/ClaudePreview.tsx` | 预览区 (文件/图表) |

### Infrastructure

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | claude-redis + claude_net (修改) |
| `autonome-backend/main.py` | Claude 容器池启动/关闭钩子 + claude router 注册 (修改) |
| `autonome-studio/src/components/chat/ChatStage.tsx` | 模式切换 (normal / claude) 集成 (修改) |
| `docs/superpowers/specs/2026-05-02-claude-code-agent-mode-design.md` | 设计规格 (3268 行) |
| `docs/superpowers/plans/2026-05-02-claude-code-agent-mode.md` | 实施计划 |
| `docs/claude_module.md` | 本文档 |

---

## 与现有系统的集成

### 独立双轨

Claude Code Agent Mode 与现有 LangGraph Agent 完全独立:

```
用户对话
  ├── 普通模式 → LangGraph Agent (bot.py)
  │               → SkillExecutor → Docker Sandbox
  └── Claude 模式 → Redis Bridge → Agent Service → Claude Code CLI
                    → Celery (重型任务)
```

### 技能复用

Claude Code 通过 `/api/claude/skills/search` 检索系统中已注册的技能，复用其参数定义和专家知识。

### 经验库共享

Claude Code 通过 `/api/claude/experiences` 将分析经验写入 ExperienceAsset 表，与普通模式共享同一经验库，支持标题合并去重。
