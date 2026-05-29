# Spec: Creator Dashboard (Streamlit Frontend)
**Version:** 1.0.0 | **Component:** `creator_dashboard/`
**Status:** Ready for Implementation

---

## 1. Problem Statement

The backend engine (`/initialize_battle`, `/execute_action`) produces rich telemetry, internal monologues, and structured dialogue per turn — but there is no GUI to consume or visualize this. A content creator running the AI battle has no way to configure personas, monitor aggression/sentiment in real time, control pacing, or crop a 4K-optimized layout for Shorts/Reels production. Without this dashboard, the engine is headless and unusable for its primary use case: producing creator content.

---

## 2. Objective

Build a single-page Streamlit Creator Dashboard (`creator_dashboard/app.py`) that connects to the running FastAPI backend, configures and launches a battle, drives turn execution, and renders real-time telemetry — all in a fixed 4K layout optimized for 9:16 post-production cropping.

---

## 3. Scope & Constraints

**Will Do:**
- Render a sidebar Configuration Matrix with all fields required by `/initialize_battle`
- Call `POST /initialize_battle` and store the returned `battle_id` in session state
- Call `POST /execute_action` (action_type: `next_turn`) and render each turn's response
- Plot a dual-axis real-time line chart for `sentiment_score` and `aggression_level` (from `telemetry`)
- Flash an Emotion Trigger Pulse indicator when a trigger keyword is detected in `spoken_dialogue`
- Render a Neural Vibe Monitor gauge that changes color/intensity based on `current_vibe`
- Display a high-contrast Arena Log (chat interface) with speaker labels
- Provide an Internal Monologue Toggle: when ON, display `internal_monologue` in a "Thinking" bubble before `spoken_dialogue`
- Provide transport controls: **Next Turn**, **Auto-Play** (timed loop), **Inject Context Bomb**, and **Kill Switch**
- Show processing overlays: "Processing LLM..." and "Voice Synthesizing..." during active API calls
- Fixed 4K resolution layout so a 9:16 crop over Chat Log or Telemetry graph retains all visual data

**Will NOT Do:**
- Play audio / call TTS engine (frontend only renders `tts_ready_text`; TTS is out of scope for this spec)
- Implement authentication or multi-user sessions
- Store or replay historical battles beyond the current session
- Build a custom Streamlit component — use native Streamlit widgets only
- Call any LLM directly — all intelligence goes through the FastAPI backend

**Hard Rules:**
- All API calls go to the backend base URL (configurable via `.env` or sidebar input, default `http://localhost:8000`)
- The `/execute_action` payload schema must be followed exactly: `{"battle_id": "...", "action_type": "next_turn" | "context_bomb" | "kill_switch"}`
- The dashboard must read `current_vibe` from its own session state (set at init) — the backend does not return it per turn
- Kill Switch must halt all ongoing API calls and Auto-Play immediately; no further turns may execute after Kill Switch fires until a new battle is initialized

---

## 4. Core Design

### 4.1 Layout Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  SIDEBAR (Module 1)        │  MAIN STAGE                            │
│  - Match Setup             │  ┌─────────────────────────────────┐   │
│  - Entity 1 Persona        │  │ Module 2: Telemetry (Top Half)  │   │
│  - Entity 2 Persona        │  │  - Dual-axis line chart         │   │
│  - Voice Engine            │  │  - Emotion Trigger Pulse        │   │
│  - Backend URL             │  │  - Neural Vibe Monitor          │   │
│  - [Initialize Battle]     │  └─────────────────────────────────┘   │
│                            │  ┌─────────────────────────────────┐   │
│                            │  │ Module 3: Arena Log (Bottom)    │   │
│                            │  │  - Chat bubbles                 │   │
│                            │  │  - Monologue toggle             │   │
│                            │  └─────────────────────────────────┘   │
│                            │  ┌─────────────────────────────────┐   │
│                            │  │ Module 4: God Mode Controls     │   │
│                            │  │  Next Turn | Auto-Play | Bomb   │   │
│                            │  │  [KILL SWITCH]                  │   │
│                            │  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

The main stage uses `st.container()` with a fixed pixel height via CSS injection to anchor the 4K layout. The telemetry section occupies the top 50% of the main stage; the Arena Log occupies ~35%; God Mode controls occupy ~15%.

### 4.2 Session State Keys

| Key | Type | Description |
|---|---|---|
| `battle_id` | `str \| None` | Set after successful `/initialize_battle` |
| `battle_active` | `bool` | False after Kill Switch; True after init |
| `turn_log` | `list[dict]` | Accumulated turn responses from `/execute_action` |
| `sentiment_history` | `list[int]` | `sentiment_score` per turn (for chart) |
| `aggression_history` | `list[int]` | `aggression_level` per turn (for chart) |
| `current_vibe` | `str` | Set at init from sidebar input; used for Vibe Monitor |
| `show_monologue` | `bool` | Controlled by Internal Monologue Toggle |
| `autoplay_active` | `bool` | True during Auto-Play loop |
| `init_payload` | `dict` | The payload sent to `/initialize_battle` (for reference) |

### 4.3 Module 1 — Configuration Matrix (Sidebar)

Sidebar fields map directly to the `/initialize_battle` payload:

**Match Setup:**
- `topic` → `st.text_input` (required)
- `turn_limit` → `st.number_input` (int, min=2, max=50, default=10)
- `current_vibe` → `st.selectbox` with options: `logical`, `emotional`, `chaotic`, `opening`, `heated`, `cornered`, `victory_lap`

**Persona Deep-Dive (two columns, Entity 1 / Entity 2):**
- `persona_name` → `st.text_input`
- `selected_llm` → `st.text_input` (e.g. `gpt-4o-api`, `mock`)
- `persona_id` → `st.text_input` (optional; maps to a JSON fixture: `gym_bro`, `tech_bro`, etc.)
- `logic_core_belief` → `st.text_area`
- `trigger_point` → `st.text_area`

**Voice Engine (per entity):**
- `voice_id` → `st.text_input`
- `voice_speed` → `st.slider` (0.5–2.0, step 0.1, default 1.0)

**Initialize Button:** `st.button("⚔️ Initialize Battle")` — calls `POST /initialize_battle`, stores `battle_id` + `current_vibe` in session state, clears all history lists.

### 4.4 Module 2 — Visual Telemetry & Battle Analytics

**Dual-Axis Line Chart (Aggression & Sentiment Tracker):**
- `st.line_chart` or `altair` chart with two series: `sentiment_score` (blue) and `aggression_level` (red)
- X-axis: turn number; Y-axis: 0–100 scale
- Updated after every `/execute_action` call by appending to `sentiment_history` / `aggression_history`

**Emotion Trigger Pulse:**
- After each turn, scan `spoken_dialogue` for keywords matching the active entity's `trigger_point`
- If a match is detected: display a colored flash banner `st.warning("⚡ TRIGGER ACTIVATED")` for 3 seconds using `st.empty()` + time-based auto-clear

**Neural Vibe Monitor:**
- A colored metric tile (`st.metric`) that updates color based on `current_vibe`:

| Vibe | Color Label |
|---|---|
| `logical` / `opening` | Cool Blue |
| `emotional` / `heated` | Amber |
| `chaotic` / `cornered` | Glowing Red |
| `victory_lap` | Gold |

- Rendered via `st.markdown` with inline CSS background color in a `st.container` block

### 4.5 Module 3 — Arena Log & Internal Monologue

**Internal Monologue Toggle:**
- `st.toggle("🧠 Show Internal Monologue")` → sets `show_monologue` in session state

**Arena Log (Chat Interface):**
- Iterate `turn_log` in order; for each entry:
  1. If `show_monologue` is True: render `internal_monologue` in a distinct `st.chat_message("assistant")` with label `"[Thinking]"` styled in italic grey
  2. Render `spoken_dialogue` in `st.chat_message(speaker)` with the entity's `persona_name` as the avatar label
- Speaker bubbles are left/right aligned: entity_1 = left, entity_2 = right (achieved via Streamlit columns)
- Log auto-scrolls to the latest entry using `st.empty()` anchored at the bottom

### 4.6 Module 4 — God Mode Controls (Transport)

Four controls rendered as a horizontal button row:

| Button | Action |
|---|---|
| **Next Turn** | `POST /execute_action` with `action_type: "next_turn"` — renders result, appends to log |
| **Auto-Play** | Toggle loop: fires Next Turn every N seconds (configurable, default 5s) until `turn_limit` or Kill Switch |
| **Inject Context Bomb** | `POST /execute_action` with `action_type: "context_bomb"` — same rendering pipeline |
| **KILL SWITCH** | Sets `battle_active = False`, `autoplay_active = False`; displays `st.error("🔴 BATTLE TERMINATED")` |

**Kill Switch styling:** Full-width, red background button via `st.markdown` unsafe_allow_html CSS override.

### 4.7 Processing Overlays

- Before every API call: set an `st.empty()` placeholder with text `"⏳ Processing LLM..."`
- After API returns: update placeholder to `"🔊 Voice Synthesizing..."` (1s), then clear
- Overlay sits above the Arena Log, below the Telemetry section

### 4.8 Backend API Client

A thin `creator_dashboard/api_client.py` module wraps all `httpx` calls:

```python
def initialize_battle(payload: dict, base_url: str) -> dict: ...
def execute_action(battle_id: str, action_type: str, base_url: str) -> dict: ...
```

Raises `httpx.HTTPStatusError` on non-2xx; the Streamlit app catches and displays `st.error(str(e))`.

---

## 5. Edge Cases & Error Handling

| Case | Handling |
|---|---|
| `/initialize_battle` returns non-200 | `st.error("Init failed: <status> <body>")` — `battle_id` stays None, controls disabled |
| `/execute_action` returns non-200 | `st.error("Turn failed: ...")` — turn is NOT appended to log; Auto-Play halts |
| `turn_limit` reached | Next Turn and Auto-Play buttons disabled; `st.info("Battle complete — turn limit reached")` |
| Kill Switch fired mid-Auto-Play | Auto-Play loop exits on next iteration check (`if not st.session_state.autoplay_active`) |
| Backend unreachable (connection refused) | `st.error("Cannot reach backend at <url>. Is the server running?")` |
| `battle_id` is None when controls clicked | `st.warning("Initialize a battle first")` — no API call made |
| `spoken_dialogue` missing from response | Log renders `"[No dialogue returned]"` placeholder — does not crash |
| `telemetry` missing from response | Chart skips that data point — no crash, gap visible in chart |

---

## 6. Acceptance Criteria

1. Submitting a valid Initialize form calls `POST /initialize_battle` exactly once and stores a non-null `battle_id` in session state.
2. Clicking **Next Turn** calls `POST /execute_action` with `action_type: "next_turn"` and the stored `battle_id`; the response's `spoken_dialogue` appears in the Arena Log within the same Streamlit rerun.
3. The dual-axis chart gains one new data point per turn reflecting the actual `sentiment_score` and `aggression_level` from that turn's telemetry.
4. When **Internal Monologue Toggle** is ON, `internal_monologue` text from each turn is visible in the Arena Log in a visually distinct bubble before the `spoken_dialogue` bubble.
5. When **Internal Monologue Toggle** is OFF, no `internal_monologue` text is visible anywhere in the Arena Log.
6. Clicking **KILL SWITCH** while Auto-Play is running stops the loop within one turn interval; no further `/execute_action` calls are made after the switch fires.
7. The Neural Vibe Monitor displays the correct color for the `current_vibe` selected at initialization.
8. Reaching `turn_limit` disables **Next Turn** and **Auto-Play**; the UI displays a "Battle complete" message without crashing.
9. A backend connection failure surfaces a user-readable `st.error` message and does not raise an unhandled Python exception.
10. The layout is fixed-width (`st.set_page_config(layout="wide")`) and visually stable across reruns — no layout shift when new turns are appended.

---

## 7. UI/UX Behavior

- `st.set_page_config(layout="wide", page_title="AI Arena — Creator Dashboard")` is the first call in `app.py`
- All controls in Module 4 are disabled (`disabled=True`) when `battle_id is None` or `battle_active is False`
- Auto-Play interval is configurable via a `st.slider` in the sidebar (1s–30s, default 5s)
- The Arena Log container has a fixed height (`overflow-y: scroll`) via `st.markdown` CSS injection so it doesn't push the transport controls off-screen as turns accumulate

---

## 8. Dependencies

| Dependency | Purpose |
|---|---|
| `streamlit` | UI framework |
| `httpx` | Sync HTTP client for backend calls |
| `altair` | Optional: richer dual-axis chart (fallback: `st.line_chart`) |
| FastAPI backend on `http://localhost:8000` | All data source — no direct LLM calls from frontend |

No new Python packages beyond `streamlit` and `httpx` unless `altair` is chosen for the chart; both are already present or trivially pip-installable.

---

## 9. File Structure

```
creator_dashboard/
├── app.py               # Main Streamlit entry point
└── api_client.py        # Thin httpx wrapper for backend calls
```

No additional modules needed. All session state and rendering logic lives in `app.py`; all HTTP logic lives in `api_client.py`.
