# Autonome Studio 系统开发知识库

> 记录系统开发过程中的成功经验、问题解决方法和最佳实践

---

## 1. Docker 服务架构

### 1.1 服务拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                        Autonome Studio                          │
│                    (AI-Native Bioinformatics IDE)                │
├───────────────┬─────────────────┬───────────────────────────────┤
│   PostgreSQL  │      Redis      │         Frontend             │
│   (端口 5433) │   (端口 6379)   │    (端口 3001 → 3000)        │
│               │  • 消息队列      │         Next.js              │
│  • 向量存储    │  • Celery Broker│                               │
│  • 主数据库    │  • 任务状态     │                               │
└───────┬───────┴────────┬────────┴───────────────┬─────────────┘
        │                │                         │
        │         ┌──────▼──────┐                 │
        │         │ Backend-API  │                 │
        │         │  (端口 8000)  │                 │
        │         │   FastAPI     │                 │
        │         │  • LangGraph  │                 │
        │         │  • REST API    │                 │
        │         └──────┬──────┘                 │
        │                │                         │
        │         ┌──────▼──────┐                 │
        │         │Backend-Worker│                 │
        │         │   Celery     │                 │
        │         │  异步任务     │                 │
        │         └─────────────┘                 │
        │                                         │
   ┌────▼────────────────────────────────────────▼────┐
   │              Docker Sandbox (沙箱)                 │
   │     autonome-tool-env (隔离执行用户代码)            │
   │     - 4GB 内存限制                                  │
   │     - 网络禁用                                      │
   │     - 能力降级                                      │
   └───────────────────────────────────────────────────┘
```

### 1.2 服务清单

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| `postgres` | autonome-postgres | 5433→5432 | PostgreSQL 15 + pgvector 向量数据库 |
| `redis` | autonome-redis | 6379→6379 | Celery 消息队列 + 任务状态存储 |
| `backend-api` | autonome-api | 8000→8000 | FastAPI 主服务 |
| `backend-worker` | autonome-worker | - | Celery 异步任务 worker |
| `frontend` | autonome-web | 3001→3000 | Next.js 16 前端 |

---

## 2. Docker 配置详解

### 2.1 docker-compose.yml（基础配置）

```yaml
# 关键设计点：
# 1. 使用具名卷 uploads_data 共享后端与沙箱的数据
# 2. 挂载 Docker socket 实现沙箱容器调度
# 3. 环境变量统一配置数据库连接

services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_USER: autonome
      POSTGRES_PASSWORD: autonome_super_password
      POSTGRES_DB: autonome_db

  backend-api:
    volumes:
      - uploads_data:/app/uploads              # 具名卷：文件上传目录
      - /var/run/docker.sock:/var/run/docker.sock  # Docker 控制权

  backend-worker:
    command: celery -A app.services.celery_app worker --loglevel=info
```

### 2.2 docker-compose.override.yml（开发覆盖）

```yaml
# 开发模式关键配置：
# 1. 挂载源码目录实现热重载
# 2. 使用 uvicorn --reload 替代生产命令
# 3. 设置 PYTHONPATH 和开发环境变量

backend-api:
  volumes:
    - ./autonome-backend/app:/app/app:cached   # 源码热重载
  command: uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend:
  build:
    target: development
  command: npm run dev
```

### 2.3 启动命令

```bash
# 开发环境（推荐）
docker-compose up --build

# 生产环境
docker-compose -f docker-compose.yml up -d --build

# 查看日志
docker-compose logs -f

# 重启特定服务
docker-compose restart backend-api
```

---

## 3. 已解决的问题

### 3.1 策略卡片异步执行链路（2026-03-05）

**问题描述**：AI 生成的策略卡片点击执行后无法触发后台任务，结果无法回传。

**根因分析**：
1. `bot.py` 中 `main_prompt` 被重复赋值，第二次覆盖删除了策略卡片 JSON 模板
2. `celery_app.py` 缺少通用代码执行任务
3. 后端缺少 `/run-analysis` 接口

**修复方案**：
1. 恢复 `main_prompt` 中的策略卡片 JSON 格式，添加 `code` 字段
2. 新增 `run_custom_python_task` Celery 任务，执行代码并回写结果到数据库
3. 新增 `/run-analysis` 接口，接收 `code`, `session_id`, `project_id`

**关键代码**：
```python
# app/agent/bot.py - 策略卡片格式
main_prompt = f"""【策略卡片模式】...
```json_strategy
{{
  "title": "数据分析与可视化",
  "code": "import pandas as pd\\n...",
  ...
}}
```

```python
# app/services/celery_app.py - 通用任务
@celery_app.task(bind=True)
def run_custom_python_task(self, params: dict):
    result_output, exit_code = run_container("autonome-tool-env", code)
    # 回写数据库
    with Session(engine) as db:
        new_msg = ChatMessage(session_id=session_id, role="assistant", content=...)
        db.add(new_msg)
        db.commit()
```

### 3.2 前端 react-resizable-panels 尺寸类型错误

**问题描述**：Panel 组件报错 `defaultSize` 必须是字符串百分比。

**修复**：
```typescript
// ❌ 错误
<Panel defaultSize={15} />

// ✅ 正确
<Panel defaultSize="15%" />
```

### 3.3 run.sh 脚本路径错误

**问题描述**：`run.sh` 使用了错误的目录路径。

**状态**：需使用 `docker-compose up` 替代。

---

## 4. 最佳实践

### 4.1 环境变量管理

- 生产环境使用 `.env` 文件（不提交到 Git）
- Docker Compose 中使用 `environment` 字段
- 敏感信息（密码、API Key）通过环境变量注入

### 4.2 卷挂载策略

| 场景 | 方式 | 示例 |
|------|------|------|
| 源码开发 | 绑定挂载 | `./backend:/app` |
| 数据持久化 | 具名卷 | `uploads_data:/app/uploads` |
| 系统资源 | 绑定挂载 | `/var/run/docker.sock` |

### 4.3 日志管理

```bash
# 查看特定服务日志
docker-compose logs -f backend-api

# 查看最近 100 行
docker-compose logs --tail=100 frontend
```

### 4.4 数据库迁移

```bash
# 进入后端容器执行迁移
docker-compose exec backend-api alembic upgrade head

# 创建新迁移
docker-compose exec backend-api alembic revision --autogenerate -m "描述"
```

---

## 5. 已知问题与待办

| 问题 | 严重程度 | 状态 |
|------|----------|------|
| run.sh 使用错误路径 | 高 | 待修复 |
| 前端有 11 处 `any` 类型 | 低 | 待清理 |
| Docker socket 挂载安全风险 | 中 | 评估中 |
| 缺少测试框架 | 中 | 待引入 |

---

## 6. 快速参考

### 6.1 常用命令

```bash
# 启动全部服务
docker-compose up --build

# 停止全部服务
docker-compose down

# 重启特定服务
docker-compose restart backend-api

# 进入容器
docker-compose exec backend-api bash

# 查看服务状态
docker-compose ps
```

### 6.2 端口映射

| 服务 | 本地端口 | 容器端口 |
|------|----------|----------|
| PostgreSQL | 5433 | 5432 |
| Redis | 6379 | 6379 |
| Backend API | 8000 | 8000 |
| Frontend | 3001 | 3000 |

### 6.3 文件存储

- 上传文件路径：`/app/uploads/project_{project_id}/`
- 宿主机通过 `uploads_data` 具名卷共享

---

*Last Updated: 2026-03-05*

---

## 7. 系统功能模块详细分析

### 7.1 后端模块架构总览

```
autonome-backend/
├── app/
│   ├── core/              # 核心基础设施
│   │   ├── config.py      # 配置管理 (Pydantic Settings)
│   │   ├── database.py    # SQLModel 数据库引擎
│   │   ├── security.py    # JWT 认证 + bcrypt 密码加密
│   │   └── logger.py      # Loguru 日志系统
│   │
│   ├── models/            # 数据模型层
│   │   └── domain.py      # SQLModel 实体 (User, Project, ChatSession, etc.)
│   │
│   ├── agent/             # AI Agent 核心
│   │   └── bot.py        # LangGraph 多Agent编排 + 策略卡片生成
│   │
│   ├── tools/             # 工具函数
│   │   ├── bio_tools.py  # Docker沙箱执行 + 生信工具
│   │   ├── geo_tools.py  # GEO数据库检索 + 向量化
│   │   └── report_tools.py # 报告生成
│   │
│   ├── services/          # 后台服务
│   │   └── celery_app.py  # Celery 异步任务队列
│   │
│   └── api/routes/       # REST API 路由
│       ├── auth.py        # 用户注册/登录/JWT签发
│       ├── chat.py        # SSE流式对话接口
│       ├── projects.py    # 项目/文件管理
│       ├── tasks.py       # 异步任务提交/状态/日志
│       ├── billing.py    # Stripe支付/算力充值
│       └── admin.py      # 系统管理
```

---

### 7.2 核心模块详解

#### 7.2.1 认证与安全模块 (`core/security.py`)

**核心功能**：
- JWT Token 生成与验证
- bcrypt 密码哈希

**关键技术**：
```python
# JWT 签发算法
def create_access_token(subject, expires_delta):
    expire = datetime.utcnow() + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 密码验证
def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
```

**关键点**：
- Token 有效期 7 天
- HS256 对称加密算法
- bcrypt 盐值自动生成

---

#### 7.2.2 数据库模型 (`models/domain.py`)

**数据模型关系图**：

```
User (1) ─────< (N) Project
  │
  └─< (1) BillingAccount

Project (1) ─────< (N) ChatSession
                       │
                       └─< (N) ChatMessage

Project (1) ─────< (N) DataFile
Project (1) ─────< (N) TaskRecord
```

**核心表结构**：

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `User` | 多租户用户 | email, hashed_password, is_superuser |
| `BillingAccount` | 算力账户 | credits_balance, total_consumed |
| `Project` | 项目/工作区 | name, owner_id, is_public, share_token |
| `ChatSession` | 对话会话 | project_id, title |
| `ChatMessage` | 消息记录 | session_id, role, content |
| `DataFile` | 上传文件 | filename, file_path, file_type |
| `PublicDataset` | 公共数据集 | accession, embedding (pgvector) |

**向量数据库**：
- 使用 `pgvector` 扩展存储 1536 维 embedding
- 支持语义相似度搜索

---

#### 7.2.3 AI Agent 模块 (`agent/bot.py`)

**核心算法**：LangGraph ReAct Agent

**架构流程**：
```
用户消息 → LangGraph StateGraph → create_react_agent 
         → 选择工具 (execute_python_code / rnaseq_qc / geo_tools)
         → 执行工具 → 结果回传 → 生成回复
```

**策略卡片模式**（关键创新）：
```python
# AI 输出格式规范
main_prompt = f"""【策略卡片模式】当用户请求画图、处理数据时...
```json_strategy
{{
  "title": "数据分析与可视化",
  "description": "简要描述此分析的目的和步骤",
  "tool_id": "execute-python",
  "code": "import pandas as pd\\nimport matplotlib.pyplot as plt\\n...",
  "estimated_time": "约 1 分钟"
}}
```
```

**数据展示协议**：
1. 表格：`print(df.head(15).to_markdown())`
2. 图表：`plt.savefig(f'/app/uploads/project_{project_id}/result.png')`
3. 渲染：`print("![结果](/api/projects/{project_id}/files/result.png/view)")`

---

#### 7.2.4 Docker 沙箱 (`tools/bio_tools.py`)

**安全隔离设计**：

| 安全措施 | 配置 |
|----------|------|
| 内存限制 | 4GB |
| 网络隔离 | `NetworkMode: "none"` |
| 能力降级 | `CapDrop: ["ALL"]` |
| 自动清理 | 容器执行后删除 |

**核心算法**：Unix Socket Docker API 调用
```python
def run_container(image: str, command: str) -> tuple[str, int]:
    # 1. 通过 Unix socket 创建容器
    # 2. 启动容器并等待完成
    # 3. 获取日志和退出码
    # 4. 自动清理容器
```

**关键技术点**：
- 直接通过 `/var/run/docker.sock` 调用 Docker API
- HTTP/1.0 强制断开连接
- JSON 响应解析（处理 Docker API 非标准响应）

---

#### 7.2.5 GEO 数据检索 (`tools/geo_tools.py`)

**检索流程**：
```
用户查询 → NCBI E-utilities (esearch) 
         → 获取 GSE ID 列表
         → Entrez.esummary 获取详情
         → OpenAI Embedding (text-embedding-3-small)
         → 存入 pgvector
         → 返回数据集卡片
```

**向量化算法**：
```python
# 文本融合
text_to_embed = f"Title: {title}\nDescription: {desc}"
# 调用 OpenAI Embedding
vector = embeddings_model.embed_query(text_to_embed)
# 存入 PostgreSQL pgvector 字段
dataset = PublicDataset(embedding=vector, ...)
```

---

#### 7.2.6 异步任务队列 (`services/celery_app.py`)

**任务类型**：

| 任务名 | 功能 | 状态广播 |
|--------|------|----------|
| `run_rnaseq_qc_pipeline` | RNA-Seq 质控 | Redis 日志流 |
| `run_variant_calling_pipeline` | 变异检测 | 进度更新 |
| `run_scrna_analysis_pipeline` | 单细胞分析 | 进度更新 |
| `run_geo_single_cell_pipeline` | GEO 单细胞分析 | Docker 日志 |
| `run_custom_python_task` | 通用代码执行 | 结果回写数据库 |

**Redis 日志流设计**：
```python
def create_task_logger(task_id):
    def log_to_redis_and_file(message, level="INFO"):
        # 1. 写入 Redis 供前端 SSE 流式读取
        redis_client.rpush(f"task_logs:{task_id}", formatted_msg)
        # 2. 同时写入服务器日志
        log.info(f"[Task {task_id}] {message}")
    return log_to_redis_and_file
```

---

#### 7.2.7 流式对话 (`api/routes/chat.py`)

**SSE 流式算法**：
```python
async def event_generator():
    async for event in agent_executor.astream_events(...):
        if event["event"] == "on_chat_model_stream":
            # 流式输出 AI 回复
            yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}
        elif event["event"] == "on_tool_start":
            # 工具开始执行
            yield {"event": "message", "data": json.dumps({"type": "tool", "tool": "execute_python_code"})}
```

**计费扣费**：
- 基础对话：1.0 积分
- 沙箱执行：+4.0 积分

---

### 7.3 前端模块架构

```
autonome-studio/src/
├── app/                  # Next.js App Router
│   ├── page.tsx         # 主 IDE 页面 (3-panel 布局)
│   ├── login/page.tsx   # 登录页
│   ├── admin/page.tsx   # 管理后台
│   └── share/[token]/   # 公开分享页
│
├── components/
│   ├── chat/
│   │   ├── ChatStage.tsx      # 聊天主面板 (SSE 流式)
│   │   ├── StrategyCard.tsx   # 策略卡片组件
│   │   ├── MarkdownBlock.tsx  # Markdown 渲染
│   │   └── DatasetCards.tsx   # 数据集卡片
│   ├── layout/
│   │   ├── Sidebar.tsx       # 左侧导航
│   │   └── TopHeader.tsx     # 顶部标题
│   └── overlays/             # 模态框
│       ├── ProjectCenter.tsx # 项目中心
│       ├── TaskCenter.tsx    # 任务看板
│       ├── ControlPanel.tsx  # 控制面板
│       └── SettingsCenter.tsx # 设置中心
│
├── store/                # Zustand 状态管理
│   ├── useAuthStore.ts      # 认证状态
│   ├── useChatStore.ts      # 聊天消息
│   ├── useWorkspaceStore.ts # 项目/文件上下文
│   ├── useTaskStore.ts      # 任务队列
│   └── useUIStore.ts        # UI 状态
│
└── lib/
    ├── api.ts           # API 客户端 (token 注入)
    └── utils.ts        # 工具函数 (cn, etc.)
```

---

#### 7.3.1 状态管理 (Zustand)

**核心 Store 解析**：

**useChatStore** - 聊天消息状态
```typescript
interface ChatState {
  messages: Message[];
  isTyping: boolean;
  addMessage(role, content): void;
  appendLastMessage(contentChunk): void;  // 流式拼接
}
```

**useWorkspaceStore** - 工作区上下文
```typescript
interface WorkspaceState {
  currentProjectId: number;
  projectFiles: RealFile[];     // 已上传文件
  mountedFiles: string[];        // 挂载到 AI 上下文的文件
  activeTool: ToolSchema | null; // 当前激活的工具
}
```

**流式消息拼接算法**：
```typescript
appendLastMessage: (contentChunk) =>
  set((state) => {
    const newMessages = [...state.messages];
    // 找到最后一条 assistant 消息，追加内容
    newMessages[newMessages.length - 1].content += contentChunk;
    return { messages: newMessages };
  })
```

---

#### 7.3.2 策略卡片组件 (`chat/StrategyCard.tsx`)

**执行流程**：
```
1. 解析 AI 回复中的 JSON 策略卡片
2. 用户点击 [Execute]
3. POST /api/tasks/submit
4. 获取 task_id
5. WebSocket 连接 /api/tasks/{task_id}/ws
6. 实时接收任务状态 (PENDING → STARTED → PROGRESS → SUCCESS/FAILURE)
7. 完成后触发 onTaskComplete 回调
```

**关键状态机**：
```typescript
type TaskStatus = 'PENDING' | 'STARTED' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
```

---

#### 7.3.3 SSE 流式聊天 (`chat/ChatStage.tsx`)

**使用 `@microsoft/fetch-event-source`**：
```typescript
await fetchEventSource(`${BASE_URL}/api/chat/stream`, {
  method: 'POST',
  body: JSON.stringify({ project_id, message, context_files }),
  onmessage(event) {
    if (event.event === 'message') {
      const data = JSON.parse(event.data);
      appendLastMessage(data.content);  // 流式追加
    } else if (event.event === 'billing') {
      updateCredits(data.balance);      // 余额更新
    }
  }
})
```

---

### 7.4 关键技术总结

| 技术领域 | 关键技术 | 应用场景 |
|----------|----------|----------|
| **后端框架** | FastAPI + Pydantic | REST API + 数据验证 |
| **AI 编排** | LangGraph + ReAct Agent | 多Agent任务路由 |
| **向量存储** | pgvector (PostgreSQL) | 公共数据集语义搜索 |
| **代码沙箱** | Docker API (Unix Socket) | 隔离执行用户代码 |
| **异步任务** | Celery + Redis | 后台生信分析 |
| **流式通信** | SSE (Server-Sent Events) | AI 实时输出 |
| **实时状态** | WebSocket | 任务进度推送 |
| **前端框架** | Next.js 16 (App Router) | SSR + CSR 混合 |
| **状态管理** | Zustand | 全局状态 (非 Context API) |
| **支付集成** | Stripe | 算力充值 |
| **密码安全** | bcrypt | 用户密码哈希 |
| **认证授权** | JWT (HS256) | Token 鉴权 |

---

### 7.5 核心算法流程图

#### 7.5.1 用户对话流程
```
用户输入 → ChatStage (SSE)
         → POST /api/chat/stream
         → JWT 鉴权 → 计费检查
         → build_bio_agent()
         → LangGraph ReAct 循环
            [选择工具] → [执行工具] → [获取结果]
         → SSE 流式返回
         → 扣减算力 → 存入数据库
```

#### 7.5.2 策略卡片执行流程
```
用户点击 [Execute]
→ POST /api/tasks/run-analysis
   { code, session_id, project_id }
→ Celery: run_custom_python_task.delay()
→ Worker 执行 Docker 沙箱
→ 结果写入 ChatMessage 表
→ 前端 WebSocket 接收 SUCCESS
→ 刷新聊天记录
```

#### 7.5.3 GEO 数据检索流程
```
用户请求查找公共数据
→ search_and_vectorize_geo_data 工具
→ NCBI E-utilities API
→ 获取 GSE 数据集列表
→ OpenAI Embedding (1536维)
→ 存入 pgvector
→ 返回数据集卡片
→ 用户点击 [一键分析]
→ submit_async_geo_analysis_task
→ Celery 后台执行 Scanpy 流程
```

---

*Last Updated: 2026-03-05*
