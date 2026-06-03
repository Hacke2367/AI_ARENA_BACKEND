# Frontend UI Redesign — v1 Implementation Plan
### Mapping the NEXUS HUD v1 build to `creator_dashboard/app.py`

| | |
|---|---|
| **Companion to** | `docs/FRONTEND_UI_REDESIGN_SPEC.md` (blueprint + locked decisions DEC-1…4) |
| **Scope** | v1 only — pure Streamlit, **no new JS deps** (DEC-4). Hotkeys + scrubber are v1.1. |
| **Files touched** | `creator_dashboard/app.py` (major refactor) · `creator_dashboard/.streamlit/config.toml` (new) · `creator_dashboard/requirements.txt` (no change — pure Streamlit) |
| **Not touched** | `creator_dashboard/api_client.py` (data contract unchanged), backend, schemas |
| **Code skeletons** | Illustrative targets, not final code. Line numbers reference the **current** `app.py`. |

---

## 0. Approach & target structure

The current `app.py` is a flat top-to-bottom script (Sections 1–9). The redesign keeps it a **single file** but refactors the body into **mode-aware render functions** so the Setup/Live split (DEC-2) and the 3-band grid are clean and testable. No widget keys or the `_payload` build logic change meaning — they relocate.

**Target section layout of the new `app.py`:**

```
SECTION 1   Imports                              (≈ unchanged)
SECTION 2   Page config                          (≈ unchanged, lines 15-20)
SECTION 3   Theme + CSS token layer  _inject_styles()   ◀ STEP 1  (replaces lines 22-44)
SECTION 4   Session-state init                   (+ triggers_count; lines 46-65)
SECTION 5   Constants  VIBE, LLM_OPTIONS, NEON tokens dict
SECTION 6   Helpers   (existing 5 + _compute_dominance, _vibe_gauge_html,
                       _ghost_box_html, _reset_battle, _panel())
SECTION 7   _render_sidebar()                     ◀ STEP 3  (slim globals; from 233-419)
SECTION 8   _render_setup()                       ◀ STEP 3  (from 259-408, full-width)
SECTION 9   Live zones:                           ◀ STEP 2
              _render_command_bar()   (Band A, from 564-619)
              _render_combatants()    (Band B col1, NEW + 411-419)
              _render_arena_log()     (Band B col2, from 518-560)
              _render_telemetry()     (Band B col3, from 421-510)
              _render_status_rail()   (Band C, from 516)
SECTION 10  Router:  setup vs live  +  autoplay loop  (from 620-639)
```

**Session-state additions (Section 4, dict at lines 47-60):**
- `triggers_count: 0` — cumulative trigger tally for the pulse panel.
- *(derived, not stored)* `mode = "live" if st.session_state.battle_id else "setup"`.

**Verdict on render order:** Band A holds the transport buttons but Band C holds the status rail they write to. Streamlit renders top-down, so the rail placeholder must be **created before Band A**. Solution in Step 2.

---

## STEP 1 — CSS token layer + canvas reclaim + panel primitive

**Replaces:** Section 3 (lines 22-44, the Kill-Switch-only `<style>`).
**Goal:** G3 (100% width), G5 (legibility), and the visual foundation for everything else.

### 1a. Base theme — new file `creator_dashboard/.streamlit/config.toml`

Set the Streamlit *chrome* (widgets, base bg, font) so native controls match the HUD; CSS handles the rest. Illustrative:

```toml
[theme]
base = "dark"
backgroundColor       = "#07090E"   # --bg-void
secondaryBackgroundColor = "#0D1320" # --bg-panel
textColor             = "#E6F1FF"   # --text-hi
primaryColor          = "#00E5FF"   # --cyan
font                  = "monospace"
```

### 1b. `_inject_styles()` — one `st.markdown(<style>…)` call right after page config

Contents (described; all class-scoped under `.nexus-*` to prevent the CSS-bleed bug class already fixed once in this repo):

1. **Font import** — `@import` Orbitron, Rajdhani, JetBrains Mono, Inter.
2. **Token `:root`** — every hex from the spec Appendix as CSS custom properties (`--bg-void`, `--cyan`, `--crimson`, `--magenta`, …).
3. **Canvas reclaim** (the G3 fix):
   ```css
   .block-container{max-width:100% !important; padding:1rem 1.5rem 0 !important;}
   [data-testid="stHeader"]{height:0; visibility:hidden;}
   [data-testid="stVerticalBlock"]{gap:.55rem;}
   [data-testid="stHorizontalBlock"]{gap:.6rem;}
   ```
4. **Panel primitive** `.nexus-panel` — `--bg-panel`, 1px `--line-idle` border, notched corner via `clip-path`, corner ticks via `::before/::after`, faint scanline via repeating-linear-gradient, `--text-hi`. `.nexus-panel.is-active` intensifies border + adds the accent glow `box-shadow`.
5. **LEDs** `.nexus-led` + state modifiers (`.led-cyan/.led-mint/.led-amber/.led-crimson/.led-magenta/.led-off`) with the pulse keyframe.
6. **Keyframes** — `nexus-pulse` (LED breathing), `nexus-trigger-flash` (magenta full-panel decay ~1s), `nexus-scanline`, `nexus-ambient` (Step 5).
7. **Generalized Kill Switch** — keep the existing `aria-label="🔴 KILL SWITCH"` selector (lines 28-40) verbatim; it's the correct scoped pattern.

### 1c. The panel-targeting technique (Streamlit's one hard problem)

You cannot put a class directly on `st.container`. Two supported routes — **prefer the first if your Streamlit supports it:**

- **Preferred (Streamlit ≥1.39):** `st.container(key="telemetry")` emits a `.st-key-telemetry` DOM class → style `.st-key-telemetry{…}` directly. Verify version at build time (`st.__version__`).
- **Fallback (any ≥1.32):** drop a sentinel inside the container and style its parent via `:has()`:
  ```python
  def _panel(key, accent="--line-idle", active=False):
      c = st.container(border=True)
      c.markdown(f'<span class="nexus-anchor" data-k="{key}"></span>',
                 unsafe_allow_html=True)
      return c   # CSS: [data-testid="stVerticalBlockBorderWrapper"]:has(.nexus-anchor[data-k="telemetry"]) {...}
  ```
  `:has()` is supported in all current Chromium/Firefox/Safari (fine for OBS/desktop capture).

> **Risk:** `:has()` parent-selection and the `.st-key-*` class are the two load-bearing assumptions. Validate both in a 10-line spike before building Step 2.

---

## STEP 2 — Live-Mode 3-band grid + internal-scroll wells  ⚑ THE SCROLL FIX

**Consumes:** current Sections 7 (telemetry 421-510), 8 (arena log 518-560), 9 (controls 564-619), the `status_placeholder` (516), and the autoplay loop (620-639).
**Goal:** G1 (zero page scroll) + the D1 fix (transport above the fold).

### 2a. Solve render-order: create the rail placeholder first, pin it last

At the very top of the live render path, before Band A:

```python
def render_live(base_url, autoplay_interval):
    rail = st.empty()                     # created FIRST so Band A buttons can write to it
    _render_command_bar(base_url, rail)   # Band A — transport writes phase text to `rail`
    _render_band_b(base_url, rail)        # Band B — 3 columns
    _render_status_rail(rail)             # Band C — fills `rail` with latency/REC chrome
```

Then **pin the rail to the viewport bottom via CSS** so it's a true always-visible status bar regardless of its DOM position:
```css
.st-key-statusrail{position:fixed; bottom:0; left:0; right:0; z-index:90; …}
```
Bonus robustness: make the command bar `position:sticky; top:0` so any residual scroll never hides transport.

### 2b. Band A — Command Bar (relocates Section 9, lines 564-619)

```python
c_status, c_transport, c_kill = st.columns([3, 6, 2])
```
- **c_status:** connection LED + `battle_id[:8]` chip + `TURN {n}/{limit}` (mono) + vibe tag (bg = `_vibe_color`). Reuses the badge data from lines 411-419.
- **c_transport:** nested `st.columns(3)` → `▶ Next Turn` (from 577-579) · `⏯ Auto-Play` (582-590) · **Context Bomb as `st.popover`** (decouples the text field from the row — the D4 fix):
  ```python
  with bomb_col.popover("💣 Context Bomb", use_container_width=True):
      txt = st.text_input("Inject narrative twist", key="bomb_text_input")
      if st.button("Detonate", disabled=not txt):
          _run_turn("context_bomb", base_url, rail, context_text=txt); st.rerun()
  ```
- **c_kill:** the Kill Switch (609-612) alone in its column with margin → the isolated "emergency corner."

All `_run_turn(...)` calls now pass `rail` instead of `status_placeholder` (signature unchanged — it already accepts the placeholder param, lines 164-169).

### 2c. Band B — the tactical grid

```python
col1, col2, col3 = st.columns([22, 46, 32])
with col1: _render_combatants()    # Step 4/5
with col2: _render_arena_log()     # internal-scroll well
with col3: _render_telemetry()     # Step 4
```

**Internal-scroll wells (the G1 mechanism):** keep the existing `st.container(height=…)` pattern (already at lines 534-537 with its TypeError fallback). Apply fixed px heights tuned to fit one viewport:
- Arena Log well: `height≈520`.
- Telemetry chart container: `height≈240`.

For *true* viewport-fit (not fixed px), override the container height in CSS via its key: `.st-key-arenalog{height:calc(100vh - 290px) !important;}`. Recommend shipping fixed px first, then the `calc()` refinement.

### 2d. Autoplay loop (relocates 620-639)

Move verbatim to the tail of `render_live`. Logic unchanged (epoch-check, single sleep). It already calls `_run_turn(... status_placeholder)` → now `rail`.

**Exit check for Step 2:** with a 10-turn battle running, the page does not scroll at 1920×1080 or 4K; only the log well scrolls internally; Next Turn + Kill are visible without scrolling.

---

## STEP 3 — Setup ↔ Live mode split (DEC-2)

**Consumes:** current Section 6 (sidebar, 233-419).
**Goal:** G2 (zero scroll to apply settings).

### 3a. The router (new Section 10)

```python
_inject_styles()
_init_session_state()
base_url, autoplay_interval = _render_sidebar()   # globals only
if st.session_state.battle_id:
    render_live(base_url, autoplay_interval)
else:
    _render_setup(base_url)
```

### 3b. `_render_setup(base_url)` — full-width combatants matrix

Relocate the match-config inputs (261-284), both entity blocks (289-338, **expanders → plain panels**), and the Initialize button + payload build + API call (343-408) into the **main canvas**:

```python
# match-config strip
t, tl, vb = st.columns([3,1,1])  # Topic / Turn Limit / Vibe   (+ Battle Context full-width below)
# combatants matrix
e1, e2 = st.columns(2)
with e1: # name, llm, persona_id, core_belief(tall), trigger(tall), voice_id, speed
with e2: # mirror
# initialize (full-width, primary) — payload build + api_client.initialize_battle UNCHANGED
```
The `_payload` dict (357-382) and the `try/except` around `api_client.initialize_battle` (383-408) move **verbatim** — only their location changes. On success → `st.rerun()` flips the router to live.

### 3c. `_render_sidebar()` — slim to globals (resolves the §2.8/§2.9 overlap)

**Implementation decision to remove input duplication:** Setup Mode owns *all* pre-battle inputs. The sidebar holds only true runtime globals:
- **Always:** Backend URL (keep scheme validation, 248-250) · Auto-Play interval slider (253-255).
- **Live mode only:** read-only match summary (topic/vibe/turns) + the battle status badge (411-419) + a new **`🆕 New Battle`** button → `_reset_battle()`.

```python
def _reset_battle():
    for k in ("battle_id","battle_active","turn_log","sentiment_history",
              "aggression_history","autoplay_active","trigger_fired","triggers_count"):
        st.session_state[k] = _SS_DEFAULTS[k]
    st.rerun()
```

> This **knowingly diverges from `FRONTEND_TSD §Module 1`** (config-in-sidebar) per DEC-2. The divergence is logged in the spec's §2.10 / §5.

---

## STEP 4 — Component polish

### 4a. Neon palette — update `_vibe_color()` (lines 86-95)
Swap the muted hexes for the locked neon tokens:
`logical→#00E5FF · opening→#1EA7C9 · emotional→#FFB300 · heated→#FF8A00 · chaotic→#FF2A4D · cornered→#C81E3C · victory_lap→#FFD23F`, default `#2A3A4A`.

### 4b. Neural Vibe Gauge — replace `col_vibe` block (435-463)
Swap the static box for a **CSS conic-gradient ring** whose color = `_vibe_color(vibe)` and whose pulse `animation-duration` scales **inversely with current aggression** (calmer = slower breath, chaotic = fast strobe). Render via `st.markdown(unsafe_allow_html=True)`; keep the existing `html.escape()` on the vibe label (439-441) — XSS guard stays.

### 4c. Magenta Trigger Pulse — replace `col_pulse` block (465-510)
- Add `triggers_count` increment in `_run_turn` right after trigger detection (after line 224): `if ss.trigger_fired: ss.triggers_count += 1`.
- Panel applies the `.nexus-trigger-flash` keyframe (magenta `#FF3DEB`, ~1s decay) when `ss.trigger_fired`; always shows `TRIGGERS: {triggers_count}`. Distinct hue from crimson chaos per DEC-1.

### 4d. Monologue ghost-box — modify Arena Log render (550-560)
Replace the monologue `st.chat_message` (553-554) with a `_ghost_box_html(text)` markdown block: dashed `--line-idle` border, no fill, ~70% opacity, italic JetBrains Mono, `// THINKING` label. **`html.escape()` the monologue + dialogue** (new XSS guard — current code interpolates raw `spoken_dialogue` at 558-560; harden during the move).

### 4e. Telemetry chart restyle — `_build_telemetry_chart()` (100-141)
Keep the dual-axis structure; restyle: sentiment stroke `#00E5FF`, aggression `#FF2A4D`, low-alpha area fills (mint under positive sentiment), and append:
```python
.configure(background="transparent")
.configure_view(stroke=None)
.configure_axis(gridColor="#1B2430", domainColor="#1B2430", labelColor="#8A9BB0", titleColor="#8A9BB0")
```
(Altair has no native glow; the area-fill + glowing latest-point node approximate it.)

### 4f. Targeted overlays
v1: route phase text (`⏳ Processing LLM…`, `🔊 Voice Synthesizing…`, lines 184/209) into the **Band C rail** (already wired via the `rail` placeholder). Polish: add a `.nexus-scrim` CSS class over the arena-log + active entity card during the call. Keep it non-reflowing (overlay, never insert).

---

## STEP 5 — Dominance meter + ambient frame

### 5a. `_compute_dominance(turn_log) -> float` (new helper, range −100…+100)
Transparent, tunable heuristic over the **existing** per-turn telemetry (no backend change):
```
per turn: score = aggression_level * (1 + sentiment_score/200)   # composed aggression weighs more
EMA per speaker (α≈0.4):  ema_e1, ema_e2
dominance = clamp( (ema_e1 - ema_e2) / (ema_e1 + ema_e2 + 1) * 100 , -100, 100 )
```
Render in Band B col1 as a horizontal tug-of-war bar (E1 cyan ◄ marker ► E2 crimson). Pure markdown/CSS.

### 5b. Vibe-reactive ambient frame (§4.4)
A fixed full-viewport border-glow div (or styling `[data-testid="stAppViewContainer"]`) whose glow color = current vibe and whose `nexus-ambient` pulse rate scales with aggression. One markdown div + one CSS class. Zero grid cost.

---

## 6. Risks & Streamlit gotchas (validate before/while building)

| Risk | Mitigation |
|---|---|
| `:has()` parent-select / `.st-key-*` class (Step 1c) | 10-line spike first; both are the load-bearing layout assumptions. |
| `st.popover` / `st.container(height=)` need ≥1.32 | OVERVIEW pins Streamlit ≥1.32 ✓; keep the existing height `try/except` fallback (534-537). |
| `position:fixed` rail/ambient surviving `st.rerun()` | CSS is re-injected each run via `_inject_styles()` at top → stable. |
| Fixed px heights vs. real viewport | Ship px constants; offer `calc(100vh-…)` via key-targeted CSS as refinement. |
| XSS via interpolated dialogue/monologue (558-560) | `html.escape()` everything user/LLM-sourced before HTML injection (extend the pattern already at 439). |
| CSS bleed across columns (prior bug) | Scope **every** rule under `.nexus-*` / `.st-key-*`; never style bare `button`/`div`. |

---

## 7. Verification checklist

- **G1** 10-turn battle, 1080p + 4K: no page scroll; only log well scrolls; Next/Kill always visible.
- **G2** Setup Mode: all combatant + match fields + Initialize visible without scroll.
- **G3** Content spans full width; no central ribbon.
- **G4** 9:16 frame over Arena Log loses no data (DEC-3).
- **G5** Digits don't reflow on telemetry update (tabular numerals); neon legible after screen-record compression.
- **Regression** Initialize / Next / Auto-Play / Context Bomb / Kill all still hit `api_client` correctly; 409/timeout/connect handling (144-161) intact.

**Smoke test:**
```bash
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000
streamlit run creator_dashboard/app.py
# Setup → Initialize (mock LLM) → run to turn limit → trip a trigger → Kill → New Battle
```
After edits, run `graphify update .` (per CLAUDE.md) to refresh the graph.

---

## 8. Out of scope (deferred to v1.1, per DEC-4)
- Keyboard transport / hotkey layer (§4.1) — needs a key-listener component.
- Live clip-markers + turn scrubber (§4.3) — needs a custom component / `components.html`.
- Operator-switchable 9:16 crop (DEC-3 fixed Arena Log as hero for v1).
