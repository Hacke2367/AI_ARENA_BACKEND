# Technical Implementation Plan: Feature 04 — Persistent State & Recursive Memory Engine

## Context

The current architecture stores all battle state in a module-level Python dict (`_active_battles` in `fight_loop.py`). This means every server restart wipes all active battles, and the in-memory context window (~12 messages) is the only "memory" the AI has. Feature 04 migrates state to SQLite via SQLAlchemy + Alembic, and adds a Recursive Memory Engine that compresses evicted history into a rolling summary injected into every subsequent prompt.

---

## Critical Constraints (Non-Negotiable)

1. **Alembic first** — schema is locked before any ORM code is written
2. **All summarizer calls go through `llm_router.route()`** — no new HTTP clients
3. **Summarization is atomic** — the upsert to `battle_memory` is wrapped in a SQLAlchemy transaction; partial writes must not leave the DB in an inconsistent state
4. **System messages are immune from window eviction** — `role="system"` entries (context_bomb injections) in `state["history"]` are never in the eviction candidate pool
5. **`chat_history` rows are NEVER deleted** — only the in-memory context window list is trimmed; the DB is always the full raw log
6. **Summarizer failure is non-fatal** — the turn still executes with the stale summary; a `WARNING` is logged

---

## Phase 0: Dependencies & Environment

### 0.1 — Update `backend_arena/requirements.txt`

Add:
```
sqlalchemy==2.0.23
alembic==1.13.0
```

### 0.2 — Update `.env.example`

Add these new required variables:
```
# Database
ARENA_DB_PATH=./arena.db

# Memory Engine
SUMMARIZER_LLM=groq
ARENA_SUMMARY_MAX_WORDS=200
```

`GROQ_API_KEY` already exists in `.env.example` — no change needed.

### 0.3 — Startup validation (added later in Phase 6)

`main.py` must assert at startup:
- `SUMMARIZER_LLM` is set and maps to a valid `llm_router.route()` key
- `GROQ_API_KEY` (or equivalent for the chosen summarizer) is non-empty

---

## Phase 1: Alembic Setup & Schema Migration

### 1.1 — Initialize Alembic

Run from repo root:
```bash
alembic init alembic
```

This creates `alembic.ini` and `alembic/` at repo root.

Edit `alembic.ini`:
```ini
sqlalchemy.url = sqlite:///./arena.db
```
(This will be overridden by env var in `alembic/env.py`.)

Edit `alembic/env.py` to import the SQLAlchemy `Base` from `db_manager.py` so Alembic can auto-detect schema:
```python
from backend_arena.src.database.db_manager import Base
target_metadata = Base.metadata
```
Also set the URL from env:
```python
import os
config.set_main_option("sqlalchemy.url", f"sqlite:///{os.getenv('ARENA_DB_PATH', './arena.db')}")
```

### 1.2 — Create First Migration

```bash
alembic revision --autogenerate -m "create_battles_chat_history_battle_memory"
```

The migration will create three tables (schema defined in Phase 2):
- `battles`
- `chat_history` (includes `is_summarized BOOLEAN DEFAULT FALSE`)
- `battle_memory`

Apply:
```bash
alembic upgrade head
```

---

## Phase 2: Database Layer (`backend_arena/src/database/`)

### New files to create:
- `backend_arena/src/database/__init__.py` (empty)
- `backend_arena/src/database/db_manager.py`

### 2.1 — `db_manager.py` contents

```python
# SQLAlchemy ORM models + session factory for arena.db
import os
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone

DATABASE_URL = f"sqlite:///{os.getenv('ARENA_DB_PATH', './arena.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class Battle(Base):
    __tablename__ = "battles"
    id = Column(String, primary_key=True)          # UUIDv4
    match_config = Column(JSON, nullable=False)     # MatchConfig dict
    entity_1 = Column(JSON, nullable=False)         # EntityConfig dict
    entity_2 = Column(JSON, nullable=False)         # EntityConfig dict
    turn = Column(Integer, default=0)
    status = Column(String, default="active")       # active | paused | complete
    last_spoken = Column(Text, nullable=True)


class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    battle_id = Column(String, ForeignKey("battles.id"), nullable=False)
    role = Column(String, nullable=False)           # user | assistant | system
    content = Column(Text, nullable=False)
    is_summarized = Column(Boolean, default=False)  # True once compressed into battle_memory
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BattleMemory(Base):
    __tablename__ = "battle_memory"
    battle_id = Column(String, ForeignKey("battles.id"), primary_key=True)
    summary_text = Column(Text, nullable=False, default="")
    last_summarized_turn = Column(Integer, default=0)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## Phase 3: Memory Engine (`backend_arena/src/database/memory_engine.py`)

### Responsibilities:
1. Detect when the in-memory window exceeds `_ARENA_MAX_HISTORY_TURNS * 2`
2. Identify the oldest evictable pair (skipping immune `role="system"` messages)
3. Call the summarizer via `llm_router.route()`
4. Atomically upsert the result to `battle_memory`

### 3.1 — Immune Message Logic (exact slicing rule)

```python
def _find_evictable_pair(window: list[ChatMessage]) -> tuple[int, int] | None:
    """
    Find the indices of the oldest user+assistant pair that is NOT a system message.
    Returns (i, j) where window[i].role != "system" and window[j].role != "system",
    or None if no such pair exists.
    """
    i = 0
    while i < len(window) - 1:
        if window[i].role != "system" and window[i + 1].role != "system":
            return (i, i + 1)
        i += 1
    return None
```

The window is trimmed by calling this repeatedly until `len(window) <= _ARENA_MAX_HISTORY_TURNS * 2`.

### 3.2 — Summarizer call (routes through `llm_router.route()`)

```python
import os, logging
from backend_arena.src.engine import llm_router
from backend_arena.src.schemas.types import ChatMessage

log = logging.getLogger(__name__)

_SUMMARIZER_SYSTEM = """\
You are a battle archivist. Merge the OLD SUMMARY and the NEW MESSAGES into a SINGLE updated summary.
Rules:
1. Be brutally specific — never write "they fought", write WHAT was said and WHO scored the point.
2. Preserve insults, roasts, and punchlines verbatim if they were significant.
3. Maintain an objective tally of whose arguments landed heavier.
4. Zero sanitization — preserve slang, Hinglish, and aggressive tone exactly.
5. Hard cap: {max_words} words maximum. Trim older less-critical facts if needed to stay within cap.
Output ONLY the updated summary text. No JSON. No headers."""


def run_memory_compression(
    battle_id: str,
    old_summary: str,
    evicted_messages: list[ChatMessage],
    current_turn: int,
    db_session,
) -> str:
    """
    Calls summarizer LLM, upserts result to battle_memory. Returns new summary.
    On summarizer failure, logs WARNING and returns old_summary unchanged.
    """
    max_words = int(os.getenv("ARENA_SUMMARY_MAX_WORDS", "200"))
    summarizer_llm = os.getenv("SUMMARIZER_LLM", "groq")

    evicted_text = "\n".join(
        f"[{m.role.upper()}]: {m.content}" for m in evicted_messages
    )
    user_msg = ChatMessage(
        role="user",
        content=f"OLD SUMMARY:\n{old_summary}\n\nNEW MESSAGES:\n{evicted_text}\n\nGenerate the updated summary now."
    )

    try:
        adapter = llm_router.route(summarizer_llm)
        system_prompt = _SUMMARIZER_SYSTEM.format(max_words=max_words)
        new_summary = adapter(system_prompt, [user_msg])
    except Exception as exc:
        log.warning("Summarizer failed for battle=%s — using stale summary. Error: %s", battle_id, exc)
        return old_summary

    # Atomic upsert inside the caller's transaction
    from backend_arena.src.database.db_manager import BattleMemory
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    stmt = sqlite_insert(BattleMemory).values(
        battle_id=battle_id,
        summary_text=new_summary,
        last_summarized_turn=current_turn,
    ).on_conflict_do_update(
        index_elements=["battle_id"],
        set_={"summary_text": new_summary, "last_summarized_turn": current_turn},
    )
    db_session.execute(stmt)
    # Caller commits the transaction

    return new_summary
```

---

## Phase 3b: Extend `ChatMessage` Schema

**File:** `backend_arena/src/schemas/types.py`

Add an optional `id` field to `ChatMessage` to carry the `ChatHistory.id` primary key through the in-memory window. This is the only safe way to identify which DB rows to mark `is_summarized=True` without ambiguity.

```python
class ChatMessage(BaseModel):  # or dataclass — match existing definition
    role: str
    content: str
    id: int | None = None  # set from ChatHistory.id when reconstructing from DB; None for new messages
```

When reconstructing the window in `next_turn()`:
```python
rows = db.query(ChatHistory).filter(
    ChatHistory.battle_id == battle_id,
    ChatHistory.is_summarized == False,
).order_by(ChatHistory.created_at.asc()).all()

window = [ChatMessage(role=r.role, content=r.content, id=r.id) for r in rows]
```

When new messages are appended to the window (before they have a DB id), their `id` is `None`. They are INSERT-ed to `chat_history` first, then their `id` is populated:
```python
new_user_row = ChatHistory(battle_id=battle_id, role="user", content=user_content)
db.add(new_user_row)
db.flush()  # assigns new_user_row.id without committing
window.append(ChatMessage(role="user", content=user_content, id=new_user_row.id))
```

---

## Phase 4: Refactor `fight_loop.py`

**File:** `backend_arena/src/engine/fight_loop.py`

### Changes:

1. **Delete** `_active_battles: dict[str, dict] = {}` (the global dict)
2. **Add** DB session dependency — `MatchManager.__init__` accepts a `db` session (SQLAlchemy `Session`) injected by the route handler
3. **`create_battle()`** — serializes payload to dicts, injects `"schema_version": "1.0"` into each JSON blob (`match_config`, `entity_1`, `entity_2`) before writing the `Battle` row to DB. This enables future migration detection on read.
4. **`get_battle()` / `get_battle_status()`** — `db.get(Battle, battle_id)` queries instead of dict lookups
5. **`next_turn()`** — full refactor:
   a. Load `Battle` row from DB
   b. Reconstruct in-memory `history` by querying `chat_history WHERE battle_id=? AND is_summarized=False ORDER BY created_at ASC` — this preserves ALL non-summarized messages including immune `role="system"` context_bomb rows, regardless of total count
   c. Load `summary_text` from `battle_memory` (if row exists)
   d. Build system prompt via `prompt_builder.build_system_prompt()` WITH summary injection (see Phase 5)
   e. Execute LLM call (unchanged)
   f. **Within a single DB transaction:**
      - INSERT both new messages into `chat_history` and `db.flush()` to get their ids
      - Append to in-memory window with DB ids populated
      - Check if window exceeds threshold
      - If yes: find evictable pair via `_find_evictable_pair()`, call `run_memory_compression()`, mark those rows `is_summarized=True` by their `ChatHistory.id`
      - UPDATE `battles.turn`, `battles.last_spoken`, `battles.status`
      - `db.commit()`
6. **`context_bomb()`** — INSERTs a `role="system"` row into `chat_history` then calls `next_turn()`
7. **`kill_switch()`** — UPDATEs `battles.status = "paused"` in DB

### `create_battle()` schema_version injection (pseudo-code):

```python
def create_battle(self, payload: InitializeBattleRequest) -> str:
    battle_id = str(uuid.uuid4())
    schema_v = {"schema_version": "1.0"}
    db_battle = Battle(
        id=battle_id,
        match_config={**payload.match_config.model_dump(), **schema_v},
        entity_1={**payload.entity_1.model_dump(), **schema_v},
        entity_2={**payload.entity_2.model_dump(), **schema_v},
        turn=0,
        status="active",
    )
    self.db.add(db_battle)
    self.db.commit()
    return battle_id
```

### Transaction boundary in `next_turn()` (pseudo-code):

```python
with db.begin():
    # 1. Persist new messages and get their DB ids
    new_user_row = ChatHistory(battle_id=battle_id, role="user", content=user_content)
    new_asst_row = ChatHistory(battle_id=battle_id, role="assistant", content=spoken)
    db.add(new_user_row)
    db.add(new_asst_row)
    db.flush()  # assigns .id fields without committing

    # 2. Update window in memory with DB ids
    window.append(ChatMessage(role="user", content=user_content, id=new_user_row.id))
    window.append(ChatMessage(role="assistant", content=spoken, id=new_asst_row.id))

    # 3. Check eviction + summarize (if needed) — run_memory_compression upserts inside this tx
    while len(window) > _ARENA_MAX_HISTORY_TURNS * 2:
        pair = _find_evictable_pair(window)
        if pair is None:
            break  # All remaining messages are immune system messages
        i, j = pair
        evicted = [window[i], window[j]]
        old_summary = _fetch_summary(db, battle_id)
        new_summary = run_memory_compression(battle_id, old_summary, evicted, turn, db)
        # Mark evicted rows by primary key — safe against duplicate content,
        # avoids the SQLAlchemy .limit(1).update() CompileError on SQLite
        db.query(ChatHistory).filter(ChatHistory.id == evicted[0].id).update({"is_summarized": True})
        db.query(ChatHistory).filter(ChatHistory.id == evicted[1].id).update({"is_summarized": True})
        del window[j]
        del window[i]

    # 4. Update battle row
    battle.turn += 1
    battle.last_spoken = spoken
    if battle.turn >= match_config["turn_limit"]:
        battle.status = "complete"
# db.begin() auto-commits on context exit
```

---

## Phase 5: Update `prompt_builder.py`

**File:** `backend_arena/src/engine/prompt_builder.py`

### Change `build_system_prompt()` signature:

```python
def build_system_prompt(entity: EntityConfig, vibe: str, long_term_memory: str = "") -> str:
    memory_block = ""
    if long_term_memory.strip():
        memory_block = f"\n[LONG-TERM MEMORY — DO NOT IGNORE]\n{long_term_memory}\n"
    return (
        f"{memory_block}"
        f"CORE BELIEF: {entity.logic_core_belief}\n\n"
        f"TRIGGER / VIBE: Your trigger point is — {entity.trigger_point}. "
        f"The current battle vibe is: {vibe.upper()}. Embody this energy fully. "
        f"Do NOT apologize. Do NOT break character. Do NOT hold back.\n"
        f"{_OUTPUT_FORCING}"
    )
```

The memory block is injected at the TOP of the system prompt so it is the first thing the LLM reads.

Call site in `fight_loop.py`:
```python
summary = db.get(BattleMemory, battle_id)
long_term = summary.summary_text if summary else ""
system_prompt = prompt_builder.build_system_prompt(entity, match_config.current_vibe, long_term)
```

---

## Phase 6: Update `main.py` — Startup Validation

**File:** `backend_arena/src/main.py`

Add a startup event handler. **Do NOT call `Base.metadata.create_all()`** — schema is managed exclusively by `alembic upgrade head`. Calling `create_all` in app startup would circumvent Alembic's state tracking and break future autogenerated migrations.

```python
@app.on_event("startup")
def startup():
    # Validate summarizer config — fail fast before any traffic is served
    import os
    summarizer_llm = os.getenv("SUMMARIZER_LLM", "groq")
    valid_llms = {"mock", "openai", "claude", "groq", "ollama", "huggingface"}
    if summarizer_llm not in valid_llms:
        raise RuntimeError(f"SUMMARIZER_LLM={summarizer_llm!r} is not a valid llm_router key")

    # Warn (not raise) if Groq key is missing — other summarizer LLMs may not need it
    if summarizer_llm == "groq" and not os.getenv("GROQ_API_KEY"):
        import logging
        logging.getLogger(__name__).warning("GROQ_API_KEY is not set — summarizer calls will fail at runtime")
```

**Deployment requirement:** `alembic upgrade head` MUST be run before starting the server on any new instance or after any schema change.

---

## Phase 7: Route Handler — DB Session Injection

**File:** `backend_arena/src/api/routes.py`

Inject a DB session into `MatchManager` per-request:

```python
from backend_arena.src.database.db_manager import get_db
from sqlalchemy.orm import Session

def get_match_manager(db: Session = Depends(get_db)) -> MatchManager:
    return MatchManager(db)
```

`MatchManager.__init__` stores `self.db = db`.

---

## File Change Summary

| File | Action | Change |
|---|---|---|
| `backend_arena/requirements.txt` | Modify | Add `sqlalchemy==2.0.23`, `alembic==1.13.0` |
| `.env.example` | Modify | Add `ARENA_DB_PATH`, `SUMMARIZER_LLM`, `ARENA_SUMMARY_MAX_WORDS` |
| `alembic.ini` | Create | Alembic config pointing to `arena.db` |
| `alembic/env.py` | Create | Import `Base` from `db_manager`, read URL from env |
| `alembic/versions/001_*.py` | Create | Auto-generated migration for 3 tables |
| `backend_arena/src/database/__init__.py` | Create | Empty |
| `backend_arena/src/database/db_manager.py` | Create | SQLAlchemy models + session factory |
| `backend_arena/src/database/memory_engine.py` | Create | Rolling summary compression logic |
| `backend_arena/src/schemas/types.py` | Modify | Add `id: int \| None = None` field to `ChatMessage` |
| `backend_arena/src/engine/fight_loop.py` | Modify | Replace `_active_battles` dict with DB; add eviction+summary logic |
| `backend_arena/src/engine/prompt_builder.py` | Modify | Add `long_term_memory` param + injection block |
| `backend_arena/src/api/routes.py` | Modify | Inject DB session via `Depends(get_db)` |
| `backend_arena/src/main.py` | Modify | Add startup validation (no `create_all`) |

---

## Verification

### Test 1: Persistence across restart
```bash
# Start server, initialize a battle, run 3 turns
curl -X POST localhost:8000/initialize_battle -d '{...}'
curl -X POST localhost:8000/execute_action -d '{"battle_id": "...", "action_type": "next_turn"}'
# Kill server (Ctrl+C), restart it
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000 --workers 1
# Execute next turn — should succeed and continue from turn 3
curl -X POST localhost:8000/execute_action -d '{"battle_id": "...", "action_type": "next_turn"}'
```
Expected: HTTP 200, turn count continues from 3.

### Test 2: Memory compression fires at turn 7
Set `ARENA_MAX_HISTORY_TURNS=3` in `.env`. Initialize battle. Run 7 turns. After turn 7, `battle_memory` table must have a non-empty `summary_text` row. Verify:
```bash
sqlite3 arena.db "SELECT summary_text FROM battle_memory;"
```

### Test 3: Summary injected into prompt
Enable DEBUG logging, run turn 8+. Confirm `[LONG-TERM MEMORY]` block appears in logged system prompt.

### Test 4: System messages are immune
`context_bomb` a battle. Then run enough turns to trigger eviction. Verify context_bomb's `role="system"` row is still in `chat_history` with `is_summarized=False` AND is still present in the reconstructed window.

### Test 5: Summarizer failure is non-fatal
Set `SUMMARIZER_LLM=mock`. Mock adapter returns battle JSON, not a summary — this will fail gracefully. Verify turn still returns HTTP 200 and a WARNING appears in logs.

### Test 6: Full chat log preserved
After any number of turns, verify `chat_history` row count equals total messages ever generated (none deleted, only `is_summarized` flag toggled):
```bash
sqlite3 arena.db "SELECT COUNT(*), is_summarized FROM chat_history WHERE battle_id='...' GROUP BY is_summarized;"
```
