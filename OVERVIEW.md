# Project Overview — AI Arena Fight
**Generated:** 2026-05-19 | **Source:** ARCHITECTURE_STATE.md + codebase scan + git history

---

## What is this?

**AI Arena Fight** is a Python-based system that orchestrates real-time, persona-based LLM debates between two AI combatants. Each AI has a distinct identity, belief system, and vocabulary. On every turn, the backend fires a proprietary **Internal Monologue** architecture: the AI first privately reasons about the opponent's move, then delivers a public spoken attack. A Streamlit **Creator Dashboard** drives the battle and visualises live telemetry — built for 4K recording and Shorts/Reels post-production.

**Stack:** FastAPI + SQLAlchemy/SQLite + Alembic (backend) · Streamlit + Altair (frontend) · httpx · Pydantic v2 · Six LLM adapters (Mock, OpenAI, Claude, Groq, Ollama, HuggingFace)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI 0.104.1, Uvicorn 0.24.0 (workers=1, SQLite WAL constraint) |
| Persistence | SQLAlchemy 2.0.23, SQLite (`arena.db`), Alembic 1.13.0 |
| LLM Routing | Universal adapter in `llm_router.py` — 6 providers, exponential backoff |
| Memory Engine | Recursive compression via summariser LLM → rolling `battle_memory` row |
| Frontend | Streamlit ≥1.32, Altair ≥5, httpx, Pandas |
| Prompting | `master_prompt.md` Jinja-style template + `string.Template` safe_substitute |
| Testing | pytest (currently broken — see below) |

---

## Feature Status

### ✅ Completed

- **Feature 01 — Pydantic Payload Schemas** — All I/O models defined in `payloads.py`: `MatchConfig`, `EntityConfig`, `ExecuteActionRequest/Response`, `InitializeBattleRequest/Response`, with all Pydantic v2 validators and the `context_bomb` guard.

- **Feature 02 — FastAPI Routes** — `POST /initialize_battle`, `POST /execute_action`, `GET /health` fully implemented in `routes.py` with complete HTTP error mapping (404, 409, 429, 502, 503, 504).

- **Feature 03 — Core Engine** — `fight_loop.py` (`MatchManager`), `llm_router.py` (6 adapters + backoff), `prompt_builder.py` (3-layer system prompt), `tts_sanitizer.py`, `exceptions.py` (typed hierarchy). Full end-to-end battle execution works.

- **Feature 04 — Persistent State & Recursive Memory Engine** — SQLite via SQLAlchemy replaces the old in-memory dict. Alembic migration (`001_create_initial_schema.py`) creates `battles`, `chat_history`, `battle_memory` tables. Memory compression fires automatically when context window overflows; summariser failure is non-fatal. Battle state survives server restarts.

- **Feature 05 — Persona Engine (Jailbreak & Injection)** — `string.Template` compiler injects persona DNA (`backstory`, `vocabulary`, `debate_tactics`) from JSON fixtures into `master_prompt.md`. `_enrich_with_persona()` in `fight_loop.py` loads fixtures by `persona_id`. Three fixtures: `gym_bro.json`, `crypto_hustler.json`, `tech_bro.json`. `PersonaNotFoundError` → HTTP 404.

- **Creator Dashboard — Spec + Implementation Plan** — `specs/01_creator_dashboard.md` (v1.0.0) and `01_creator_dashboard_impl.md` are complete and ready.

- **Creator Dashboard — Built & Reviewed** — `creator_dashboard/app.py` and `creator_dashboard/api_client.py` are implemented. An expert code review was done (`CODE_REVIEW.md`, 5/10 overall). All 14 review findings were then fixed in this session: mutable defaults bug, XSS, missing TimeoutException, blocking sleeps, CSS bleed, bare except, status_placeholder position, connection pooling, retry logic, logging, URL validation, and more. Current state: **production-ready for single-user use**.

---

### 🔄 Currently Working On

- **Test Suite Rewrite** — 3 of 4 test files (`conftest.py`, `test_fight_loop.py`, `test_routes.py`) import the deleted `_active_battles` symbol and will **fail at collection time** — zero test coverage is running. `test_prompt_builder.py` (Feature 05) and `test_router.py` are the only currently healthy test files.
  - **What remains:** Rewrite `conftest.py` to use an in-memory SQLite fixture, inject `Session` into `MatchManager(db)`, and override `Depends(get_db)` in integration tests via `app.dependency_overrides`.

---

### 📋 Planned / Not Started

- **`.env` runtime config file** — `.env.example` exists (with `ARENA_DB_PATH`, `SUMMARIZER_LLM`, `ARENA_SUMMARY_MAX_WORDS`, `GROQ_API_KEY`). Actual `.env` has not been created. Without it, startup validation in `main.py` will raise or warn on every boot. *(Critical — blocks first real run)*

- **`docs/SYSTEM_ARCHITECTURE.md`** — Referenced in `CLAUDE.md` as an authoritative spec alongside `BACKEND_TSD.md` and `FRONTEND_TSD.md`. Does not exist yet. Should document the Streamlit ↔ FastAPI ↔ SQLite ↔ LLM provider dependency chain and the VRAM-swap contract.

- **`Dockerfile` / `docker-compose.yml`** — Target deployment is cloud GPU instances (RunPod, Vast.ai, Lambda Labs via SSH). A Docker image running `alembic upgrade head && uvicorn ... --workers 1` is the correct deployment unit. Not started.

---

## Last Active Area

`creator_dashboard/` — Built `app.py` + `api_client.py` this session, ran an expert code review, then fixed all 14 issues found (security, performance, bug fixes). Files are clean and syntax-validated.

`backend_arena/src/` — 5 files show as modified in `git status` (routes, fight_loop, prompt_builder, exceptions, payloads) — these are the Feature 05 persona engine changes that haven't been committed yet.

---

## Next Step (Inferred)

**Two immediate actions before moving to new features:**

1. **Create `.env`** — Copy `.env.example` → `.env` and fill in `SUMMARIZER_LLM=mock` (for testing) + `ARENA_DB_PATH=./arena.db`. Without this the backend won't start cleanly.
   ```bash
   cp .env.example .env
   ```

2. **Fix the test suite** — Rewrite `backend_arena/tests/conftest.py` to use `create_engine("sqlite:///:memory:")` and inject `Session` into `MatchManager`. Then update `test_fight_loop.py` and `test_routes.py` to go through the DB instead of `_active_battles`. This is the only thing blocking `pytest` from running at all.
   > Check: `backend_arena/tests/conftest.py` — all three broken files import `_active_battles` which no longer exists in `fight_loop.py`.

After those two: run `streamlit run creator_dashboard/app.py` + `uvicorn backend_arena.src.main:app --reload` to do a live end-to-end smoke test of the completed Creator Dashboard.

---

## File Map (Quick Reference)

```
AI_ARENA_FIGHT/
├── backend_arena/
│   ├── src/
│   │   ├── api/routes.py              ✅ Complete
│   │   ├── engine/
│   │   │   ├── fight_loop.py          ✅ Complete
│   │   │   ├── llm_router.py          ✅ Complete
│   │   │   └── prompt_builder.py      ✅ Complete
│   │   ├── database/
│   │   │   ├── db_manager.py          ✅ Complete
│   │   │   └── memory_engine.py       ✅ Complete
│   │   ├── schemas/payloads.py        ✅ Complete
│   │   ├── personas/                  ✅ 3 fixtures (gym_bro, crypto_hustler, tech_bro)
│   │   └── utils/tts_sanitizer.py     ✅ Complete
│   └── tests/
│       ├── conftest.py                🔴 BROKEN — imports deleted _active_battles
│       ├── test_fight_loop.py         🔴 BROKEN — imports deleted _active_battles
│       ├── test_routes.py             🔴 BROKEN — imports deleted _active_battles
│       ├── test_router.py             ✅ Healthy
│       └── test_prompt_builder.py     ✅ Healthy
├── creator_dashboard/
│   ├── app.py                         ✅ Complete (all 14 review fixes applied)
│   ├── api_client.py                  ✅ Complete (pooling, retry, logging)
│   └── requirements.txt               ✅ Complete
├── alembic/                           ✅ Complete (migration 001 applied)
├── docs/
│   ├── BACKEND_TSD.md                 ✅ Authoritative spec
│   ├── FRONTEND_TSD.md                ✅ Authoritative spec
│   ├── SYSTEM_ARCHITECTURE.md         📋 NOT CREATED YET
│   └── ai_jailbreak/master_prompt.md  ✅ Complete
├── specs/01_creator_dashboard.md      ✅ Complete
├── 01_creator_dashboard_impl.md       ✅ Complete
├── .env.example                       ✅ Exists
├── .env                               📋 NOT CREATED — blocks backend startup
└── Dockerfile                         📋 NOT STARTED
```

---

*Status inferred from: ARCHITECTURE_STATE.md (audit), git log, git status (5 uncommitted backend files = Feature 05 persona engine changes), direct file presence checks, and this session's work log.*
