# Feature 05 Implementation Plan: Persona Engine (Jailbreak & Injection)

## Context

Feature 05 wires the Layer 1 DNA (character JSON files) to the Layer 2 Master Template (`docs/ai_jailbreak/master_prompt.md`) via a rebuilt `prompt_builder.py` compiler. It is the final piece of the core LLM prompting pipeline before any external LLM is called.

Spec reviewed and approved at v1.1.0. All prior blockers resolved:
- Architecture decision: caller passes `persona_id`; backend enriches from JSON before DB persist.
- Backward compatibility: all new fields are `Optional` with `None` default.
- Safe injection: `string.Template` (`$variable` syntax) replaces `str.format()` to handle literal `{}` in persona content.
- `tts_sanitizer.py` acknowledged as the existing Layer 3 implementation (no duplication).

Two persona fixtures (`gym_bro.json`, `crypto_hustler.json`) were already on disk. `docs/ai_jailbreak/master_prompt.md` existed but used `{placeholder}` syntax — converted as part of this feature.

---

## Files Changed

| # | File | Action |
|---|---|---|
| 1 | `docs/ai_jailbreak/master_prompt.md` | Convert `{x}` → `$x`; add `$long_term_memory` slot after §6 |
| 2 | `backend_arena/src/schemas/payloads.py` | Add 4 Optional fields to `EntityConfig`; expand `current_vibe` Literal |
| 3 | `backend_arena/src/exceptions.py` | Add `PersonaNotFoundError` |
| 4 | `backend_arena/src/engine/prompt_builder.py` | Full rewrite — `string.Template` + `lru_cache` + list joining |
| 5 | `backend_arena/src/engine/fight_loop.py` | Add `_enrich_with_persona()` + call in `create_battle()` |
| 6 | `backend_arena/src/api/routes.py` | Add `PersonaNotFoundError → 404` in `initialize_battle` |
| 7 | `backend_arena/src/personas/tech_bro.json` | Create Tech Bro persona fixture |
| 8 | `backend_arena/tests/test_prompt_builder.py` | Create new test file (10 tests) |

---

## Architecture Flow

```
POST /initialize_battle
  └─ routes.py → MatchManager.create_battle()
       └─ _enrich_with_persona(entity)          # fight_loop.py
            └─ reads src/personas/{id}.json
            └─ entity.model_copy(update={dna})
       └─ stores enriched entity → DB

POST /execute_action → next_turn()
  └─ EntityConfig reconstructed from DB
  └─ prompt_builder.build_system_prompt(entity, vibe, memory)
       └─ string.Template(master_prompt.md).safe_substitute(
              persona_name, backstory, vocabulary,
              debate_tactics, current_vibe, long_term_memory
          )
  └─ LLM call → _parse_llm_output()
  └─ tts_sanitizer.sanitize(spoken_dialogue)   # Layer 3 (existing)
```

---

## Schema Changes (payloads.py)

### EntityConfig — new Optional fields
```python
persona_id: Optional[str] = None       # "tech_bro" → loads tech_bro.json
backstory: Optional[str] = None        # populated from JSON, injected as $backstory
vocabulary: Optional[list[str]] = None # list[str] → joined with \n → $vocabulary
debate_tactics: Optional[list[str]] = None  # list[str] → joined with \n → $debate_tactics
```

### MatchConfig — expanded vibe enum
```python
current_vibe: Literal[
    "logical", "emotional", "chaotic",           # legacy (preserved)
    "opening", "heated", "cornered", "victory_lap",  # new
]
```

---

## prompt_builder.py Design

```python
_TEMPLATE_PATH = Path(__file__).parent.parent.parent.parent / "docs/ai_jailbreak/master_prompt.md"

@lru_cache(maxsize=1)
def _load_template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))

def build_system_prompt(entity: EntityConfig, vibe: str, long_term_memory: str = "") -> str:
    ...
    return _load_template().safe_substitute(
        persona_name=entity.persona_name,
        backstory=entity.backstory or entity.logic_core_belief,  # fallback for legacy
        vocabulary=_format_list(entity.vocabulary),
        debate_tactics=_format_list(entity.debate_tactics),
        current_vibe=vibe.upper(),
        long_term_memory=memory_block,
    )
```

Key decisions:
- `lru_cache(maxsize=1)`: template loaded once per process, not per request.
- `safe_substitute()`: missing keys produce empty string instead of crash; template validated by startup test.
- Fallback to `logic_core_belief`: old `EntityConfig` rows without `backstory` continue to produce valid prompts.
- `$long_term_memory` sits between §6 and §7 in the template, exactly where the memory engine injects its summary.

---

## Persona JSON Schema

```json
{
  "persona_name": "string",
  "backstory": "multi-paragraph string",
  "vocabulary": ["• phrase — usage note", ...],
  "debate_tactics": ["1. TACTIC NAME. — description", ...]
}
```

Available fixtures: `gym_bro.json`, `crypto_hustler.json`, `tech_bro.json`.

---

## Error Handling

| Error | HTTP Status | Where |
|---|---|---|
| `persona_id` file missing | 404 | `routes.py` catches `PersonaNotFoundError` |
| JSON schema mismatch (Pydantic) | 422 | FastAPI default validation error |
| `persona_id = None` | — | `_enrich_with_persona()` returns entity unchanged |

---

## Backward Compatibility

- All new `EntityConfig` fields are `Optional` → existing `/initialize_battle` payloads require no changes.
- `fight_loop.py` DB reconstruction (`EntityConfig(**{k: v ...})`) populates new fields as `None` for old rows.
- `build_system_prompt()` function signature unchanged → all existing call sites in `fight_loop.py` unaffected.
- Legacy vibe values ("logical", "emotional", "chaotic") still valid.

---

## Testing

### New: `backend_arena/tests/test_prompt_builder.py` (10 tests)

| Test | Covers |
|---|---|
| `test_entity_config_with_full_dna_validates` | AC1 — new fields accepted |
| `test_entity_config_without_dna_validates` | AC1 — backward compat, all None |
| `test_match_config_accepts_new_vibes` | vibe enum expansion |
| `test_match_config_accepts_legacy_vibes` | vibe enum backward compat |
| `test_build_system_prompt_injects_all_dna_fields` | AC2 — full injection |
| `test_build_system_prompt_falls_back_to_logic_core_belief` | AC2 — legacy fallback |
| `test_build_system_prompt_omits_memory_block_when_empty` | memory block gating |
| `test_build_system_prompt_includes_memory_block_when_present` | memory injection |
| `test_build_system_prompt_joins_list_with_newlines` | list formatting |
| `test_master_prompt_contains_all_canonical_placeholders` | AC3 — template guard |
| `test_enrich_with_invalid_persona_id_raises` | AC4 — PersonaNotFoundError |
| `test_enrich_with_valid_persona_id_loads_dna` | AC4 — happy path |

### Existing tests: no changes required
- `conftest.py::mock_entity` — no new required fields, still valid.
- All `test_fight_loop.py`, `test_router.py`, `test_routes.py` tests unaffected.

---

## Verification Checklist

```bash
# Run new tests
pytest backend_arena/tests/test_prompt_builder.py -v

# Confirm existing tests still pass (backward compat)
pytest backend_arena/tests/ -v

# Smoke test: tech_bro battle via curl
curl -X POST http://localhost:8000/initialize_battle \
  -H "Content-Type: application/json" \
  -d '{
    "match_config": {"topic": "Soft skills vs coding skills", "turn_limit": 4, "current_vibe": "opening"},
    "entity_1": {
      "selected_llm": "mock", "persona_name": "placeholder",
      "logic_core_belief": "x", "trigger_point": "y",
      "voice_id": "v1", "voice_speed": 1.0, "persona_id": "tech_bro"
    },
    "entity_2": {
      "selected_llm": "mock", "persona_name": "placeholder",
      "logic_core_belief": "x", "trigger_point": "y",
      "voice_id": "v2", "voice_speed": 1.0, "persona_id": "gym_bro"
    }
  }'

# Should return 200 with battle_id.
# Then: POST /execute_action with action_type=next_turn
# Verify spoken_dialogue has no *asterisks*, [brackets], or emoji.

# Persona-not-found: should return 404
curl -X POST http://localhost:8000/initialize_battle \
  -d '{"match_config": {...}, "entity_1": {..., "persona_id": "ghost"}, ...}'
```
