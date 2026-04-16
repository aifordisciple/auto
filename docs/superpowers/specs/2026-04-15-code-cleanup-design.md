# Code Cleanup Design — Dead Code & Broken References

**Date:** 2026-04-15
**Scope:** Remove deleted/broken code, fix reference breaks, ensure project starts cleanly
**Approach:** Conservative (方案 B)

---

## Context

The V2 architecture upgrade removed 133 files (old AI agent framework, AI routes, AI/ML services, models) but these deletions were never committed. Additionally, several hub files still reference deleted modules, and some test files import deleted code.

## Part 1: Commit Deleted Files (133 files)

Stage and commit the 133 already-deleted files. These are unstaged deletions from the V2 upgrade:

- `app/agent/` (46 files) — entire old AI agent framework
- `app/api/routes/` (17 files) — AI-related routes
- `app/services/` (36 files) — AI/ML services
- `app/models/` (6 files) — deleted models (SystemSkill, FeedbackWeight, etc.)
- `app/core/` (1 file) — llm_model_config
- `app/tools/` (1 file) — geo_tools
- `autonome-studio/` (26 files) — frontend AI components

## Part 2: Delete Duplicate/Dead Code Files

| File | Lines | Reason |
|------|------:|--------|
| `app/core/skill_parser copy.py` | 1085 | Duplicate of skill_parser.py, no imports |
| `autonome-studio/src/components/chat/components/SysLogCard.tsx` | 277 | No imports anywhere |
| `autonome-studio/src/components/common/FilePicker.tsx` | 328 | No imports, active alternative exists |

## Part 3: Fix Alembic Reference Break

`alembic/env.py` line 12 imports `SystemSkill` from deleted `app.models.system_skill`. Remove this import.

## Part 4: Fix Hub File Reference Breaks

- `app/models/domain.py` — remove re-exports of deleted models
- `main.py` — remove registrations of deleted routes/services
- Other `__init__.py` hub files — clean broken imports

## Part 5: Delete Broken Test Files

~25 test files import deleted modules and cannot run. Delete them.

## Verification

After all changes:
1. `docker-compose down && docker-compose up -d` — verify no startup errors
2. Check backend logs for import errors
3. Verify frontend builds without errors
