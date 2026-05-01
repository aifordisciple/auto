# Claude Code Agent Mode 设计文档

> 创建日期: 2026-05-02
> 状态: Draft

## 概述

在现有 AI 对话模式（常规模式）基础上，新增 **Claude 模式**：Docker 沙箱容器中的 Claude Code CLI 作为自主 Agent，处理用户需求。Claude Code 可以读取系统中的技能，生信重型任务通过 Celery 分布式执行，用户通过 Web 端与 Claude Code 交互并管理任务。

## 用户交互流程

```
用户提问
  → Claude Code brainstorming 交互, 提出选项和问题, 明确需求
  → Claude Code 生成代码 + Plan 让用户确认
  → 用户可提出修改意见, 直到确认 Plan
  → 轻量级任务: Claude Code 直接在沙箱内执行
  → 重型任务: Claude Code 返回策略卡片和代码, 系统 Celery 执行
  → 任务信息提交系统, 实时可查详情
  → 任务完成, 通知用户, 返回结果卡片 (用户手动触发结果解读)
```

## 核心设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 通信协议 | Redis pub/sub + 专网 | 复用现有基础设施, 沙箱无外网 |
| 会话模型 | Project/Conversation 两层 | Project = 大目标容器, Conversation = Claude Code 交互螺旋 |
| 并发 | 用户多会话并行 | 生信长任务 + 快捷问答可同时进行 |
| 技能发现 | 外挂检索工具 | 不占 Claude Code 上下文, 精准匹配 |
| 任务执行 | Claude Code 自判轻重 | 轻的沙箱内直接做, 重的走 Celery |
| 前端布局 | 三栏 (左导航 | 对话 | 右预览) | 保留原有侧栏, 新增预览区 |
| 系统定位 | 独立双轨, 与现有 Agent 并行 | 前端切换模式, 互不干扰 |
| 容器管理 | 混合池 | 兼顾启动速度和资源控制 |
| 沙箱网络 | 专网 + Redis 白名单 | 安全隔离同时支持通信 |
| API Key | BYOK (用户自带) | 用户自管理, 计费清晰 |
| 持久化 | 全持久化到 PostgreSQL | 离线恢复, 完整历史 |
| Claude Code 控制 | `-p` + `--resume` + stream-json | 上下文保持 + 进程管理简洁 |
| 进程生命周期 | 每轮对话后退出, 下轮 --resume | 节省资源, 用户掌控 |
| 结果解读 | 用户手动触发 | 用户掌控节奏 |

---

## 1. 整体架构

```
┌─ Web UI (Next.js) ──────────────────────────────────────────────────┐
│  ┌──────────────────┐  ┌─────────────────────────────────────────┐ │
│  │  Mode Switch     │  │  Three Pane Chat View                    │ │
│  │  [常规] [Claude] │  │  ┌─ Sidebar ──┬─ Timeline ──┬─ Preview ┐│ │
│  │                  │  │  │ 会话列表    │ 思考/工具/   │ 图表/报  ││ │
│  │                  │  │  │ 导航切换    │ 结果/Plan    │ 告/文件  ││ │
│  └──────────────────┘  │  └────────────┴──────────────┴──────────┘│ │
└────────────────────────┴──────────────────────────────────────────┘
              │                          ▲
              ▼                          │
┌─ FastAPI Backend ───────────────────────────────────────────────────┐
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ Claude Mode      │  │ Existing         │  │ Task Manager     │ │
│  │ Routes           │  │ Chat Routes      │  │ (Celery)         │ │
│  │ /api/claude/*    │  │ /api/chat        │  │                  │ │
│  └──────┬───────────┘  └──────────────────┘  └────────▲─────────┘ │
│         │                                              │           │
│         ▼                                              │           │
│  ┌──────────────────┐                          ┌───────┴─────────┐ │
│  │ Claude Session   │                          │ Celery Task     │ │
│  │ Manager          │                          │ Queue           │ │
│  │ (DB + Redis)     │                          │ (重型任务)       │ │
│  └──────┬───────────┘                          └─────────────────┘ │
└─────────┼──────────────────────────────────────────────────────────┘
          │ Redis pub/sub (dedicated claude_net network)
          ▼
┌─ Docker Sandbox ────────────────────────────────────────────────────┐
│  ┌──────────────────┐                                                │
│  │ Agent Service    │  管理 Claude Code 生命周期                     │
│  │ (Python daemon)  │  Redis ↔ stdin/stdout 桥接                    │
│  └──────┬───────────┘                                                │
│         │ spawn with --resume                                       │
│         ▼                                                           │
│  ┌──────────────────┐                                                │
│  │ Claude Code CLI  │  读取 /app/skills                              │
│  │                   │  调用 Skill Search Tool                       │
│  │                   │  轻量任务直接执行                              │
│  │                   │  重型任务 → Agent Service → Redis → Celery   │
│  └──────────────────┘                                                │
│  Mounts: /app/skills (ro), /workspace (rw), /opt/conda (ro)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据流与会话生命周期

### 2.1 消息传递链路

```
用户发消息
  → POST /api/claude/sessions/{sid}/conversations/{cid}/messages
  → Claude Session Manager: 存消息到 PostgreSQL + PUBLISH claude:session:{sid}
  → Redis (claude_net)
  → Agent Service SUBSCRIBE 收到
  → spawn Claude Code (--resume + -p)
  → Claude Code 思考 → 工具调用 → 执行
  → stdout: JSONL stream-json
  → Agent Service 逐行解析 → 事件
  → PUBLISH claude:session:{sid}:events
  → Backend SSE 推送到前端 + 持久化到 DB
  → Frontend 实时渲染
```

### 2.2 Claude Code 生命周期

```
用户开启会话 → Session Manager 从容器池获取 Claude 容器
  → Agent Service 启动 (docker exec)
    → 注入: API_KEY, session_id, skill_search_endpoint

首次消息到达 → spawn Claude Code (--resume 模式)
  → 系统提示: 角色定义 + 技能目录摘要 + 工具说明

对话循环:
  用户消息 → Claude Code → 回复 + 工具调用
    ├─ 轻量任务: 沙箱内直接执行
    ├─ 重型任务: 返回代码包 → Agent → Redis → Celery
    └─ 确认方案: 生成 plan 让用户审核
  每轮对话后进程退出 (--resume 保存状态)
  下一条消息到达 → Agent 重新 spawn (--resume 恢复)

会话关闭 / 超时 → Agent Service 清理 → 容器回收池
```

### 2.3 重型任务执行流

```
Claude Code 判断为重型任务
  → tool_call: submit_heavy_task { skill_id, code, parameters }
  → Agent Service 转发到 Redis: claude:task:submit
  → Backend: 创建 TaskRecord → 投递 Celery → 返回 task_id
  → Agent Service 注入 Claude Code 上下文: "任务已提交, ID=xxx"
  → Celery Worker 执行, 进度日志 → Redis
  → 任务完成 → 结果通知用户
  → 用户手动触发 → Agent Service 恢复 Claude Code → 解读结果
```

---

## 3. Agent Service 设计

沙箱内的 Python daemon, 是整个双向通信的枢纽。

### 3.1 职责

```
Agent Service
├─ Redis 连接管理
│   ├─ SUBSCRIBE claude:session:{sid}       ← 接收后端消息
│   └─ PUBLISH claude:session:{sid}:events  → 发送 Claude Code 事件
│
├─ Claude Code 生命周期
│   ├─ spawn: 构建命令 (--resume --output-format stream-json -p "...")
│   ├─ 解析 stdout JSONL → 事件流
│   ├─ 超时控制 (单轮思考限制)
│   └─ 优雅终止 (收到 cancel, 超时)
│
├─ 工具执行
│   ├─ skill_search(query) → 调用宿主机 SkillMatcher API
│   ├─ submit_heavy_task(skill_id, code, params) → 提交 Celery 任务
│   ├─ read_file(path) / write_file(path, content) → /workspace 内文件操作
│   └─ execute_sandbox(command, timeout) → 轻量任务直接在沙箱运行
│
└─ 心跳 & 状态上报
    ├─ 定时上报 Agent 状态到 Redis
    └─ 通知后端 Claude Code 当前状态 (idle/thinking/executing)
```

### 3.2 事件类型

```python
EVENT_TYPES = {
    "thinking":     "深度思考内容",
    "text_delta":   "回复文本增量",
    "text_end":     "回复文本块结束",
    "tool_use":     {"tool_name", "tool_input", "status": "started"},
    "tool_result":  {"tool_name", "status": "success/failed", "output"},
    "plan":         {"title", "steps", "code_snapshot", "estimated_cost"},
    "task_submitted": {"task_id", "celery_queue"},
    "status":       "idle/thinking/executing/waiting_user",
    "error":        {"message", "code"},
    "usage":        {"input_tokens", "output_tokens"},
}
```

### 3.3 内置工具定义

Claude Code 启动时通过系统提示注入:

```
## 可用工具

1. skill_search(query: str) → List[Skill]
   搜索匹配的技能, 返回技能名称/描述/参数列表

2. submit_heavy_task(skill_id, code, params, estimated_duration) → TaskInfo
   提交重型任务到 Celery, 返回 task_id 和状态追踪地址

3. read_file(path: str) → str
   读取沙箱内 /workspace 下的文件内容

4. write_file(path: str, content: str) → None
   写入文件到 /workspace

5. execute_sandbox(command: str, timeout: int) → ExecutionResult
   在沙箱内直接执行命令 (用于轻量任务)
```

---

## 4. 数据模型

```sql
-- Claude 会话 (对应 Project)
CREATE TABLE claude_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, archived, closed
    container_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Claude 对话 (Session 下的对话轮次)
CREATE TABLE claude_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES claude_sessions(id) ON DELETE CASCADE,
    title VARCHAR(500),
    claude_session_id VARCHAR(200), -- Claude Code --resume 的 session id
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Claude 消息
CREATE TABLE claude_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES claude_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- user, assistant, system
    content TEXT,
    events_json JSONB,          -- 完整事件流 (思考/工具调用/结果)
    plan_json JSONB,            -- Claude Code 生成的方案
    code_snapshot TEXT,         -- 生成的代码快照
    task_ids UUID[] DEFAULT '{}',
    usage_json JSONB,           -- token 用量
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Claude 任务关联 (重型任务追踪)
CREATE TABLE claude_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES claude_messages(id),
    session_id UUID NOT NULL REFERENCES claude_sessions(id),
    celery_task_id VARCHAR(200),
    skill_id VARCHAR(200),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, running, success, failed
    code TEXT,
    parameters JSONB,
    output_files JSONB DEFAULT '[]',
    error_text TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Claude 容器池
CREATE TABLE claude_containers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'idle', -- idle, busy, warming, dead
    user_id UUID,
    session_id UUID,
    last_used_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. 前端设计

### 5.1 三栏布局

```
┌──┬──────────────────────────┬──────────────────────────┐
│左│  ┌─ Conversation ──────┐ │  ┌─ Preview / Files ───┐ │
│侧│  │ [User] 帮我做差异... │ │  │ 📊 volcano_plot.png │ │
│栏│  │                      │ │  │ 图表预览             │ │
│  │  │ [Claude] 💭 思考...  │ │  │                      │ │
│导│  │ 理解需求...          │ │  │ 📄 deg_results.csv  │ │
│航│  │                      │ │  │ 表格预览             │ │
│  │  │ 🔧 skill_search      │ │  │                      │ │
│  │  │                      │ │  └──────────────────────┘ │
│  │  │ ┌─ Plan Card ─────┐ │ │                           │
│  │  │ │ 1. 检查输入文件  │ │ │                           │
│  │  │ │ 2. DESeq2 标准化 │ │ │                           │
│  │  │ │ 3. 差异表达计算  │ │ │                           │
│  │  │ │ [修改] [确认执行]│ │ │                           │
│  │  │ └─────────────────┘ │ │                           │
│  │  │                      │ │                           │
│  │  │ ┌─ Task Card ─────┐ │ │                           │
│  │  │ │ 🔄 运行中 12min  │ │ │                           │
│  │  │ └─────────────────┘ │ │                           │
│  │  └─────────────────────┘ │                           │
│  │  [输入框]                │                           │
│  │  [会话选择器] [新建对话] │                           │
└──┴──────────────────────────┴──────────────────────────┘
```

### 5.2 关键组件

| 组件 | 职责 |
|------|------|
| `ClaudeChatStage` | 主容器, 三栏布局, 会话管理 |
| `ClaudeMessageList` | 消息时间线, 渲染不同消息类型 |
| `ThinkingBlock` | 可折叠的思考过程展示 |
| `ToolCallCard` | 工具调用卡片 (技能搜索/文件操作/沙箱执行) |
| `PlanCard` | 方案卡片, 展示步骤+代码, 提供修改/确认按钮 |
| `TaskCard` | 任务追踪卡片, 实时状态+进度 |
| `ClaudePreview` | 右侧预览区, 文件/图表/报告 |
| `ClaudeInputBox` | 输入框 + 文件上传 + @-mention 技能 |
| `SessionSidebar` | 会话列表 + 新建会话 |
| `ClaudeModeToggle` | 常规模式 / Claude 模式切换 |

---

## 6. API 路由

```
POST   /api/claude/sessions                          # 创建新会话
GET    /api/claude/sessions                          # 获取会话列表
GET    /api/claude/sessions/{sid}                    # 获取会话详情
PATCH  /api/claude/sessions/{sid}                    # 更新会话 (标题、状态)
DELETE /api/claude/sessions/{sid}                    # 删除会话

POST   /api/claude/sessions/{sid}/conversations      # 创建新对话
GET    /api/claude/sessions/{sid}/conversations      # 获取对话列表
PATCH  /api/claude/sessions/{sid}/conversations/{cid}# 更新对话

POST   /api/claude/sessions/{sid}/conversations/{cid}/messages  # 发送消息 (SSE)
GET    /api/claude/sessions/{sid}/conversations/{cid}/messages  # 获取历史消息

POST   /api/claude/sessions/{sid}/conversations/{cid}/cancel    # 取消当前执行

GET    /api/claude/tasks/{task_id}                   # 查询任务状态和结果
GET    /api/claude/tasks/{task_id}/logs              # 获取任务执行日志 (SSE)

GET    /api/claude/skills/search?q=...               # 技能搜索 (给 Claude Code 用)
GET    /api/claude/skills/{skill_id}                 # 获取技能详情
```

### 核心 API 行为

- **发送消息**: 存消息到 DB → publish 到 Redis → 订阅 `claude:session:{sid}:events` → SSE 推前端
- **取消执行**: publish `claude:session:{sid}:control` → Agent Service 收到 → SIGTERM Claude Code

---

## 7. Docker 与网络配置

### 7.1 新增服务

```yaml
claude-redis:
  image: redis:7-alpine
  container_name: autonome-claude-redis
  restart: unless-stopped
  networks:
    - claude_net
  command: redis-server --maxmemory 512mb
```

### 7.2 网络拓扑

```
现有网络:
  default (bridge)
    ├── postgres
    ├── redis          (db 0/1/2: celery + cache)
    ├── backend-api
    ├── backend-worker
    └── frontend

新增网络:
  claude_net (isolated bridge)
    ├── claude-redis   (db 3: Claude 消息通道)
    ├── backend-api    (双网卡, 同时挂 default)
    └── claude-sandbox-xxx  (动态容器, 仅连 claude_net)
```

### 7.3 Claude 沙箱容器配置

```yaml
Image: autonome-claude-sandbox:latest
Env:
  - CLAUDE_SESSION_ID={session_id}
  - ANTHROPIC_API_KEY={user_key}
  - ANTHROPIC_BASE_URL={user_endpoint}
  - REDIS_URL=redis://claude-redis:6379/3
HostConfig:
  Memory: 128GB
  NetworkMode: claude_net
  CapDrop: ["ALL"]
Mounts:
  - uploads/:/workspace (rw)
  - skills/:/app/skills (ro)
  - conda/:/opt/conda (ro)
  - biosource/:/app/biosource (ro)
  - user_pkgs/:/app/user_packages (rw)
Entrypoint: ["sleep", "infinity"]
```

### 7.4 容器池配置

```python
CLAUDE_POOL_CONFIG = {
    "min_idle": 1,
    "max_idle": 3,
    "idle_timeout": 600,      # 空闲 10 分钟回收
    "max_per_user": 3,        # 每用户最多 3 个并发
    "warmup_on_start": True,
}
```

---

## 8. 安全与隔离

### 多层安全边界

| Layer | 措施 |
|-------|------|
| Layer 1: 前端认证 | JWT httpOnly cookie, 所有路由验证用户身份 |
| Layer 2: BYOK 存储 | 用户 API key AES-256-GCM 加密存储, 仅后端解密后注入容器环境变量, 绝不经过 Redis/日志/前端 |
| Layer 3: 后端授权 | 会话归属校验, 用户配额检查, 容器仅注入当前用户 key |
| Layer 4: Docker 网络 | Claude 沙箱仅连 claude_net, 无法访问 default 网络和外网 |
| Layer 5: 容器隔离 | CapDrop: ALL, 非 root, /workspace 按 session 隔离, 只读挂载关键目录 |
| Layer 6: 容器超时 | 自动销毁僵尸容器, 防止资源泄漏 |

### 攻击面缓解

| 风险 | 措施 |
|------|------|
| 用户代码逃逸 | 非 root, CapDrop ALL, 禁用特权模式 |
| 网络滥用 | claude_net 隔离, 禁止出站 |
| 资源耗尽 | 128GB 内存硬限制, CPU 限制, 超时 kill |
| 文件系统破坏 | /workspace 隔离, 只读挂载关键目录 |
| 信息泄露 | 环境变量仅含当前用户 key, 容器销毁时清除 |

---

## 9. 边界情况与容错

### Claude Code 异常

| 场景 | 处理 |
|------|------|
| 无响应 (超时) | Agent 检测持续 idle > 5min, 发 heartbeat, 无响应则 SIGTERM → 通知用户 |
| 进程崩溃 | 捕获 exit code, 保留 stderr, 通知用户 + 尝试重启 |
| API 配额耗尽 | 解析 API error → 用户侧显示 "API 额度不足" |
| 输出非合法 JSONL | 跳过非法行, 剩余文本作为 raw text 流式推送 |
| --resume 失败 | 会话状态损坏 → 降级为全新 spawn, 通知用户 "上下文已重置" |

### Agent Service 异常

| 场景 | 处理 |
|------|------|
| Agent Service 崩溃 | 后端心跳超时 → 销毁容器, 从池中分配新容器, 重新注入上下文 |
| Redis 连接断开 | 指数退避重连 (最多 5 次), 告警日志 |
| 消息丢失 | 发送后订阅事件, 30s 无 ack → 重发 |

### 用户侧边界

| 场景 | 处理 |
|------|------|
| 用户关闭页面 | 会话保持 active, Claude Code 继续处理当前轮, 结果持久化 |
| 用户重新打开 | 从 DB 加载完整历史, 回放未读事件, 更新到最新状态 |
| 用户切换会话 | 停止当前 SSE 流, 订阅新 session 的事件通道 |
| 用户删除执行中会话 | 发送 cancel → 清理容器 → 撤销 Celery 任务 → 软删除 DB |
| 多 tab 同一会话 | 每 tab 独立 SSE 连接, 后端广播事件 |

---

## 10. 实施阶段

### Phase 1: 基础设施 (最小闭环)
- 构建 Claude 沙箱镜像 (Dockerfile.sandbox 扩展 + Agent Service)
- 新增 claude-redis + claude_net 网络
- 后端: Claude Session Manager + 数据模型 + API 路由 + Redis 桥接
- Agent Service 核心: spawn Claude Code, JSONL 解析, 双向通信
- 前端: 最小 ClaudeChatStage (三栏布局, 消息发送, SSE 流式渲染, 思考块 + 文本)

### Phase 2: 工具与能力
- 技能检索工具 (skill_search)
- 沙箱内执行工具 (execute_sandbox, read_file, write_file)
- 重型任务投递工具 (submit_heavy_task) + Celery 集成
- Plan 卡片交互 (PlanCard 组件: 展示/修改/确认)

### Phase 3: 任务管理与预览
- 任务追踪 (TaskCard 实时状态, 任务日志 SSE, 完成通知)
- 右侧预览区 (文件列表, 图片/图表/CSV/HTML 报告预览)
- 会话管理 (会话列表侧栏, 新建/切换/删除, Conversation 切换)

### Phase 4: 容器池 + 容错
- Claude 容器池 (预热池, 动态分配, 空闲回收, 并发限制)
- Agent Service 容错 (心跳检测, 自动恢复, 异常重启 + 上下文恢复, Redis 断线重连)
- 全持久化 (离线消息回放, 事件流存档与恢复)

### Phase 5: 体验优化
- 流式渲染优化 (tool_use 动画, 思考折叠)
- API Key 管理界面 (加密存储, 测试连接)
- 使用量统计 (token 用量, CU 消耗)
- 经验提取集成 (Claude Code 成功模式自动入库)

---

## 11. 关键风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| `--resume` 不可靠 | 上下文丢失, 对话体验断裂 | Phase 1 先验证稳定性; 准备降级方案 (每次传完整上下文) |
| stream-json 格式变更 | 解析器失效 | 关注 Claude Code 版本; 解析器加 schema 校验 + 容错 fallback |
| 多容器内存压力 | 宿主机 OOM | 容器池上限控制; 按 memory 利用率动态限制并发 |
| API key 泄露 | 安全事件 | key 仅存 DB 加密, 仅注入容器 env, 不经过日志/Redis/前端 |
| Agent Service 复杂度 | 出 bug 概率高 | 充分单元测试; 无状态设计, 异常即退出等重启 |
