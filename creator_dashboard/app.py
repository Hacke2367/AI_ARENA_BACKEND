# ─── SECTION 1: Imports ───────────────────────────────────────────────────────
import html as html_mod
import logging
import time

import altair as alt
import httpx
import pandas as pd
import streamlit as st

import api_client

_log = logging.getLogger(__name__)

# ─── SECTION 2: Page Config (must be first Streamlit call) ────────────────────
st.set_page_config(
    layout="wide",
    page_title="AI Arena — Creator Dashboard",
    page_icon="⚔️",
)

# ─── SECTION 3: CSS Injection ─────────────────────────────────────────────────
# Fix: target only the Kill Switch button by aria-label — avoids bleeding to
# other buttons in different column layouts on the same page.
st.markdown(
    """
    <style>
    button[aria-label="🔴 KILL SWITCH"] {
        background-color: #CC0000 !important;
        color: white !important;
        font-weight: bold !important;
        border: none !important;
    }
    button[aria-label="🔴 KILL SWITCH"]:hover {
        background-color: #990000 !important;
    }
    button[aria-label="🔴 KILL SWITCH"]:disabled {
        background-color: #660000 !important;
        opacity: 0.5 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── SECTION 4: Session State Initialization ──────────────────────────────────
_SS_DEFAULTS: dict = {
    "battle_id": None,
    "battle_active": False,
    "turn_log": [],           # list[dict] — raw ExecuteActionResponse JSON per turn
    "sentiment_history": [],  # list[int], range -100 to 100
    "aggression_history": [], # list[int], range 0 to 100
    "current_vibe": "logical",
    "show_monologue": False,
    "autoplay_active": False,
    "autoplay_last_fired": 0.0,  # epoch float
    "init_payload": {},
    "turn_limit": 10,
    "trigger_fired": False,
}
# Fix: copy mutable defaults so each session gets its own list/dict instance,
# preventing cross-session data leakage when multiple tabs are open.
for _k, _v in _SS_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v

# ─── SECTION 5: Helper Functions ──────────────────────────────────────────────

def _extract_trigger_keywords(trigger_point: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in trigger_point.lower().split():
        clean = token.strip("'\".,!?;:")
        if len(clean) >= 4 and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _check_trigger_fired(spoken_dialogue: str, trigger_point: str) -> bool:
    keywords = _extract_trigger_keywords(trigger_point)
    lowered = spoken_dialogue.lower()
    return any(kw in lowered for kw in keywords)


def _vibe_color(vibe: str) -> str:
    return {
        "logical": "#4A90D9",
        "opening": "#4A90D9",
        "emotional": "#E8A838",
        "heated": "#E8A838",
        "chaotic": "#E84040",
        "cornered": "#E84040",
        "victory_lap": "#D4AF37",
    }.get(vibe, "#888888")


# Fix: removed string-quoted return type — altair is imported at module top,
# so the forward-reference form is unnecessary.
def _build_telemetry_chart(
    sentiment_history: list, aggression_history: list
) -> alt.LayerChart | None:
    if not sentiment_history:
        return None
    turns = list(range(1, len(sentiment_history) + 1))
    df = pd.DataFrame({
        "Turn": turns,
        "Sentiment": sentiment_history,
        "Aggression": aggression_history,
    })
    sentiment_line = (
        alt.Chart(df)
        .mark_line(color="#4A90D9", strokeWidth=2, point=alt.OverlayMarkDef(color="#4A90D9", size=60))
        .encode(
            x=alt.X("Turn:Q", axis=alt.Axis(tickMinStep=1, title="Turn")),
            y=alt.Y(
                "Sentiment:Q",
                scale=alt.Scale(domain=[-100, 100]),
                axis=alt.Axis(title="Sentiment", titleColor="#4A90D9"),
            ),
            tooltip=[alt.Tooltip("Turn:Q"), alt.Tooltip("Sentiment:Q")],
        )
    )
    aggression_line = (
        alt.Chart(df)
        .mark_line(color="#E84040", strokeWidth=2, point=alt.OverlayMarkDef(color="#E84040", size=60))
        .encode(
            x=alt.X("Turn:Q"),
            y=alt.Y(
                "Aggression:Q",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(title="Aggression", titleColor="#E84040"),
            ),
            tooltip=[alt.Tooltip("Turn:Q"), alt.Tooltip("Aggression:Q")],
        )
    )
    return (
        alt.layer(sentiment_line, aggression_line)
        .resolve_scale(y="independent")
        .properties(title="Aggression & Sentiment Tracker", height=220)
    )


def _handle_turn_error(exc: Exception, base_url: str) -> None:
    if isinstance(exc, httpx.ConnectError):
        _log.error("Backend unreachable at %s", base_url)
        st.error(f"Cannot reach backend at {base_url}. Is the server running?")
    elif isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 409:
            _log.info("Battle complete — 409 from backend")
            st.info("Battle complete — turn limit reached.")
            st.session_state.battle_active = False
        else:
            _log.error("HTTP %d from backend: %s", exc.response.status_code, exc.response.text)
            st.error(f"Turn failed: {exc.response.status_code} — {exc.response.text}")
    elif isinstance(exc, httpx.TimeoutException):
        _log.error("Timeout on backend call")
        st.error("Request timed out — LLM is taking too long.")
    else:
        _log.error("Unhandled error type in _handle_turn_error: %s", type(exc))
        st.error(f"Unexpected error: {exc}")


def _run_turn(
    action_type: str,
    base_url: str,
    status_placeholder,
    context_text: str | None = None,
) -> None:
    ss = st.session_state

    # Preconditions
    if ss.battle_id is None:
        st.warning("Initialize a battle first.")
        return
    if not ss.battle_active:
        st.warning("Battle is terminated — start a new battle.")
        return
    if action_type != "kill_switch" and len(ss.turn_log) >= ss.turn_limit:
        st.info("Battle complete — turn limit reached.")
        return

    ss.trigger_fired = False
    status_placeholder.info("⏳ Processing LLM...")
    _log.debug("_run_turn battle_id=%s action=%s", ss.battle_id, action_type)

    # Fix: catch specific httpx exceptions. Unknown exceptions are logged and re-raised
    # so bugs in api_client surface in logs rather than being silently swallowed.
    try:
        response = api_client.execute_action(
            ss.battle_id, action_type, base_url, context_text
        )
    except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        status_placeholder.empty()
        _handle_turn_error(exc, base_url)
        if ss.autoplay_active:
            ss.autoplay_active = False
        return
    except Exception as exc:
        status_placeholder.empty()
        _log.error("Unhandled error in _run_turn action=%s", action_type, exc_info=True)
        st.error("Unexpected error — check server logs.")
        if ss.autoplay_active:
            ss.autoplay_active = False
        raise

    # Fix: removed time.sleep(1) — the overlay flash happens naturally between
    # the API response and the next st.rerun(); no hard block needed.
    status_placeholder.info("🔊 Voice Synthesizing...")
    status_placeholder.empty()

    # Append to log and update telemetry
    ss.turn_log.append(response)
    telemetry = response.get("telemetry")
    if telemetry:
        ss.sentiment_history.append(telemetry.get("sentiment_score", 0))
        ss.aggression_history.append(telemetry.get("aggression_level", 0))

    # Trigger detection
    speaker = response.get("speaker", "entity_1")
    entity_key = "entity_1" if speaker == "entity_1" else "entity_2"
    trigger_point = ss.init_payload.get(entity_key, {}).get("trigger_point", "")
    spoken = response.get("spoken_dialogue", "")
    ss.trigger_fired = _check_trigger_fired(spoken, trigger_point) if trigger_point else False
    _log.debug("turn complete speaker=%s trigger_fired=%s", speaker, ss.trigger_fired)

    # Kill switch post-processing
    if action_type == "kill_switch":
        ss.battle_active = False
        ss.autoplay_active = False


# ─── SECTION 6: Sidebar — Module 1 (Configuration Matrix) ────────────────────
with st.sidebar:
    st.title("⚔️ AI Arena")
    st.caption("Creator Dashboard v1.0")
    st.divider()

    # 6a. Backend URL
    base_url: str = st.text_input(
        "Backend URL",
        value="http://localhost:8000",
        placeholder="http://localhost:8000",
    )

    # Fix: validate URL scheme before passing to api_client — prevents silent
    # failures on malformed or dangerous URLs (file://, javascript:, etc.)
    if base_url and not base_url.startswith(("http://", "https://")):
        st.error("Backend URL must start with http:// or https://")
        st.stop()

    # 6b. Auto-Play interval
    autoplay_interval: int = st.slider(
        "Auto-Play Interval (s)", min_value=1, max_value=30, value=5, step=1
    )

    st.divider()

    # 6c. Match Setup
    st.subheader("Match Setup")
    topic = st.text_input("Topic", placeholder="Is roasting considered cyberbullying?")
    battle_context_input = st.text_area(
        "Battle Context (optional)",
        placeholder=(
            "Set the shared world-premise BOTH AIs must accept as absolute truth.\n\n"
            "Example: Pyaar (love) is completely normal and obvious in this world. "
            "Every person has experienced it. Neither side can deny its existence — "
            "only argue its value or effects."
        ),
        height=110,
        help=(
            "This context is injected into BOTH entities' system prompts and stays "
            "fixed for the entire battle. Use it to define world rules, scenario "
            "constraints, or any premise both combatants must accept before arguing."
        ),
    )
    turn_limit_input = st.number_input(
        "Turn Limit", min_value=2, max_value=50, value=10, step=1
    )
    current_vibe_input = st.selectbox(
        "Starting Vibe",
        options=["logical", "emotional", "chaotic", "opening", "heated", "cornered", "victory_lap"],
        index=0,
    )

    st.divider()

    # 6d. Entity 1
    with st.expander("Entity 1 — Persona", expanded=True):
        e1_persona_name = st.text_input("Persona Name", key="e1_name", placeholder="Toxic Gym Bro")
        e1_selected_llm = st.selectbox(
            "LLM",
            options=["mock", "openai", "claude", "ollama", "groq", "huggingface"],
            key="e1_llm",
        )
        e1_persona_id = st.text_input(
            "Persona ID (optional)", key="e1_pid", placeholder="gym_bro"
        )
        e1_core_belief = st.text_area(
            "Core Belief",
            key="e1_belief",
            placeholder="People who don't lift are fundamentally weak.",
            height=80,
        )
        e1_trigger = st.text_area(
            "Trigger Point",
            key="e1_trigger",
            placeholder="If someone calls gym a waste of time, lose your temper.",
            height=80,
        )
        e1_voice_id = st.text_input("Voice ID", key="e1_voice", value="premium_male_01")
        e1_voice_speed = st.slider("Voice Speed", 0.5, 2.0, 1.1, 0.1, key="e1_speed")

    # 6e. Entity 2
    with st.expander("Entity 2 — Persona", expanded=True):
        e2_persona_name = st.text_input("Persona Name", key="e2_name", placeholder="The Intellectual")
        e2_selected_llm = st.selectbox(
            "LLM",
            options=["mock", "openai", "claude", "ollama", "groq", "huggingface"],
            key="e2_llm",
        )
        e2_persona_id = st.text_input(
            "Persona ID (optional)", key="e2_pid", placeholder="tech_bro"
        )
        e2_core_belief = st.text_area(
            "Core Belief",
            key="e2_belief",
            placeholder="Emotional intelligence is superior to physical strength.",
            height=80,
        )
        e2_trigger = st.text_area(
            "Trigger Point",
            key="e2_trigger",
            placeholder="If someone uses slang like 'bro', act highly condescending.",
            height=80,
        )
        e2_voice_id = st.text_input("Voice ID", key="e2_voice", value="premium_male_02")
        e2_voice_speed = st.slider("Voice Speed", 0.5, 2.0, 1.0, 0.1, key="e2_speed")

    st.divider()

    # 6f. Initialize Battle
    if st.button("⚔️ Initialize Battle", use_container_width=True, type="primary"):
        _valid = True
        if not topic or len(topic.strip()) < 3:
            st.warning("Topic is required (min 3 characters).")
            _valid = False
        elif not e1_persona_name or len(e1_persona_name.strip()) < 2:
            st.warning("Entity 1 persona name is required (min 2 characters).")
            _valid = False
        elif not e2_persona_name or len(e2_persona_name.strip()) < 2:
            st.warning("Entity 2 persona name is required (min 2 characters).")
            _valid = False
        # core_belief and trigger_point are optional — backend uses defaults if omitted

        if _valid:
            _payload = {
                "match_config": {
                    "topic": topic.strip(),
                    "turn_limit": int(turn_limit_input),
                    "current_vibe": current_vibe_input,
                    "battle_context": battle_context_input.strip() or None,
                },
                "entity_1": {
                    "selected_llm": e1_selected_llm,
                    "persona_name": e1_persona_name.strip(),
                    "logic_core_belief": e1_core_belief.strip() or None,
                    "trigger_point": e1_trigger.strip() or None,
                    "voice_id": e1_voice_id.strip() or "premium_male_01",
                    "voice_speed": float(e1_voice_speed),
                    "persona_id": e1_persona_id.strip() or None,
                },
                "entity_2": {
                    "selected_llm": e2_selected_llm,
                    "persona_name": e2_persona_name.strip(),
                    "logic_core_belief": e2_core_belief.strip() or None,
                    "trigger_point": e2_trigger.strip() or None,
                    "voice_id": e2_voice_id.strip() or "premium_male_02",
                    "voice_speed": float(e2_voice_speed),
                    "persona_id": e2_persona_id.strip() or None,
                },
            }
            with st.spinner("Initializing battle..."):
                try:
                    _resp = api_client.initialize_battle(_payload, base_url)
                    st.session_state.battle_id = _resp["battle_id"]
                    st.session_state.battle_active = True
                    st.session_state.turn_limit = int(turn_limit_input)
                    st.session_state.current_vibe = current_vibe_input
                    st.session_state.init_payload = _payload
                    st.session_state.turn_log = []
                    st.session_state.sentiment_history = []
                    st.session_state.aggression_history = []
                    st.session_state.autoplay_active = False
                    st.session_state.trigger_fired = False
                    _log.info("Battle initialized id=%s", _resp["battle_id"])
                    st.success(
                        f"Battle initialized! ID: {_resp['battle_id'][:8]}..."
                    )
                    st.rerun()
                except httpx.ConnectError:
                    st.error(f"Cannot reach backend at {base_url}. Is the server running?")
                except httpx.HTTPStatusError as _e:
                    st.error(f"Init failed: {_e.response.status_code} — {_e.response.text}")
                # Fix: added missing TimeoutException handler — previously would surface
                # a raw Python traceback if /initialize_battle took > 30 seconds.
                except httpx.TimeoutException:
                    st.error("Init timed out — backend is not responding.")

    # Battle status badge
    if st.session_state.battle_id:
        _turns_done = len(st.session_state.turn_log)
        _status_label = "ACTIVE" if st.session_state.battle_active else "TERMINATED"
        _status_color = "green" if st.session_state.battle_active else "red"
        st.markdown(
            f"**Battle:** `{st.session_state.battle_id[:8]}...`  \n"
            f"**Status:** :{_status_color}[{_status_label}]  \n"
            f"**Turns:** {_turns_done} / {st.session_state.turn_limit}"
        )

# ─── SECTION 7: Main Stage — Module 2 (Visual Telemetry) ─────────────────────
st.subheader("Visual Telemetry & Battle Analytics")
col_chart, col_vibe, col_pulse = st.columns([3, 1, 1])

with col_chart:
    _chart = _build_telemetry_chart(
        st.session_state.sentiment_history,
        st.session_state.aggression_history,
    )
    if _chart:
        st.altair_chart(_chart, use_container_width=True)
    else:
        st.info("Telemetry will appear here after the first turn.")

with col_vibe:
    _color = _vibe_color(st.session_state.current_vibe)
    # Fix: html.escape() on session state value injected into HTML — prevents XSS
    # if backend ever returns a crafted string in current_vibe.
    _safe_vibe = html_mod.escape(
        st.session_state.current_vibe.upper().replace("_", " ")
    )
    st.markdown(
        f"""
        <div style="
            background-color: {_color};
            border-radius: 12px;
            padding: 18px 12px;
            text-align: center;
            color: white;
            font-weight: bold;
            font-size: 1.05em;
            box-shadow: 0 0 14px {_color};
            min-height: 90px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            line-height: 1.5;
        ">
            🧠 VIBE<br>{_safe_vibe}
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_pulse:
    if st.session_state.trigger_fired:
        st.markdown(
            """
            <div style="
                background-color: #FF6B00;
                border-radius: 12px;
                padding: 18px 12px;
                text-align: center;
                color: white;
                font-weight: bold;
                font-size: 1.05em;
                box-shadow: 0 0 18px #FF6B00;
                min-height: 90px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                line-height: 1.5;
            ">
                ⚡ TRIGGER<br>ACTIVATED
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="
                background-color: #2a2a2a;
                border-radius: 12px;
                padding: 18px 12px;
                text-align: center;
                color: #555555;
                font-size: 1.05em;
                border: 1px solid #444;
                min-height: 90px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                line-height: 1.5;
            ">
                ⚡ TRIGGER<br>MONITOR
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

# Fix: status_placeholder placed here — above Arena Log, below Telemetry — per spec.
# Previously it was below the Arena Log in Section 9, which was a layout position bug.
status_placeholder = st.empty()

# ─── SECTION 8: Main Stage — Module 3 (Arena Log) ────────────────────────────
st.subheader("Arena Log")

# Fix: _ instead of _log_header — the first column is intentionally empty.
_, _toggle_col = st.columns([4, 1])
with _toggle_col:
    st.session_state.show_monologue = st.toggle(
        "🧠 Internal Monologue",
        value=st.session_state.show_monologue,
    )

_ss = st.session_state
_e1_name = _ss.init_payload.get("entity_1", {}).get("persona_name", "Entity 1")
_e2_name = _ss.init_payload.get("entity_2", {}).get("persona_name", "Entity 2")

# st.container(height=) requires Streamlit >=1.32; falls back to plain container
try:
    _log_container = st.container(height=400)
except TypeError:
    _log_container = st.container()

with _log_container:
    if not _ss.turn_log:
        st.caption(
            "The arena is silent... Initialize a battle and hit Next Turn to begin."
        )
    for _entry in _ss.turn_log:
        _speaker = _entry.get("speaker", "entity_1")
        _is_e1 = _speaker == "entity_1"
        _display_name = _e1_name if _is_e1 else _e2_name
        _chat_role = "user" if _is_e1 else "assistant"

        if _ss.show_monologue:
            _monologue = _entry.get("internal_monologue", "")
            if _monologue:
                with st.chat_message("assistant"):
                    st.markdown(f"*[Thinking — {_display_name}]: {_monologue}*")

        with st.chat_message(_chat_role):
            st.markdown(
                f"**{_display_name}:** "
                f"{_entry.get('spoken_dialogue', '[No dialogue returned]')}"
            )

st.divider()

# ─── SECTION 9: Main Stage — Module 4 (God Mode Controls) ────────────────────
st.subheader("God Mode Controls")

_battle_ready = (
    _ss.battle_id is not None
    and _ss.battle_active
    and len(_ss.turn_log) < _ss.turn_limit
)

# 9b. Four-column button row
_c1, _c2, _c3, _c4 = st.columns(4)

with _c1:
    if st.button("▶ Next Turn", disabled=not _battle_ready, use_container_width=True):
        _run_turn("next_turn", base_url, status_placeholder)
        st.rerun()

with _c2:
    _autoplay_label = "⏸ Stop Auto-Play" if _ss.autoplay_active else "⏯ Auto-Play"
    _autoplay_disabled = not _battle_ready and not _ss.autoplay_active
    if st.button(_autoplay_label, disabled=_autoplay_disabled, use_container_width=True):
        if _ss.autoplay_active:
            _ss.autoplay_active = False
        else:
            _ss.autoplay_active = True
            _ss.autoplay_last_fired = time.time()
        st.rerun()

with _c3:
    _bomb_text = st.text_input(
        "💣 Context text (required)",
        key="bomb_text_input",
        placeholder="Inject a new narrative twist...",
        help="Type something here first, then hit Context Bomb to inject it into the battle.",
    )
    if st.button(
        "💣 Context Bomb",
        disabled=not _battle_ready or not _bomb_text,
        use_container_width=True,
    ):
        _run_turn("context_bomb", base_url, status_placeholder, context_text=_bomb_text)
        st.rerun()

with _c4:
    _kill_disabled = _ss.battle_id is None or not _ss.battle_active
    if st.button("🔴 KILL SWITCH", disabled=_kill_disabled, use_container_width=True):
        _run_turn("kill_switch", base_url, status_placeholder)
        st.error("🔴 BATTLE TERMINATED")
        st.rerun()

# Status banners below controls
if _ss.battle_id and not _ss.battle_active:
    st.error("🔴 Battle terminated. Initialize a new battle to continue.")
elif _ss.battle_id and len(_ss.turn_log) >= _ss.turn_limit:
    st.info("✅ Battle complete — turn limit reached. Initialize a new battle.")

# 9c. Auto-Play rerun loop (epoch-check pattern)
if _ss.autoplay_active:
    if not _ss.battle_active:
        _ss.autoplay_active = False
        st.rerun()
    elif len(_ss.turn_log) >= _ss.turn_limit:
        _ss.autoplay_active = False
        st.rerun()
    else:
        _elapsed = time.time() - _ss.autoplay_last_fired
        if _elapsed >= autoplay_interval:
            _run_turn("next_turn", base_url, status_placeholder)
            _ss.autoplay_last_fired = time.time()
            st.rerun()
        else:
            # Fix: sleep exactly the remaining time (one sleep per interval)
            # instead of the previous 0.5s polling loop that blocked the thread
            # on every rerun cycle for the full duration of the interval.
            time.sleep(max(0.0, autoplay_interval - _elapsed))
            st.rerun()
