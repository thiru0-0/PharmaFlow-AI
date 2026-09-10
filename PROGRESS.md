# PharmaFlow AI — Build Progress

Resume-from-here log. Update after every checkpoint.

## Environment (as found)
- OS: Windows 11, PowerShell + Git Bash
- Python 3.14.7 (venv at `backend/.venv`), Node 24.19
- **No local PostgreSQL / Docker.** DB target = user-provided `DATABASE_URL` (Postgres). Code is
  SQLAlchemy-portable; falls back to local SQLite file only for offline dev if `DATABASE_URL` unset.
- `ortools` 9.15, `psycopg` 3.3 confirmed installing cleanly on 3.14.

## Decisions
- Scope focus this session: **P0 end-to-end first** (per user).
- DB: user will provide a Postgres `DATABASE_URL`. Until provided, checkpoints run on SQLite
  (`sqlite:///./pharmaflow_dev.db`) which still enforces FKs + CHECK + triggers for the state machine.
- Registry: SHA-256 hash chain + Ed25519 signatures, per-actor keypairs.
- Route optimizer: OR-Tools CVRP (P1).

## Checkpoint status
- [x] A — DB, models, migrations (alembic 0001 + init_db), seed A-G load cleanly (SQLite; Postgres pending URL)
- [x] B — Auth, RBAC, registry hash-chain + Ed25519 verified via API tests (11,12,14 green)
- [x] C — Full lifecycle ACTIVE->DESTROYED_CERTIFIED via API + scenarios.run_happy, registry_valid=True
- [x] D — Re-entry blocks sale + notifies controller+manufacturer, measured latency 6 ms (tests 1,3,4,5)
- [ ] E — Frontend for all 5 roles calls real API, no mock data
- [~] F — scenarios.run_fraud 0.01s / run_happy 0.07s server-side (UI-driven still to wire in E)
- [x] G — 15/15 critical tests pass (`pytest -q` -> 15 passed)
- [ ] H — Docs, polish, commit

## Verified commands
- `python -m alembic upgrade head` -> ok
- `python -m scripts.init_db` -> 8 accounts, 8 batches (A..G + A' second manufacturer)
- `python -m pytest -q` -> 15 passed
- scenarios: fraud 6ms notify latency, happy -> DESTROYED_CERTIFIED registry valid, verify_all healthy 29 events

## DB note
Still on SQLite fallback — user chose "provide a DATABASE_URL" but none supplied yet.
All code is SQLAlchemy-portable; guards.py has a Postgres (plpgsql) branch. To switch:
set backend/.env DATABASE_URL=postgresql+psycopg://... then `alembic upgrade head` + `python -m scripts.init_db`.

## Next
1. Frontend (Next.js) — all 5 role dashboards on the real API (Checkpoint E).
2. Wire demo reset + scenario buttons in Admin UI (Checkpoint F).
3. README + commit (Checkpoint H).
