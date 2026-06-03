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

# ─── SECTION 3: CSS Token Layer (NEXUS HUD) ───────────────────────────────────
def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* ── fonts ──────────────────────────────────────────────────────────── */
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=Rajdhani:wght@400;600;700&family=JetBrains+Mono:ital,wght@0,400;0,600;1,400&family=Inter:wght@400;500&display=swap');

        /* ── design tokens ───────────────────────────────────────────────────── */
        :root {
          --bg-void:        #07090E;
          --bg-panel:       #0D1320;
          --bg-inset:       #0A0E16;
          --line-hair:      #1B2430;
          --line-idle:      #2A3A4A;
          --cyan:           #00E5FF;
          --cyan-dim:       #1EA7C9;
          --mint:           #00FF9C;
          --amber:          #FFB300;
          --amber-hot:      #FF8A00;
          --crimson:        #FF2A4D;
          --crimson-deep:   #C81E3C;
          --gold:           #FFD23F;
          --magenta:        #FF3DEB;
          --text-hi:        #E6F1FF;
          --text-mid:       #8A9BB0;
          --text-lo:        #4A5A6A;
        }

        /* ── canvas reclaim ──────────────────────────────────────────────────── */
        /* Remove default Streamlit ribbon → 100% horizontal use (G3) */
        .block-container {
          max-width: 100% !important;
          padding: 1rem 1.5rem 3.5rem !important; /* bottom pad reserved for Band C rail */
        }
        [data-testid="stHeader"]          { height: 0 !important; visibility: hidden !important; }
        [data-testid="stVerticalBlock"]   { gap: 0.55rem !important; }
        [data-testid="stHorizontalBlock"] { gap: 0.60rem !important; }
        /* Tighten Streamlit's default element padding for dashboard density */
        [data-testid="stVerticalBlock"] > div { padding-top: 0 !important; }

        /* ── panel primitive ─────────────────────────────────────────────────── */
        /* Applied in Steps 2-4 when .nexus-panel class is added to containers.  */
        /* Idle by default; .is-active lights the accent glow.                   */
        .nexus-panel {
          background: var(--bg-panel);
          border: 1px solid var(--line-idle);
          border-radius: 2px;
          padding: 0.75rem 1rem;
          position: relative;
          /* Notched top-left corner — the "military HUD" motif */
          clip-path: polygon(
            10px 0%, 100% 0%, 100% calc(100% - 10px),
            calc(100% - 10px) 100%, 0% 100%, 0% 10px
          );
          /* Subtle scanline grain — kept faint so it survives H.264 compression */
          background-image: repeating-linear-gradient(
            0deg,
            transparent, transparent 2px,
            rgba(255,255,255,0.011) 2px, rgba(255,255,255,0.011) 4px
          );
        }
        .nexus-panel.is-active {
          border-color: var(--panel-accent, var(--cyan));
          box-shadow:
            0 0 14px var(--panel-glow,    rgba(0,229,255,0.30)),
            inset 0 1px 0 var(--panel-glow-in, rgba(0,229,255,0.08));
        }
        /* Corner tick marks (targeting reticle motif) */
        .nexus-panel::before,
        .nexus-panel::after {
          content: '';
          position: absolute;
          width: 8px; height: 8px;
          border-color: var(--panel-accent, var(--line-idle));
          border-style: solid;
        }
        .nexus-panel::before { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
        .nexus-panel::after  { bottom: -1px; left: -1px;  border-width: 0 0 2px 2px; }

        /* ── status LEDs ─────────────────────────────────────────────────────── */
        .nexus-led {
          display: inline-block;
          width: 8px; height: 8px;
          border-radius: 50%;
          background: var(--led-color, var(--text-lo));
          box-shadow: 0 0 5px var(--led-color, var(--text-lo));
          vertical-align: middle;
          flex-shrink: 0;
        }
        .led-cyan    { --led-color: var(--cyan); }
        .led-mint    { --led-color: var(--mint); }
        .led-off     { --led-color: var(--text-lo); opacity: 0.4; box-shadow: none; }
        .led-amber   { --led-color: var(--amber);   animation: nexus-pulse 1.2s ease-in-out infinite; }
        .led-crimson { --led-color: var(--crimson); animation: nexus-pulse 0.45s ease-in-out infinite; }
        .led-magenta { --led-color: var(--magenta); animation: nexus-pulse 0.25s ease-in-out 3; }

        /* ── keyframes ───────────────────────────────────────────────────────── */
        @keyframes nexus-pulse {
          0%, 100% { opacity: 1;   box-shadow: 0 0 6px var(--led-color); }
          50%       { opacity: 0.3; box-shadow: 0 0 2px var(--led-color); }
        }
        /* DEC-1: trigger is magenta (#FF3DEB), not crimson — distinct from chaotic vibe */
        @keyframes nexus-trigger-flash {
          0%   { background-color: rgba(255,61,235,0.30);
                 box-shadow: 0 0 22px rgba(255,61,235,0.50); }
          65%  { background-color: rgba(255,61,235,0.10);
                 box-shadow: 0 0 8px  rgba(255,61,235,0.18); }
          100% { background-color: transparent; box-shadow: none; }
        }
        .nexus-trigger-active {
          animation: nexus-trigger-flash 1s ease-out forwards;
        }
        @keyframes nexus-ambient {
          0%, 100% { opacity: 0.55; }
          50%       { opacity: 1.00; }
        }

        /* ── typography globals ──────────────────────────────────────────────── */
        [data-testid="stChatMessage"] * {
          font-family: 'JetBrains Mono', 'Courier New', monospace !important;
        }
        [data-testid="stMetricLabel"] {
          font-family: 'Rajdhani', sans-serif !important;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          font-size: 0.78em !important;
        }
        [data-testid="stMarkdown"] h3,
        .stSubheader {
          font-family: 'Rajdhani', sans-serif !important;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--text-mid) !important;
          font-size: 0.85em !important;
        }
        /* Tabular numerals everywhere data changes — prevents digit-width
           jitter on 4K recording when values update each turn */
        [data-testid="stMetricValue"],
        [data-testid="stChatMessage"],
        .nexus-data {
          font-variant-numeric: tabular-nums !important;
        }

        /* ── ghost box (internal monologue) ──────────────────────────────────── */
        /* Rendered in Step 4 via _ghost_box_html(); class defined here so the   */
        /* keyframe + token inheritance is set up before it's first used.        */
        .nexus-ghost {
          border: 1px dashed var(--line-idle);
          border-radius: 2px;
          padding: 0.5rem 0.75rem;
          opacity: 0.72;
          font-family: 'JetBrains Mono', monospace;
          font-style: italic;
          font-size: 0.82em;
          color: var(--text-mid);
          margin-bottom: 0.35rem;
          background: var(--bg-inset);
        }

        /* ── kill switch — scoped aria-label selector (preserved) ────────────── */
        button[aria-label="🔴 KILL SWITCH"] {
          background-color: #CC0000 !important;
          color: white !important;
          font-weight: bold !important;
          border: none !important;
        }
        button[aria-label="🔴 KILL SWITCH"]:hover    { background-color: #990000 !important; }
        button[aria-label="🔴 KILL SWITCH"]:disabled { background-color: #660000 !important; opacity: 0.5 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_styles()

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
    "triggers_count": 0,
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
        "logical":     "#00E5FF",
        "opening":     "#1EA7C9",
        "emotional":   "#FFB300",
        "heated":      "#FF8A00",
        "chaotic":     "#FF2A4D",
        "cornered":    "#C81E3C",
        "victory_lap": "#FFD23F",
    }.get(vibe, "#2A3A4A")


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
        .mark_line(color="#00E5FF", strokeWidth=2, point=alt.OverlayMarkDef(color="#00E5FF", size=60))
        .encode(
            x=alt.X("Turn:Q", axis=alt.Axis(tickMinStep=1, title="Turn")),
            y=alt.Y(
                "Sentiment:Q",
                scale=alt.Scale(domain=[-100, 100]),
                axis=alt.Axis(title="Sentiment", titleColor="#00E5FF"),
            ),
            tooltip=[alt.Tooltip("Turn:Q"), alt.Tooltip("Sentiment:Q")],
        )
    )
    aggression_line = (
        alt.Chart(df)
        .mark_line(color="#FF2A4D", strokeWidth=2, point=alt.OverlayMarkDef(color="#FF2A4D", size=60))
        .encode(
            x=alt.X("Turn:Q"),
            y=alt.Y(
                "Aggression:Q",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(title="Aggression", titleColor="#FF2A4D"),
            ),
            tooltip=[alt.Tooltip("Turn:Q"), alt.Tooltip("Aggression:Q")],
        )
    )
    return (
        alt.layer(sentiment_line, aggression_line)
        .resolve_scale(y="independent")
        .properties(title="Aggression & Sentiment Tracker", height=220)
        .configure_view(strokeWidth=0)
        .configure_axis(
            gridColor="#1B2430",
            domainColor="#1B2430",
            labelColor="#8A9BB0",
            titleColor="#8A9BB0",
        )
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
    if ss.trigger_fired:
        ss.triggers_count += 1
    _log.debug("turn complete speaker=%s trigger_fired=%s", speaker, ss.trigger_fired)

    # Kill switch post-processing
    if action_type == "kill_switch":
        ss.battle_active = False
        ss.autoplay_active = False


def _vibe_gauge_html(vibe: str, aggression: int) -> str:
    """Animated ring: color = vibe token, pulse speed ∝ 1/aggression (Step 4b)."""
    _color = _vibe_color(vibe)
    _safe  = html_mod.escape(vibe.upper().replace("_", " "))
    _speed = max(0.5, 3.0 - (aggression / 100) * 2.5)
    _glow  = 8 + int((aggression / 100) * 18)
    return (
        f'<div style="display:flex;flex-direction:column;align-items:center;'
        f'gap:.3rem;padding:.4rem 0;">'
        f'<div style="width:68px;height:68px;border-radius:50%;'
        f'border:3px solid {_color};background:rgba(0,0,0,.35);'
        f'box-shadow:0 0 {_glow}px {_color},inset 0 0 {_glow//2}px {_color}55;'
        f'display:flex;align-items:center;justify-content:center;font-size:1.4em;'
        f'animation:nexus-pulse {_speed:.2f}s ease-in-out infinite;">'
        f'🧠</div>'
        f'<div style="font-family:Rajdhani,sans-serif;font-weight:700;'
        f'letter-spacing:.05em;font-size:.75em;color:{_color};'
        f'text-align:center;line-height:1.2;">{_safe}</div>'
        f'</div>'
    )


def _compute_dominance(turn_log: list) -> float:
    """EMA-weighted dominance: +100 = E1 winning, −100 = E2 winning (Step 5a)."""
    if not turn_log:
        return 0.0
    ema_e1 = ema_e2 = 0.0
    alpha = 0.4
    for entry in turn_log:
        tel   = entry.get("telemetry") or {}
        agg   = max(0, min(100, int(tel.get("aggression_level", 0))))
        sen   = max(-100, min(100, int(tel.get("sentiment_score", 0))))
        score = agg * (1.0 + sen / 200.0)
        if entry.get("speaker") == "entity_1":
            ema_e1 = alpha * score + (1.0 - alpha) * ema_e1
        else:
            ema_e2 = alpha * score + (1.0 - alpha) * ema_e2
    denom = ema_e1 + ema_e2 + 1e-9
    return max(-100.0, min(100.0, (ema_e1 - ema_e2) / denom * 100.0))


# ─── SECTION 5b: Live HUD Render Functions ────────────────────────────────────

def _render_combatants() -> None:
    """Band B col1 — entity vitals cards (stub; fleshed out in Step 4)."""
    ss = st.session_state
    _payload = ss.init_payload
    with st.container(border=True):
        st.markdown(
            '<p style="font-family:Rajdhani,sans-serif;font-weight:700;letter-spacing:.06em;'
            'text-transform:uppercase;color:var(--text-mid);font-size:.85em;margin:0 0 .5rem 0;">'
            '⚔ COMBATANTS</p>',
            unsafe_allow_html=True,
        )
        for _ek in ("entity_1", "entity_2"):
            _e = _payload.get(_ek, {})
            _name = html_mod.escape(_e.get("persona_name", _ek.upper()))
            _llm  = html_mod.escape(_e.get("selected_llm", "—"))
            st.markdown(
                f'<div style="border:1px solid var(--line-idle);border-radius:2px;'
                f'padding:8px 10px;margin-bottom:.4rem;background:var(--bg-inset);">'
                f'<span style="font-family:Rajdhani,sans-serif;font-weight:700;'
                f'color:var(--text-hi);">{_name}</span>'
                f'<span style="float:right;font-size:.7em;'
                f'font-family:\'JetBrains Mono\',monospace;color:var(--cyan);'
                f'background:rgba(0,229,255,.08);padding:2px 6px;border-radius:2px;">'
                f'{_llm}</span></div>',
                unsafe_allow_html=True,
            )
        if ss.battle_id:
            _done = len(ss.turn_log)
            _sc = "#00FF9C" if ss.battle_active else "#FF2A4D"
            _sl = "ACTIVE" if ss.battle_active else "TERMINATED"
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:.75em;'
                f'color:var(--text-mid);margin-top:.4rem;">'
                f'ID&nbsp;<span style="color:var(--text-hi)">{ss.battle_id[:8]}…</span><br>'
                f'<span style="color:{_sc}">{_sl}</span>&nbsp;'
                f'<span>{_done}/{ss.turn_limit} turns</span></div>',
                unsafe_allow_html=True,
            )
        # Dominance meter — derived from existing turn_log telemetry, no backend change
        if ss.turn_log:
            _dom   = _compute_dominance(ss.turn_log)
            _e1_n  = _payload.get("entity_1", {}).get("persona_name", "E1")
            _e2_n  = _payload.get("entity_2", {}).get("persona_name", "E2")
            _pct   = max(5.0, min(95.0, 50.0 + (_dom / 100.0) * 45.0))
            _mc    = "var(--cyan)" if _dom >= 0 else "var(--cyan-dim)"
            st.markdown(
                f'<div style="margin-top:.75rem;">'
                f'<div style="font-family:Rajdhani,sans-serif;font-weight:700;'
                f'letter-spacing:.05em;text-transform:uppercase;color:var(--text-lo);'
                f'font-size:.7em;margin-bottom:.25rem;">DOMINANCE</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:.68em;'
                f'font-family:\'JetBrains Mono\',monospace;margin-bottom:.2rem;">'
                f'<span style="color:var(--cyan);">{html_mod.escape(_e1_n[:12])}</span>'
                f'<span style="color:var(--cyan-dim);">{html_mod.escape(_e2_n[:12])}</span>'
                f'</div>'
                f'<div style="height:5px;background:var(--bg-inset);'
                f'border:1px solid var(--line-idle);border-radius:3px;position:relative;">'
                f'<div style="position:absolute;left:{_pct:.1f}%;top:50%;'
                f'transform:translate(-50%,-50%);width:10px;height:10px;border-radius:50%;'
                f'background:{_mc};box-shadow:0 0 6px {_mc};"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )


def _render_telemetry() -> None:
    """Band B col3 — vibe gauge, trigger pulse (DEC-1 magenta), chart."""
    ss = st.session_state
    with st.container(border=True):
        st.markdown(
            '<p style="font-family:Rajdhani,sans-serif;font-weight:700;letter-spacing:.06em;'
            'text-transform:uppercase;color:var(--text-mid);font-size:.85em;margin:0 0 .5rem 0;">'
            '📡 TELEMETRY</p>',
            unsafe_allow_html=True,
        )
        vg_col, tp_col = st.columns(2)
        with vg_col:
            _last_agg = ss.aggression_history[-1] if ss.aggression_history else 0
            st.markdown(_vibe_gauge_html(ss.current_vibe, _last_agg), unsafe_allow_html=True)
        with tp_col:
            _tc = ss.triggers_count
            if ss.trigger_fired:
                st.markdown(
                    f'<div class="nexus-trigger-active" style="border:1px solid #FF3DEB;'
                    f'border-radius:2px;padding:12px 8px;text-align:center;color:#FF3DEB;'
                    f'font-weight:700;font-size:.85em;font-family:Rajdhani,sans-serif;'
                    f'letter-spacing:.04em;min-height:64px;display:flex;'
                    f'flex-direction:column;justify-content:center;">'
                    f'⚡ TRIGGER<br><span style="font-size:.7em">FIRED · {_tc}×</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="background:var(--bg-inset);border:1px solid var(--line-idle);'
                    f'border-radius:2px;padding:12px 8px;text-align:center;'
                    f'color:var(--text-lo);font-size:.85em;font-family:Rajdhani,sans-serif;'
                    f'letter-spacing:.04em;min-height:64px;display:flex;'
                    f'flex-direction:column;justify-content:center;">'
                    f'⚡ TRIGGER<br><span style="font-size:.7em">MONITOR · {_tc}×</span></div>',
                    unsafe_allow_html=True,
                )
        _chart = _build_telemetry_chart(ss.sentiment_history, ss.aggression_history)
        if _chart:
            st.altair_chart(_chart, use_container_width=True)
        else:
            st.markdown(
                '<p style="color:var(--text-lo);font-size:.82em;text-align:center;'
                'margin-top:.75rem;">Telemetry activates after the first turn.</p>',
                unsafe_allow_html=True,
            )


def _render_arena_log() -> None:
    """Band B col2 — terminal chat stream, internal-scroll well (9:16 hero, DEC-3)."""
    ss = st.session_state
    _e1_name = ss.init_payload.get("entity_1", {}).get("persona_name", "Entity 1")
    _e2_name = ss.init_payload.get("entity_2", {}).get("persona_name", "Entity 2")
    with st.container(border=True):
        hdr, tog = st.columns([4, 1])
        with hdr:
            st.markdown(
                '<p style="font-family:Rajdhani,sans-serif;font-weight:700;letter-spacing:.06em;'
                'text-transform:uppercase;color:var(--text-mid);font-size:.85em;margin:0;">'
                '⚔ ARENA LOG</p>',
                unsafe_allow_html=True,
            )
        with tog:
            ss.show_monologue = st.toggle("🧠 Monologue", value=ss.show_monologue)
        try:
            _well = st.container(height=520)
        except TypeError:
            _well = st.container()
        with _well:
            if not ss.turn_log:
                st.caption(
                    "The arena is silent… Initialize a battle and hit Next Turn to begin."
                )
            for _entry in ss.turn_log:
                _speaker = _entry.get("speaker", "entity_1")
                _is_e1 = _speaker == "entity_1"
                _name = _e1_name if _is_e1 else _e2_name
                _role = "user" if _is_e1 else "assistant"
                if ss.show_monologue:
                    _mono = _entry.get("internal_monologue", "")
                    if _mono:
                        # XSS guard: escape both name and monologue before unsafe HTML injection
                        st.markdown(
                            f'<div class="nexus-ghost">// THINKING — '
                            f'{html_mod.escape(_name)}<br>'
                            f'{html_mod.escape(_mono)}</div>',
                            unsafe_allow_html=True,
                        )
                with st.chat_message(_role):
                    st.markdown(
                        f"**{_name}:** "
                        f"{_entry.get('spoken_dialogue', '[No dialogue returned]')}"
                    )


def _render_command_bar(base_url: str, rail) -> None:
    """Band A — status cluster + transport cluster + kill switch, pinned at top."""
    ss = st.session_state
    _battle_ready = (
        ss.battle_id is not None
        and ss.battle_active
        and len(ss.turn_log) < ss.turn_limit
    )
    with st.container(border=True):
        c_status, c_transport, c_kill = st.columns([3, 6, 2])

        with c_status:
            _color = _vibe_color(ss.current_vibe)
            _safe_vibe = html_mod.escape(ss.current_vibe.upper().replace("_", " "))
            _led_cls = (
                "led-mint" if ss.battle_active
                else ("led-crimson" if ss.battle_id else "led-off")
            )
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:.8em;'
                f'display:flex;align-items:center;gap:.5rem;padding:.2rem 0;">'
                f'<span class="nexus-led {_led_cls}"></span>'
                f'<span style="color:var(--text-mid);">TURN&nbsp;'
                f'<span style="color:var(--text-hi);font-variant-numeric:tabular-nums;">'
                f'{len(ss.turn_log):02d}</span>/{ss.turn_limit:02d}</span>'
                f'<span style="background:{_color};color:#000;font-size:.75em;'
                f'padding:2px 7px;border-radius:2px;font-family:Rajdhani,sans-serif;'
                f'font-weight:700;letter-spacing:.05em;">{_safe_vibe}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with c_transport:
            t1, t2, t3 = st.columns(3)
            with t1:
                if st.button("▶ Next Turn", disabled=not _battle_ready, use_container_width=True):
                    _run_turn("next_turn", base_url, rail)
                    st.rerun()
            with t2:
                _ap_lbl = "⏸ Stop" if ss.autoplay_active else "⏯ Auto-Play"
                _ap_dis = not _battle_ready and not ss.autoplay_active
                if st.button(_ap_lbl, disabled=_ap_dis, use_container_width=True):
                    if ss.autoplay_active:
                        ss.autoplay_active = False
                    else:
                        ss.autoplay_active = True
                        ss.autoplay_last_fired = time.time()
                    st.rerun()
            with t3:
                # Popover decouples the text field from the button row (D4 fix)
                if hasattr(st, "popover"):
                    with st.popover("💣 Bomb"):
                        _bomb_text = st.text_input(
                            "Inject narrative twist",
                            key="bomb_text_input",
                            placeholder="Inject a new narrative twist...",
                        )
                        if st.button(
                            "Detonate 💥",
                            disabled=not _battle_ready or not _bomb_text,
                            use_container_width=True,
                        ):
                            _run_turn("context_bomb", base_url, rail, context_text=_bomb_text)
                            st.rerun()
                else:
                    _bomb_text = st.text_input(
                        "💣 Context text",
                        key="bomb_text_input",
                        placeholder="Inject a new narrative twist...",
                    )
                    if st.button(
                        "💣 Context Bomb",
                        disabled=not _battle_ready or not _bomb_text,
                        use_container_width=True,
                    ):
                        _run_turn("context_bomb", base_url, rail, context_text=_bomb_text)
                        st.rerun()

        with c_kill:
            _kill_dis = ss.battle_id is None or not ss.battle_active
            if st.button("🔴 KILL SWITCH", disabled=_kill_dis, use_container_width=True):
                _run_turn("kill_switch", base_url, rail)
                st.error("🔴 BATTLE TERMINATED")
                st.rerun()


def _render_status_rail(rail) -> None:
    """Band C — thin status bar written into the pre-created rail placeholder."""
    ss = st.session_state
    _led_cls = (
        "led-mint" if ss.battle_active
        else ("led-crimson" if ss.battle_id else "led-off")
    )
    _state = "LIVE" if ss.battle_active else ("TERMINATED" if ss.battle_id else "STANDBY")
    rail.markdown(
        f'<div style="background:var(--bg-panel);border-top:1px solid var(--line-idle);'
        f'padding:5px 1.5rem;display:flex;align-items:center;gap:1.5rem;'
        f'font-family:\'JetBrains Mono\',monospace;font-size:.7em;color:var(--text-mid);">'
        f'<span><span class="nexus-led {_led_cls}"></span>&nbsp;{_state}</span>'
        f'<span style="color:var(--text-lo);">AI ARENA · NEXUS HUD v1</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_ambient_frame(vibe: str, aggression: int) -> None:
    """Fixed viewport border-glow that tints to current vibe and pulses with aggression (Step 5b)."""
    _color = _vibe_color(vibe)
    _speed = max(0.6, 3.0 - (aggression / 100) * 2.4)
    st.markdown(
        f'<style>.nexus-ambient{{border-color:{_color}40 !important;'
        f'box-shadow:inset 0 0 60px {_color}12,inset 0 0 2px {_color}30 !important;'
        f'animation:nexus-ambient {_speed:.1f}s ease-in-out infinite !important;}}</style>'
        f'<div class="nexus-ambient" style="position:fixed;inset:0;pointer-events:none;'
        f'z-index:998;border:1px solid {_color}40;"></div>',
        unsafe_allow_html=True,
    )


def render_live(base_url: str, autoplay_interval: int) -> None:
    """Orchestrates the 3-band no-scroll HUD: Band A (command) · Band B (grid) · Band C (rail)."""
    ss = st.session_state

    # Rail placeholder created FIRST — Band A transport can write status to it
    rail = st.empty()

    # ── Band A: Command Bar (transport always at top — D1 fix) ──────────────
    _render_command_bar(base_url, rail)

    # ── Band B: Tactical Grid ────────────────────────────────────────────────
    col1, col2, col3 = st.columns([22, 46, 32])
    with col1:
        _render_combatants()
    with col2:
        _render_arena_log()
    with col3:
        _render_telemetry()

    # ── Band C: Status Rail ──────────────────────────────────────────────────
    _render_status_rail(rail)

    # Vibe-reactive ambient viewport glow (Step 5b)
    _last_agg = ss.aggression_history[-1] if ss.aggression_history else 0
    _render_ambient_frame(ss.current_vibe, _last_agg)

    # Battle end-state banners
    if ss.battle_id and not ss.battle_active:
        st.error("🔴 Battle terminated. Initialize a new battle to continue.")
    elif ss.battle_id and len(ss.turn_log) >= ss.turn_limit:
        st.info("✅ Battle complete — turn limit reached. Initialize a new battle.")

    # Auto-Play rerun loop (epoch-check pattern — logic unchanged from original)
    if ss.autoplay_active:
        if not ss.battle_active:
            ss.autoplay_active = False
            st.rerun()
        elif len(ss.turn_log) >= ss.turn_limit:
            ss.autoplay_active = False
            st.rerun()
        else:
            _elapsed = time.time() - ss.autoplay_last_fired
            if _elapsed >= autoplay_interval:
                _run_turn("next_turn", base_url, rail)
                ss.autoplay_last_fired = time.time()
                st.rerun()
            else:
                time.sleep(max(0.0, autoplay_interval - _elapsed))
                st.rerun()


# ─── SECTION 6: Config — reset, sidebar globals, full-width setup grid ────────

def _reset_battle() -> None:
    """Reset all battle session state to defaults and rerun (used by New Battle)."""
    for _k in (
        "battle_id", "battle_active", "turn_log", "sentiment_history",
        "aggression_history", "autoplay_active", "trigger_fired", "triggers_count",
    ):
        _v = _SS_DEFAULTS[_k]
        st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v
    st.rerun()


def _render_sidebar() -> tuple[str, int]:
    """Slim sidebar — runtime globals only. Returns (base_url, autoplay_interval)."""
    ss = st.session_state
    with st.sidebar:
        st.markdown(
            '<p style="font-family:Orbitron,sans-serif;font-weight:700;font-size:1.1em;'
            'color:var(--cyan);letter-spacing:.1em;margin:0 0 .1rem 0;">AI ARENA</p>'
            '<p style="font-family:\'JetBrains Mono\',monospace;font-size:.68em;'
            'color:var(--text-lo);margin:0 0 .6rem 0;">NEXUS HUD v1</p>',
            unsafe_allow_html=True,
        )
        st.divider()

        base_url: str = st.text_input(
            "Backend URL",
            value="http://localhost:8000",
            placeholder="http://localhost:8000",
        )
        # URL scheme validation — prevents silent failures on malformed / dangerous URLs
        if base_url and not base_url.startswith(("http://", "https://")):
            st.error("Backend URL must start with http:// or https://")
            st.stop()

        autoplay_interval: int = st.slider(
            "Auto-Play Interval (s)", min_value=1, max_value=30, value=5, step=1
        )

        # Live-mode read-only summary + New Battle (shown only after Initialize)
        if ss.battle_id:
            st.divider()
            _topic = ss.init_payload.get("match_config", {}).get("topic", "—")
            _color = _vibe_color(ss.current_vibe)
            _safe_topic = html_mod.escape(_topic)
            _safe_vibe  = html_mod.escape(ss.current_vibe.upper().replace("_", " "))
            _sc  = "#00FF9C" if ss.battle_active else "#FF2A4D"
            _sl  = "ACTIVE"  if ss.battle_active else "TERMINATED"
            _done = len(ss.turn_log)
            st.markdown(
                f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:.74em;'
                f'color:var(--text-mid);line-height:1.9;">'
                f'<span style="color:var(--text-lo);">TOPIC</span><br>'
                f'<span style="color:var(--text-hi);">{_safe_topic}</span><br><br>'
                f'<span style="color:var(--text-lo);">VIBE&nbsp;</span>'
                f'<span style="background:{_color};color:#000;padding:1px 6px;'
                f'border-radius:2px;font-size:.88em;">{_safe_vibe}</span><br><br>'
                f'<span style="color:{_sc};">{_sl}</span>&nbsp;'
                f'<span style="color:var(--text-mid);">{_done}/{ss.turn_limit} turns</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.divider()
            if st.button("🆕 New Battle", use_container_width=True):
                _reset_battle()

    return base_url, autoplay_interval


def _render_setup(base_url: str) -> None:
    """Full-width combatants matrix — Setup Mode (DEC-2). Used before Initialize."""
    ss = st.session_state

    st.markdown(
        '<h2 style="font-family:Orbitron,sans-serif;color:var(--cyan);letter-spacing:.1em;'
        'font-size:1.25em;margin:0 0 .15rem 0;">⚔ AI ARENA</h2>'
        '<p style="font-family:\'JetBrains Mono\',monospace;font-size:.72em;'
        'color:var(--text-lo);margin:0 0 1rem 0;">CONFIGURE BATTLE · NEXUS HUD v1</p>',
        unsafe_allow_html=True,
    )

    # ── Match Config strip ────────────────────────────────────────────────────
    mc_topic, mc_limit, mc_vibe = st.columns([4, 1, 2])
    with mc_topic:
        topic = st.text_input("Topic", placeholder="Is roasting considered cyberbullying?")
    with mc_limit:
        turn_limit_input = st.number_input("Turns", min_value=2, max_value=50, value=10, step=1)
    with mc_vibe:
        current_vibe_input = st.selectbox(
            "Starting Vibe",
            options=["logical", "emotional", "chaotic", "opening", "heated", "cornered", "victory_lap"],
        )
    battle_context_input = st.text_area(
        "Battle Context (optional — shared world-premise both AIs must accept)",
        placeholder=(
            "Example: Pyaar (love) is completely normal and obvious in this world. "
            "Every person has experienced it. Neither side can deny its existence — "
            "only argue its value or effects."
        ),
        height=68,
        help=(
            "Injected into BOTH entity system prompts and stays fixed for the entire battle. "
            "Use it to define world rules or constraints both combatants must accept."
        ),
    )

    st.divider()

    # ── Combatants Matrix — side-by-side (G2 fix: all fields visible, zero scroll) ──
    e1_col, e2_col = st.columns(2)

    with e1_col:
        st.markdown(
            '<p style="font-family:Rajdhani,sans-serif;font-weight:700;letter-spacing:.06em;'
            'text-transform:uppercase;color:var(--cyan);font-size:.9em;margin:0 0 .35rem 0;">'
            '◤ ENTITY 1</p>',
            unsafe_allow_html=True,
        )
        e1_persona_name = st.text_input("Persona Name", key="e1_name", placeholder="Toxic Gym Bro")
        e1_selected_llm = st.selectbox(
            "LLM", options=["mock", "openai", "claude", "ollama", "groq", "huggingface"], key="e1_llm",
        )
        e1_persona_id = st.text_input("Persona ID (optional)", key="e1_pid", placeholder="gym_bro")
        e1_core_belief = st.text_area(
            "Core Belief", key="e1_belief",
            placeholder="People who don't lift are fundamentally weak.", height=90,
        )
        e1_trigger = st.text_area(
            "Trigger Point", key="e1_trigger",
            placeholder="If someone calls gym a waste of time, lose your temper.", height=90,
        )
        ev1, es1 = st.columns([2, 1])
        with ev1:
            e1_voice_id = st.text_input("Voice ID", key="e1_voice", value="premium_male_01")
        with es1:
            e1_voice_speed = st.slider("Speed", 0.5, 2.0, 1.1, 0.1, key="e1_speed")

    with e2_col:
        st.markdown(
            '<p style="font-family:Rajdhani,sans-serif;font-weight:700;letter-spacing:.06em;'
            'text-transform:uppercase;color:var(--cyan-dim);font-size:.9em;margin:0 0 .35rem 0;">'
            'ENTITY 2 ◢</p>',
            unsafe_allow_html=True,
        )
        e2_persona_name = st.text_input("Persona Name", key="e2_name", placeholder="The Intellectual")
        e2_selected_llm = st.selectbox(
            "LLM", options=["mock", "openai", "claude", "ollama", "groq", "huggingface"], key="e2_llm",
        )
        e2_persona_id = st.text_input("Persona ID (optional)", key="e2_pid", placeholder="tech_bro")
        e2_core_belief = st.text_area(
            "Core Belief", key="e2_belief",
            placeholder="Emotional intelligence is superior to physical strength.", height=90,
        )
        e2_trigger = st.text_area(
            "Trigger Point", key="e2_trigger",
            placeholder="If someone uses slang like 'bro', act highly condescending.", height=90,
        )
        ev2, es2 = st.columns([2, 1])
        with ev2:
            e2_voice_id = st.text_input("Voice ID", key="e2_voice", value="premium_male_02")
        with es2:
            e2_voice_speed = st.slider("Speed", 0.5, 2.0, 1.0, 0.1, key="e2_speed")

    st.divider()

    # ── Initialize Battle (full-width primary — always in view, G2) ───────────
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
                    ss.battle_id        = _resp["battle_id"]
                    ss.battle_active    = True
                    ss.turn_limit       = int(turn_limit_input)
                    ss.current_vibe     = current_vibe_input
                    ss.init_payload     = _payload
                    ss.turn_log         = []
                    ss.sentiment_history  = []
                    ss.aggression_history = []
                    ss.autoplay_active  = False
                    ss.trigger_fired    = False
                    ss.triggers_count   = 0
                    _log.info("Battle initialized id=%s", _resp["battle_id"])
                    st.success(f"Battle initialized! ID: {_resp['battle_id'][:8]}…")
                    st.rerun()
                except httpx.ConnectError:
                    st.error(f"Cannot reach backend at {base_url}. Is the server running?")
                except httpx.HTTPStatusError as _e:
                    st.error(f"Init failed: {_e.response.status_code} — {_e.response.text}")
                except httpx.TimeoutException:
                    st.error("Init timed out — backend is not responding.")


# ─── SECTION 7: Router — Setup Mode ↔ Live Mode ──────────────────────────────
base_url, autoplay_interval = _render_sidebar()
if st.session_state.battle_id:
    render_live(base_url, autoplay_interval)
else:
    _render_setup(base_url)
