# Code Review — Backend (Expert Level)

**Reviewed:** `backend_arena/src/` — 10 files
**Date:** 2026-05-22
**Standard:** Production-grade (security, concurrency, performance, scalability)

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 10
**Overall Quality Score:** 6 / 10
**Overall Improvement Chance:** 65%
**Verdict:** ❌ Not production-ready. Solid architecture and intentional design choices, but real concurrency bugs (cross-thread DB session, unlocked adapter cache), missing schema bootstrap, deprecated FastAPI APIs, and a permissive CORS policy block deployment.

### Score Breakdown

| File | Score | Production-Ready? |
|------|-------|---|
| `main.py` | 5/10 | ❌ |
| `api/routes.py` | 6/10 | ⚠️ |
| `engine/llm_router.py` | 6/10 | ⚠️ |
| `engine/fight_loop.py` | 5/10 | ❌ |
| `engine/prompt_builder.py` | 8/10 | ✅ |
| `schemas/payloads.py` | 8/10 | ✅ |
| `schemas/types.py` | 8/10 | ✅ |
| `exceptions.py` | 7/10 | ✅ |
| `database/db_manager.py` | 5/10 | ❌ |
| `database/memory_engine.py` | 6/10 | ⚠️ |
| `utils/tts_sanitizer.py` | 7/10 | ✅ |

---

## 🔴 Critical Fixes (Do First)

### 1. Cross-Thread SQLAlchemy Session — `engine/fight_loop.py:220-229`

```python
with ThreadPoolExecutor(max_workers=1) as _pool:
    _future = _pool.submit(
        run_memory_compression,
        battle_id, current_summary, evicted, turn,
        self.db,   # ← Session passed to a different thread
    )
```

**Problem:** SQLAlchemy `Session` is **not thread-safe**. The session is created in the FastAPI request thread (via `Depends(get_db)`) and then handed to a worker thread inside an executor. Concurrent reads/writes through this same session from two threads can cause partial commits, `DetachedInstanceError`, and silent data corruption — exactly the kind of bug that won't surface until production load.

**Fix:** Either run the summariser synchronously (it's already capped at 5s), OR use a fresh session inside the executor by passing only the connection URL / a session factory.

```python
from backend_arena.src.database.db_manager import SessionLocal

def _run_compression_in_thread(...):
    with SessionLocal() as worker_db:
        return run_memory_compression(..., worker_db)
```

---

### 2. Adapter Cache Race Condition — `engine/llm_router.py:202-221`

```python
_adapter_cache: dict[str, LLMAdapter] = {}

def route(selected_llm: str) -> LLMAdapter:
    if selected_llm not in _adapter_cache:
        ...
        _adapter_cache["openai"] = OpenAIAdapter()
    return _adapter_cache[selected_llm]
```

**Problem:** Module-level mutable dict with no lock. Under concurrent FastAPI requests, two threads can both check `not in` simultaneously, both build a fresh `OpenAIAdapter()`, and the second write clobbers the first — leaking the first client and creating socket/file-descriptor pressure. Worse, a request reading mid-construction can get a half-initialized object.

**Fix:** Use `threading.Lock` or `functools.lru_cache` (which is thread-safe):

```python
from functools import lru_cache

@lru_cache(maxsize=None)
def route(selected_llm: str) -> LLMAdapter:
    return _build_adapter(selected_llm)
```

---

### 3. CORS Wildcard — `main.py:22-27`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Problem:** Allows ANY origin to call the API with ANY headers and ANY method. If this server is ever exposed beyond localhost, any malicious site can drive battles, exhaust LLM credits, and leak `battle_id`s through victims' browsers.

**Fix:** Read allowed origins from env, default to dashboard URL only:

```python
allowed = os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",")
app.add_middleware(CORSMiddleware, allow_origins=allowed, allow_methods=["GET","POST"], allow_headers=["*"])
```

---

### 4. No Schema Bootstrap — `database/db_manager.py` + `main.py`

`Base.metadata.create_all(engine)` is never called and there's no visible Alembic migration runner. Fresh `.venv` / fresh DB on a new machine → server starts but **first request crashes with `no such table: battles`**.

**Fix:** Either invoke Alembic on startup (`subprocess.run(["alembic","upgrade","head"])`) OR add a fallback `Base.metadata.create_all(engine)` guarded by an env flag (`ARENA_AUTO_CREATE_SCHEMA=1`).

---

### 5. `get_db()` UnboundLocalError on Session Construction Failure — `database/db_manager.py:70-78`

```python
def get_db():
    db = SessionLocal()     # ← if this raises, db is never bound
    try:
        yield db
    except Exception:
        db.rollback()
    finally:
        db.close()           # ← UnboundLocalError if SessionLocal() failed
```

**Fix:** Move assignment inside the try, or use a context manager:

```python
def get_db():
    db = None
    try:
        db = SessionLocal()
        yield db
    except Exception:
        if db: db.rollback()
        raise
    finally:
        if db: db.close()
```

---

### 6. `_with_backoff` Never Catches LLM Response → JSON Pipeline — `llm_router.py:65-77, 96-103, 125-136`

```python
r = self._client.chat.completions.create(...)
return r.choices[0].message.content   # could be None
```

OpenAI, Claude, Ollama, and HuggingFace can all return `None`/empty content (refusals, safety filters). That `None` flows into `fight_loop.py:174` → `_parse_llm_output(raw)` → `json.loads(None)` → `TypeError`. The double-retry fallback only catches `JSONDecodeError`, not `TypeError`.

**Fix:** Defensive null-coalesce in each adapter:

```python
content = r.choices[0].message.content
if not content:
    raise LLMConnectionError("Empty response from OpenAI")
return content
```

---

## 🟡 Important Improvements

### 7. Monolithic `next_turn` — `fight_loop.py:110-279`

170-line function does: persona enrichment, prompt building, history fetch, LLM call, JSON parse, persistence, eviction, summarisation, response building. SRP violation — hurts testability and refactoring.

**Fix:** Extract `_build_window()`, `_call_llm_with_retry()`, `_persist_messages()`, `_run_eviction()` as private methods.

### 8. Deprecated `@app.on_event("startup")` — `main.py:34`

FastAPI 0.93+ moved to lifespan context managers. Project is now on 0.136.1 — this will emit deprecation warnings in logs.

**Fix:**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    ...
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)
```

### 9. Catch-All `Exception` Swallows Real Errors — `routes.py:53,102` + `fight_loop.py:251`

```python
except Exception as exc:
    raise HTTPException(status_code=500, detail="Battle initialization failed") from exc
```

In production this loses the actual error type, stack, and SQL state. Add structured logging:

```python
except Exception as exc:
    log.exception("Battle init failed for %s", payload.entity_1.persona_name)
    raise HTTPException(500, "Battle initialization failed") from exc
```

### 10. Hardcoded SQLite Dialect — `db_manager.py:15` + `memory_engine.py:4`

```python
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
```

Switching to PostgreSQL in production requires code changes. Use the cross-dialect `sqlalchemy.JSON` and a dialect-aware upsert wrapper.

### 11. Telemetry Values Aren't Clamped — `fight_loop.py:276-277`

```python
sentiment_score=int(result["sentiment_score"]),
aggression_level=int(result["aggression_level"]),
```

If LLM returns `"high"` or `120`, this either raises `ValueError` or fails Pydantic validation. Should clamp:

```python
sentiment_score=max(-100, min(100, int(result.get("sentiment_score", 0)))),
aggression_level=max(0, min(100, int(result.get("aggression_level", 0)))),
```

### 12. `_PERSONAS_DIR` Path Magic — `fight_loop.py:45`

```python
_PERSONAS_DIR = pathlib.Path(__file__).parent.parent / "personas"
```

Resolves relative to source file. Breaks if the package is installed (vs. run from repo). Should be env-configurable: `os.getenv("ARENA_PERSONAS_DIR", default_path)`.

### 13. No Request ID / Battle ID in Logs

Across `llm_router.py`, `fight_loop.py`, `memory_engine.py` — log messages lack `battle_id` or a correlation ID consistently. When two battles run concurrently, log lines interleave with no way to demultiplex. Add `extra={"battle_id": ...}` to every log call.

### 14. `ThreadPoolExecutor` Created Per Iteration — `fight_loop.py:220`

A new pool is spun up for each eviction cycle. Should be a module-level executor reused across calls, or removed entirely (synchronous call is simpler given the 5s timeout).

---

## 🟢 Nice to Have

- **`speaker` should be `Literal["entity_1","entity_2","system"]`** in `payloads.py:75` — currently free-form `str`.
- **`Optional[str]` defaults are inconsistent** in `payloads.py:36-46` — string default for `logic_core_belief`/`trigger_point` but `None` for `backstory`/`vocabulary`. Either always use string defaults and remove the `or` fallback in `prompt_builder.py`, OR always use `None` and handle defaults downstream.
- **`max_tokens=2048`** is hardcoded in Claude and HuggingFace adapters — make env-configurable.
- **Magic threshold `2000`** in `memory_engine.py:45` for overflow override should be `_OVERFLOW_THRESHOLD_CHARS = 2000`.
- **`_SUMMARIZER_SYSTEM.format(...)`** is fragile if any `{` appears literally — use `string.Template` like `prompt_builder.py`.
- **`tts_sanitizer`** doesn't handle nested `*outer *inner* outer*` or parenthetical `(stage directions)`.
- **`Base.metadata.create_all`** missing — even an explicit `# Bootstrap via Alembic only` comment would be helpful.

---

## ✅ What's Genuinely Good

1. **Adapter pattern in `llm_router.py`** — Protocol-based, easily extensible, error-mapped per provider. Best part of the codebase.
2. **Self-healing eviction loop** — On summariser failure, messages stay in the window with `is_summarized=False` for next-turn retry. Excellent design choice.
3. **Pydantic `extra="forbid"`** — Catches typos in payloads at the API boundary.
4. **Indexed `(battle_id, is_summarized)`** — The right composite index for the hot-path query in `next_turn`.
5. **JSON parsing with multiple fallback strategies** in `_parse_llm_output` — handles fenced code blocks AND bare JSON.
6. **`PK-based update` for `is_summarized`** in `fight_loop.py:232-237` — explicit PK match, no role/content matching. Matches the project's saved pattern from memory.
7. **`prompt_builder` uses `string.Template`** — safer than f-strings against unintended interpolation.
8. **Domain exceptions** in `exceptions.py` — clean hierarchy, easy to map to HTTP codes.

---

## 📋 Recommended Fix Order

1. **Cross-thread session** (`fight_loop.py`) — silent data corruption risk
2. **Adapter cache lock** (`llm_router.py`) — race condition under load
3. **CORS allowlist** (`main.py`) — security
4. **Schema bootstrap** — deployment blocker
5. **Null-check LLM responses** — crash risk
6. **`get_db` UnboundLocal** — silent ops failure
7. **Lifespan migration** — deprecation
8. **Clamp telemetry ints** — runtime validation error
9. **Refactor `next_turn`** — maintainability
10. **Log correlation IDs** — observability
