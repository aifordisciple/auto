# AUTONOME STUDIO - Project Knowledge Base

**Generated:** 2026-03-04
**Commit:** ec6e91e
**Branch:** main

## OVERVIEW

AI-Native Bioinformatics IDE — monorepo with FastAPI/LangGraph backend + Next.js 16 frontend. Multi-agent system for bioinformatics workflows (RNA-Seq, single-cell, variant calling) with Docker-sandboxed code execution.

## STRUCTURE

```
autonome/
├── autonome-backend/    # FastAPI + LangGraph AI agent system (port 8000)
├── autonome-studio/     # Next.js 16 IDE frontend (port 3001)
├── docker-compose.yml   # 5-service orchestration
├── run.sh               # ⚠️ BROKEN - use docker-compose instead
└── auto_deploy.sh       # Git + Docker deployment
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| API routes | `autonome-backend/app/api/routes/` |
| AI agent logic | `autonome-backend/app/agent/bot.py` |
| Docker sandbox tools | `autonome-backend/app/tools/bio_tools.py` |
| Domain models | `autonome-backend/app/models/domain.py` |
| Frontend pages | `autonome-studio/src/app/` |
| Zustand stores | `autonome-studio/src/store/` |
| API client | `autonome-studio/src/lib/api.ts` |
| Config (backend) | `autonome-backend/app/core/config.py` |

## CONVENTIONS

**Backend (Python/FastAPI)**
- Pydantic Settings from `.env` files
- SQLModel ORM with Alembic migrations
- Loguru for logging (NOT stdlib)
- JWT auth with 7-day expiry, HS256

**Frontend (Next.js/TypeScript)**
- Path alias: `@/*` → `./src/*`
- Zustand for state (NOT Context API)
- Framer Motion for animations
- shadcn/ui component patterns
- Dark mode default (`className="dark"` on `<html>`)

## ANTI-PATTERNS (THIS PROJECT)

### Critical - Fix Immediately
```typescript
// ❌ WRONG - react-resizable-panels v4
<Panel defaultSize={15} />

// ✅ CORRECT - must be string percentage
<Panel defaultSize="15%" />
```

- **NEVER** use `any` type (11 violations found)
- **NEVER** use numeric `defaultSize` in react-resizable-panels (5 violations in page.tsx)
- **ALWAYS** use Zustand for global state

### Logging Anti-Patterns
- **NEVER** use `print()` in Python - use `log.info()`, `log.error()`
- **NEVER** use `console.log()` in TypeScript

## KNOWN ISSUES

| Issue | Location | Severity |
|-------|----------|----------|
| run.sh uses wrong dirs | `run.sh` lines 2,4 | CRITICAL |
| Hardcoded IP 113.44.66.210 | docker-compose.override.yml, Dockerfiles | HIGH |
| Docker socket mounted | docker-compose.yml | SECURITY |
| No test framework | entire project | MEDIUM |
| `any` type violations | 11 files | LOW |

## UNIQUE STYLES

**Multi-Agent System (LangGraph)**
- 5 specialist agents: Advisor, Cleaner, Analyst, Interpreter, Reporter
- Supervisor routes tasks via StateGraph
- Each agent prefixed with role emoji in output

**Docker Sandbox**
- Code execution in isolated containers (`autonome-tool-env` image)
- 4GB memory limit, network disabled, capabilities dropped
- Host `uploads_data` volume mounted to `/app/uploads`

**3-Panel IDE Layout**
- Left (15%): Navigation + history
- Center (60%): AI chat stage
- Right (25%): Data center + tools

## COMMANDS

```bash
# Full stack (Docker) - RECOMMENDED
docker-compose up --build

# Backend only
cd autonome-backend && uvicorn main:app --reload --port 8000

# Frontend only
cd autonome-studio && npm run dev

# Celery worker (async tasks)
celery -A app.services.celery_app worker --loglevel=info

# Database migrations
cd autonome-backend && alembic revision --autogenerate -m "msg"
alembic upgrade head
```

## NOTES

- PostgreSQL with pgvector for embeddings
- Stripe billing (credits-based)
- Frontend uses dark mode by default
- Files stored in project folders: `/app/uploads/project_{id}/`

## 核心开发与部署工作流规范

你当前运行在一个由 Git 进行版本控制，并使用 Docker Compose 进行服务编排的 Mac 服务器项目中。对于收到的任何开发任务，你必须严格遵循以下步骤：

1. **执行开发**：完成用户要求的代码编写或编辑任务。
2. **状态验证**：每次代码修改完成后，你必须先执行`docker-compose down && docker-compose up -d`重启docker服务，然后执行`docker logs  autonome-api | tail -30` 和 `docker logs  autonome-web | tail -30`来查看docker logs测试是否有报错，如有报错则返回进行修复。
3. **自动部署**：上一步状态验证通过后，你必须调用项目根目录下的 `./auto_deploy.sh` 脚本来完成后续动作。
   - 必须使用 `-s` 参数传递简要的修改总结（如 "feat: 增加用户登录接口"）。
   - 必须使用 `-d` 参数传递详细的修改说明（Comments），解释修改了哪些逻辑及原因。
   - 示例命令：`./auto_deploy.sh -s "fix: 修复数据库连接超时" -d "调整了 db_config.js 中的 timeout 参数，从 3000ms 增加到 5000ms，以适应当前网络环境。"`，注意：该脚本已内置 `git add .`、`git commit` 以及 `docker-compose down && docker-compose up -d --build` 的完整逻辑，你只需调用该脚本并传入准确的参数即可。