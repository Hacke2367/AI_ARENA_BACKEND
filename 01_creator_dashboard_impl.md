# Implementation Plan: Creator Dashboard (Streamlit Frontend)
**Spec:** `specs/01_creator_dashboard.md` v1.0.0
**Component:** `creator_dashboard/`

---

## Critical Spec Corrections (Read Before Coding)

Two spec items conflict with the live backend schema — correct before implementation:

1. **`selected_llm` is NOT free text.** The backend enforces a `Literal` enum: `["mock", "openai", "claude", "ollama", "groq", "huggingface"]`. The sidebar must use `st.selectbox`, not `st.text_input`, for this field.

2. **`sentiment_score` range is -100 to 100, NOT 0–100.** The Pydantic schema in `payloads.py` sets `ge=-100, le=100`. The Aggression/Sentiment chart Y-axis must span -100 to 100 for sentiment; 0 to 100 for aggression. Use separate axes.

3. **`context_bomb` requires `context_text`.** The `ExecuteActionRequest` validator raises `ValueError` if `action_type == "context_bomb"` and `context_text` is null. The Inject Context Bomb button must provide a text input first and disable the button if that field is empty.

---

## Files

| Action | File | Reason |
|--------|------|--------|
| CREATE | `creator_dashboard/app.py` | Main Streamlit entry — all layout, session state, rendering |
| CREATE | `creator_dashboard/api_client.py` | Thin `httpx` wrapper — all HTTP calls isolated here |
| CREATE | `creator_dashboard/requirements.txt` | Frontend-specific deps |

No existing files to modify. The `creator_dashboard/` directory does not exist yet — create it.

---

## Architecture Decisions

### Decision 1 — `httpx.Client` (sync), not `AsyncClient`
Streamlit's execution model is a single synchronous rerun per interaction. `asyncio.run()` cannot be called from inside Streamlit's main thread (it already has an event loop in some versions, causing `RuntimeError`). Use `httpx.Client` (sync) with explicit timeouts.

Rationale: Derived from spec §4.8 — "thin httpx wrapper"; Streamlit is a sync framework.
Alternative: `requests` library — rejected because `httpx` is already in the backend requirements and handles connection errors more cleanly.

### Decision 2 — Altair for the dual-axis chart, not `st.line_chart`
`st.line_chart` normalizes all series to the same Y-axis domain, which would compress sentiment (-100 to 100) and aggression (0 to 100) onto the same scale without clear separation. Altair supports independent Y-axis domains per layer and explicit color encoding.

Rationale: Spec §4.4 — "dual-axis line chart"; spec correction above (two different ranges).
Alternative: Two separate `st.line_chart` calls stacked vertically — rejected because spec explicitly says one chart with two series, and stacking doubles the vertical space.

### Decision 3 — `st.rerun()` drives Auto-Play, not `time.sleep()` inside a loop
A `while True: time.sleep(N)` loop inside `app.py` would block Streamlit's thread and make the Kill Switch unresponsive until the sleep completes. Instead: Auto-Play sets a flag + timestamp in session state, and each Streamlit rerun checks whether enough time has elapsed before firing the next turn. `st.rerun()` is called at the end of the Auto-Play branch to schedule the next check.

Rationale: Spec §4.6 — "Kill Switch must halt... immediately"; Streamlit's rerun model.
Alternative: `st.experimental_rerun()` (deprecated in Streamlit ≥1.27) — rejected; use `st.rerun()`.

### Decision 4 — Trigger Pulse uses word-level keyword extraction, not substring match
The `trigger_point` field is a full sentence (e.g., "If someone uses slang like 'bro', act highly condescending"). Doing a raw `trigger_point in spoken_dialogue` would never match because it searches for the whole sentence. Extract meaningful nouns/keywords from `trigger_point` by tokenizing on spaces, filtering stop-words (under 4 chars), and checking if any token appears in `spoken_dialogue.lower()`.

Rationale: Spec §4.4 — "scan `spoken_dialogue` for keywords matching the active entity's `trigger_point`".
Alternative: Regex or NLP library — rejected; adds a dependency; simple token filter is good enough for creator-facing visual feedback.

---

## Session State Keys — Complete Initialization Block

All keys must be initialized at top of `app.py` before any widget renders, using the guard pattern:

```python
if "battle_id" not in st.session_state:
    st.session_state.battle_id = None
if "battle_active" not in st.session_state:
    st.session_state.battle_active = False
if "turn_log" not in st.session_state:
    st.session_state.turn_log = []          # list[dict] — raw ExecuteActionResponse JSON
if "sentiment_history" not in st.session_state:
    st.session_state.sentiment_history = [] # list[int], range -100 to 100
if "aggression_history" not in st.session_state:
    st.session_state.aggression_history = []# list[int], range 0 to 100
if "current_vibe" not in st.session_state:
    st.session_state.current_vibe = "logical"
if "show_monologue" not in st.session_state:
    st.session_state.show_monologue = False
if "autoplay_active" not in st.session_state:
    st.session_state.autoplay_active = False
if "autoplay_last_fired" not in st.session_state:
    st.session_state.autoplay_last_fired = 0.0  # float epoch seconds
if "init_payload" not in st.session_state:
    st.session_state.init_payload = {}
if "turn_limit" not in st.session_state:
    st.session_state.turn_limit = 10
if "trigger_fired" not in st.session_state:
    st.session_state.trigger_fired = False  # cleared each rerun after display
```

---

## Function Specifications

### `api_client.py`

---

#### `initialize_battle(payload: dict, base_url: str, timeout: float = 30.0) -> dict`
- **Purpose:** POST to `/initialize_battle`, return parsed JSON dict on success.
- **Input:** `payload` — dict matching `InitializeBattleRequest`; `base_url` — e.g. `"http://localhost:8000"`; `timeout` — seconds before raising.
- **Output:** Dict with keys `battle_id`, `status`, `message`.
- **Raises:** `httpx.HTTPStatusError` on 4xx/5xx (call `.raise_for_status()` explicitly); `httpx.ConnectError` on unreachable host; `httpx.TimeoutException` on timeout.
- **Implementation:**
  ```python
  with httpx.Client(timeout=timeout) as client:
      r = client.post(f"{base_url}/initialize_battle", json=payload)
      r.raise_for_status()
      return r.json()
  ```

---

#### `execute_action(battle_id: str, action_type: str, base_url: str, context_text: str | None = None, timeout: float = 90.0) -> dict`
- **Purpose:** POST to `/execute_action`, return parsed JSON dict on success.
- **Input:** `battle_id`, `action_type` (one of `next_turn | context_bomb | kill_switch`), `context_text` (required and non-empty when `action_type == "context_bomb"`).
- **Output:** Dict matching `ExecuteActionResponse` keys: `speaker`, `internal_monologue`, `spoken_dialogue`, `tts_ready_text`, `voice_params`, `telemetry`.
- **Raises:** Same as `initialize_battle`. Timeout is 90s because LLM calls can take up to 60s (backend timeout) plus network.
- **Implementation:**
  ```python
  body = {"battle_id": battle_id, "action_type": action_type}
  if context_text:
      body["context_text"] = context_text
  with httpx.Client(timeout=timeout) as client:
      r = client.post(f"{base_url}/execute_action", json=body)
      r.raise_for_status()
      return r.json()
  ```

---

### `app.py` — Top-Level Helpers

---

#### `_extract_trigger_keywords(trigger_point: str) -> list[str]`
- **Purpose:** Extract meaningful words from a trigger_point sentence for pulse detection.
- **Logic:** `trigger_point.lower().split()` → filter tokens where `len(token.strip("'\".,!?")) >= 4` → strip punctuation → deduplicate → return list.
- **Example:** `"If someone uses slang like 'bro', act highly condescending"` → `["someone", "uses", "slang", "like", "highly", "condescending"]`

---

#### `_check_trigger_fired(spoken_dialogue: str, trigger_point: str) -> bool`
- **Purpose:** Return True if any extracted keyword appears in `spoken_dialogue`.
- **Calls:** `_extract_trigger_keywords(trigger_point)`.
- **Logic:** `any(kw in spoken_dialogue.lower() for kw in keywords)`.

---

#### `_vibe_color(vibe: str) -> str`
- **Purpose:** Map `current_vibe` string to a hex CSS color.
- **Output:** One of:

| Vibe | Hex |
|---|---|
| `logical`, `opening` | `#4A90D9` (Cool Blue) |
| `emotional`, `heated` | `#E8A838` (Amber) |
| `chaotic`, `cornered` | `#E84040` (Glowing Red) |
| `victory_lap` | `#D4AF37` (Gold) |
| (default/unknown) | `#888888` (Grey) |

---

#### `_run_turn(action_type: str, context_text: str | None = None) -> None`
- **Purpose:** Central function that executes one `/execute_action` call, appends to session state, and handles all error cases. Called by Next Turn, Auto-Play, and Context Bomb.
- **Preconditions checked (returns early with `st.warning` if violated):**
  - `st.session_state.battle_id is None` → `st.warning("Initialize a battle first")`
  - `not st.session_state.battle_active` → `st.warning("Battle is terminated — start a new battle")`
  - `len(st.session_state.turn_log) >= st.session_state.turn_limit` → `st.info("Battle complete — turn limit reached")`; disable call
- **Flow:**
  1. Set `st.session_state.trigger_fired = False`
  2. Show `status_placeholder.info("⏳ Processing LLM...")` (placeholder is a function-level `st.empty()` passed in or defined locally)
  3. Call `api_client.execute_action(battle_id, action_type, base_url, context_text)`
  4. On success: clear placeholder, show `status_placeholder.info("🔊 Voice Synthesizing...")` for 1 second, then clear
  5. Append response dict to `st.session_state.turn_log`
  6. Append `response["telemetry"]["sentiment_score"]` to `sentiment_history`
  7. Append `response["telemetry"]["aggression_level"]` to `aggression_history`
  8. Determine active speaker's `trigger_point` from `init_payload` (entity_1 or entity_2 based on `response["speaker"]`)
  9. Set `st.session_state.trigger_fired = _check_trigger_fired(response.get("spoken_dialogue", ""), trigger_point)`
  10. If `action_type == "kill_switch"`: set `st.session_state.battle_active = False`, `st.session_state.autoplay_active = False`
- **Error handling:**
  - `httpx.ConnectError` → `st.error(f"Cannot reach backend at {base_url}. Is the server running?")`
  - `httpx.HTTPStatusError` where `status_code == 409` → battle complete; disable controls: `st.info("Battle complete — turn limit reached")`, set `battle_active = False`
  - `httpx.HTTPStatusError` (other) → `st.error(f"Turn failed: {e.response.status_code} — {e.response.text}")`
  - `httpx.TimeoutException` → `st.error("Request timed out — LLM is taking too long")`
  - All errors: do NOT append anything to `turn_log` or history lists; if `autoplay_active` was True, set it False

---

## Logic Flow

### Flow 1 — Initialize Battle

```
User clicks "⚔️ Initialize Battle"
1. Validate required sidebar fields:
   - topic not empty → else st.warning("Topic is required")
   - entity_1.persona_name, entity_2.persona_name not empty → else st.warning(...)
   - entity_1.logic_core_belief ≥ 10 chars → else st.warning(...)
   - entity_1.trigger_point ≥ 5 chars → else st.warning(...)
   (Mirror backend Pydantic constraints; stop on first failure)

2. Build payload dict from sidebar widget values:
   {
     "match_config": {"topic": ..., "turn_limit": ..., "current_vibe": ...},
     "entity_1": {"selected_llm": ..., "persona_name": ..., "logic_core_belief": ...,
                  "trigger_point": ..., "voice_id": ..., "voice_speed": ...,
                  "persona_id": ... or None},
     "entity_2": { same structure }
   }
   Note: persona_id → pass None if field is empty string (don't pass empty string to backend)

3. Show st.spinner("Initializing battle...")

4. Call api_client.initialize_battle(payload, base_url)

5. On success:
   - st.session_state.battle_id = response["battle_id"]
   - st.session_state.battle_active = True
   - st.session_state.turn_limit = sidebar turn_limit value
   - st.session_state.current_vibe = sidebar current_vibe value
   - st.session_state.init_payload = payload (store for trigger detection later)
   - Clear: turn_log=[], sentiment_history=[], aggression_history=[], autoplay_active=False
   - st.success(f"Battle initialized! ID: {battle_id[:8]}...")
   - st.rerun()

6. On error:
   - httpx.ConnectError → st.error("Cannot reach backend at {url}. Is the server running?")
   - httpx.HTTPStatusError → st.error(f"Init failed: {e.response.status_code} — {e.response.text}")
   - battle_id stays None; no other state changes
```

---

### Flow 2 — Next Turn (manual)

```
User clicks "Next Turn" button
1. Guard check: _run_turn("next_turn") handles all preconditions
2. _run_turn fires the API call
3. st.rerun() triggers at the end of the button handler block to refresh the Arena Log and chart
```

---

### Flow 3 — Auto-Play loop

```
User clicks "Auto-Play" toggle (ON state)
1. Set st.session_state.autoplay_active = True
2. Set st.session_state.autoplay_last_fired = time.time()
3. st.rerun()

Each Streamlit rerun while autoplay_active == True:
1. Check: not battle_active → set autoplay_active=False, return
2. Check: len(turn_log) >= turn_limit → set autoplay_active=False, return
3. elapsed = time.time() - autoplay_last_fired
4. If elapsed >= autoplay_interval (from sidebar slider):
   - _run_turn("next_turn")
   - st.session_state.autoplay_last_fired = time.time()
   - st.rerun()
5. Else:
   - time.sleep(0.5)  # short poll to avoid busy-wait burning CPU
   - st.rerun()

User clicks "Auto-Play" toggle (OFF state):
1. Set st.session_state.autoplay_active = False
   (next rerun loop check will halt the loop)
```

---

### Flow 4 — Inject Context Bomb

```
1. Check: context_bomb_text (from st.text_area below the button) is not empty
   → If empty: st.warning("Enter context text before injecting a bomb") — return
2. _run_turn("context_bomb", context_text=context_bomb_text)
3. st.rerun()
```

---

### Flow 5 — Kill Switch

```
1. _run_turn("kill_switch")
   Inside _run_turn:
   - Calls api_client.execute_action(battle_id, "kill_switch", base_url)
   - On 200: sets battle_active=False, autoplay_active=False
   - Response turn IS appended to turn_log (battle is paused, not erased)
2. st.error("🔴 BATTLE TERMINATED")
3. st.rerun()
```

---

## File Internal Layout

### `creator_dashboard/api_client.py`

```
Section 1 — Module docstring (one line: "HTTP client wrapper for Arena backend API.")
Section 2 — Imports: httpx only
Section 3 — initialize_battle()
Section 4 — execute_action()
```

No classes. No global state. No configuration read here — all config is passed as `base_url` argument.

---

### `creator_dashboard/app.py`

```
Section 1 — Imports
  import time
  import streamlit as st
  import altair as alt
  import pandas as pd
  from creator_dashboard import api_client

Section 2 — Page config (MUST be first Streamlit call)
  st.set_page_config(layout="wide", page_title="AI Arena — Creator Dashboard", page_icon="⚔️")

Section 3 — CSS injection (fixed height containers, kill switch red button, monologue grey style)

Section 4 — Session state initialization (all keys, guard pattern)

Section 5 — Helper functions (_extract_trigger_keywords, _check_trigger_fired, _vibe_color, _run_turn)

Section 6 — Sidebar (Module 1)
  6a. Backend URL input
  6b. Auto-Play interval slider
  6c. Match Setup fields
  6d. Entity 1 fields (inside st.expander("Entity 1 — Persona"))
  6e. Entity 2 fields (inside st.expander("Entity 2 — Persona"))
  6f. Initialize Battle button + handler

Section 7 — Main stage: Module 2 (Telemetry)
  7a. col_chart, col_vibe, col_pulse = st.columns([3, 1, 1])
  7b. Altair dual-axis chart in col_chart
  7c. Neural Vibe Monitor in col_vibe
  7d. Emotion Trigger Pulse display in col_pulse

Section 8 — Main stage: Module 3 (Arena Log)
  8a. Internal Monologue toggle
  8b. Arena Log container with fixed height CSS class
  8c. Loop over turn_log and render bubbles

Section 9 — Main stage: Module 4 (God Mode Controls)
  9a. Status overlay placeholder
  9b. Four-column button row: Next Turn | Auto-Play | Context Bomb setup | Kill Switch
  9c. Auto-Play rerun loop (runs after widget rendering if autoplay_active)
```

---

## Edge Case Implementation Map

| Edge Case (Spec §5) | Mechanism | Location |
|--------------------|-----------|----------|
| `/initialize_battle` returns non-200 | `r.raise_for_status()` → `HTTPStatusError` caught in init handler → `st.error(...)` | `app.py` §6f |
| `/execute_action` returns non-200 | Same raise pattern in `_run_turn` → caught, not appended to log, autoplay halted | `app.py` `_run_turn` |
| `turn_limit` reached (local check) | Guard in `_run_turn`: `len(turn_log) >= turn_limit` → `st.info("Battle complete...")` | `app.py` `_run_turn` |
| `turn_limit` reached (409 from backend) | `HTTPStatusError` with `status_code==409` → same message, `battle_active=False` | `app.py` `_run_turn` |
| Kill Switch mid-Auto-Play | `_run_turn("kill_switch")` sets `autoplay_active=False`; Auto-Play loop checks this flag | `app.py` §9b + `_run_turn` |
| Backend unreachable | `httpx.ConnectError` → `st.error("Cannot reach backend at {url}...")` | `api_client.py` (raises); `app.py` (catches) |
| `battle_id` is None when control clicked | Guard at top of `_run_turn` → `st.warning` + early return | `app.py` `_run_turn` |
| `spoken_dialogue` missing from response | `response.get("spoken_dialogue", "[No dialogue returned]")` | `app.py` §8c rendering |
| `telemetry` missing from response | `if "telemetry" in response:` gate before appending to history lists | `app.py` `_run_turn` |
| `context_bomb` empty `context_text` | Pre-check before calling `_run_turn`; button shows `st.warning` | `app.py` §9b |
| `persona_id` empty string sent to backend | Convert `"" → None` before building payload; backend's `extra="forbid"` would accept None | `app.py` §6f |

---

## Module 2 — Altair Chart Specification

```python
import altair as alt
import pandas as pd

def _build_telemetry_chart(sentiment_history: list, aggression_history: list) -> alt.Chart:
    turns = list(range(1, len(sentiment_history) + 1))
    df = pd.DataFrame({
        "Turn": turns,
        "Sentiment": sentiment_history,
        "Aggression": aggression_history,
    })
    sentiment_line = (
        alt.Chart(df)
        .mark_line(color="#4A90D9", strokeWidth=2)
        .encode(
            x=alt.X("Turn:Q", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("Sentiment:Q", scale=alt.Scale(domain=[-100, 100]),
                    axis=alt.Axis(title="Sentiment", titleColor="#4A90D9")),
        )
    )
    aggression_line = (
        alt.Chart(df)
        .mark_line(color="#E84040", strokeWidth=2)
        .encode(
            x="Turn:Q",
            y=alt.Y("Aggression:Q", scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(title="Aggression", titleColor="#E84040")),
        )
    )
    return alt.layer(sentiment_line, aggression_line).resolve_scale(y="independent")
```

Render: `st.altair_chart(_build_telemetry_chart(...), use_container_width=True)` in col_chart.

---

## Module 3 — Arena Log Rendering (per-turn)

For each `entry` in `st.session_state.turn_log`:

```
speaker = entry.get("speaker", "entity_1")
is_e1 = speaker == "entity_1"

# Determine persona name from init_payload
e1_name = init_payload.get("entity_1", {}).get("persona_name", "Entity 1")
e2_name = init_payload.get("entity_2", {}).get("persona_name", "Entity 2")
display_name = e1_name if is_e1 else e2_name

# Internal Monologue bubble (if toggle ON)
if st.session_state.show_monologue:
    monologue = entry.get("internal_monologue", "")
    if monologue:
        with st.chat_message("assistant"):
            st.markdown(f"*[Thinking — {display_name}]: {monologue}*")

# Spoken Dialogue bubble
with st.chat_message("user" if is_e1 else "assistant"):
    st.markdown(f"**{display_name}:** {entry.get('spoken_dialogue', '[No dialogue returned]')}")
```

Note: Streamlit's `st.chat_message` only supports `"user"` and `"assistant"` as role strings for distinct bubble alignment. Map entity_1 → "user" (left), entity_2 → "assistant" (right).

---

## CSS Injection Specification

Inject via `st.markdown(css_str, unsafe_allow_html=True)` at the top of `app.py` (before any containers):

```css
/* Arena Log fixed height scroll */
[data-testid="stVerticalBlock"] .arena-log {
    max-height: 400px;
    overflow-y: auto;
}

/* Kill Switch red button */
button[data-testid="kill-switch-btn"] {
    background-color: #CC0000 !important;
    color: white !important;
    font-weight: bold !important;
    width: 100% !important;
}

/* Monologue bubble italic grey */
.thinking-bubble {
    color: #888888;
    font-style: italic;
}
```

Note: Streamlit's CSS class targeting is fragile across versions. If `[data-testid]` selectors break on the installed Streamlit version, fall back to targeting `div.stChatMessage` for bubbles and wrapping the Arena Log in a manual `st.container()` with a height set via `height` parameter (Streamlit ≥1.30 supports `st.container(height=400)`).

---

## Neural Vibe Monitor Rendering

```python
color = _vibe_color(st.session_state.current_vibe)
vibe_html = f"""
<div style="
    background-color: {color};
    border-radius: 12px;
    padding: 18px;
    text-align: center;
    color: white;
    font-weight: bold;
    font-size: 1.1em;
    box-shadow: 0 0 12px {color};
">
    VIBE<br>{st.session_state.current_vibe.upper().replace("_", " ")}
</div>
"""
col_vibe.markdown(vibe_html, unsafe_allow_html=True)
```

---

## God Mode Controls — Exact Button Layout

```python
c1, c2, c3, c4 = st.columns(4)
battle_ready = (
    st.session_state.battle_id is not None
    and st.session_state.battle_active
    and len(st.session_state.turn_log) < st.session_state.turn_limit
)

with c1:
    if st.button("▶ Next Turn", disabled=not battle_ready):
        _run_turn("next_turn")
        st.rerun()

with c2:
    autoplay_label = "⏸ Stop Auto" if st.session_state.autoplay_active else "⏯ Auto-Play"
    if st.button(autoplay_label, disabled=not battle_ready and not st.session_state.autoplay_active):
        if st.session_state.autoplay_active:
            st.session_state.autoplay_active = False
        else:
            st.session_state.autoplay_active = True
            st.session_state.autoplay_last_fired = time.time()
        st.rerun()

with c3:
    bomb_text = st.text_input("Context injection text", key="bomb_text_input",
                               placeholder="Inject a new narrative twist...")
    if st.button("💣 Context Bomb", disabled=not battle_ready or not bomb_text):
        _run_turn("context_bomb", context_text=bomb_text)
        st.rerun()

with c4:
    kill_disabled = st.session_state.battle_id is None or not st.session_state.battle_active
    if st.button("🔴 KILL SWITCH", disabled=kill_disabled):
        _run_turn("kill_switch")
        st.error("🔴 BATTLE TERMINATED")
        st.rerun()
```

---

## Dependencies — `creator_dashboard/requirements.txt`

```
streamlit>=1.30.0
httpx>=0.25.1
altair>=5.0.0
pandas>=2.0.0
```

`pandas` is needed by Altair for the DataFrame input. All four are installable via `pip install -r creator_dashboard/requirements.txt`.

---

## Hard Boundaries

- Do NOT call any LLM directly from `app.py` or `api_client.py` — all intelligence goes through the FastAPI backend
- Do NOT use `asyncio.run()` or `async def` in `app.py` — Streamlit is synchronous
- Do NOT use `st.experimental_rerun()` — it is deprecated; use `st.rerun()`
- Do NOT store secrets or API keys in `app.py` — backend URL only, no LLM keys
- Do NOT call `time.sleep()` for durations > 1 second inside `app.py` — it blocks the thread; use the Auto-Play epoch-check pattern instead (the 1-second "Voice Synthesizing..." overlay is the only exception)
- Do NOT import from `backend_arena/` — frontend has zero knowledge of backend internals; only the JSON contract matters

---

## Acceptance Criteria

**AC1 — Initialize stores battle_id**
```bash
# Start backend: uvicorn backend_arena.src.main:app --reload
# Start frontend: streamlit run creator_dashboard/app.py
# Fill in sidebar: topic="Test", LLM="mock", all fields, click Initialize
```
Expected: `st.success` message appears containing a truncated UUID; `battle_id` in session state is non-null; Next Turn button becomes enabled.

**AC2 — Next Turn appends to Arena Log**
```bash
# After AC1: click "Next Turn"
```
Expected: One new chat bubble appears in the Arena Log within the same rerun; the dual-axis chart gains one new data point.

**AC3 — Chart data points match telemetry**
```bash
# Run 3 turns, inspect chart
```
Expected: Chart has exactly 3 data points. Sentiment line maps to the `sentiment_score` values from each turn response (-100 to 100). Aggression line maps to `aggression_level` values (0 to 100). Both use independent Y-axes.

**AC4 — Internal Monologue toggle**
```bash
# With turns logged, toggle ON
```
Expected: Grey italic "Thinking" bubble appears before each `spoken_dialogue` bubble. Toggle OFF → no thinking bubble visible in the Arena Log.

**AC5 — Kill Switch stops Auto-Play**
```bash
# Start Auto-Play, immediately click Kill Switch
```
Expected: No further `/execute_action` calls after the kill_switch call. "BATTLE TERMINATED" error banner displayed. Next Turn and Auto-Play buttons become disabled.

**AC6 — Turn limit reached**
```bash
# Set turn_limit=2, run 2 turns
```
Expected: After turn 2, Next Turn and Auto-Play buttons are disabled. `st.info("Battle complete...")` is displayed.

**AC7 — Backend unreachable**
```bash
# Stop backend, click Next Turn
```
Expected: `st.error("Cannot reach backend at http://localhost:8000. Is the server running?")` shown. No crash. No entry added to turn_log.

**AC8 — Context Bomb requires text**
```bash
# Leave context text input empty, click Context Bomb
```
Expected: Button is disabled when context text field is empty — click is not possible. (Button has `disabled=True` when `bomb_text` is falsy.)

**AC9 — Neural Vibe Monitor color**
```bash
# Initialize with vibe="chaotic"
```
Expected: The Vibe Monitor tile renders with background color `#E84040` (Glowing Red) and displays "CHAOTIC".

**AC10 — Layout stability**
```bash
# Run 10 turns, observe layout
```
Expected: The Arena Log container scrolls internally and does not push God Mode Controls off-screen. Telemetry section remains at fixed top position.
