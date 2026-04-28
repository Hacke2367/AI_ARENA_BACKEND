# Technical Implementation Specification
# Feature 02: Core API Orchestrator (`routes.py`)
**Version:** 1.0.0 | **Derived from:** `docs/features/02_api_routes_feature.md` v1.0.0

---

## 1. Files Modified

| Action | File |
|---|---|
| CREATE | `backend_arena/src/api/routes.py` |
| MODIFY | `backend_arena/src/main.py` |
| MODIFY | `backend_arena/src/engine/fight_loop.py` |

---

## 2. Architecture Decisions

### Decision 1 — APIRouter, Not Inline App Routes
All endpoints are registered on a `fastapi.APIRouter` instance (not directly on `app`).
`main.py` mounts it via `app.include_router(router)`. This already matches the existing
`main.py` import: `from backend_arena.src.api.routes import router`.

### Decision 2 — All Endpoints Are `async def`
Spec Constraint 2 mandates async. Every route handler uses `async def` to allow concurrent
battle sessions without blocking the event loop.

### Decision 3 — MatchManager via `Depends`
A `MatchManager` class (defined in `backend_arena/src/engine/fight_loop.py`) is injected into
each endpoint via FastAPI's `Depends(get_match_manager)`. This decouples routing from state
logic and makes future swap-out of the manager trivial.

A module-level factory function `get_match_manager()` returns the singleton instance:
```python
_manager = MatchManager()
def get_match_manager() -> MatchManager:
    return _manager
```

### Decision 4 — action_type Dispatch via if/elif, Not a Dict Map
The `execute_action` endpoint routes `action_type` via explicit `if/elif` branches for
clarity and traceable error handling. Each branch calls a distinct `MatchManager` method.

### Decision 5 — CORS in main.py, Not in routes.py
FastAPI `CORSMiddleware` is added to the `FastAPI` app instance in `main.py`. Adding it to
`APIRouter` is not supported by FastAPI — spec intent ("routes level") is satisfied by
registering it in the same module lifecycle as the router mount.

### Decision 6 — Conflict Resolution: /health
`main.py` currently defines `GET /health` returning `{"status": "ok"}`. The spec requires
`{"status": "online", "version": "1.0.0"}`. Resolution: move `/health` into `routes.py` with
the spec-correct response, and remove the existing definition from `main.py` to eliminate
the duplicate route conflict.

---

## 3. MatchManager Stub (fight_loop.py)

`routes.py` imports `MatchManager` from `fight_loop.py`. Since `fight_loop.py` is currently
empty, a minimal stub must be written there first. It exposes only the interface that
`routes.py` needs — no implementation logic required for Feature 02.

```
MatchManager
  .create_battle(payload: InitializeBattleRequest) -> str        # returns battle_id
  .get_battle(battle_id: str) -> Optional[dict]                  # None = not found
  .get_battle_status(battle_id: str) -> Optional[str]            # "active"|"paused"|"terminated"
  .next_turn(battle_id: str) -> ExecuteActionResponse
  .context_bomb(battle_id: str) -> ExecuteActionResponse
  .kill_switch(battle_id: str) -> ExecuteActionResponse
```

All methods raise `NotImplementedError` in the stub. Feature 03 provides the implementation.

---

## 4. Endpoint Contract Table

### GET `/health`
| Field | Value |
|---|---|
| Handler | `async def health()` |
| Response | `{"status": "online", "version": "1.0.0"}` |
| Status | 200 |
| Auth | None |

### POST `/initialize_battle`
| Field | Value |
|---|---|
| Handler | `async def initialize_battle(payload: InitializeBattleRequest, manager: MatchManager = Depends(...))` |
| Input model | `InitializeBattleRequest` |
| Output model | `InitializeBattleResponse` |
| Success | 200 |
| Error | 500 — `HTTPException(status_code=500, detail="Battle initialization failed")` |
| Error trigger | Any exception from `manager.create_battle()` |

### POST `/execute_action`
| Field | Value |
|---|---|
| Handler | `async def execute_action(payload: ExecuteActionRequest, manager: MatchManager = Depends(...))` |
| Input model | `ExecuteActionRequest` |
| Output model | `ExecuteActionResponse` |
| Success | 200 |

Error map:
| Condition | HTTP Code | detail |
|---|---|---|
| `manager.get_battle(battle_id)` returns `None` | 404 | `"Battle session expired or invalid"` |
| `battle_status == "paused"` and `action_type == "next_turn"` | 400 | `"Invalid action for current state"` |
| `asyncio.TimeoutError` (LLM >60s) | 504 | `"LLM gateway timeout"` |

action_type dispatch:
| action_type | MatchManager method |
|---|---|
| `"next_turn"` | `manager.next_turn(battle_id)` |
| `"context_bomb"` | `manager.context_bomb(battle_id)` |
| `"kill_switch"` | `manager.kill_switch(battle_id)` |

---

## 5. Imports Required in routes.py

```python
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from backend_arena.src.schemas.payloads import (
    InitializeBattleRequest,
    InitializeBattleResponse,
    ExecuteActionRequest,
    ExecuteActionResponse,
)
from backend_arena.src.engine.fight_loop import MatchManager
```

---

## 6. main.py Modifications

Remove:
```python
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

Add after `app = FastAPI(...)`:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`app.include_router(router)` line stays unchanged.

---

## 7. File Layout (routes.py Internal Order)

```
Section 1 — Imports
Section 2 — router = APIRouter()
Section 3 — _manager singleton + get_match_manager() factory
Section 4 — GET /health
Section 5 — POST /initialize_battle
Section 6 — POST /execute_action
```

---

## 8. Hard Boundaries

- NO database imports in `routes.py`
- NO LLM client calls in `routes.py` — all dispatched through MatchManager
- NO synchronous blocking I/O — all handlers must be `async def`
- NO business logic (persona construction, prompt building) in `routes.py`
- NO Pydantic model definitions in `routes.py`

---

## 9. Acceptance Verification

Start the server:
```bash
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000
```

**AC1 — Health check returns correct shape**
```bash
curl -s http://localhost:8000/health
# Expected: {"status":"online","version":"1.0.0"}
```

**AC2 — Initialize battle returns battle_id**
```bash
curl -s -X POST http://localhost:8000/initialize_battle \
  -H "Content-Type: application/json" \
  -d '{"match_config":{"topic":"Is roasting cyberbullying?","turn_limit":10,"current_vibe":"logical"},"entity_1":{"selected_llm":"mock","persona_name":"Gym Bro","logic_core_belief":"Lifting is life.","trigger_point":"Anyone calling gym useless.","voice_id":"v01","voice_speed":1.1},"entity_2":{"selected_llm":"mock","persona_name":"Intellectual","logic_core_belief":"Mind over muscle.","trigger_point":"Anyone using bro slang.","voice_id":"v02","voice_speed":1.0}}'
# Expected: {"battle_id":"<uuid>","status":"initialized","message":"..."}
```

**AC3 — Invalid action_type returns 422**
```bash
curl -s -X POST http://localhost:8000/execute_action \
  -H "Content-Type: application/json" \
  -d '{"battle_id":"test-battle-001","action_type":"force_win"}'
# Expected: HTTP 422
```

**AC4 — Unknown battle_id returns 404**
```bash
curl -s -X POST http://localhost:8000/execute_action \
  -H "Content-Type: application/json" \
  -d '{"battle_id":"nonexistent-id-xyz","action_type":"next_turn"}'
# Expected: HTTP 404, detail: "Battle session expired or invalid"
```
