# AUTONOME-BACKEND - FastAPI AI Agent System

## OVERVIEW

FastAPI + LangGraph multi-agent backend for bioinformatics workflows. Docker-sandboxed code execution, JWT auth, Celery async tasks.

## STRUCTURE

```
app/
├── api/routes/      # REST endpoints (auth, chat, projects, billing, admin)
├── agent/           # LangGraph multi-agent orchestration
├── core/            # config, database, security, logger
├── models/          # SQLModel domain entities
├── tools/           # Docker sandbox + bioinformatics tools
└── services/        # Celery async task queue
```

## WHERE TO LOOK

| Task | File |
|------|------|
| Add API endpoint | `app/api/routes/*.py` |
| Modify agent behavior | `app/agent/bot.py` |
| Add sandbox tool | `app/tools/bio_tools.py` |
| New data model | `app/models/domain.py` |
| Auth logic | `app/core/security.py`, `app/api/deps.py` |
| Celery tasks | `app/services/celery_app.py` |

## CONVENTIONS

- **Settings**: `app/core/config.py` — Pydantic BaseSettings, reads `.env`
- **Logging**: Use `from app.core.logger import log` (Loguru)
- **DB Sessions**: Inject via `Depends(get_session)` from `app/api/deps.py`
- **Auth**: `Depends(get_current_user)` for protected routes
- **Admin**: `Depends(get_current_superuser)` for admin routes

## ANTI-PATTERNS

- Don't use `print()` — use `log.info()`, `log.error()`
- Don't create engine instances — use `from app.core.database import engine`
- Don't hash passwords manually — use `verify_password()`, `get_password_hash()`

## AGENT SYSTEM

**5 Specialists** (in `bot.py`):
1. **Advisor** — Scientific guidance, no code
2. **Cleaner** — Data preprocessing (uses `execute_python_code`)
3. **Analyst** — Analysis + visualization (uses all bio tools)
4. **Interpreter** — Biological interpretation
5. **Reporter** — Report generation (uses `generate_publishable_report`)

**Supervisor** routes based on conversation state via LangGraph `StateGraph`.

## DOCKER SANDBOX

```python
# Tool: execute_python_code
# Image: autonome-tool-env
# Limits: 4GB RAM, no network, dropped caps
# Mount: HOST_UPLOAD_DIR → /app/uploads (rw)
```

## COMMANDS

```bash
uvicorn main:app --reload --port 8000    # Dev server
celery -A app.services.celery_app worker --loglevel=info  # Async worker
alembic upgrade head                      # Run migrations
python make_admin.py <email>              # Promote user to admin
```
