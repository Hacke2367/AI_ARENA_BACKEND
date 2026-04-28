# Technical Implementation Specification
# Feature 01: Core Data Contracts & Security Guard (`payloads.py`)
**Version:** 1.0.0 | **Derived from:** `docs/features/payload_feature.md` v1.0.0
**Target file:** `backend_arena/src/schemas/payloads.py`

---

## 1. Architecture Decisions

### Decision 1 — Single Custom Base Class
All models inherit from one shared base class `ArenaBaseModel`:
```python
class ArenaBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
```
`extra="forbid"` implements the No Garbage Policy from Constraint 2 — any unknown key in the
payload raises `ValidationError` instantly. `str_strip_whitespace=True` implements
Auto-Sanitization from Constraint 3 — no manual `.strip()` calls anywhere in the codebase.
Both constraints are enforced in a single declaration, not repeated per model.

### Decision 2 — `Literal` for Enumerations, Not `Enum`
All closed-value string fields use `typing.Literal`:
```python
current_vibe: Literal["logical", "emotional", "chaotic"]
selected_llm: Literal["mock", "openai", "claude", "ollama", "groq"]
action_type:  Literal["next_turn", "context_bomb", "kill_switch"]
```
Rationale: `Literal` serializes to its raw string value natively (no `.value` unwrapping),
produces cleaner OpenAPI schema output, and avoids importing a separate Enum registry into a
module that must remain logic-free.

### Decision 3 — `Field(...)` for All Constraints
Every field uses `Field(...)` (required) or `Field(default, ...)` with explicit constraint
parameters. No `@field_validator` decorators. All constraints are expressible via built-in
`Field()` arguments (`min_length`, `max_length`, `ge`, `le`), keeping the module declarative
and free of imperative logic.

### Decision 4 — Nested Models, Not Dicts
`InitializeBattleRequest` holds typed sub-models (`MatchConfig`, `EntityConfig`), not raw
`dict` fields. Pydantic v2 propagates deep validation automatically — a bad `turn_limit` on a
nested `MatchConfig` raises `ValidationError` at the root request parse, not silently mid-flight.

### Decision 5 — Strict Input/Output Separation
Models are grouped into two logical namespaces within the file:
- **Input models** (`*Request` suffix): consumed by FastAPI route handlers
- **Output models** (`*Response` suffix + sub-models): produced by the fight engine and
  serialized back to the Streamlit frontend

This separation makes the contract surface explicit and prevents accidental reuse of an
output model as an input validator.

---

## 2. Class Hierarchy

```
ArenaBaseModel (BaseModel)
│
├── [Input Models]
│   ├── MatchConfig
│   ├── EntityConfig
│   ├── InitializeBattleRequest
│   │   ├── .match_config : MatchConfig
│   │   ├── .entity_1    : EntityConfig
│   │   └── .entity_2    : EntityConfig
│   └── ExecuteActionRequest
│
└── [Output Models]
    ├── VoiceParams
    ├── Telemetry
    ├── ExecuteActionResponse
    │   ├── .voice_params : VoiceParams
    │   └── .telemetry    : Telemetry
    └── InitializeBattleResponse
```

---

## 3. Full Field Specification

### `ArenaBaseModel`
| Config key | Value | Enforces |
|---|---|---|
| `extra` | `"forbid"` | No Garbage Policy |
| `str_strip_whitespace` | `True` | Auto-Sanitization |

---

### `MatchConfig`
| Field | Type | Constraint | Enforces |
|---|---|---|---|
| `topic` | `str` | `min_length=3, max_length=200` | Edge Case 1 (overflow), min sanity |
| `turn_limit` | `int` | `ge=1, le=50` | Edge Case 1 (500 rejected) |
| `current_vibe` | `Literal[...]` | `"logical"`, `"emotional"`, `"chaotic"` | Closed enum |

---

### `EntityConfig`
| Field | Type | Constraint |
|---|---|---|
| `selected_llm` | `Literal[...]` | `"mock"`, `"openai"`, `"claude"`, `"ollama"`, `"groq"` |
| `persona_name` | `str` | `min_length=2, max_length=50` |
| `logic_core_belief` | `str` | `min_length=10, max_length=1000` |
| `trigger_point` | `str` | `min_length=5, max_length=1000` |
| `voice_id` | `str` | `min_length=2, max_length=50` |
| `voice_speed` | `float` | `ge=0.5, le=2.0` |

---

### `InitializeBattleRequest`
| Field | Type | Constraint |
|---|---|---|
| `match_config` | `MatchConfig` | Required nested model |
| `entity_1` | `EntityConfig` | Required nested model |
| `entity_2` | `EntityConfig` | Required nested model |

---

### `ExecuteActionRequest`
| Field | Type | Constraint |
|---|---|---|
| `battle_id` | `str` | `min_length=5` |
| `action_type` | `Literal[...]` | `"next_turn"`, `"context_bomb"`, `"kill_switch"` |

---

### `VoiceParams` (output sub-model)
| Field | Type | Constraint |
|---|---|---|
| `id` | `str` | `min_length=1` |
| `speed` | `float` | `ge=0.5, le=2.0` |

---

### `Telemetry` (output sub-model)
| Field | Type | Constraint |
|---|---|---|
| `sentiment_score` | `int` | `ge=-100, le=100` |
| `aggression_level` | `int` | `ge=0, le=100` |

---

### `ExecuteActionResponse`
| Field | Type | Constraint |
|---|---|---|
| `speaker` | `str` | `min_length=2` |
| `internal_monologue` | `str` | `min_length=1` (cannot be empty) |
| `spoken_dialogue` | `str` | `min_length=1` (cannot be empty) |
| `tts_ready_text` | `str` | `min_length=1` (cannot be empty) |
| `voice_params` | `VoiceParams` | Required nested model |
| `telemetry` | `Telemetry` | Required nested model |

---

### `InitializeBattleResponse`
| Field | Type | Constraint |
|---|---|---|
| `battle_id` | `str` | `min_length=5` |
| `status` | `str` | `default="initialized"` |
| `message` | `str` | Required |

---

## 4. File Layout (Module Internal Order)

```python
# backend_arena/src/schemas/payloads.py

# Section 1 — Imports
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# Section 2 — Base class
class ArenaBaseModel(BaseModel): ...

# Section 3 — Output sub-models (declared before output responses that reference them)
class VoiceParams(ArenaBaseModel): ...
class Telemetry(ArenaBaseModel): ...

# Section 4 — Input models
class MatchConfig(ArenaBaseModel): ...
class EntityConfig(ArenaBaseModel): ...
class InitializeBattleRequest(ArenaBaseModel): ...
class ExecuteActionRequest(ArenaBaseModel): ...

# Section 5 — Output response models
class ExecuteActionResponse(ArenaBaseModel): ...
class InitializeBattleResponse(ArenaBaseModel): ...
```

`VoiceParams` and `Telemetry` are declared before `ExecuteActionResponse` because Python
resolves class references at class-body evaluation time in Pydantic v2 (no forward-ref
needed if ordering is correct).

---

## 5. Validation Error Contract (What Callers Receive)

FastAPI's Pydantic v2 integration automatically converts `ValidationError` to
**HTTP 422 Unprocessable Entity** with this JSON body shape:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "match_config", "topic"],
      "msg": "String should have at least 3 characters",
      "input": "Hi",
      "ctx": { "min_length": 3 }
    }
  ]
}
```

No custom error handling code belongs in `payloads.py`. FastAPI owns the HTTP error
translation layer. `payloads.py` raises `ValidationError`; FastAPI catches and serializes it.

---

## 6. Edge Case Implementation Map

| Edge Case (from spec §4) | Implementation Mechanism |
|---|---|
| `turn_limit=500` rejected | `Field(..., ge=1, le=50)` on `MatchConfig.turn_limit` |
| `"   Gym Bro   "` auto-trimmed | `str_strip_whitespace=True` in `ConfigDict` (base class) |
| `"override_system": true` rejected | `extra="forbid"` in `ConfigDict` (base class) |

All three edge cases are handled entirely by the base class `ConfigDict`. Zero imperative code.

---

## 7. Acceptance Verification (4 Criteria from spec §6)

Run from repo root with `py -c "..."`:

**Criterion 1 — Import succeeds**
```bash
py -c "from backend_arena.src.schemas.payloads import MatchConfig, EntityConfig, InitializeBattleRequest, ExecuteActionRequest, ExecuteActionResponse, InitializeBattleResponse, VoiceParams, Telemetry; print('PASS')"
```
Expected: `PASS`

**Criterion 2 — Short topic raises ValidationError**
```bash
py -c "
from pydantic import ValidationError
from backend_arena.src.schemas.payloads import MatchConfig
try:
    MatchConfig(topic='Hi', turn_limit=5, current_vibe='logical')
    print('FAIL - no error raised')
except ValidationError as e:
    print('PASS -', e.error_count(), 'error(s)')
"
```
Expected: `PASS - 1 error(s)`

**Criterion 3 — Invalid LLM key raises ValidationError**
```bash
py -c "
from pydantic import ValidationError
from backend_arena.src.schemas.payloads import EntityConfig
try:
    EntityConfig(selected_llm='huggingface', persona_name='Test', logic_core_belief='x'*10,
                 trigger_point='x'*5, voice_id='v1', voice_speed=1.0)
    print('FAIL - no error raised')
except ValidationError as e:
    print('PASS -', e.error_count(), 'error(s)')
"
```
Expected: `PASS - 1 error(s)`

**Criterion 4 — Extra field raises ValidationError**
```bash
py -c "
from pydantic import ValidationError
from backend_arena.src.schemas.payloads import MatchConfig
try:
    MatchConfig(topic='Valid debate topic', turn_limit=5, current_vibe='logical', override_system=True)
    print('FAIL - no error raised')
except ValidationError as e:
    print('PASS -', e.error_count(), 'error(s)')
"
```
Expected: `PASS - 1 error(s)`

---

## 8. Out-of-Scope (Hard Boundaries)

Per spec §2, the following are strictly forbidden inside `payloads.py`:
- FastAPI `APIRouter` or any route decorator
- Database connection or ORM imports
- LLM API client imports (`anthropic`, `openai`, `httpx`)
- Business logic or conditional branching
- Any `@field_validator` that makes external calls

Violations of these boundaries must be caught in code review before merge.
