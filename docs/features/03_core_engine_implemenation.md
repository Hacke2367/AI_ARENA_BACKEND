# Epic 03 Implementation Plan: Core Match Engine & Infrastructure

## Context

Epic 03 v2.0.0 supersedes the prior monolithic spec that was BLOCKED for SCOPE_VIOLATION. The new spec decomposes work into three layers (Foundation → Router → Orchestrator) and resolves the prior contract bugs (missing Claude route, undefined Fallback Stub, unversioned `ChatMessage`, exception module location).

The backend today is a thin FastAPI skeleton: `routes.py` dispatches to a `MatchManager` whose every method raises `NotImplementedError`. `payloads.py` already defines the public Pydantic contract. Files like `llm_router.py`, `prompt_builder.py`, `tts_sanitizer.py`, `exceptions.py`, and `schemas/types.py` do not exist.

Contract gaps that must be fixed *during* Epic 03:
- `ExecuteActionRequest` has no `context_text` field — `context_bomb` cannot accept the text payload that Epic §4C requires.
- `routes.py` swallows every exception via bare `except Exception` and returns HTTP 500. The epic mandates `BattleTurnLimitError → 409` and other typed mappings.
- `main.py` does not call `load_dotenv()` despite `python-dotenv==1.0.0` being installed and the spec requiring `.env` configuration.
- `requirements.txt` is missing the `openai` and `groq` SDKs.

Intended outcome: a fully wired engine where `POST /execute_action` with `selected_llm="mock"` returns a Pydantic-valid `ExecuteActionResponse` end-to-end without external network calls, and where each of the four cloud routes (openai, claude, groq, ollama) has a working adapter behind a single `LLMAdapter` Protocol.

---

## Order of Execution

Each step depends only on prior steps. Steps 1–2 establish the dependency foundation per the user directive.

### Step 1 — Foundation: `backend_arena/src/exceptions.py` (NEW)

Single canonical home for every typed exception. Both `fight_loop.py` and `routes.py` import from here; this prevents the circular-import risk flagged in the prior review.

```python
class ArenaError(Exception): ...
class LLMAuthError(ArenaError): ...
class LLMConnectionError(ArenaError): ...
class LLMTimeoutError(ArenaError): ...
class RateLimitError(ArenaError): ...
class BattleNotFoundError(ArenaError): ...
class BattleTurnLimitError(ArenaError): ...
```

No imports from `backend_arena.src.*` — leaf of the dependency tree.

### Step 2 — Foundation: `backend_arena/src/schemas/types.py` (NEW)

Defines the cross-adapter `ChatMessage` dataclass replacing `list[dict]` (per the prior review's IRREVERSIBLE_CONTRACT finding):

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str
```

`frozen=True` makes truncation safer (truncation logic cannot accidentally mutate a slice).

### Step 3 — Payload Amendment: `backend_arena/src/schemas/payloads.py` (EDIT)

Add the field that the existing `routes.py` dispatch already implies but is missing:

```python
class ExecuteActionRequest(ArenaBaseModel):
    battle_id: str = Field(..., min_length=5)
    action_type: Literal["next_turn", "context_bomb", "kill_switch"]
    context_text: Optional[str] = Field(default=None, max_length=2000)
```

Add a Pydantic v2 `model_validator(mode="after")` that asserts `context_text is not None` when `action_type == "context_bomb"`. Keeps the field optional for the other two action types.

### Step 4 — Utility: `backend_arena/src/utils/tts_sanitizer.py` (NEW)

Pure function `sanitize(text: str) -> str` that strips `*action*` and `[bracket]` markers using two precompiled `re.compile` patterns. No side effects, no logging — single responsibility. Called from `fight_loop.next_turn` step 6 below.

### Step 5 — Prompt Builder: `backend_arena/src/engine/prompt_builder.py` (NEW)

Epic 03 punts on the full 3-Layer specification (a future feature spec). For Epic 03 we provide a *minimal* `build_system_prompt(entity: EntityConfig, vibe: str) -> str` that:

1. Emits the **Core Belief** layer using `entity.logic_core_belief`.
2. Emits the **Trigger/Vibe** layer using `entity.trigger_point` and the `vibe` arg.
3. Emits the **Output Forcing** instruction mandating the LLM return a JSON object with exactly four keys: `internal_monologue`, `spoken_dialogue`, `sentiment_score` (-100..100), `aggression_level` (0..100). A schema version literal (`"v1"`) is embedded in the prompt for future migrations.

`fight_loop.py` calls this once per turn before invoking the router.

### Step 6 — Router: `backend_arena/src/engine/llm_router.py` (NEW)

**Protocol:**

```python
class LLMAdapter(Protocol):
    def __call__(
        self, system_prompt: str, chat_history: list[ChatMessage]
    ) -> str: ...
```

**Adapters (one per provider):**

| Adapter | SDK / Transport | Env var |
|---|---|---|
| `MockAdapter` | Deterministic JSON return | none |
| `OpenAIAdapter` | `openai.OpenAI()` v1.x client | `OPENAI_API_KEY` |
| `ClaudeAdapter` | `anthropic.Anthropic()` (already pinned `anthropic==0.31.0`) | `ANTHROPIC_API_KEY` |
| `GroqAdapter` | `groq` SDK | `GROQ_API_KEY` |
| `OllamaAdapter` | `httpx.Client(base_url=os.getenv("OLLAMA_BASE_URL"))` POST `/api/chat` | `OLLAMA_BASE_URL` |

Each adapter converts `list[ChatMessage]` to its provider's native message format **inside the adapter**; `fight_loop.py` never sees provider-specific shapes.

`route(selected_llm: str) -> LLMAdapter` factory returns the correct adapter (cached singleton). The factory must cover **all five** values in the `EntityConfig.selected_llm` Literal (`mock | openai | claude | ollama | groq`). An `else` branch raises `ValueError`.

**Backoff helper (private `_call_with_backoff`):**

Wraps every provider call. On `RateLimitError` → up to **3 retries** with the exact math from Epic §3:

```python
delay_n = min(base_delay * (multiplier ** n), max_wait)
sleep_s = random.uniform(0, delay_n)   # full jitter
# base_delay=2.0, multiplier=2.0, max_wait=10.0
```

After 3 failures, re-raise `RateLimitError` to `fight_loop.py`.

**Exception mapping inside adapters:**

| Provider error | Maps to |
|---|---|
| HTTP 401/403 | `LLMAuthError` |
| HTTP 429 | `RateLimitError` (handled by `_call_with_backoff`) |
| `httpx.ConnectError` / `ConnectionRefusedError` | `LLMConnectionError` |
| `httpx.ReadTimeout` (>30s, configurable) | `LLMTimeoutError` |

### Step 7 — Orchestrator: `backend_arena/src/engine/fight_loop.py` (REPLACE STUB)

**State container:**

```python
_active_battles: dict[str, dict] = {}
# Per battle:
# {
#   "match_config": MatchConfig,
#   "entity_1": EntityConfig, "entity_2": EntityConfig,
#   "history": list[ChatMessage],
#   "turn": int,
#   "status": Literal["active", "paused", "complete"]
# }
```

**`MatchManager` methods:**

`create_battle(payload) -> str`:
- Generate UUIDv4 `battle_id`.
- Seed state with empty `history`, `turn=0`, `status="active"`.

`get_battle(battle_id) -> Optional[dict]` and `get_battle_status(battle_id) -> Optional[str]`:
- Used by `routes.py`; thin dict lookups; return `None` when missing (matches existing contract).

`next_turn(battle_id) -> ExecuteActionResponse`:

1. Fetch state. If missing → raise `BattleNotFoundError`.
2. If `status == "complete"` or `turn >= match_config.turn_limit` → raise `BattleTurnLimitError`.
3. Determine current speaker: `entity_1` when `turn % 2 == 0`, else `entity_2`.
4. **Truncate**: while `len(history) > ARENA_MAX_HISTORY_TURNS * 2`, pop the two oldest entries (one user/one assistant pair). System messages from `context_bomb` are pinned and not counted toward this limit.
5. Build system prompt via `prompt_builder.build_system_prompt(entity, match_config.current_vibe)`.
6. Call `llm_router.route(entity.selected_llm)(system_prompt, history)`.
7. Parse JSON via `_parse_llm_output(raw)`. On `json.JSONDecodeError`: log WARNING with raw text and `battle_id`, retry **once**. On second failure: emit the **Fallback Stub** (Epic §4C) with hardcoded `sentiment_score=0`, `aggression_level=0`.
8. Map to the **6-field `ExecuteActionResponse`** exactly per Epic §4B:
   - `speaker` ← entity key from step 3 (`"entity_1"` or `"entity_2"`).
   - `internal_monologue` ← LLM output.
   - `spoken_dialogue` ← LLM output.
   - `tts_ready_text` ← `tts_sanitizer.sanitize(spoken_dialogue)`.
   - `voice_params` ← `VoiceParams(id=entity.voice_id, speed=entity.voice_speed)`.
   - `telemetry` ← `Telemetry(sentiment_score=..., aggression_level=...)`.
9. Append `ChatMessage(role="assistant", content=spoken_dialogue)` to history. Increment `turn`. If `turn >= turn_limit` → set `status="complete"`.
10. Return the response.

`context_bomb(battle_id, text) -> ExecuteActionResponse`:
- Append `ChatMessage(role="system", content=f"[SYSTEM OVERRIDE]: {text}")` to history.
- Delegate to `next_turn(battle_id)`.

`kill_switch(battle_id) -> ExecuteActionResponse`:
- Set `status="paused"`. Does **not** call the LLM.
- Return a fixed pause payload that satisfies every `min_length=1` Pydantic constraint:

```python
ExecuteActionResponse(
    speaker="system",
    internal_monologue="[PAUSED]",
    spoken_dialogue="[PAUSED]",
    tts_ready_text="Battle paused.",
    voice_params=VoiceParams(id="system", speed=1.0),
    telemetry=Telemetry(sentiment_score=0, aggression_level=0),
)
```

**JSON parsing helper `_parse_llm_output(raw: str) -> dict`:**
- Try `json.loads(raw)` directly.
- If that fails, regex-extract the first `{...}` block (LLMs often wrap JSON in prose).
- If extraction also fails, raise `json.JSONDecodeError` to the caller.

### Step 8 — API Layer: `backend_arena/src/api/routes.py` (EDIT)

Replace the bare `except Exception` with a typed exception ladder per Epic §2 + §4A:

```python
except BattleNotFoundError:
    raise HTTPException(status_code=404, detail="Battle not found")
except BattleTurnLimitError:
    raise HTTPException(status_code=409, detail="Battle is complete")
except LLMAuthError:
    raise HTTPException(status_code=502, detail="LLM auth failed")
except LLMConnectionError:
    raise HTTPException(status_code=503, detail="LLM unreachable")
except LLMTimeoutError:
    raise HTTPException(status_code=504, detail="LLM timed out")
except RateLimitError:
    raise HTTPException(status_code=429, detail="LLM rate-limited")
```

Update the dispatch to pass `context_text` for `context_bomb`:

```python
if payload.action_type == "context_bomb":
    fn = lambda: manager.context_bomb(payload.battle_id, payload.context_text)
else:
    fn = lambda: dispatch[payload.action_type](payload.battle_id)
```

Keep the existing 60s outer `asyncio.wait_for` timeout. The inner 30s read timeout is enforced inside the adapter (per `LLMTimeoutError` contract).

### Step 9 — App Bootstrap: `backend_arena/src/main.py` (EDIT)

Prepend env loading and logging configuration before app creation:

```python
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
```

This makes the Fallback Stub WARNING actually surface.

### Step 10 — Dependencies: `backend_arena/requirements.txt` (EDIT)

Add the missing SDKs (compatible with the existing `httpx==0.25.1` and `pydantic==2.5.0` pins):

```
openai==1.40.0
groq==0.9.0
pytest==7.4.3
pytest-asyncio==0.21.1
```

### Step 11 — Configuration: `.env.example` (NEW, repo root)

Document the env vars from Epic §1:

```
ARENA_MAX_HISTORY_TURNS=6
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROQ_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
```

Verify `.env` is in `.gitignore` (the existing gitignore covers `graphify-out` only — confirm and append `.env` if missing).

### Step 12 — Tests: `backend_arena/tests/` (NEW)

- `tests/conftest.py` — fixtures: fresh `MatchManager` per test, prebuilt `InitializeBattleRequest` with `selected_llm="mock"`.
- `tests/test_router.py` — Acceptance Criteria 1 (mock) + 2 (Ollama resilience): mock returns valid JSON, invalid `OLLAMA_BASE_URL` raises `LLMConnectionError`, simulated 401 raises `LLMAuthError`, simulated 429 retries 3× then raises `RateLimitError`.
- `tests/test_fight_loop.py` — Acceptance Criteria 3 + 4: 7× `next_turn` → history contains exactly system + last 6 turns; double `JSONDecodeError` → Fallback Stub returned and Pydantic-validates; `BattleTurnLimitError` raised at `turn == turn_limit`.
- `tests/test_routes.py` — FastAPI `TestClient`: 404 / 409 / 502 / 503 / 504 / 429 mappings.

---

## Critical Files Reference

| Action | Path |
|---|---|
| CREATE | `backend_arena/src/exceptions.py` |
| CREATE | `backend_arena/src/schemas/types.py` |
| EDIT | `backend_arena/src/schemas/payloads.py` |
| CREATE | `backend_arena/src/utils/tts_sanitizer.py` |
| CREATE | `backend_arena/src/engine/prompt_builder.py` |
| CREATE | `backend_arena/src/engine/llm_router.py` |
| REPLACE | `backend_arena/src/engine/fight_loop.py` |
| EDIT | `backend_arena/src/api/routes.py` |
| EDIT | `backend_arena/src/main.py` |
| EDIT | `backend_arena/requirements.txt` |
| CREATE | `.env.example` |
| CREATE | `backend_arena/tests/{conftest,test_router,test_fight_loop,test_routes}.py` |

## Existing Utilities to Reuse

| Source | Reuse for |
|---|---|
| `payloads.VoiceParams`, `payloads.Telemetry`, `payloads.ExecuteActionResponse` | Direct construction inside `fight_loop.next_turn`; no new response models |
| `payloads.EntityConfig.selected_llm` Literal | Authoritative routing keys; `llm_router.route()` factory must cover all five values to avoid the runtime dead-end flagged in spec review |
| `python-dotenv==1.0.0` (already pinned) | `main.py` only needs `load_dotenv()` |
| `anthropic==0.31.0` (already pinned) | Used directly inside `ClaudeAdapter` |
| Pydantic v2 `model_validator` | Enforces `context_text` presence when `action_type == "context_bomb"` |

---

## Verification

End-to-end smoke (after implementation, from repo root):

```bash
pip install -r backend_arena/requirements.txt
cp .env.example .env
uvicorn backend_arena.src.main:app --workers 1 --port 8000
```

Second terminal:

```bash
# 1. Initialize a mock battle
curl -X POST localhost:8000/initialize_battle \
  -H 'Content-Type: application/json' \
  -d @backend_arena/tests/fixtures/init_mock_battle.json

# 2. Step (mock route — no external calls)
curl -X POST localhost:8000/execute_action \
  -H 'Content-Type: application/json' \
  -d '{"battle_id":"<id>","action_type":"next_turn"}'
```

Expected: HTTP 200, Pydantic-valid `ExecuteActionResponse` with all 6 fields populated.

Pytest run (full Epic 03 acceptance suite):

```bash
pytest backend_arena/tests -v
```

Hits all four Epic acceptance criteria:
- Mock routing returns valid response with telemetry
- Invalid Ollama URL → `LLMConnectionError` → HTTP 503
- Double JSON decode failure → Fallback Stub (Pydantic-valid)
- 7 `next_turn` calls → history contains system prompt + last 6 turns

Disaster check (unset `OLLAMA_BASE_URL` and route to `ollama`): server must respond with HTTP 503 in <30s rather than hang.
