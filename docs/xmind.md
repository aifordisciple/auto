# AUTONOME STUDIO — 系统思维导图

> AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端
> 多 Agent 系统 + Docker 沙箱代码执行

---

## 一、技术架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      AUTONOME STUDIO                            │
├──────────────────────┬──────────────────────────────────────────┤
│   Frontend (Next.js) │   Backend (FastAPI)                     │
│   Port 3001          │   Port 8000                             │
│                      │                                          │
│  ┌──────────────┐   │   ┌──────────────┐   ┌───────────────┐  │
│  │  Pages/Routes │   │   │  API Routes  │   │  Agent System │  │
│  │  (App Router) │   │   │  (REST API)  │   │  (LangGraph)  │  │
│  └──────┬───────┘   │   └──────┬───────┘   └───────┬───────┘  │
│         │            │          │                    │          │
│  ┌──────▼───────┐   │   ┌──────▼───────┐   ┌───────▼───────┐  │
│  │  Components   │   │   │   Services   │   │  Skill System │  │
│  │  (Overlays)   │   │   │  (Business)  │   │  (Forge/Exec) │  │
│  └──────┬───────┘   │   └──────┬───────┘   └───────┬───────┘  │
│         │            │          │                    │          │
│  ┌──────▼───────┐   │   ┌──────▼───────┐   ┌───────▼───────┐  │
│  │  Zustand      │   │   │   Models     │   │  Docker 沙箱  │  │
│  │  Stores       │   │   │  (SQLAlchemy)│   │  (Code Exec)  │  │
│  └──────────────┘   │   └──────────────┘   └───────────────┘  │
├──────────────────────┴──────────────────────────────────────────┤
│  PostgreSQL (pgvector) │ Redis (Cache+Broker) │ Celery Worker  │
│  Port 5433             │ Port 6379            │ Async Tasks     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、系统模块思维导图

### 1. 后端模块 (autonome-backend)

```
autonome-backend/
├── main.py                          # FastAPI 应用入口、路由注册、CORS、生命周期
├── app/
│   ├── api/
│   │   ├── deps.py                  # 依赖注入：DB会话、当前用户、OAuth
│   │   ├── deps_rbac.py             # RBAC 权限依赖：角色/权限校验装饰器
│   │   └── routes/
│   │       ├── auth.py              # 认证：注册、登录、OAuth、Token刷新
│   │       ├── users.py             # 用户：个人信息、头像、偏好设置
│   │       ├── rbac.py              # RBAC：角色管理、权限分配、角色继承
│   │       ├── projects.py          # 项目：CRUD、成员管理、项目设置
│   │       ├── chat.py              # 对话：消息收发、流式响应、对话历史
│   │       ├── skills.py            # 技能：CRUD、执行、参数校验
│   │       ├── skills_forge.py      # 技能锻造：创建/编辑技能包
│   │       ├── skills_market.py     # 技能市场：发布、搜索、评分、安装
│   │       ├── skill_recommend.py   # 技能推荐：智能匹配、参数推断
│   │       ├── files.py             # 文件：上传、下载、项目文件管理
│   │       ├── datasets.py          # 数据集：上传、预览、元数据管理
│   │       ├── workflows.py         # 工作流：创建、编辑、执行、状态追踪
│   │       ├── billing.py           # 计费：积分余额、消费记录、充值
│   │       ├── admin.py             # 管理后台：用户管理、系统配置、统计
│   │       ├── notifications.py     # 通知：系统通知、消息推送
│   │       └── search.py            # 全局搜索：跨模块搜索
│   │
│   ├── models/
│   │   ├── user.py                  # User: 用户基础模型、OAuth关联
│   │   ├── rbac.py                  # Role, Permission, UserRole: RBAC模型
│   │   ├── project.py               # Project, ProjectMember: 项目与成员
│   │   ├── chat.py                  # Conversation, Message: 对话与消息
│   │   ├── skill.py                 # Skill, SkillVersion: 技能与版本
│   │   ├── dataset.py               # Dataset, DatasetFile: 数据集与文件
│   │   ├── workflow.py              # Workflow, WorkflowRun: 工作流与运行
│   │   ├── billing.py               # CreditTransaction, Subscription: 积分与订阅
│   │   ├── notification.py          # Notification: 通知模型
│   │   └── file.py                  # FileAttachment: 文件附件
│   │
│   ├── services/
│   │   ├── skill_executor.py        # 技能执行：Docker沙箱调度、结果收集
│   │   ├── skill_parser.py          # SKILL.md 解析：YAML前置+Markdown体
│   │   ├── skill_matcher.py         # 统一技能匹配器（三阶段混合）
│   │   ├── skill_keywords_indexer.py # 关键词提取：从SKILL.md自动提取
│   │   ├── skill_matcher_config.py  # 匹配配置：同义词映射、权重
│   │   ├── skill_embedding_service.py # 语义向量：技能描述向量化
│   │   ├── skill_vector_search.py   # 向量检索：pgvector相似度搜索
│   │   ├── llm_skill_matcher.py     # LLM精排：复杂需求理解、参数推断
│   │   ├── intent_recognition.py    # 意图识别：用户查询意图分类
│   │   ├── success_evaluator.py     # 成功评估：执行结果质量判定
│   │   ├── celery_app.py            # Celery配置：异步任务队列
│   │   ├── llm_service.py           # LLM调用：多模型统一接口
│   │   ├── embedding_service.py     # 通用嵌入服务：文本向量化
│   │   └── cache_service.py         # 缓存服务：Redis封装
│   │
│   ├── agent/
│   │   ├── bot.py                   # 主Agent：对话路由、工具调度、LangGraph
│   │   ├── crafter.py               # 技能锻造Agent：辅助用户创建技能
│   │   └── evaluator.py             # 评估Agent：执行结果评估
│   │
│   ├── tools/
│   │   ├── bio_tools.py             # 生物信息学工具集：Docker沙箱执行
│   │   ├── file_tools.py            # 文件操作工具：读写、格式转换
│   │   ├── search_tools.py          # 搜索工具：数据库查询、文献检索
│   │   └── code_tools.py            # 代码工具：执行、调试、可视化
│   │
│   └── core/
│       ├── config.py                # 配置管理：环境变量、全局设置
│       ├── security.py              # 安全：JWT、密码哈希、OAuth
│       ├── database.py              # 数据库：SQLAlchemy引擎、会话管理
│       └── exceptions.py            # 异常：自定义异常类、错误处理
│
├── alembic/                         # 数据库迁移
└── scripts/
    └── make_admin.py                # 提升管理员脚本
```

### 2. 前端模块 (autonome-studio)

```
autonome-studio/
├── src/
│   ├── app/                         # Next.js App Router 页面
│   │   ├── page.tsx                 # 首页/登录
│   │   ├── (dashboard)/             # 主工作区布局
│   │   │   ├── layout.tsx           # Dashboard 布局
│   │   │   ├── page.tsx             # 工作台首页
│   │   │   ├── projects/            # 项目管理页
│   │   │   ├── datasets/            # 数据集页
│   │   │   ├── workflows/           # 工作流页
│   │   │   └── settings/            # 设置页
│   │   └── auth/                    # 认证相关页
│   │       ├── login/               # 登录
│   │       ├── register/            # 注册
│   │       └── callback/            # OAuth回调
│   │
│   ├── components/
│   │   ├── layout/                  # 布局组件
│   │   │   ├── Sidebar.tsx          # 侧边栏导航
│   │   │   ├── Header.tsx           # 顶部栏
│   │   │   └── CommandBar.tsx       # 命令栏 (Cmd+K)
│   │   │
│   │   ├── chat/                    # 对话组件
│   │   │   ├── ChatPanel.tsx        # 对话主面板
│   │   │   ├── MessageList.tsx      # 消息列表
│   │   │   ├── MessageInput.tsx     # 输入框
│   │   │   └── CodeBlock.tsx        # 代码块渲染
│   │   │
│   │   ├── overlays/                # 浮层/弹窗组件
│   │   │   ├── SkillCenter.tsx      # 技能中心（统一入口）
│   │   │   ├── SkillCenter/
│   │   │   │   ├── SkillExecutePanel.tsx    # 技能执行面板
│   │   │   │   ├── SkillMarketPanel.tsx     # 技能市场面板
│   │   │   │   ├── MySkillsPanel.tsx        # 我的技能面板
│   │   │   │   ├── ForgePanel.tsx           # 技能工厂面板
│   │   │   │   └── SettingsPanel.tsx        # 设置面板
│   │   │   ├── ProjectManager.tsx   # 项目管理浮层
│   │   │   ├── DatasetBrowser.tsx   # 数据集浏览浮层
│   │   │   ├── WorkflowEditor.tsx   # 工作流编辑浮层
│   │   │   ├── UserProfile.tsx      # 用户资料浮层
│   │   │   └── NotificationPanel.tsx # 通知面板
│   │   │
│   │   └── ui/                      # 通用UI组件
│   │       ├── Button.tsx
│   │       ├── Dialog.tsx
│   │       ├── Toast.tsx
│   │       └── ...
│   │
│   ├── store/                       # Zustand 状态管理
│   │   ├── useAuthStore.ts          # 认证状态：用户信息、Token、积分
│   │   ├── useChatStore.ts          # 对话状态：消息、会话列表
│   │   ├── useProjectStore.ts       # 项目状态：当前项目、文件树
│   │   ├── useSkillStore.ts         # 技能状态：技能列表、执行状态
│   │   ├── useForgeStore.ts         # 锻造状态：创建/编辑技能流程
│   │   ├── useDatasetStore.ts       # 数据集状态
│   │   ├── useWorkflowStore.ts      # 工作流状态
│   │   └── useNotificationStore.ts  # 通知状态
│   │
│   ├── services/                    # API 服务层
│   │   ├── api.ts                   # Axios 实例、拦截器
│   │   ├── auth.ts                  # 认证 API
│   │   ├── projects.ts              # 项目 API
│   │   ├── skills.ts                # 技能 API
│   │   ├── datasets.ts              # 数据集 API
│   │   ├── workflows.ts             # 工作流 API
│   │   ├── billing.ts               # 计费 API
│   │   └── search.ts                # 搜索 API
│   │
│   ├── lib/                         # 工具库
│   │   ├── utils.ts                 # 通用工具函数
│   │   └── constants.ts             # 常量定义
│   │
│   └── types/                       # TypeScript 类型定义
│       ├── api.ts                   # API 响应类型
│       ├── skill.ts                 # 技能相关类型
│       ├── project.ts               # 项目相关类型
│       └── user.ts                  # 用户相关类型
│
└── public/                          # 静态资源
```

---

## 三、数据模型关系

```
User ──1:N──→ Project          用户拥有多个项目
User ──1:N──→ Conversation     用户拥有多个对话
User ──1:N──→ Skill            用户创建多个技能
User ──1:N──→ CreditTransaction 用户积分记录
User ──M:N──→ Role             用户拥有多个角色 (RBAC)

Role ──M:N──→ Permission       角色拥有多个权限
Role ──1:N──→ Role             角色继承 (自引用)

Project ──M:N──→ User          项目成员 (ProjectMember)
Project ──1:N──→ Dataset       项目包含多个数据集
Project ──1:N──→ Workflow      项目包含多个工作流
Project ──1:N──→ FileAttachment 项目包含多个文件

Conversation ──1:N──→ Message  对话包含多条消息

Skill ──1:N──→ SkillVersion    技能有多个版本
Skill ──M:N──→ User            技能收藏/安装

Dataset ──1:N──→ DatasetFile   数据集包含多个文件

Workflow ──1:N──→ WorkflowRun  工作流有多次运行
```

---

## 四、Agent 系统架构

```
用户消息
    │
    ▼
┌──────────┐    意图识别     ┌──────────────┐
│  主Agent  │ ─────────────→ │ 意图识别服务  │
│  (bot.py) │ ←───────────── │              │
└────┬─────┘    匹配结果     └──────────────┘
     │
     ├──→ 技能执行路径
     │    └──→ SkillExecutor → Docker沙箱 → 结果收集
     │
     ├──→ 对话生成路径
     │    └──→ LLM Service → 流式响应
     │
     ├──→ 工具调用路径
     │    ├──→ bio_tools (生物信息学)
     │    ├──→ file_tools (文件操作)
     │    ├──→ search_tools (搜索)
     │    └──→ code_tools (代码执行)
     │
     └──→ 技能锻造路径
          └──→ Crafter Agent → SKILL.md生成 → 技能包创建
```

### 技能推荐三阶段架构

```
用户查询
    │
    ▼
┌──────────┐  快速筛选(<50ms)  ┌───────────────────┐
│ 规则引擎  │ ──────────────→ │ 关键词索引+同义词  │
│          │ ←────────────── │ skill_keywords_    │
└──────────┘   候选技能集     │ indexer.py         │
    │                         └───────────────────┘
    ▼
┌──────────┐  语义匹配(~100ms) ┌───────────────────┐
│ 向量检索  │ ──────────────→  │ pgvector + 嵌入   │
│          │ ←──────────────  │ skill_vector_      │
└──────────┘   精选候选集      │ search.py          │
    │                          └───────────────────┘
    ▼
┌──────────┐  精准排序(~1-2s)  ┌───────────────────┐
│ LLM精排  │ ──────────────→  │ 参数推断+排序     │
│          │ ←──────────────  │ llm_skill_         │
└──────────┘   最终推荐+参数   │ matcher.py         │
                                └───────────────────┘
```

---

## 五、Docker 服务编排

```
docker-compose.yml
│
├── backend-api (autonome-api:8000)
│   └── FastAPI + Uvicorn
│   └── 挂载: autonome-backend/
│
├── frontend (autonome-web:3001)
│   └── Next.js + Node
│   └── 挂载: autonome-studio/
│
├── postgres (autonome-postgres:5433)
│   └── PostgreSQL + pgvector 扩展
│   └── 数据卷: postgres_data
│
├── redis (autonome-redis:6379)
│   └── Cache + Celery Broker
│   └── 数据卷: redis_data
│
└── backend-worker (autonome-worker)
    └── Celery Worker
    └── 异步任务执行
```

---

## 六、认证与安全

```
认证流程:
  注册/登录 → JWT Token (Access + Refresh)
  OAuth2.0 → GitHub/微信 → 关联账号 → JWT Token

权限模型 (RBAC):
  User → Role → Permission
  ├── 系统角色: admin, user, guest
  ├── 角色继承: admin > user > guest
  └── 权限粒度: 资源+操作 (如 project:write, skill:execute)

安全机制:
  ├── JWT Token 过期 + Refresh Token 续期
  ├── CORS 白名单
  ├── 输入校验 (Pydantic Schema)
  ├── SQL注入防护 (SQLAlchemy ORM)
  └── Docker 沙箱隔离执行
```

---

## 七、功能分类总览（按功能划分）

### 7.1 用户与认证

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 用户与认证 | 账号注册 | 邮箱密码注册 | `auth/register/` 页面，表单校验 | `routes/auth.py` POST /register，密码哈希+邮箱校验 |
| 用户与认证 | 账号注册 | 邮箱验证 | 注册后发送验证邮件提示 | `services/email_service.py` 发送验证链接 |
| 用户与认证 | 账号登录 | 邮箱密码登录 | `auth/login/` 页面，登录表单 | `routes/auth.py` POST /login，JWT签发 |
| 用户与认证 | 账号登录 | OAuth2.0 登录 | GitHub/微信登录按钮，回调页 `auth/callback/` | `routes/auth.py` OAuth流程，账号关联 |
| 用户与认证 | Token管理 | Access Token | 自动附加到请求头，过期拦截 | `core/security.py` JWT签发/验证，15min过期 |
| 用户与认证 | Token管理 | Refresh Token | 静默刷新，无感续期 | `routes/auth.py` POST /refresh，7天过期 |
| 用户与认证 | 个人资料 | 头像上传 | `UserProfile.tsx` 头像裁剪上传 | `routes/users.py` PUT /me/avatar，文件存储 |
| 用户与认证 | 个人资料 | 信息编辑 | `UserProfile.tsx` 表单编辑 | `routes/users.py` PUT /me，字段校验 |
| 用户与认证 | 偏好设置 | 主题/语言 | `settings/` 页面，Zustand持久化 | `routes/users.py` PUT /me/preferences |

### 7.2 权限与角色 (RBAC)

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 权限与角色 | 角色管理 | 角色CRUD | 管理后台角色管理页面 | `routes/rbac.py` 角色增删改查API |
| 权限与角色 | 角色管理 | 角色继承 | 角色树形展示，继承关系配置 | `models/rbac.py` Role自引用，`deps_rbac.py` 继承解析 |
| 权限与角色 | 权限分配 | 用户角色绑定 | 用户详情页分配角色 | `routes/rbac.py` POST /users/{id}/roles |
| 权限与角色 | 权限分配 | 权限定义 | 权限列表管理 | `models/rbac.py` Permission模型，资源+操作粒度 |
| 权限与角色 | 权限校验 | 接口级鉴权 | — | `deps_rbac.py` 依赖注入，角色/权限装饰器 |
| 权限与角色 | 权限校验 | 前端权限控制 | 组件级权限判断，菜单/按钮显隐 | `useAuthStore.ts` 角色/权限状态 |

### 7.3 项目管理

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 项目管理 | 项目CRUD | 创建项目 | `ProjectManager.tsx` 新建表单 | `routes/projects.py` POST /，项目初始化 |
| 项目管理 | 项目CRUD | 编辑项目 | 项目设置页，名称/描述修改 | `routes/projects.py` PUT /{id} |
| 项目管理 | 项目CRUD | 删除项目 | 确认弹窗，级联删除提示 | `routes/projects.py` DELETE /{id}，软删除 |
| 项目管理 | 项目CRUD | 项目列表 | `projects/` 页面，卡片/列表视图 | `routes/projects.py` GET /，分页+筛选 |
| 项目管理 | 成员管理 | 邀请成员 | 成员管理面板，邮箱邀请 | `routes/projects.py` POST /{id}/members |
| 项目管理 | 成员管理 | 角色分配 | 成员角色下拉选择 | `routes/projects.py` PUT /{id}/members/{uid} |
| 项目管理 | 成员管理 | 移除成员 | 成员列表操作按钮 | `routes/projects.py` DELETE /{id}/members/{uid} |
| 项目管理 | 文件管理 | 文件上传 | 拖拽上传组件 | `routes/files.py` POST /upload，多文件支持 |
| 项目管理 | 文件管理 | 文件浏览 | 文件树组件，目录导航 | `routes/files.py` GET /{project_id}/files |
| 项目管理 | 文件管理 | 文件下载 | 右键菜单下载 | `routes/files.py` GET /files/{id}/download |

### 7.4 AI 对话

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| AI 对话 | 对话管理 | 新建对话 | 侧边栏新建按钮 | `routes/chat.py` POST /conversations |
| AI 对话 | 对话管理 | 对话历史 | 侧边栏对话列表 | `routes/chat.py` GET /conversations |
| AI 对话 | 对话管理 | 删除对话 | 对话项右键删除 | `routes/chat.py` DELETE /conversations/{id} |
| AI 对话 | 消息交互 | 发送消息 | `MessageInput.tsx` 输入框+发送 | `routes/chat.py` POST /conversations/{id}/messages |
| AI 对话 | 消息交互 | 流式响应 | SSE事件流，逐字渲染 | `routes/chat.py` GET /stream，Server-Sent Events |
| AI 对话 | 消息交互 | 代码块渲染 | `CodeBlock.tsx` 语法高亮+复制 | — |
| AI 对话 | 消息交互 | Markdown渲染 | 消息内容Markdown解析 | — |
| AI 对话 | Agent路由 | 意图识别 | — | `services/intent_recognition.py` 查询意图分类 |
| AI 对话 | Agent路由 | 工具调度 | — | `agent/bot.py` LangGraph工具节点 |
| AI 对话 | Agent路由 | 技能匹配 | — | `services/skill_matcher.py` 三阶段匹配 |

### 7.5 技能系统

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 技能系统 | 技能执行 | 技能浏览 | `SkillExecutePanel.tsx` 分类浏览 | `routes/skills.py` GET /，分类+标签筛选 |
| 技能系统 | 技能执行 | 参数填写 | 动态参数表单，类型校验 | `services/skill_parser.py` 参数定义解析 |
| 技能系统 | 技能执行 | 执行提交 | 执行按钮+进度展示 | `services/skill_executor.py` Docker沙箱调度 |
| 技能系统 | 技能执行 | 结果展示 | 结果面板，表格/图表/文件 | `routes/skills.py` GET /executions/{id} |
| 技能系统 | 技能推荐 | 智能推荐 | 推荐技能卡片 | `routes/skill_recommend.py` POST /recommend |
| 技能系统 | 技能推荐 | 参数推断 | 推荐参数预填 | `services/llm_skill_matcher.py` LLM参数推断 |
| 技能系统 | 技能推荐 | 反馈闭环 | 推荐结果点赞/踩 | `routes/skill_recommend.py` POST /feedback |
| 技能系统 | 技能锻造 | 创建技能 | `ForgePanel.tsx` 向导式创建 | `routes/skills_forge.py` POST /，SKILL.md生成 |
| 技能系统 | 技能锻造 | 编辑技能 | 代码编辑器+参数配置 | `routes/skills_forge.py` PUT /{id} |
| 技能系统 | 技能锻造 | AI辅助 | Crafter Agent交互 | `agent/crafter.py` 辅助生成技能包 |
| 技能系统 | 技能市场 | 浏览市场 | `SkillMarketPanel.tsx` 搜索+分类 | `routes/skills_market.py` GET /market |
| 技能系统 | 技能市场 | 发布技能 | 发布按钮+版本说明 | `routes/skills_market.py` POST /publish |
| 技能系统 | 技能市场 | 评分评论 | 星级评分+评论框 | `routes/skills_market.py` POST /{id}/rate |
| 技能系统 | 技能市场 | 安装技能 | 安装按钮+依赖检查 | `routes/skills_market.py` POST /{id}/install |
| 技能系统 | 我的技能 | 已创建技能 | `MySkillsPanel.tsx` 创建列表 | `routes/skills.py` GET /my/created |
| 技能系统 | 我的技能 | 已收藏技能 | 收藏列表 | `routes/skills.py` GET /my/favorites |
| 技能系统 | 我的技能 | 执行历史 | 历史记录列表 | `routes/skills.py` GET /my/history |
| 技能系统 | 技能管理 | 分类管理 | `SettingsPanel.tsx` 分类CRUD | `routes/skills.py` 分类管理API |
| 技能系统 | 技能管理 | 标签管理 | 标签CRUD | `routes/skills.py` 标签管理API |
| 技能系统 | 技能管理 | 审核队列 | 待审核技能列表 | `routes/skills_market.py` GET /pending |

### 7.6 数据集管理

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 数据集管理 | 数据集CRUD | 创建数据集 | `DatasetBrowser.tsx` 新建表单 | `routes/datasets.py` POST /，元数据初始化 |
| 数据集管理 | 数据集CRUD | 编辑数据集 | 编辑弹窗 | `routes/datasets.py` PUT /{id} |
| 数据集管理 | 数据集CRUD | 删除数据集 | 确认弹窗 | `routes/datasets.py` DELETE /{id} |
| 数据集管理 | 文件管理 | 上传文件 | 拖拽上传，进度条 | `routes/datasets.py` POST /{id}/files |
| 数据集管理 | 文件管理 | 数据预览 | 表格预览组件，分页 | `routes/datasets.py` GET /{id}/preview |
| 数据集管理 | 文件管理 | 元数据管理 | 文件属性编辑 | `routes/datasets.py` PUT /files/{fid}/meta |

### 7.7 工作流

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 工作流 | 工作流编辑 | 可视化编辑 | `WorkflowEditor.tsx` 节点拖拽+连线 | `routes/workflows.py` CRUD |
| 工作流 | 工作流编辑 | 节点配置 | 节点属性面板 | `routes/workflows.py` PUT /{id}/nodes |
| 工作流 | 工作流执行 | 运行工作流 | 运行按钮+参数配置 | `routes/workflows.py` POST /{id}/run |
| 工作流 | 工作流执行 | 状态追踪 | 运行状态面板，实时更新 | `routes/workflows.py` GET /runs/{rid} |
| 工作流 | 工作流执行 | 日志查看 | 运行日志流 | `routes/workflows.py` GET /runs/{rid}/logs |

### 7.8 计费系统

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 计费系统 | 积分管理 | 余额查询 | 顶部栏积分显示 | `routes/billing.py` GET /balance |
| 计费系统 | 积分管理 | 消费记录 | 消费历史列表 | `routes/billing.py` GET /transactions |
| 计费系统 | 积分管理 | 充值 | 充值弹窗 | `routes/billing.py` POST /recharge |
| 计费系统 | 积分管理 | 积分扣减 | — | `services/skill_executor.py` 执行前扣减 |
| 计费系统 | 订阅管理 | 订阅计划 | 订阅页面 | `routes/billing.py` GET /plans |
| 计费系统 | 订阅管理 | 订阅/续费 | 订阅操作 | `routes/billing.py` POST /subscribe |

### 7.9 通知系统

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 通知系统 | 消息通知 | 通知列表 | `NotificationPanel.tsx` 下拉面板 | `routes/notifications.py` GET / |
| 通知系统 | 消息通知 | 标记已读 | 单条/全部已读 | `routes/notifications.py` PUT /{id}/read |
| 通知系统 | 消息通知 | 实时推送 | WebSocket/SSE 新消息提醒 | `routes/notifications.py` SSE推送 |

### 7.10 管理后台

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 管理后台 | 用户管理 | 用户列表 | 管理页面用户表格 | `routes/admin.py` GET /admin/users |
| 管理后台 | 用户管理 | 禁用/启用 | 操作按钮 | `routes/admin.py` PUT /admin/users/{id}/status |
| 管理后台 | 用户管理 | 角色分配 | 角色选择 | `routes/rbac.py` POST /users/{id}/roles |
| 管理后台 | 系统配置 | 参数配置 | 配置编辑页 | `routes/admin.py` GET/PUT /admin/config |
| 管理后台 | 数据统计 | 使用统计 | 统计仪表盘 | `routes/admin.py` GET /admin/stats |
| 管理后台 | 技能审核 | 审核队列 | 待审核列表 | `routes/skills_market.py` GET /pending |
| 管理后台 | 技能审核 | 通过/拒绝 | 审核操作 | `routes/skills_market.py` PUT /{id}/review |

### 7.11 全局功能

| 功能大类 | 功能小类 | 功能点 | 前端实现 | 后端实现 |
|---------|---------|--------|---------|---------|
| 全局功能 | 全局搜索 | 跨模块搜索 | `CommandBar.tsx` Cmd+K搜索 | `routes/search.py` GET /search |
| 全局功能 | 全局搜索 | 快捷跳转 | 搜索结果点击跳转 | — |
| 全局功能 | 主题系统 | 深色/浅色 | 主题切换按钮，CSS变量 | — |
| 全局功能 | 国际化 | 中英文 | i18n语言包切换 | — |
| 全局功能 | 响应式 | 移动端适配 | 响应式布局断点 | — |

---

## 八、外部服务集成

```
┌─────────────────────────────────────────────────┐
│                  外部服务                         │
├──────────────┬──────────────────────────────────┤
│ LLM Provider │ OpenAI / Anthropic / 本地模型     │
│ OAuth        │ GitHub OAuth / 微信登录           │
│ SMS          │ 短信验证码服务                     │
│ Email        │ SMTP 邮件服务                     │
│ Storage      │ 本地文件系统 / S3 对象存储         │
│ Vector DB    │ pgvector (PostgreSQL扩展)          │
└──────────────┴──────────────────────────────────┘
```

---

## 九、SKILL.md 规范

```yaml
---
skill_id: "unique_skill_id"           # 唯一标识
name: "技能名称"                       # 显示名称
version: "1.0.0"                      # 语义版本
executor_type: "Python_env"           # 执行器类型
entry_point: "scripts/main.py"        # 入口文件
timeout_seconds: 3600                 # 超时时间
category: "category_id"               # 分类ID
category_name: "分类名称"              # 分类显示名
subcategory: "subcategory_id"         # 子分类ID
subcategory_name: "子分类名称"         # 子分类显示名
tags: ["tag1", "tag2"]                # 标签
visibility: "private"                 # 可见性: private/team/public
license: "MIT"                        # 开源协议
---

## 1. 技能意图与功能边界
*AI判断何时调用此技能*

## 2. 动态参数定义规范
| 参数键名 | 数据类型 | 必填 | 默认值 | 详细描述说明 |

## 3. 操作指令与专家级知识库
*专家指导、参数推断逻辑、结果解读*
```

### 执行器类型

| 类型 | 说明 | 入口 |
|------|------|------|
| `Python_env` | 单Python脚本，argparse传参 | `scripts/main.py` |
| `R_env` | 单R脚本，commandArgs传参 | `scripts/main.R` |
| `Logical_Blueprint` | Nextflow DSL2 工作流 | `main.nf` |
| `Python_Package` | 完整Python包 | `src/__init__.py` |

---

## 十、部署与运维

```
开发环境:
  docker-compose up -d              # 一键启动
  docker logs autonome-api          # 查看日志
  alembic upgrade head              # 数据库迁移

生产部署:
  ./auto_deploy.sh -s "摘要" -d "详情"  # 自动部署脚本
  ├── git add .                     # 暂存变更
  ├── git commit                    # 提交代码
  ├── docker-compose build          # 重建镜像
  └── docker-compose up -d          # 重启服务

数据备份:
  pg_dump → PostgreSQL 备份
  redis-cli BGSAVE → Redis 备份
```
