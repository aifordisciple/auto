# AUTONOME STUDIO - Project Knowledge Base

**Generated:** 2026-03-03
**Commit:** 498322e
**Branch:** main

## OVERVIEW

AI-Native Bioinformatics IDE — monorepo with FastAPI/LangGraph backend + Next.js 16 frontend. Multi-agent system for bioinformatics workflows (RNA-Seq, single-cell, variant calling) with Docker-sandboxed code execution.

## STRUCTURE

```
autonome/
├── autonome-backend/    # FastAPI + LangGraph AI agent system (port 8000)
├── autonome-studio/     # Next.js 16 IDE frontend (port 3000)
├── docker-compose.yml   # 5-service orchestration
└── run.sh               # Local dev startup
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
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
- Loguru for logging (not stdlib)
- JWT auth with 7-day expiry, HS256

**Frontend (Next.js/TypeScript)**
- Path alias: `@/*` → `./src/*`
- Zustand for state (not Context API)
- Framer Motion for animations
- shadcn/ui component patterns

## ANTI-PATTERNS (THIS PROJECT)

```typescript
// ❌ WRONG - react-resizable-panels v4
<Panel defaultSize={15} />

// ✅ CORRECT - must be string percentage
<Panel defaultSize="15%" />
```

- **NEVER** use `any` type suppressions
- **NEVER** use numeric `defaultSize` in react-resizable-panels
- **ALWAYS** use Zustand for global state

## UNIQUE STYLES

**Multi-Agent System (LangGraph)**
- 5 specialist agents: Advisor, Cleaner, Analyst, Interpreter, Reporter
- Supervisor routes tasks via StateGraph
- Each agent prefixed with role emoji in output

**Docker Sandbox**
- Code execution in isolated containers (`autonome-tool-env` image)
- 4GB memory limit, network disabled, capabilities dropped
- Host `uploads/` volume-mounted for data I/O

**3-Panel IDE Layout**
- Left (15%): Navigation + history
- Center (60%): AI chat stage
- Right (25%): Data center + tools

## COMMANDS

```bash
# Full stack (Docker)
docker-compose up --build

# Local development
./run.sh                    # Backend :8000, Frontend :3001

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
- No test framework configured yet
- Frontend uses dark mode by default (`className="dark"` on `<html>`)
