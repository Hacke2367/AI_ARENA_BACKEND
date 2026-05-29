# ARCHITECTURE_STATE.md
_Generated: 2026-05-03T00:00:00Z | Total LOC scanned: 1,261 (18 Python files + 4 spec docs)_

---

## 1. The Blueprint

**AI Arena Fight** is a FastAPI backend that orchestrates real-time, persona-based LLM debates. Two AI combatants — each with a distinct identity, belief system, and vocabulary — take alternating turns producing two simultaneous outputs per turn: a hidden `internal_monologue` (tactical reasoning) and a public `spoken_dialogue` (the actual attack). This dual-output, Internal Monologue architecture is the system's core innovation: no LLM speaks until it has first privately analysed the opponent's last move and selected a tactic. The resulting structured JSON is consumed by a Streamlit Creator Dashboard for real-time telemetry visualisation and TTS pipelines for audio output.

The current stack is pure Python: **FastAPI 0.104.1** handles HTTP, **SQLAlchemy 2.0.23 + SQLite** (`arena.db`) own all persistent state, **Alembic 1.13.0** tracks schema migrations, and a universal `llm_router` dispatches to six provider adapters (Mock, OpenAI, Claude, Groq, Ollama, HuggingFace). Only one LLM adapter is initialised per provider key and cached for the process lifetime. Uvicorn is pinned to `--workers 1` to prevent SQLite WAL contention.

The system now also implements a **Recursive Memory Engine**: when the in-memory context window exceeds `(ARENA_MAX_HISTORY_TURNS * 2) + 1` messages, the oldest non-immune user/assistant pair is evicted and compressed by a summariser LLM (default: Groq) into a rolling `battle_memory` row. The compressed summary is injected at the top of every subsequent system prompt. The full raw log is preserved in `chat_history` forever — only the active window is trimmed. Summariser failure is non-fatal; the battle continues on the stale summary with a WARNING logged.

---

## 2. Rock-Solid — Working Components

| File | LOC | Role | Completeness | Robustness | Spec-Align | Status |
|------|-----|------|-------------|------------|------------|--------|
| `backend_arena/src/main.py` | 35 | App bootstrap, CORS, startup validation | 95 | 90 | 95 | SOLID |
| `backend_arena/src/api/routes.py` | 88 | FastAPI endpoints `/initialize_battle`, `/execute_action`, `/health`; async executor; full error-to-HTTP mapping | 95 | 90 | 95 | SOLID |
| `backend_arena/src/engine/fight_loop.py` | 264 | `MatchManager`: DB-backed battle state, turn sequencing, eviction loop, fallback stub | 92 | 85 | 92 | SOLID |
| `backend_arena/src/engine/llm_router.py` | 187 | Universal adapter: Mock, OpenAI, Claude, Groq, Ollama, HuggingFace; exponential backoff; adapter cache | 95 | 88 | 95 | SOLID |
| `backend_arena/src/engine/prompt_builder.py` | 29 | 3-layer system prompt assembly from `master_prompt.md` template; `long_term_memory` injection | 90 | 85 | 90 | SOLID |
| `backend_arena/src/schemas/payloads.py` | 53 | Pydantic v2 models for all I/O payloads; `model_validator` for `context_bomb` guard; 7 vibe literals | 95 | 92 | 95 | SOLID |
| `backend_arena/src/schemas/types.py` | 7 | `ChatMessage` dataclass with optional `id` for PK-safe eviction | 100 | 100 | 100 | SOLID |
| `backend_arena/src/database/db_manager.py` | 61 | SQLAlchemy ORM models (`Battle`, `ChatHistory`, `BattleMemory`); session factory; composite index; rollback on error | 95 | 92 | 95 | SOLID |
| `backend_arena/src/database/memory_engine.py` | 73 | Summariser call via `llm_router.route()`; overflow-triggered word-cap override; atomic upsert via `INSERT OR REPLACE` | 92 | 85 | 92 | SOLID |
| `backend_arena/src/exceptions.py` | 16 | Typed exception hierarchy (`ArenaError` → 6 sub-classes) | 100 | 100 | 100 | SOLID |
| `backend_arena/src/utils/tts_sanitizer.py` | 7 | Strips `*actions*` and `[brackets]` from text for TTS pipeline | 100 | 90 | 100 | SOLID |
| `alembic/env.py` | 43 | Alembic online/offline migration runner; reads DB URL from env; `render_as_batch=True` for SQLite | 95 | 92 | 95 | SOLID |
| `alembic/versions/001_create_initial_schema.py` | 55 | Creates `battles`, `chat_history` (with composite index), `battle_memory` tables; full downgrade path | 100 | 95 | 100 | SOLID |
| `docs/ai_jailbreak/master_prompt.md` | 93 | Master jailbreak template: Identity, DNA substitution slots, Forbidden tokens, Victory conditions, Output Forcing JSON contract | 100 | 100 | 100 | SOLID |

**End-to-end capability right now:** A client can POST `/initialize_battle` to create a DB-persisted battle with two LLM personas, then POST `/execute_action` repeatedly to drive alternating turns. Each turn produces the full 6-key response schema (`speaker`, `internal_monologue`, `spoken_dialogue`, `tts_ready_text`, `voice_params`, `telemetry`). After server restart, the same `battle_id` continues from where it left off. Memory compression fires automatically beyond the configured history window.

---

## 3. Tech Debt — Needs Refactor

### `backend_arena/tests/conftest.py` — (C:20 R:20 S:20)
Test fixture file written for the **old in-memory architecture** — imports `_active_battles` (a module-level dict that no longer exists in `fight_loop.py`) and instantiates `MatchManager()` with no arguments (the current constructor requires a SQLAlchemy `Session`).

- **Issue:** `from backend_arena.src.engine.fight_loop import _active_battles` — this symbol was deleted when Feature 04 migrated state to SQLite. Import will raise `ImportError` at collection time, blocking the **entire test suite**.
- **Issue:** `MatchManager()` call with no args fails — `__init__` now requires `db: Session`.
- **Missing:** SQLite in-memory test DB fixture (`create_engine("sqlite:///:memory:")`) + `SessionLocal` binding + per-test `db` session injection into `MatchManager(db)`.

### `backend_arena/tests/test_fight_loop.py` — (C:25 R:25 S:25)
All 8 tests reference `_active_battles` and the old no-arg `MatchManager()` interface.

- **Issue:** `from backend_arena.src.engine.fight_loop import _FALLBACK_STUB, _active_battles` — `_active_battles` does not exist; test collection fails immediately.
- **Issue:** `_active_battles[battle_id]["status"]`, `_active_battles[battle_id]["history"]`, `_active_battles[battle_id]["turn"] = 10` — all attempt to read/write a dict that no longer holds state. DB must be queried instead.
- **Issue:** `test_history_truncated_after_seven_turns` asserts `len(state["history"]) <= 12` against the old in-memory list — the actual check is now against DB `chat_history` rows.
- **Missing:** Tests for DB persistence across `MatchManager` instance boundaries, eviction immunity of `role="system"` rows, and summariser-failure non-fatal path.

### `backend_arena/tests/test_routes.py` — (C:40 R:40 S:40)
Integration tests run against the live FastAPI app but also import the defunct `_active_battles`.

- **Issue:** `from backend_arena.src.engine.fight_loop import _active_battles` — same import failure as above.
- **Issue:** `_active_battles[battle_id]["turn"] = 10` in `test_execute_action_turn_limit_returns_409` — state mutation must go through the DB session, not a dict.
- **Missing:** DB teardown between tests (each test should operate on an isolated in-memory SQLite DB via FastAPI's `Depends` override to prevent cross-test state bleed).

---

## 4. The Pending Pipeline

### 4a. Missing Components

| Component | Required By | Priority |
|-----------|-------------|----------|
| `creator_dashboard/app.py` | `docs/FRONTEND_TSD.md`; CLAUDE.md run command | CRITICAL |
| `.env` (runtime config file) | Feature 04 spec §1 (startup validation fails without `SUMMARIZER_LLM`, `GROQ_API_KEY`, `ARENA_DB_PATH`) | CRITICAL |
| `docs/SYSTEM_ARCHITECTURE.md` | CLAUDE.md spec-driven development mandate | HIGH |
| Test suite rewrite for DB-backed `MatchManager` | Feature 04 §6 acceptance criteria; currently all 3 test files fail at import | HIGH |
| `Dockerfile` / `docker-compose.yml` | Target deployment on RunPod/Vast.ai/Lambda Labs cloud GPU instances | MEDIUM |
| `backend_arena/src/utils/memory_manager.py` deletion confirmation | Feature 04 spec §2 ("strictly deprecated and must be deleted") — already absent, but should be confirmed gone in CI | LOW |

### 4b. Next 5 Engineering Actions (Priority Ordered)

1. **[CRITICAL] Rewrite all three test files to use an in-memory SQLite test DB** — every test currently fails at import due to the `_active_battles` symbol removal; zero test coverage is running. Use `pytest` fixture with `create_engine("sqlite:///:memory:")`, run `Base.metadata.create_all()` on it (test-only; not app startup), inject a `Session` into `MatchManager(db)`. Override `Depends(get_db)` in integration tests via `app.dependency_overrides`.

2. **[CRITICAL] Create `.env` file from `.env.example`** — without `SUMMARIZER_LLM`, `ARENA_DB_PATH`, and the relevant API key, the startup validation in `main.py` will either raise `RuntimeError` or emit a WARNING on every boot, and `alembic upgrade head` will use the default `./arena.db` path which may not be where operators expect it.

3. **[CRITICAL] Build `creator_dashboard/app.py`** — the Streamlit frontend is the operator's sole control surface (Next Turn, Context Bomb, Kill Switch, Telemetry charts, Internal Monologue toggle). Without it the system can only be driven via raw `curl`/HTTP. The `docs/FRONTEND_TSD.md` spec is complete and ready to implement.

4. **[HIGH] Write `docs/SYSTEM_ARCHITECTURE.md`** — CLAUDE.md names this as an authoritative source of truth alongside `BACKEND_TSD.md` and `FRONTEND_TSD.md`. Its absence means future contributors lack the cross-service dependency map (especially the Streamlit ↔ FastAPI ↔ SQLite ↔ LLM provider chain) and the VRAM-swap contract.

5. **[MEDIUM] Add `Dockerfile` and `docker-compose.yml`** — the target runtime is cloud GPU instances (RunPod, Vast.ai, Lambda Labs) accessed over SSH. A Docker image that runs `alembic upgrade head && uvicorn ... --workers 1` is the safest deployment unit; without it, operators must manually manage the Python environment and risk running `--workers > 1` which violates the SQLite WAL constraint.

---
_Generated by /audit skill · AI Arena Fight_
