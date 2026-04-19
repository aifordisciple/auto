# AUTONOME STUDIO 系统架构全览

> AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端
> 多 Agent 系统 + Docker 沙箱代码执行 + Vercel AI SDK v5 流式通信

---

## 目录

- [1. 系统总览](#1-系统总览)
- [2. Monorepo 结构](#2-monorepo-结构)
- [3. Docker 服务编排](#3-docker-服务编排)
- [4. 后端架构 (autonome-backend)](#4-后端架构)
  - [4.1 入口与中间件](#41-入口与中间件)
  - [4.2 核心基础设施 (app/core)](#42-核心基础设施)
  - [4.3 多 Agent 编排 (app/agent)](#43-多-agent-编排)
  - [4.4 API 路由层 (app/api)](#44-api-路由层)
  - [4.5 数据模型层 (app/models)](#45-数据模型层)
  - [4.6 业务服务层 (app/services)](#46-业务服务层)
  - [4.7 LangChain 工具层 (app/tools)](#47-langchain-工具层)
  - [4.8 MCP 协议层 (app/mcp)](#48-mcp-协议层)
  - [4.9 工具模块 (app/utils)](#49-工具模块)
  - [4.10 Celery 异步任务 (app/tasks)](#410-celery-异步任务)
  - [4.11 内置技能包 (app/skills)](#411-内置技能包)
  - [4.12 Pydantic 模式 (app/schemas)](#412-pydantic-模式)
- [5. 前端架构 (autonome-studio)](#5-前端架构)
  - [5.1 构建与配置](#51-构建与配置)
  - [5.2 页面与路由 (src/app)](#52-页面与路由)
  - [5.3 状态管理 (src/store)](#53-状态管理)
  - [5.4 自定义 Hooks (src/hooks)](#54-自定义-hooks)
  - [5.5 API 客户端层 (src/lib)](#55-api-客户端层)
  - [5.6 业务服务 (src/services)](#56-业务服务)
  - [5.7 平台适配层 (src/adapter)](#57-平台适配层)
  - [5.8 UI 组件体系 (src/components)](#58-ui-组件体系)
- [6. 共享包 (packages)](#6-共享包)
- [7. 核心数据流](#7-核心数据流)
- [8. 关键设计模式](#8-关键设计模式)

---

## 1. 系统总览

Autonome Studio 是一个面向生物信息学的 AI 原生 IDE，核心能力包括：

- **AI 对话驱动分析**：用户通过自然语言描述需求，AI 自动识别意图并调度技能或代码执行
- **多 Agent 编排**：3 层意图路由（规则 → LLM 分类 → 参数提取）+ 6 个专业 Agent 节点
- **Docker 沙箱执行**：隔离的代码执行环境，支持 Python/R/Nextflow 工作流
- **技能生态系统**：可复用的分析技能包，支持创建、测试、发布、市场交易
- **Vercel AI SDK v5**：UIMessage Stream Protocol 实现前后端流式通信

**技术栈概览**：

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + SQLModel + LangGraph + LangChain |
| 前端框架 | Next.js 16 (App Router) + React 19 + TypeScript 5 |
| 状态管理 | Zustand 5 + Immer |
| 数据库 | PostgreSQL 15 + pgvector |
| 缓存/队列 | Redis 7 (Cache + Celery Broker) |
| 异步任务 | Celery |
| 容器化 | Docker + Docker Compose |
| AI SDK | Vercel AI SDK v5 (@ai-sdk/react + @ai-sdk/openai) |
| UI 组件 | Tailwind CSS v4 + shadcn/ui (new-york, slate) |
| 代码编辑 | Monaco Editor |
| 终端 | xterm.js |
| 图表 | ECharts |
| 工作流可视化 | ReactFlow |
| 动画 | Framer Motion |

---

## 2. Monorepo 结构

```
autonome/
├── autonome-backend/          # FastAPI + LangGraph 后端 (Python 3.11/3.12)
│   ├── main.py                # 应用入口
│   ├── app/                   # 核心应用代码 (139 文件, ~54,530 行)
│   ├── requirements.txt       # Python 依赖
│   ├── Dockerfile             # 生产镜像
│   └── Dockerfile.sandbox     # 沙箱镜像 (暖池容器)
├── autonome-studio/           # Next.js 16 前端 (React 19, TypeScript 5)
│   ├── src/                   # 前端源码
│   ├── package.json           # Node 依赖
│   ├── Dockerfile             # 生产镜像 (4 阶段构建)
│   └── next.config.ts         # Next.js 配置
├── packages/                  # 共享包 (pnpm workspace)
│   ├── shared-types/          # @autonome/shared-types - 类型定义
│   ├── shared-utils/          # @autonome/shared-utils - 工具函数
│   ├── shared-components/     # @autonome/shared-components - 共享组件
│   └── shared-store/          # @autonome/shared-store - 共享状态
├── docs/                      # 架构文档、规范、计划
├── scripts/                   # 运维脚本
├── uploads/                   # 用户文件上传 (bind-mount → /workspace)
├── docker-compose.yml         # 服务编排
├── docker-compose.override.yml # 开发热重载覆盖
├── auto_deploy.sh             # Git 提交+推送脚本
└── package.json               # Monorepo 根配置 (pnpm 8.15.0)
```

---

## 3. Docker 服务编排

### 3.1 服务定义 (docker-compose.yml)

| 服务 | 容器名 | 镜像/构建 | 端口 | 用途 |
|------|--------|-----------|------|------|
| **postgres** | autonome-postgres | `postgres:15-alpine` | 5433:5432 | PostgreSQL + pgvector |
| **redis** | autonome-redis | `redis:7-alpine` | 6379 | 缓存 + Celery Broker |
| **backend-api** | autonome-api | `./autonome-backend` | 8000 | FastAPI + uvicorn |
| **backend-worker** | autonome-worker | `./autonome-backend` | — | Celery 异步任务 Worker |
| **frontend** | autonome-web | `./autonome-studio` | 3001:3000 | Next.js 前端 |

**数据卷**：
- `pgdata` — PostgreSQL 持久化
- `redis_data` — Redis 持久化
- `./uploads:/workspace` — 用户文件 bind-mount

### 3.2 开发热重载 (docker-compose.override.yml)

| 服务 | 热重载方式 |
|------|-----------|
| backend-api | 挂载 `./autonome-backend/app` + `main.py`，`uvicorn --reload` |
| backend-worker | 挂载同上，Ollama 环境变量 |
| frontend | build target: development，挂载 `src/` + 配置文件，`npm run dev` |

### 3.3 Dockerfile 架构

**后端 Dockerfile**：
- 基础镜像：`python:3.11-slim-bookworm`
- 从 `docker:24.0.7-cli` 复制 Docker CLI（Docker-in-Docker 支持）
- 清华 PyPI 镜像加速
- 入口：`uvicorn main:app --host 0.0.0.0 --port 8000`

**沙箱 Dockerfile (Dockerfile.sandbox)**：
- 基础镜像：`python:3.11-slim`
- 安装：curl, git, nodejs, npm, `@anthropic-ai/claude-code`, mcp, sentence-transformers, faiss-cpu, numpy
- 入口：`sleep infinity`（暖池模式，容器常驻复用）

**前端 Dockerfile**（4 阶段）：
1. **deps** — npm install（npmmirror 镜像）
2. **builder** — `next build`
3. **runner** — standalone 生产镜像，`node server.js`
4. **development** — `npm run dev` 开发模式

---

## 4. 后端架构

### 4.1 入口与中间件

**文件**：`autonome-backend/main.py` (256 行)

**应用创建流程**：

```
FastAPI(title="Autonome Studio", version="2.0.0")
    │
    ├── 中间件注册
    │   ├── CORSMiddleware (allow_origins=["*"], allow_credentials=False)
    │   └── 全局异常处理器 (确保 CORS 头在错误响应中)
    │
    ├── 启动事件 (on_startup)
    │   └── create_db_and_tables() — 自动建表
    │
    ├── 路由注册 (30+ 路由模块)
    │   └── 见 4.4 API 路由层
    │
    └── 静态文件挂载
        └── /workspace — 用户上传文件目录
```

**API 路由注册表**：

| 前缀 | 模块 | 标签 |
|------|------|------|
| `/api/auth` | `routes/auth.py` | Auth |
| `/api/users` | `routes/users.py` | Users |
| `/api/system` | `routes/system.py` | System |
| `/api/projects` | `routes/projects.py` | Projects |
| `/api/chat` | `routes/chat.py` | Chat |
| `/api/chat` | `routes/chat_session.py` | ChatSession |
| `/api/chat` | `routes/chat_bookmark.py` | ChatBookmark |
| `/api/chat` | `routes/chat_tags.py` | ChatTags |
| `/api/chat` | `routes/chat_search.py` | ChatSearch |
| `/api/chat` | `routes/chat_queue.py` | ChatQueue |
| `/api/billing` | `routes/billing.py` | Billing |
| `/api/public` | `routes/public.py` | Public |
| `/api/admin` | `routes/admin.py` | Admin |
| `/api/tasks` | `routes/tasks.py` | Tasks |
| `/api/skills` | `routes/skills/` | Skills (12 子模块) |
| `/api/skills/forge` | `routes/skills_forge.py` | SkillForge |
| `/api/skills/market` | `routes/skills_market.py` | SkillMarket |
| `/api/skills/share` | `routes/skill_share.py` | SkillShare |
| `/api/skills/recommend` | `routes/skill_recommend.py` | SkillRecommend |
| `/api/templates` | `routes/templates.py` | Templates |
| `/api/experiences` | `routes/experiences.py` | Experiences |
| `/api/packages` | `routes/packages.py` | Packages |
| `/api/genomes` | `routes/genomes.py` | Genomes |
| `/api/databases` | `routes/databases.py` | Databases |
| `/api/terminal` | `routes/terminal.py` | Terminal |
| `/api/monitor` | `routes/skill_monitor.py` | SkillMonitor |
| `/api/dashboard` | `routes/dashboard.py` | Dashboard |
| `/api/learning` | `routes/learning.py` | Learning |

### 4.2 核心基础设施 (app/core)

共 9 个文件，2,385 行代码。

| 文件 | 行数 | 核心功能 |
|------|------|----------|
| `config.py` | 67 | Pydantic BaseSettings：数据库 URL、Redis、JWT、Stripe、Ollama/MLX 配置 |
| `database.py` | 49 | SQLModel 引擎创建、`create_db_and_tables()`、`get_session()` 依赖注入生成器 |
| `security.py` | 36 | bcrypt 密码哈希、JWT 创建（python-jose，HS256，7 天有效期） |
| `logger.py` | 31 | Loguru 配置：控制台 + 轮转文件（30 天保留） |
| `content_filter.py` | 497 | LLM 输出过滤器：thinking 标签清理、代码块修复、`StreamContentFilter` 有状态流过滤 |
| `docker_api.py` | 98 | 原始 Docker Engine API（Unix Socket 直连） |
| `sandbox_config.py` | 212 | Docker 沙箱路径、挂载配置、用户包路径、环境变量 |
| `skill_parser.py` | 1114 | SKILL.md 解析器：YAML frontmatter + 参数表 + 专家知识；`SkillBundleParser`（文件系统）、`DBSkillParser`（数据库）、`get_combined_skills()`（合并去重） |
| `parallel_executor.py` | 388 | 通用并行执行框架：`ParallelTask` ABC、`ParallelExecutor`、`SimpleParallelTask` |
| `sample_table.py` | 309 | 样本表 TSV 解析：`SampleInfo`、`SampleTable`（分组/索引） |
| `vercel_stream.py` | 123 | Vercel AI SDK v5 UIMessage Stream Protocol 编码器 |
| `init_templates.py` | 63 | 技能模板初始化脚本 |

**关键实现细节**：

**`config.py`** — 环境配置：
```python
class Settings(BaseSettings):
    DATABASE_URL: str          # PostgreSQL 连接串
    REDIS_URL: str             # Redis 连接串
    SECRET_KEY: str            # JWT 签名密钥
    STRIPE_SECRET_KEY: str     # Stripe 支付密钥
    OLLAMA_BASE_URL: str       # Ollama 本地模型地址
    MLX_BASE_URL: str          # MLX 模型地址
```

**`vercel_stream.py`** — SSE 事件协议：
- `text-start` / `text-delta` / `text-end` — 文本流
- `data-thinking` — 思考过程（DeepSeek/Claude）
- `data-session_info` — 会话创建信息
- `data-billing` — 费用 + 余额
- `data-ai_message_id` / `data-ai_message_content` — 消息元数据
- `data-intent` — 意图分类结果
- `tool-call` / `tool-result` — 工具调用
- `step-start` — 多步骤标记
- `finish` — 流结束 + 使用统计
- `error` — 错误事件

**`content_filter.py`** — 有状态流过滤：
- `StreamContentFilter` 类处理跨 SSE chunk 的 thinking 标签拆分
- 支持 DeepSeek R1、Claude、o1、reasoning、reflection 等多种 thinking 标签
- 清理参数标签、系统意图标签、沙箱结果标记

**`skill_parser.py`** — 技能解析核心：
- `SkillBundleParser`：从文件系统解析 SKILL.md（YAML frontmatter + Markdown 参数表 + 专家知识）
- `DBSkillParser`：从数据库解析，支持 RBAC 过滤
- `get_combined_skills()`：合并数据库技能 + 文件系统技能，按 skill_id 去重

### 4.3 多 Agent 编排 (app/agent)

共 9 个文件，827 行代码。

#### 4.3.1 Agent 图结构 (graph.py)

```
LangGraph StateGraph
    │
    ├── 节点
    │   ├── intent_router_node — 意图路由（调用 IntentRouterEngine）
    │   ├── chat_node — 通用对话
    │   ├── skill_forge_node — 代码生成/执行
    │   ├── explicit_skill_node — 指定技能执行
    │   ├── diagnostic_node — 错误诊断
    │   ├── literature_node — 文献查询
    │   └── data_probe_node — 数据探查
    │
    └── 条件边
        └── intent_router_node → 根据 IntentType 分发到对应节点
```

**AgentState TypedDict**：
```python
class AgentState(TypedDict):
    messages: list[BaseMessage]
    context: dict
    intent_data: IntentExtraction
    skill_id: str | None
    execution_result: dict | None
```

#### 4.3.2 3 层意图路由 (router/)

**IntentType 枚举**：`chat` | `skill_forge` | `explicit_skill` | `diagnostic` | `literature` | `data_probe`

**路由流水线**：

```
用户查询
    │
    ▼
[L0 规则拦截] — 0ms，命中率 ~30-40%
    │  8 条规则：SystemState / ActiveView / ExplicitSkill /
    │  ErrorPattern / Literature / Probe / CodeGen / Chitchat
    │
    ▼ (未命中)
[L1 LLM 分类] — ~200ms
    │  双模式：结构化输出（OpenAI）或 JSON 模式（本地模型）
    │  输出：IntentExtraction (意图类型 + 置信度)
    │
    ▼
[L2 参数提取] — ~200ms（仅 skill_forge/explicit_skill/data_probe）
    │  提取：SlotExtraction (参数 + 缺失槽位 + 上下文增强)
    │
    ▼
[条件边] → 路由到 6 个 Agent 节点之一
```

**文件清单**：

| 文件 | 行数 | 功能 |
|------|------|------|
| `router/engine.py` | 86 | `IntentRouterEngine`：L0+L1+L2 流水线编排 |
| `router/l0_rules.py` | 279 | L0 规则拦截：8 条规则，关键词+正则匹配 |
| `router/l1_classifier.py` | 186 | L1 LLM 分类：结构化输出 / JSON 模式双模式 |
| `router/l2_extractor.py` | 160 | L2 参数提取：技能/探查/锻造参数推断 |
| `router/schemas.py` | 107 | `IntentType`、`IntentExtraction`、`SlotExtraction`、`AgentState` |

#### 4.3.3 独立文献 Agent (literature_agent.py)

- 158 行，独立 ReAct 模式 Agent
- 内置 `create_skill_draft` 工具
- 从学习中心检索文献并生成技能草稿

### 4.4 API 路由层 (app/api)

共 40 个文件，17,156 行代码。

#### 4.4.1 依赖注入 (deps.py)

| 函数 | 功能 |
|------|------|
| `get_current_user()` | OAuth2PasswordBearer，JWT 验证，返回当前用户 |
| `verify_token_and_get_user()` | SSE 专用 token 验证（无自定义头） |
| `get_current_superuser()` | 超级管理员权限验证 |

#### 4.4.2 认证路由 (routes/auth.py, 75 行)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/register` | POST | 用户注册（邮箱+密码） |
| `/login` | POST | 用户登录（OAuth2 x-www-form-urlencoded），返回 JWT |
| `/me` | GET | 获取当前用户信息 |

#### 4.4.3 用户路由 (routes/users.py, 364 行)

用户资料 CRUD、LLM 配置更新、头像上传。

#### 4.4.4 项目路由 (routes/projects.py, 1076 行)

| 功能 | 端点 |
|------|------|
| 项目 CRUD | GET/POST/PUT/DELETE `/projects` |
| 文件上传 | POST 单文件 + 分片上传 |
| 文件夹管理 | 创建/重命名/移动 |
| 项目分享 | 生成分享 token |
| 公开数据集 | 预装数据集管理 |

**安全措施**：路径遍历防护（`..` 和绝对路径检查）、`references/` 目录只读保护。

#### 4.4.5 聊天路由 (routes/chat.py, 471 行)

**核心流式端点 `POST /api/chat/stream`**：

```
1. 认证 + 计费检查（余额不足返回 402）
2. 会话创建/恢复
3. 持久化用户消息
4. 意图分类（IntentRouterEngine L0+L1+L2）
5. 选择系统提示词（SYSTEM_PROMPT_CHAT 或 SYSTEM_PROMPT_CODE）
6. 加载对话历史
7. Vercel AI SDK v5 UIMessage Stream 输出
8. StreamContentFilter 有状态过滤
9. 持久化 AI 消息 + 扣除积分
```

**队列端点 `POST /api/chat/stream/queue`**：订阅 Redis pub/sub，接收 Celery Worker 驱动的响应。

#### 4.4.6 聊天子路由

| 文件 | 行数 | 功能 |
|------|------|------|
| `chat_session.py` | 258 | 会话 CRUD、标题更新、列表 |
| `chat_bookmark.py` | 157 | 消息书签 CRUD |
| `chat_tags.py` | 226 | 会话标签 CRUD + 标签-会话关联 |
| `chat_search.py` | 140 | 全文聊天搜索 |
| `chat_queue.py` | 203 | 队列项提交/列表/状态 |

#### 4.4.7 计费路由 (routes/billing.py, 636 行)

| 功能 | 端点 |
|------|------|
| 钱包查询 | GET 钱包余额（credits_balance + credits_frozen + credits_overdraft） |
| Stripe 充值 | POST 创建 Checkout Session |
| Webhook | POST Stripe 事件回调 |
| 交易记录 | GET 交易流水 |
| 计算记录 | GET 计算资源使用记录 |
| 资源规格 | GET 可用资源规格及定价 |
| 管理员操作 | POST 调整余额/暂停/恢复 |

#### 4.4.8 管理员路由 (routes/admin.py, 944 行)

| 功能 | 说明 |
|------|------|
| 仪表盘统计 | 用户数、会话数、任务数、收入 |
| 用户管理 | 列表、激活/停用、积分调整 |
| 系统配置 | LLM 模型管理、视觉模型配置 |
| 技能审核 | 审批/拒绝待审核技能 |
| 执行模式 | Docker/Native 模式切换 |
| 嵌入模型 | Ollama bge-m3 / OpenAI 配置 |
| Claude 权限 | 容器/宿主机执行权限授权 |

#### 4.4.9 技能路由 (routes/skills/, 12 子模块)

| 子模块 | 行数 | 功能 |
|--------|------|------|
| `crud.py` | 458 | 技能资产 CRUD、列表、详情、创建、更新、删除 |
| `catalog.py` | 168 | 分类列表、标签列表、技能目录 |
| `forge.py` | 387 | `/craft_from_material`、`/craft_from_bundle`、`/bundle` |
| `testing.py` | 142 | 沙箱测试执行 |
| `transform.py` | 362 | Live coding 转换 |
| `versions.py` | 165 | 技能版本管理 |
| `stats.py` | 199 | 执行历史 + 统计 |
| `favorites.py` | 151 | 收藏切换 + 列表 |
| `reviews.py` | 136 | 评价提交 + 列表 |
| `my.py` | 92 | "我的技能"列表 |
| `admin.py` | 110 | 管理员技能审核（审批/拒绝） |
| `draft.py` | 111 | 技能草稿管理 |

#### 4.4.10 技能锻造路由 (routes/skills_forge.py, 1019 行)

AI 对话式技能创建会话：
- 创建/列表/获取/删除锻造会话
- 聊天流（SSE）：text/draft/error/done 事件
- 草稿更新、技能提交

#### 4.4.11 技能市场路由 (routes/skills_market.py, 1045 行)

- 技能发布/下架
- 市场搜索/浏览
- 热门/推荐
- 评分/评价

#### 4.4.12 其他路由

| 文件 | 行数 | 功能 |
|------|------|------|
| `skill_share.py` | 648 | 技能分享 + 用户组管理 |
| `skill_version.py` | 347 | 技能版本 CRUD |
| `skill_recommend.py` | 788 | 技能推荐引擎（三阶段匹配） |
| `skill_monitor.py` | 184 | 技能执行监控 |
| `templates.py` | 300 | 技能模板 CRUD |
| `experiences.py` | 354 | 经验资产 CRUD |
| `sample_sheets.py` | 773 | 样本表生成/预览 |
| `packages.py` | 414 | 用户包安装/卸载（Python/R） |
| `genomes.py` | 685 | 参考基因组 CRUD |
| `databases.py` | 529 | 分析数据库 CRUD |
| `terminal.py` | 349 | Web 终端：会话创建/销毁/执行/调整大小 |
| `public.py` | 57 | 公开分享访问 |
| `dashboard.py` | 1305 | 项目仪表盘：分析、概览、最近活动 |
| `learning.py` | 389 | 学习中心：文献 CRUD、知识块、笔记、标签 |
| `system.py` | 392 | 系统配置、LLM 模型管理、视觉模型配置 |
| `tasks.py` | 348 | 任务提交/列表/状态（Celery）、WebSocket 状态、SSE 日志、终止/清理 |

### 4.5 数据模型层 (app/models)

共 18 个文件，2,667 行代码。

#### 4.5.1 模型枢纽 (domain.py, 348 行)

重导出所有子模块模型，作为统一导入入口。

#### 4.5.2 枚举定义 (enums.py, 114 行)

| 枚举 | 值 |
|------|-----|
| `RoleEnum` | admin, user |
| `SkillStatus` | DRAFT, PRIVATE, PENDING_REVIEW, PUBLISHED, DEPRECATED |
| `SkillVisibility` | private, team, public |
| `ExecutionMode` | docker, native |
| `ExperienceType` | workflow, analysis, report |
| `PermissionLevel` | read, write, admin |
| `PackageLanguage` | python, r |
| `PackageStatus` | pending, installed, failed |
| `DatabaseType` | genome, annotation, expression, variant |
| `LiteratureStatus` | pending, processing, ready, failed |
| `ChunkType` | paragraph, section, page |

#### 4.5.3 UUID 生成器 (uuid.py, 67 行)

`generate_project_id()`、`generate_session_id()`、`generate_msg_id()`、`generate_skill_id()` 等。

#### 4.5.4 核心模型

| 模型文件 | 行数 | 核心模型 |
|----------|------|----------|
| `user.py` | 75 | `User`（邮箱、LLM 配置字段、关系）、`BillingAccount` |
| `project.py` | 90 | `Project`（字符串 PK）、`DataFile`、`ProjectUpdate`、`PublicDataset` |
| `chat.py` | 112 | `ChatSession`、`ChatMessage`（JSONB 附件）、`MessageBookmark`、`SessionSummaryCache`、`ChatSessionTag`、`SessionTagRelation` |
| `chat_queue.py` | 84 | `ChatQueueItem`、`QueueItemStatus` |
| `task.py` | 66 | `TaskRecord`（semantic_dir_name、blueprint_root_id、step_number） |
| `config.py` | 48 | `SystemConfig`（LLM + 视觉模型配置） |
| `billing.py` | 511 | `Wallet`、`ComputeRecord`、`TransactionLedger`、`ResourceFlavor` + 请求/响应模式 |
| `experience.py` | 117 | `ExperienceAsset` + CRUD 模式 |
| `sharing.py` | 96 | `UserGroup`、`UserGroupMember`、`SkillShare`、`SkillShareGroup` |
| `package.py` | 105 | `UserPackage`、`UserPackageCreate`、`UserPackagePublic`、`UserPackageQuota` |
| `genome.py` | 300 | `GenomeAsset` + CRUD 模式 |
| `database.py` | 174 | `AnalysisDatabase` + CRUD 模式 |
| `learning.py` | 252 | `Literature`、`LiteratureChunk`、`LiteratureNote`、`LiteratureTag` + CRUD 模式 |
| `skill_bundle.py` | 194 | Bundle 数据类（技能文件系统写入） |
| `skill_template.py` | 99 | `SkillTemplate`、`TemplateType` |
| `forge_session.py` | 187 | `ForgeSession`、`ForgeMessage`、`ForgeStatus`、`ForgeChatRequest`、`SkillDraftUpdate`、`SkillDraftSchema` |

#### 4.5.5 技能子模型 (skill/)

| 文件 | 行数 | 模型 |
|------|------|------|
| `asset.py` | 149 | `SkillAssetBase`、`SkillAsset`、`SkillAssetCreate`、`SkillAssetUpdate`、`SkillAssetPublic` |
| `version.py` | 35 | `SkillVersion` |
| `history.py` | 30 | `SkillExecutionHistory` |
| `favorite.py` | 30 | `SkillFavorite` |
| `review.py` | 28 | `SkillReview` |
| `recommendation.py` | 97 | `SkillRecommendationLog`、`SkillMatchingFeedback` |
| `share.py` | 30 | `ResultShare` |
| `draft.py` | 117 | `PendingSkillDraft`、`DraftStatus`、`TriggerSource` |

### 4.6 业务服务层 (app/services)

共 30+ 个文件，18,888 行代码。

#### 4.6.1 核心服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `skill_executor.py` | 1613 | **最大服务** — 技能执行引擎：Docker/Nextflow/Native 执行、参数注入、计费集成 | 被 `routes/skills/crud.py`、`routes/skills/forge.py`、`routes/tasks.py` 调用 |
| `billing_service.py` | 765 | `BillingService`：钱包 CRUD、冻结/结算/退款/扣款、充值、风控检查 | 被 `routes/billing.py`、`routes/chat.py`、`skill_executor.py` 调用 |
| `cache_service.py` | 894 | Redis TTL 缓存 + 清理任务 | 被多个路由和服务调用 |
| `container_pool_service.py` | 752 | Docker 容器暖池（预启动容器加速执行） | 被 `bio_tools.py` 的 `run_container_pooled()` 调用 |

#### 4.6.2 技能匹配服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `skill_matcher.py` | 874 | 技能匹配：关键词 + 语义 + 分类评分 | 被 `routes/skill_recommend.py` 调用 |
| `skill_matcher_with_fallback.py` | 342 | 多策略匹配 + 回退 | 被 `skill_matcher.py` 调用 |
| `skill_matcher_config.py` | 620 | 匹配器配置：权重、别名、分类映射 | 被 `skill_matcher.py` 引用 |
| `skill_keywords_indexer.py` | 452 | 技能关键词索引 | 被 `skill_matcher.py` 调用 |

#### 4.6.3 技能管理服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `skill_templates.py` | 971 | 内置技能模板 + `BUILTIN_TEMPLATES` 列表 | 被 `routes/templates.py` 调用 |
| `skill_bundle_writer.py` | 517 | SKILL.md 和 Bundle 文件系统写入 | 被 `routes/skills/forge.py`、`skill_executor.py` 调用 |
| `skill_monitor.py` | 440 | 技能执行监控 | 被 `routes/skill_monitor.py` 调用 |
| `skill_validator.py` | 48 | 技能铁律验证 | 被 `skill_bundle_writer.py` 调用 |

#### 4.6.4 执行相关服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `native_executor.py` | 462 | Native（非 Docker）技能执行，用于官方技能 | 被 `skill_executor.py` 调用 |
| `blueprint_runner.py` | 379 | Blueprint（多步工作流）DAG 执行器 | 被 `skill_executor.py` 调用 |
| `terminal_manager.py` | 443 | Web 终端会话管理（Docker PTY） | 被 `routes/terminal.py` 调用 |
| `pty_manager.py` | 653 | PTY 进程管理 | 被 `terminal_manager.py` 调用 |
| `package_installer.py` | 630 | Python/R 包安装到用户级目录 | 被 `routes/packages.py` 调用 |

#### 4.6.5 AI 与评估服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `code_reviewer.py` | 430 | AI 代码审查服务 | 被 `routes/skills/forge.py` 调用 |
| `success_evaluator.py` | 528 | 执行成功评估启发式 | 被 `skill_executor.py` 调用 |
| `risk_control.py` | 482 | 风控：速率限制、成本上限 | 被 `routes/chat.py`、`billing_service.py` 调用 |

#### 4.6.6 学习中心服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `learning_service.py` | 487 | 学习中心：文献/知识块/笔记 CRUD、语义搜索 | 被 `routes/learning.py` 调用 |
| `learning_ingestion_service.py` | 487 | PDF 摄入 + 分块 | 被 `learning_service.py` 调用 |
| `pdf_processor.py` | 192 | PDF 文本提取（PyMuPDF/pdfplumber） | 被 `learning_ingestion_service.py` 调用 |

#### 4.6.7 推荐与反馈服务

| 服务 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `recommendation_feedback_service.py` | 454 | 技能推荐反馈追踪 | 被 `routes/skill_recommend.py` 调用 |
| `chat_queue_service.py` | 457 | 聊天队列：提交/处理队列项 | 被 `routes/chat_queue.py` 调用 |

#### 4.6.8 其他服务

| 服务 | 行数 | 功能 |
|------|------|------|
| `sample_sheet_generator.py` | 931 | 样本表生成 |
| `bundle_parser.py` | 342 | 上传 Bundle（.zip/.tar.gz）解析 |
| `celery_app.py` | 150 | Celery 应用 + Redis 客户端 + 任务注册 |
| `task_logger.py` | 108 | Redis 任务日志流 |

#### 4.6.9 计量子系统 (meters/)

| 文件 | 行数 | 功能 |
|------|------|------|
| `meters/base.py` | 209 | `BaseMeter` ABC — 计算资源计量抽象基类 |
| `meters/executor_meter.py` | 285 | `ExecutorMeter` — Docker 容器资源计量（CPU、内存、时长） |
| `meters/nextflow_meter.py` | 396 | `NextflowMeter` — Nextflow 流水线计量 |
| `meters/terminal_meter.py` | 220 | `TerminalMeter` — 终端会话计量 |

#### 4.6.10 Celery 任务 (tasks/)

| 文件 | 行数 | 功能 |
|------|------|------|
| `tasks/executor_tasks.py` | 93 | Celery 任务：Python/R/Nextflow 执行 |
| `tasks/pipeline_tasks.py` | 242 | Celery 任务：流水线执行 |
| `tasks/sandbox_tasks.py` | 496 | Celery 任务：沙箱代码执行 |
| `tasks/skill_bundle_tasks.py` | 968 | Celery 任务：技能 Bundle 构建 + 执行 |

### 4.7 LangChain 工具层 (app/tools)

共 4 个文件，1,890 行代码。

| 文件 | 行数 | 工具 | 关联代码 |
|------|------|------|----------|
| `bio_tools.py` | 993 | `execute_python_code`、`run_container`、`run_container_simple`、`run_nextflow_in_sandbox`、`run_container_pooled`、`execute_python_code_pooled` | 被 Agent 图节点调用 |
| `probe_tools.py` | 642 | `peek_tabular_data`、`scan_workspace`、`inspect_h5ad`、`inspect_fastq`、`inspect_bam` | 被 `data_probe_node` 调用 |
| `literature_tools.py` | 143 | `search_learning_center`（RAG 工具）、`get_learning_tools()`、`should_use_learning_tools()` | 被 `literature_node` 调用 |
| `report_tools.py` | 112 | `generate_publishable_report`（Markdown → 学术 HTML） | 被 Agent 节点调用 |

**Docker 沙箱执行模式**：

| 模式 | 函数 | 特点 |
|------|------|------|
| 标准执行 | `run_container()` | Docker API via Unix Socket，含计费 |
| 简化执行 | `run_container_simple()` | 轻量执行，无计费 |
| 暖池执行 | `run_container_pooled()` | 预热容器，节省 3-5s 启动 |
| Nextflow | `run_nextflow_in_sandbox()` | 启用网络，Nextflow 专用 |
| 池化 Python | `execute_python_code_pooled()` | 暖池 + Python 代码执行 |

**沙箱挂载架构**：
- 只读 Conda 层：`/opt/conda:ro`（官方环境）
- 读写用户包层：`/app/user_packages/user_{id}:rw`
- 工作目录：`HOST_UPLOAD_DIR → /workspace`（读写）

### 4.8 MCP 协议层 (app/mcp)

共 2 个文件，755 行代码。

| 文件 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `autonome_skills_mcp.py` | 432 | `AutonomeSkillsMCP`：技能搜索、模式查询、分类列表、双轨搜索（关键词 + 语义） | 被 `skill_matcher.py` 调用 |
| `semantic_search.py` | 323 | `SemanticSearchEngine`：sentence-transformers (all-MiniLM-L6-v2) + FAISS 语义搜索 | 被 `autonome_skills_mcp.py` 调用 |

**AutonomeSkillsMCP 方法**：

| 方法 | 功能 |
|------|------|
| `search_skills()` | 关键词搜索（默认） |
| `search_skills_enhanced()` | 双轨搜索：0.4×关键词 + 0.6×语义 |
| `get_skill_schema()` | 参数模式查询 |
| `get_skill_parameters()` | 扁平化参数列表 |
| `list_categories()` | 分类列表 |
| `get_all_skills()` | 全量技能列表 |

### 4.9 工具模块 (app/utils)

共 7 个文件，1,827 行代码。

| 文件 | 行数 | 功能 | 关联代码 |
|------|------|------|----------|
| `llm_config.py` | 199 | `get_llm_config()`：用户级覆盖 → 系统配置 → 环境变量回退；`LLMConfig` NamedTuple | 被 `routes/chat.py`、Agent 节点调用 |
| `semantic_naming.py` | 603 | 任务结果语义目录命名 | 被 `skill_executor.py` 调用 |
| `task_metadata.py` | 495 | 从 SKILL.md 提取任务元数据 | 被 `skill_executor.py` 调用 |
| `argparse_injector.py` | 163 | argparse 参数注入（技能脚本） | 被 `skill_executor.py` 调用 |
| `result_extractor.py` | 154 | LLM 结果提取（代码块、JSON） | 被 Agent 节点调用 |
| `command_builder.py` | 81 | Shell 命令构建 | 被 `bio_tools.py` 调用 |
| `ansi_cleaner.py` | 122 | ANSI 转义码清理 | 被 `terminal_manager.py` 调用 |

### 4.10 Celery 异步任务 (app/tasks)

共 4 个文件，1,390 行代码。

| 文件 | 行数 | 功能 |
|------|------|------|
| `__init__.py` | 42 | Celery 应用导入 |
| `billing_tasks.py` | 224 | 定期计费任务（结算、清理） |
| `chat_queue_task.py` | 336 | 队列项处理任务 |
| `learning_tasks.py` | 788 | 文献摄入异步任务 |

### 4.11 内置技能包 (app/skills)

| 目录 | 内容 |
|------|------|
| `bio-fastq-quality/` | SKILL.md + 示例 Python 脚本 |
| `fastqc_multiqc_01/` | SKILL.md + Nextflow process + 样本表模板 |
| `meta_nextflow_generator_bundle/` | SKILL.md + `nf_compiler.py` + `sample_channel.py` |
| `rnaseq_basic_01/` | SKILL.md + Nextflow + Python/R 脚本（10+ pytools, 10+ rscripts, shell runners） |
| `singlecell_seurat_01/` | SKILL.md + Nextflow + R 脚本（30+ 分析脚本）+ sctype DB |

### 4.12 Pydantic 模式 (app/schemas)

| 文件 | 行数 | 核心模式 |
|------|------|----------|
| `chat.py` | 106 | `ChatRequest`（message, project_id, session_id, skill_id, context_files） |
| `skill.py` | 88 | `CraftRequest`、`SkillTestRequest`、`SkillTransformRequest` |

---

## 5. 前端架构

### 5.1 构建与配置

| 配置文件 | 说明 |
|----------|------|
| `next.config.ts` | `output: 'standalone'` 容器化部署 |
| `tsconfig.json` | 严格模式，`@/*` 路径别名 |
| `postcss.config.mjs` | Tailwind CSS v4 via `@tailwindcss/postcss` |
| `components.json` | shadcn/ui：new-york 风格，slate 基色，lucide 图标 |
| `vitest.config.ts` | jsdom 环境，`@/` 别名 |
| `eslint.config.mjs` | Next.js core-web-vitals + TypeScript |

**核心依赖**：

| 包 | 版本 | 用途 |
|----|------|------|
| next | 16.1.6 | App Router |
| react | 19.2.3 | UI 框架 |
| zustand | 5.0.11 | 状态管理 |
| immer | 11.1.4 | 不可变更新 |
| ai | 5.0.179 | Vercel AI SDK v5 |
| @ai-sdk/openai | — | OpenAI 适配器 |
| @monaco-editor/react | — | 代码编辑器 |
| @xterm/xterm | — | 终端 |
| echarts | — | 图表 |
| reactflow | — | 工作流可视化 |
| framer-motion | — | 动画 |
| react-markdown | — | Markdown 渲染 |
| zod | 4.3.6 | 运行时类型验证 |
| sonner | — | Toast 通知 |
| lucide-react | — | 图标 |
| jspdf | — | PDF 生成 |
| dagre | — | 图布局 |
| @tanstack/react-virtual | — | 虚拟滚动 |
| @microsoft/fetch-event-source | — | SSE 连接 |

### 5.2 页面与路由 (src/app)

| 路径 | 类型 | 功能 |
|------|------|------|
| `layout.tsx` | 根布局 | ThemeProvider + ToastProvider 包裹，全屏视口 |
| `page.tsx` | 主 IDE 页 | 三面板布局：Sidebar + ChatStage + GlobalOverlay，处理认证重定向、项目名缓存、键盘快捷键、Markdown 导出 |
| `globals.css` | 全局样式 | Tailwind v4 + shadcn CSS 变量，深色模式，聊天消息排版，流式动画（光标闪烁、淡入），滚动到底按钮，移动端安全区域，网格背景 |
| `login/page.tsx` | 登录页 | 登录/注册表单，OAuth2 x-www-form-urlencoded，背景发光效果 |
| `admin/page.tsx` | 管理后台 | 标签页：统计概览、用户管理、集群监控、执行模式管理、嵌入模型配置 |
| `admin/skills/page.tsx` | 技能管理 | 管理员技能审核子页面 |
| `dashboard/page.tsx` | 仪表盘 | 钱包概览 + 4 面板：活跃工作流、计费分析、待办事项、最近资产 |
| `debug-chat/page.tsx` | 调试页 | 调试用聊天页面 |
| `share/[token]/page.tsx` | 分享页 | 公开分享工作区查看器（只读），显示消息 + 附加数据集 |
| `api/chat/route.ts` | BFF 代理 | 接收 Vercel AI SDK v5 UIMessage payload，从 `parts[]` 提取最后用户消息，转发到 FastAPI `/api/chat/stream`，处理 402 |
| `api/chat/queue/route.ts` | BFF 代理 | 队列 API 路由 |
| `api/chat/queue-actions/route.ts` | BFF 代理 | 队列操作路由（添加/删除/清空/重排） |

**主 IDE 页面 (page.tsx) 布局**：

```
┌──────────────────────────────────────────────────────┐
│ TopHeader                                            │
├──────┬───────────────────────────────┬───────────────┤
│      │                               │               │
│ Side │      ChatStage (60%)          │   Assets      │
│ bar  │                               │   (25%)       │
│(15%) │                               │               │
│      │                               │               │
│      │                               │               │
├──────┴───────────────────────────────┴───────────────┤
│ ChatInputBox                                         │
└──────────────────────────────────────────────────────┘
```

### 5.3 状态管理 (src/store)

共 8 个 Zustand Store。

#### 5.3.1 useAuthStore

| 状态 | 类型 | 持久化 |
|------|------|--------|
| `token` | `string \| null` | 是 (`autonome-auth-storage`) |
| `user` | `{id, email, full_name, credits_balance, is_superuser}` | 是 |

| 动作 | 功能 |
|------|------|
| `setToken` / `setUser` | 设置认证信息 |
| `updateCredits` | 更新积分余额 |
| `logout` | 清除认证状态 |
| `fetchProfile` | 调用 `/api/auth/me` 获取用户信息 |

#### 5.3.2 useChatStore

| 状态 | 类型 | 说明 |
|------|------|------|
| `messages[]` | `Message[]` | 后端 API 消息 |
| `mirroredMessages[]` | `UIMessage[]` | Vercel AI SDK 镜像 |
| `mirroredIsTyping` | `boolean` | AI 正在输入 |
| `currentSessionId` | `string \| null` | 当前会话 |
| `lastBilling` | `object \| null` | 最近计费信息 |
| `thinkingContent` | `string` | AI 思考内容 |
| `isThinking` | `boolean` | 是否正在思考 |
| `queueItems[]` | `QueueItem[]` | 消息队列 |
| `searchQuery` / `searchResults` | 搜索状态 | 全文搜索 |
| `bookmarks[]` / `tags[]` | 书签/标签 | 消息书签和会话标签 |

**双消息模型**：`messages[]`（后端 API 格式）和 `mirroredMessages[]`（Vercel AI SDK 格式），由 `useChatSync` 桥接。

#### 5.3.3 useUIStore

| 状态 | 类型 | 持久化 |
|------|------|--------|
| `activeOverlay` | 12 种 Overlay 类型联合 \| null | 否 |
| `isTerminalFullscreen` | `boolean` | 否 |
| `isMobileMenuOpen` | `boolean` | 否 |
| `autoExecuteStrategy` | `boolean` | 是 |
| `theme` | `'dark' \| 'light'` | 是 |
| `skillFilterMode` | `string` | 否 |
| `globalTaskMode` | `string` | 是 |
| `inlineExpansions{}` | `Record<string, boolean>` | 否 |

**Overlay 类型**：`dataCenter` | `projectCenter` | `skillCenter` | `taskCenter` | `settingsCenter` | `learningCenter` | `forgeOverlay` | `packageManager` | `webTerminal` | `userCenter` | `uploadManager` | `controlPanel`

#### 5.3.4 useWorkspaceStore

| 状态 | 类型 | 持久化 |
|------|------|--------|
| `currentProjectId` | `string \| null` | 是 |
| `currentSessionId` | `string \| null` | 否 |
| `currentSessionTitle` | `string` | 否 |
| `projectFiles[]` | `FileNode[]` | 否 |
| `mountedFiles[]` | `string[]` | 否 |
| `activeTool` | `string \| null` | 否 |
| `toolParams` | `Record<string, any>` | 否 |
| `pendingChatAttachments[]` | 附件列表 | 否 |
| `pendingChatSkill` | 技能信息 | 否 |
| `pastedAttachments[]` | 粘贴附件 | 否 |
| `taskMode` | `string` | 否 |
| `claudeCodeSessionId` | `string \| null` | 否 |

#### 5.3.5 useTaskStore

| 状态 | 类型 |
|------|------|
| `tasks[]` | `Task[]` |
| `activeTaskId` | `string \| null` |
| `logs[]` | `LogEntry[]` |
| `isLoading` | `boolean` |

#### 5.3.6 useForgeStore

| 状态 | 类型 | 说明 |
|------|------|------|
| `sessionId` | `string \| null` | 锻造会话 ID |
| `sessionTitle` | `string` | 会话标题 |
| `sessionStatus` | `ForgeStatus` | 会话状态 |
| `skillId` | `string \| null` | 关联技能 ID |
| `messages[]` | `ForgeMessage[]` | 锻造对话消息 |
| `skillDraft` | `SkillDraftSchema` | 技能草稿 |
| `executorType` | `string` | 执行器类型 |
| `skillFiles[]` | `SkillFileNode[]` | 虚拟文件系统 |
| `activeFileId` | `string \| null` | 当前编辑文件 |
| `openTabs[]` | `string[]` | 打开的标签页 |
| `expandedFolders` | `Set<string>` | 展开的文件夹 |

#### 5.3.7 useLearningStore

| 状态 | 类型 | 说明 |
|------|------|------|
| `literatures[]` | `Literature[]` | 文献列表 |
| `selectedLiterature` | `Literature \| null` | 选中文献 |
| `chunks[]` | `Chunk[]` | 知识块 |
| `notes[]` | `Note[]` | 笔记 |
| `searchResults[]` | `SearchResult[]` | 搜索结果 |
| `tags[]` | `Tag[]` | 标签 |
| `isUploading` | `boolean` | 上传中 |
| `uploadProgress` | `number` | 上传进度 |

**轮询机制**：3s 间隔，200 次最大尝试，用于异步 PDF 解析状态检查。

#### 5.3.8 useShortcutStore

| 状态 | 类型 | 持久化 |
|------|------|--------|
| `shortcuts{}` | 8 个默认快捷键 | 是（合并策略） |

### 5.4 自定义 Hooks (src/hooks)

| Hook | 文件 | 功能 | 关联代码 |
|------|------|------|----------|
| `useChatEventListeners` | `useChatEventListeners.ts` | 全局事件监听：refresh-chat、append-result-message、scroll-to-task-result、shortcut-focus-input | 被 `ChatStage` 调用 |
| `useChatQueue` | `useChatQueue.ts` | 消息队列 CRUD：addToQueue、removeFromQueue、clearQueue、reorderQueue | 被 `ChatInputBox` 调用 |
| `useChatSync` | `useChatSync.ts` | 桥接 Vercel AI SDK v5 `UIMessage[]` → Zustand `Message[]`；处理 `data-*` 自定义事件（thinking、session_info、billing、ai_message_id、queue 事件） | 被 `ChatStage` 调用 |
| `useFilePreview` | `useFilePreview.ts` | 文件预览：image/PDF/table/code/text，30+ 语言映射 | 被 `DataPreviewCard` 调用 |
| `useIsMobile` | `useIsMobile.ts` | 响应式断点：`useIsMobile()` (<768px)、`useBreakpoint()` (sm/md/lg/xl) | 被多个组件调用 |
| `useKeyboardShortcut` | `useKeyboardShortcut.ts` | 单个键盘快捷键绑定，修饰键匹配，跳过输入框 | 被 `ShortcutManager` 调用 |
| `useMessageActions` | `useMessageActions.ts` | 消息重试、编辑重发、深度解读（生物学解读） | 被 `MessageActionButtons` 调用 |
| `usePasteUpload` | `usePasteUpload.ts` | Ctrl+V 粘贴处理，上传到 `raw_data/.pasted` | 被 `ChatInputBox` 调用 |
| `usePerformance` | `usePerformance.ts` | `useDebounce`、`useThrottle`、`useDebouncedCallback`、`useThrottledCallback`、`useSearch`、`useLazyMemo` | 被多个组件调用 |
| `useSkillParams` | `useSkillParams.ts` | 从 `/api/skills/params/:skillId` 获取技能参数定义 | 被 `SkillExecutePanel` 调用 |
| `useSmartScroll` | `useSmartScroll.ts` | 智能滚动：新消息自动滚动、用户上滚暂停、requestAnimationFrame + easeOutCubic 缓动 | 被 `ChatStage` 调用 |

### 5.5 API 客户端层 (src/lib)

#### 5.5.1 核心 API 客户端 (api.ts)

```typescript
BASE_URL = window.location.hostname:8000  // 动态构建
getToken() → localStorage('autonome_access_token')
fetchAPI() → 自动注入 JWT、401 重定向 /login、CORS 错误处理
```

#### 5.5.2 API 域模块

| 模块 | 文件 | 功能 |
|------|------|------|
| `skillForge.ts` | 技能 CRUD：listSkills（缓存）、craftFromMaterial、createSkillBundle、testDraftSkill、testDraftSkillStream（SSE 10min 超时）、savePrivateSkill、getSkill、updateSkill、deleteSkill、submitForReview、getCatalog、listMySkills、getVersions、createVersion、rollbackVersion、getStats、getExecutionHistory |
| `forgeSession.ts` | 锻造会话：createSession、listSessions、getSession、deleteSession、updateDraft、commitSkill、submitSkill、chatStream（SSE: text/draft/error/done） |
| `skillDraft.ts` | 自动草稿：getDrafts、getDraftStats、getDraft、updateDraft、publishDraft、dismissDraft、markReviewed |
| `folder.ts` | 文件夹操作：createFolder、moveFile、getFolderTree |
| `admin.ts` | 管理员：getPendingSkills、reviewSkill（APPROVE/REJECT） |
| `template.ts` | 模板：listTemplates、getTemplate、instantiateTemplate、extractTemplate、getCategories |
| `genome.ts` | 参考基因组：listGenomes（缓存）、listSpecies、getGenome、getGenomeConfig、CRUD、toggleActive、shareGenome、validatePaths、exportTsv、importTsv |
| `database.ts` | 分析数据库：listDatabases（缓存）、listTypes、listSpecies、CRUD、toggleActive、shareDatabase、incrementUsage、validatePath |
| `chatQueue.ts` | 消息队列：add、getStatus、update、delete、clear、reorder、recover |
| `errorDiagnostic.ts` | 错误诊断：diagnose、fix、getCommonErrors |
| `executionState.ts` | 本地存储：saveParams、getAllParams、getRecentFailed、markSuccess、removeParams、clearAll |
| `pinnedSkills.ts` | 本地存储：getPinnedSkills（最多 10）、pinSkill、unpinSkill、isPinned |
| `quickExecute.ts` | 技能匹配：matchSkills（fast/precise/auto 模式）、detectIntent |
| `feedback.ts` | 行为追踪：recordBehavior、getStats |
| `learning.ts` | 学习中心：listLiteratures、uploadPDF、getLiterature、deleteLiterature、getStatus、getChunks、search、ingestDOI、forgeContext |

#### 5.5.3 API 缓存 (apiCache.ts)

- 内存 TTL 缓存 + 请求去重
- `cachedFetch`、`invalidateCache`、`useCachedQuery` React Hook
- 预设 TTL：技能 5min、基因组/数据库 10min、用户偏好 30min

#### 5.5.4 其他工具模块

| 文件 | 功能 |
|------|------|
| `analytics.ts` | 用户行为分析：批量事件追踪（sendBeacon）。事件：query、recommend、click、view_detail、execute、modify_param、retry、abort、success、failure、feedback、favorite、share |
| `contentFilter.ts` | LLM 输出清理：剥离 thinking 标签（DeepSeek、Claude、o1、reasoning、reflection）、参数标签、系统意图标签、沙箱结果标记；处理不完整/流式标签 |
| `KeyboardShortcuts.ts` | 全局快捷键系统：`useKeyboardShortcuts` Hook、平台感知键格式化。`GLOBAL_SHORTCUTS`（8 个快捷键）、`SKILL_CENTER_SHORTCUTS`（4 个快捷键）、`useShortcutsHelp` |
| `utils.ts` | `cn()` 工具（clsx + twMerge） |

### 5.6 业务服务 (src/services)

| 服务 | 功能 |
|------|------|
| `BatchExecutionService` | 并行技能执行：可配置并行度、stopOnError、进度追踪、取消 |
| `WorkflowOrchestrator` | DAG 工作流验证（循环依赖检测）、拓扑排序执行顺序、工作流模板 |
| `DefaultValueInferencer` | 智能参数默认值：从用户历史偏好和项目数据类型（single-cell、rna-seq、atac-seq）推断 |
| `ErrorDiagnosticService` | 模式匹配错误诊断：分类为 parameter/environment/data/system，生成用户友好消息和修复建议 |
| `ParameterTemplateService` | 保存/加载/应用参数模板（按技能），搜索和最近使用追踪（localStorage） |
| `TeamSharingService` | 团队资源共享（模板/工作流/技能），权限检查，使用统计 |

### 5.7 平台适配层 (src/adapter)

7 个文件，双实现（Web vs Tauri Desktop）。

| 文件 | 功能 | Web 实现 | Tauri 实现 |
|------|------|----------|------------|
| `platform.ts` | 平台检测 | `isWeb()` | `isTauri()`、`getTauriInvoke()` |
| `api.adapter.ts` | API 客户端 | `fetchAPI()` | Tauri IPC invoke |
| `fs.adapter.ts` | 文件系统 | 抛出错误（用后端 API） | Tauri IPC（openFilePicker、saveFilePicker、readFile、writeFile 等） |
| `sse.adapter.ts` | SSE 流 | fetch + ReadableStream 解析 | Tauri IPC |
| `websocket.adapter.ts` | WebSocket | 标准 WebSocket + 自动重连 | Tauri IPC |
| `updater.adapter.tsx` | 自动更新 | 无 | `useAutoUpdate()` Hook + `UpdateNotification` 组件 |

**生物信息学文件过滤器** (`fs.adapter.ts`)：FASTQ、FASTA、BAM、VCF、H5AD 等。

### 5.8 UI 组件体系 (src/components)

#### 5.8.1 布局组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `Sidebar` | `layout/Sidebar.tsx` | 左侧导航：Logo、导航项（控制面板、项目、任务、数据中心、技能中心、学习中心、终端）、会话管理、用户菜单（主题切换、管理员链接、登出） |
| `TopHeader` | `layout/TopHeader.tsx` | 顶部栏：侧边栏切换、面包屑导航、模式指示器、积分余额显示、分享/导出下拉菜单。15s 周期刷新用户信息 |
| `SessionSidebar` | `layout/SessionSidebar.tsx` | 聊天会话列表：时间分组（今天/7天内/更早）、标签过滤、会话 CRUD（重命名、删除）、搜索模态框、书签 |

#### 5.8.2 聊天系统组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `ChatStage` | `chat/ChatStage.tsx` | 主聊天容器（动态导入） |
| `ChatInputBox` | `chat/ChatInputBox.tsx` | 消息输入：附件、技能选择、任务模式 |
| `ChatSearchModal` | `chat/ChatSearchModal.tsx` | 全文聊天搜索模态框 |
| `BookmarkPanel` | `chat/BookmarkPanel.tsx` | 书签消息面板 |
| `MemoizedMessageItem` | `chat/MemoizedMessageItem.tsx` | 优化消息渲染 |
| `VirtualizedMessageList` | `chat/VirtualizedMessageList.tsx` | 虚拟滚动列表（@tanstack/react-virtual） |
| `StreamingMarkdown` | `chat/StreamingMarkdown.tsx` | 流式 Markdown 渲染器 |
| `QueueIndicator` | `chat/QueueIndicator.tsx` | 队列状态指示器 |
| `MessageActionButtons` | `chat/components/MessageActionButtons.tsx` | 消息操作按钮 |
| `AttachmentPicker` | `chat/components/AttachmentPicker.tsx` | 文件附件选择器 |
| `ExecutionResultCard` | `chat/components/ExecutionResultCard.tsx` | 任务执行结果展示 |
| `TablePreview` | `chat/components/TablePreview.tsx` | 数据表格预览 |
| `DataPreviewCard` | `chat/DataPreviewCard/index.tsx` | 数据文件预览卡片 |
| `InteractivePlotCard` | `chat/InteractivePlotCard/index.tsx` | 交互式图表（ECharts） |
| `PlotCanvas` | `chat/InteractivePlotCard/PlotCanvas.tsx` | ECharts 画布渲染器 |
| `SkillDraftCard` | `chat/SkillDraftCard/index.tsx` | 技能草稿建议卡片 |
| `AssetTree` | `chat/shared/AssetTree.tsx` | 文件资产树组件 |

#### 5.8.3 Overlay 面板组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `GlobalOverlay` | `GlobalOverlay.tsx` | Overlay 管理器：挂载所有 Overlay 组件，Escape 关闭，主题同步，framer-motion 滑入动画 |
| `ControlPanel` | `overlays/ControlPanel.tsx` | 控制面板 |
| `DataCenter` | `overlays/DataCenter.tsx` | 数据管理：文件浏览器、基因组管理、数据库管理 |
| `ProjectCenter` | `overlays/ProjectCenter.tsx` | 项目工作区选择器 |
| `SkillCenter` | `overlays/SkillCenter.tsx` | 技能中心（5 Tab）：执行、我的、市场、工厂、设置 |
| `TaskCenter` | `overlays/TaskCenter.tsx` | 后台任务监控 |
| `SettingsCenter` | `overlays/SettingsCenter.tsx` | 应用设置 |
| `LearningCenter` | `overlays/LearningCenter.tsx` | 文献/知识管理 |
| `ForgeOverlay` | `overlays/ForgeOverlay.tsx` | 技能锻造工作区 |
| `PackageManager` | `overlays/PackageManager.tsx` | 包管理 |
| `WebTerminal` | `overlays/WebTerminal.tsx` | xterm.js 终端 |
| `UserCenter` | `overlays/UserCenter/index.tsx` | 用户资料、AI 模型设置、安全、快捷键、钱包面板 |
| `UploadManager` | `overlays/UploadManager.tsx` | 文件上传管理器 |
| `TopUpModal` | `overlays/TopUpModal.tsx` | 积分充值模态框 |
| `CreateFolderModal` | `overlays/CreateFolderModal.tsx` | 创建文件夹对话框 |
| `MoveFileModal` | `overlays/MoveFileModal.tsx` | 移动文件对话框 |
| `RenameModal` | `overlays/RenameModal.tsx` | 重命名对话框 |

#### 5.8.4 技能中心子组件 (overlays/SkillCenter/)

| 组件 | 功能 |
|------|------|
| `SkillExecutePanel` | 技能执行面板 |
| `SkillMarketPanel` | 技能市场面板 |
| `MySkillsPanel` | 我的技能面板 |
| `ForgePanel` | 技能锻造面板 |
| `SettingsPanel` | 设置面板 |
| `ParameterGroupPanel` | 参数分组面板 |
| `SampleSheetGenerator` | 样本表生成器 |
| `SkillDetailDrawer` | 技能详情抽屉 |

#### 5.8.5 其他组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `ThemeProvider` | `ThemeProvider.tsx` | 同步 `useUIStore.theme` 到 `document.documentElement` class |
| `ToastProvider` | `ToastProvider.tsx` | Sonner Toast（右上角，深色，5s 时长） |
| `MarkdownBlock` | `MarkdownBlock.tsx` | Markdown 渲染组件 |
| `CommandPalette` | `CommandPalette/CommandPalette.tsx` | 命令面板（Cmd+K） |
| `FilePicker` | `FilePicker.tsx` | 文件选择组件 |
| `HybridPathInput` | `HybridPathInput.tsx` | 路径输入（本地/远程） |
| `ShortcutManager` | `ShortcutManager.tsx` | 全局快捷键注册 |
| `OnboardingGuide` | `onboarding/OnboardingGuide.tsx` | 引导指南 |
| `MobileNav` | `mobile/MobileNav.tsx` | 移动端底部导航 |
| `MobileSidebarSheet` | `mobile/MobileSidebarSheet.tsx` | 移动端侧边栏 |

#### 5.8.6 技能锻造页面组件 (app/skill-forge/)

| 组件 | 功能 |
|------|------|
| `CategoryTagsEditor` | 分类标签编辑器 |
| `DependenciesEditor` | 依赖编辑器 |
| `ExpertKnowledgeEditor` | 专家知识编辑器 |
| `ForgeFileUploader` | 文件上传器 |
| `ForgeToolbar` | 工具栏 |
| `SkillDraftEditor` | 草稿编辑器 |
| `SkillEditorMain` | 编辑器主体 |
| `SkillFileTree` | 文件树 |
| `TestPanel` | 测试面板（LogViewer、OutputPreview） |
| `VersionHistoryPanel` | 版本历史面板 |
| `ParameterSchemaEditor` | 参数模式编辑器（ParameterItem、TypeSelector、types） |

#### 5.8.7 仪表盘面板 (app/dashboard/components/)

| 组件 | 功能 |
|------|------|
| `BillingAnalyticsPanel` | 计费分析面板 |
| `ActiveWorkflowsPanel` | 活跃工作流面板 |
| `ActionItemsPanel` | 待办事项面板 |
| `RecentAssetsPanel` | 最近资产面板 |
| `ETABadge` | 预计时间徽章 |
| `MiniDAGView` | 迷你 DAG 视图 |

---

## 6. 共享包 (packages)

4 个 pnpm workspace 共享包，均使用 tsup 构建（CJS + ESM + DTS）。

| 包名 | NPM 名 | 功能 | 依赖 |
|------|--------|------|------|
| `shared-types/` | `@autonome/shared-types` | 纯类型定义：`ApiResponse<T>`、`User`、`Project`、`Skill`、`ChatMessage`、`Task`、`FolderNode`、`PlatformType`；技能执行器类型 | 无运行时依赖 |
| `shared-utils/` | `@autonome/shared-utils` | 运行时工具：`cn()`、`formatDate`、`formatFileSize`、`delay`、`generateId`、`debounce`、`throttle`、`safeJsonParse`、`isBrowser`、`isTauri` | clsx, tailwind-merge |
| `shared-components/` | `@autonome/shared-components` | 重导出 adapter 层；实际组件从 `@autonome/studio/*` 直接导入 | shared-utils, clsx, lucide-react |
| `shared-store/` | `@autonome/shared-store` | 重导出 shared-types 类型；实际 Zustand Store 从 `@autonome/studio/store/*` 直接导入 | zustand |

---

## 7. 核心数据流

### 7.1 聊天流（主数据流）

```
用户输入
    │
    ▼
[ChatInputBox] ──→ [useChat (Vercel AI SDK v5)]
    │                        │
    │                        ▼
    │               [BFF: /api/chat/route.ts]
    │                        │ 注入 JWT + 上下文
    │                        ▼
    │               [FastAPI: /api/chat/stream]
    │                        │
    │                        ├── 1. 认证 + 计费检查 (402)
    │                        ├── 2. 会话创建/恢复
    │                        ├── 3. 持久化用户消息
    │                        ├── 4. 意图分类 (L0+L1+L2)
    │                        ├── 5. 选择系统提示词
    │                        ├── 6. 加载对话历史
    │                        └── 7. SSE 流式输出
    │                                 │
    │                                 ▼
    │                        [VercelDataStreamEncoder]
    │                        text-delta / data-thinking / data-billing / ...
    │                                 │
    ▼                                 ▼
[useChatSync] ←── UIMessage[] ←── SSE Stream
    │
    ├── 提取 text from parts[]
    ├── 处理 data-* 自定义事件
    └── 写入 useChatStore.messages[]
           │
           ▼
    [VirtualizedMessageList] → [MemoizedMessageItem]
           │
           ├── StreamingMarkdown (文本渲染)
           ├── InteractivePlotCard (图表)
           ├── ExecutionResultCard (执行结果)
           ├── DataPreviewCard (数据预览)
           └── SkillDraftCard (技能草稿)
```

### 7.2 技能执行流

```
用户选择技能 + 填写参数
    │
    ▼
[SkillExecutePanel] ──→ [skillForgeApi.testDraftSkill / testDraftSkillStream]
    │
    ▼
[FastAPI: /api/skills/testing] 或 [/api/tasks]
    │
    ▼
[SkillExecutor.execute()]
    │
    ├── 1. 参数注入 (argparse_injector)
    ├── 2. 样本表生成 (sample_sheet_generator)
    ├── 3. 选择执行模式
    │       ├── Docker: run_container() / run_container_pooled()
    │       ├── Nextflow: run_nextflow_in_sandbox()
    │       └── Native: native_executor
    ├── 4. 计费 (freeze → execute → settle/refund)
    ├── 5. 结果文件发现
    └── 6. 执行历史记录
           │
           ▼
    [ExecutionResultCard] ← 结果展示
```

### 7.3 技能锻造流

```
[ForgePanel] ──→ [forgeSessionApi.createSession]
    │
    ▼
[FastAPI: /api/skills/forge]
    │
    ├── AI 对话式创建 (SSE: text/draft/error/done)
    ├── 草稿更新 (updateDraft)
    ├── 技能提交 (commitSkill / submitSkill)
    └── 沙箱测试 (testDraftSkillStream)
           │
           ▼
    [useForgeStore] ← 状态管理
    ├── skillDraft (草稿数据)
    ├── skillFiles[] (虚拟文件系统)
    └── messages[] (锻造对话)
```

### 7.4 技能推荐流

```
用户查询
    │
    ▼
[SkillMatcher.match()]
    │
    ├── 阶段 1: 关键词匹配 (skill_keywords_indexer)
    │   └── 从 SKILL.md 提取 primary/secondary/context 关键词
    │
    ├── 阶段 2: 语义匹配 (skill_embedding_service + pgvector)
    │   └── 0.4×关键词 + 0.6×语义
    │
    └── 阶段 3: LLM 精排 (llm_skill_matcher)
        └── 参数推断 + 置信度评分
           │
           ▼
    [SkillRecommendationLog] + [SkillMatchingFeedback]
```

### 7.5 计费流

```
任务提交
    │
    ▼
[BillingService.freeze()] — 预估费用冻结
    │
    ▼
[任务执行] — Docker/Nextflow/Native
    │
    ▼
[BaseMeter.measure()] — 资源计量
    │   ├── ExecutorMeter (Docker 容器)
    │   ├── NextflowMeter (流水线)
    │   └── TerminalMeter (终端)
    │
    ▼
[BillingService.settle()] — 结算实际费用
    │   └── 或 [BillingService.refund()] — 失败/超时退款
    │
    ▼
[TransactionLedger] — 双分录审计日志
```

---

## 8. 关键设计模式

### 8.1 多租户隔离

所有数据查询通过 `owner_id == current_user.id` 过滤，确保用户间数据隔离。

### 8.2 3 层意图路由

L0 规则（免费，~30-40% 命中）→ L1 LLM 分类（~$0.001）→ L2 参数提取（~$0.001），渐进式成本优化。

### 8.3 预授权计费

冻结预估费用 → 执行 → 计量实际资源 → 结算/退款，防止超额消费。

### 8.4 双轨技能搜索

关键词（0.4 权重）+ 语义（0.6 权重），兼顾精确匹配和语义理解。

### 8.5 Vercel AI SDK v5 流式通信

UIMessage Stream Protocol，`parts[]` 替代 `content` 字符串，自定义 `data-*` 事件传递结构化数据。

### 8.6 Docker 沙箱隔离

只读 Conda 层 + 读写用户包层 + 网络隔离，暖池预启动容器加速执行。

### 8.7 有状态流过滤

`StreamContentFilter` 处理跨 SSE chunk 的 thinking 标签拆分，确保流式输出干净。

### 8.8 双消息模型

前端 `useChatStore` 维护 `messages[]`（后端 API 格式）和 `mirroredMessages[]`（Vercel AI SDK 格式），由 `useChatSync` 单向桥接。

### 8.9 Overlay 单例模式

`useUIStore.activeOverlay` 使用联合类型确保同一时间只有一个面板打开，避免 UI 冲突。

### 8.10 平台适配

`src/adapter/` 提供 Web 和 Tauri Desktop 双实现，API/SSE/WebSocket/文件系统透明切换。

### 8.11 组合技能源

`get_combined_skills()` 合并数据库技能（用户创建）+ 文件系统技能（官方内置），按 skill_id 去重。

### 8.12 Celery + Redis 异步

Celery Worker 处理耗时任务（技能执行、PDF 摄入），Redis pub/sub 将结果推送到 SSE 流。

---

## 附录：运维脚本

| 脚本 | 路径 | 功能 |
|------|------|------|
| `auto_deploy.sh` | 项目根目录 | Git 提交 + 推送（`-s` 摘要，`-d` 详情） |
| `cleanup_zombie_containers.sh` | `scripts/` | 清理 `autonome-tool-env` 僵尸容器（排除暖池），建议 cron 每 6 小时 |
