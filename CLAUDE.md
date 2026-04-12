# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# AUTONOME STUDIO

AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端。多 Agent 系统 + Docker 沙箱代码执行。

详细架构: `docs/ARCHITECTURE.md` | 开发规范: `docs/CONVENTIONS.md` | 命令参考: `docs/COMMANDS.md`

---

## 强制注释铁律

- **绝不允许删除或精简原有注释**，修改代码时必须同步更新注释
- 核心业务逻辑必须有详尽的中文注释，说明"为什么"而非仅"做什么"
- 违规判定：注释被替换为 `//... existing code...` 则提交无效
- 代码超过 1000 行必须按功能模块拆分

---

## 开发与部署工作流

每次代码修改后必须遵循：

1. **执行开发** — 完成代码编写
2. **状态验证** — `docker-compose down && docker-compose up -d`，检查日志无报错
3. **自动部署** — `./auto_deploy.sh -s "feat: 简要总结" -d "详细修改说明"`（脚本内置 git add/commit/push）

---

## 常用命令

```bash
# Docker 服务
docker-compose up -d                                    # 启动
docker-compose down && docker-compose up -d              # 重启（代码修改后）
docker logs autonome-api | tail -30                      # 后端日志
docker logs autonome-web | tail -30                      # 前端日志
docker-compose exec postgres psql -U autonome autonome_db # 数据库

# 后端本地开发
cd autonome-backend
uvicorn main:app --reload --port 8000                   # 开发服务器
celery -A app.services.celery_app worker --loglevel=info # Celery worker
alembic upgrade head                                     # 数据库迁移
alembic revision --autogenerate -m "描述"                # 创建迁移
python make_admin.py <email>                             # 提升管理员

# 前端本地开发
cd autonome-studio
npm run dev                                              # 开发服务器 (port 3000)
npm run build                                            # 生产构建
npm run lint                                             # ESLint

# 根目录 monorepo
pnpm dev                                                 # 启动前端
pnpm build                                               # 构建前端
pnpm lint                                                # Lint 所有包
```

**添加前端依赖后必须重建镜像：** `docker-compose build --no-cache frontend && docker-compose up -d`

---

## Docker 服务

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| backend-api | autonome-api | 8000 | FastAPI 后端 |
| frontend | autonome-web | 3001 | Next.js 前端 |
| postgres | autonome-postgres | 5433 | PostgreSQL + pgvector |
| redis | autonome-redis | 6379 | Cache + Celery broker |
| backend-worker | autonome-worker | — | Celery async tasks |

Access: Frontend http://localhost:3001 | API http://localhost:8000/docs

---

## 架构概览

### Monorepo 结构

```
autonome-backend/   FastAPI + LangGraph 后端 (Python 3.11)
autonome-studio/    Next.js 16 前端 (React 19, TypeScript 5)
packages/           共享包 (shared-types, shared-components, shared-store, shared-utils)
docs/               架构文档、规范、计划
scripts/            运维脚本
uploads/            用户文件上传 (bind-mount 到容器 /workspace)
```

### 后端架构 (autonome-backend)

```
app/
├── agent/           LangGraph 多 Agent 编排
│   ├── unified_executor.py   主 Agent 构建器 (build_unified_agent)
│   ├── schemas.py            Pydantic 模式 (IntentClassification, StrategyCard 等)
│   ├── nodes/                Agent 图节点 (chat, router, skill_execute, sandbox_planner)
│   ├── tools/                Agent 工具定义 (code_execution, data_probe, file_operation)
│   └── prompts/              系统提示词和技能提示词
├── api/
│   ├── deps.py               依赖注入 (get_current_user, get_session)
│   └── routes/               40+ 路由模块，按领域组织
│       └── skills/           技能子路由 (crud, forge, catalog, draft 等)
├── core/
│   ├── config.py             Pydantic BaseSettings (读取 .env)
│   ├── database.py           SQLModel 引擎 + 会话工厂 (PostgreSQL/pgvector + SQLite fallback)
│   ├── security.py           JWT (HS256, 7天) + bcrypt
│   ├── logger.py             Loguru 日志配置
│   ├── skill_parser.py       SKILL.md YAML 解析器
│   └── sandbox_config.py     Docker 沙箱配置
├── models/                   SQLModel 领域模型 (20+ 模型文件)
│   └── domain.py             重导出枢纽
├── services/                 65+ 服务模块
│   ├── celery_app.py         Celery 配置 + 任务注册
│   ├── skill_matcher.py      技能匹配 (规则+向量+LLM 三阶段)
│   ├── skill_executor.py     技能执行引擎
│   ├── container_pool_service.py  Docker 容器暖池
│   └── pty_manager.py        PTY 终端管理
├── tools/
│   ├── bio_tools.py          Docker 沙箱代码执行 (核心工具)
│   ├── probe_tools.py        数据探针工具
│   ├── geo_tools.py          GEO 数据库工具
│   └── report_tools.py       报告生成工具
├── mcp/                      Model Context Protocol (语义搜索, 技能 MCP)
└── skills/                   技能包目录 (每个含 SKILL.md)
```

**Agent V2 架构：** `build_unified_agent()` 使用 LangGraph StateGraph，单一统一节点分发到专业模块。意图类型：CHAT / EXPLICIT_SKILL / VAGUE_ANALYSIS / TROUBLESHOOT / SYSTEM_ACTION。VAGUE_ANALYSIS 路由到 SandboxPlanner（门控），回退到 SuperExecutorV4。

**5 个专家 Agent：** Advisor (科学指导) / Cleaner (数据预处理) / Analyst (分析+可视化) / Interpreter (生物学解读) / Reporter (报告生成)

**Docker 沙箱：** 镜像 `autonome-tool-env`，4GB RAM，无网络，`HOST_UPLOAD_DIR` → `/workspace` (rw)，暖池管理。

### 前端架构 (autonome-studio)

```
src/
├── app/              Next.js App Router
│   ├── page.tsx      主 IDE 工作区 (3 面板布局)
│   ├── login/        认证页
│   ├── admin/        管理后台
│   ├── dashboard/    研究项目指挥中心
│   └── share/[token] 共享项目访问
├── components/
│   ├── chat/         ChatStage, 消息组件, StreamingMarkdown
│   ├── layout/       Sidebar, TopHeader, SessionSidebar
│   └── overlays/     模态面板 (DataCenter, SkillCenter, Settings 等)
├── store/            Zustand stores
│   ├── useChatStore.ts       消息、流式、书签、标签
│   ├── useUIStore.ts         Overlay 管理、主题、任务模式 (persisted)
│   ├── useWorkspaceStore.ts  项目上下文、文件、工具参数 (persisted)
│   ├── useAuthStore.ts       用户会话
│   └── useForgeStore.ts      技能锻造状态
├── hooks/            自定义 hooks (useChatStream, useMessageActions 等)
├── lib/
│   ├── api.ts        后端 API 客户端 (动态 BASE_URL, JWT 自动注入)
│   └── utils.ts      cn() 工具
└── adapter/          平台抽象层 (Web vs Tauri 桌面)
```

**3 面板布局：** Sidebar (15%) | ChatStage (60%) | Assets (25%)

**技术栈：** Tailwind CSS v4 + shadcn/ui (new-york, slate) | react-resizable-panels v4 | Monaco Editor | xterm.js | ECharts | ReactFlow | Framer Motion | SSE via `@microsoft/fetch-event-source`

**API 客户端：** 动态 `BASE_URL` 使用 `window.location.hostname:8000`，JWT 存储在 `localStorage('autonome_access_token')`，401 自动重定向 `/login`。

---

## Probe Tools 模式

处理任何数据文件前，Agent **必须**调用探针工具，**禁止**猜测列名或路径。

| 工具 | 用途 |
|------|------|
| `peek_tabular_data` | 预览表格 (CSV/TSV) 表头和维度 |
| `scan_workspace` | 扫描目录结构 |
| `inspect_h5ad` | 解析 .h5ad 单细胞数据 |
| `inspect_fastq` | 预览 FASTQ 测序文件 |
| `inspect_bam` | 预览 BAM 比对文件 |

---

## SKILL 系统

- Skills 位于 `autonome-backend/app/skills/`，每个包含 `SKILL.md` (YAML 元数据 + 参数定义 + 专家知识)
- 执行器类型：`Python_env` (argparse) / `R_env` (commandArgs) / `Logical_Blueprint` (Nextflow DSL2) / `Python_Package`
- Agent 优先匹配 SKILL，无法匹配时才 Live Coding
- SKILL 解析器：`app/core/skill_parser.py`

---

## 规范速查

**后端：** Loguru 日志 (`from app.core.logger import log`)，SQLModel ORM，JWT HS256/7天，`Depends(get_session)` 注入 DB 会话，`Depends(get_current_user)` 保护路由

**前端：** `@/*` 路径别名，Zustand 状态管理 (禁止 Context API 做全局状态)，深色模式默认，Tailwind v4 + shadcn/ui

| 禁止 | 正确做法 |
|------|----------|
| `any` 类型 | 定义明确接口 |
| `console.log()` | 使用 logger 或移除 |
| `print()` | `log.info()` |
| 硬编码中文到 matplotlib | 英文或变量 |
| 猜测列名/路径 | 先调用探针工具 |
| React Context 全局状态 | Zustand |

**React Resizable Panels v4：** `defaultSize="15%"` (字符串)，**禁止** `defaultSize={15}` (数字)

**环境变量：** 使用 `TASK_OUT_DIR` 获取输出目录，禁止硬编码路径

---

## 重要文件索引

| Task | Location |
|------|----------|
| Agent 统一执行器 | `autonome-backend/app/agent/unified_executor.py` |
| Agent 模式定义 | `autonome-backend/app/agent/schemas.py` |
| Docker 沙箱执行 | `autonome-backend/app/tools/bio_tools.py` |
| Probe Tools | `autonome-backend/app/tools/probe_tools.py` |
| API 路由 | `autonome-backend/app/api/routes/` |
| 数据模型枢纽 | `autonome-backend/app/models/domain.py` |
| SKILL 解析器 | `autonome-backend/app/core/skill_parser.py` |
| 技能匹配器 | `autonome-backend/app/services/skill_matcher.py` |
| 主 IDE 页面 | `autonome-studio/src/app/page.tsx` |
| API 客户端 | `autonome-studio/src/lib/api.ts` |
| Zustand Stores | `autonome-studio/src/store/` |
| 平台适配层 | `autonome-studio/src/adapter/` |

---

## Known Issues

| Issue | Location |
|-------|----------|
| Hardcoded IP 113.44.66.210 | docker-compose.override.yml, frontend API calls |
| Docker socket mounted | docker-compose.yml (security risk) |
| `celery_app.py` uses `print()` (14 instances) | Should use `log.info()` |
