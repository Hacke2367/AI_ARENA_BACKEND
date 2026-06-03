# Frontend UI Redesign — Design Specification Report
### Codename: **"NEXUS HUD"** — Tactical Warfare Engine for the Creator Dashboard

| | |
|---|---|
| **Document type** | UI Design Blueprint (descriptive — no implementation code) |
| **Author role** | Lead UI/UX Architect & Frontend Engineer |
| **Authoritative inputs** | `docs/FRONTEND_TSD.md`, `OVERVIEW.md`, current `creator_dashboard/app.py` + `api_client.py` |
| **Target medium** | 4K (3840×2160) screen recording → 16:9 master, 9:16 Shorts/Reels crop |
| **Theme** | Cyberpunk / high-tech terminal / Matrix tactical dashboard |
| **Status** | Blueprint for review. Do **not** implement until approved. |

---

## 0. Executive Summary & Diagnosis

### 0.1 Why the current UI scrolls (root-cause, read from `app.py`)

The redesign mandate ("excessive scrolling to apply settings ruins the workflow") is real and traceable to four concrete structural decisions in the existing build:

| # | Current behaviour (`app.py`) | Consequence |
|---|---|---|
| **D1** | Main canvas stacks **vertically**: Telemetry → `divider` → Arena Log (`height=400`) → `divider` → God Mode Controls (§7→§8→§9). | The transport buttons (**Next Turn / Kill Switch**) sit *below* a 400 px log + a chart. The creator must scroll **past the entire battle** to reach the controls they press every single turn. This is the single worst ergonomic defect. |
| **D2** | All combatant config lives in the **sidebar** as two `expanded=True` expanders, each with name + LLM + persona-id + 80 px core-belief + 80 px trigger + voice-id + speed slider. | The sidebar becomes ~1,400 px tall. Reaching the **Initialize Battle** button requires sidebar scrolling — exactly the "scroll to apply settings" pain. |
| **D3** | Default Streamlit block padding + capped content width are untouched. | On a 4K display the layout floats in a narrow central ribbon — **horizontal space is wasted** and content is forced taller (more scroll). |
| **D4** | The **Context Bomb** text field is nested *inside* a transport button column (`_c3`). | It inflates the control-row height and mixes a text input into the transport cluster, breaking the "press-to-act" rhythm. |

### 0.2 The core thesis

> **Stop scrolling by separating the two phases of the workflow in time, and laying out each phase as a fixed single-viewport grid that consumes 100% of the 4K canvas horizontally.**

Two design moves carry the entire redesign:

1. **A two-mode canvas** — *Setup Mode* (full-width combatant configuration, used once) collapses into *Live Mode* (a fixed tactical HUD, used every turn). Configuration and operation never compete for the same vertical space.
2. **A three-band Live HUD** where the transport controls are pinned to a **top command bar** (always above the fold), and the log/telemetry scroll **internally** inside fixed-height containers rather than pushing the page taller.

### 0.3 Design goals (acceptance criteria for the redesign)

| Goal | Target |
|---|---|
| **G1 — Zero page scroll in Live Mode** | All live controls, log, and telemetry fit within 100 vh at 1080p and 4K. Only the chat *body* scrolls, internally. |
| **G2 — Zero scroll to apply settings** | Every config field for a standard 2-combatant match is reachable without scrolling in Setup Mode. |
| **G3 — 100% horizontal utilization** | Content spans the full 4K width; no wasted central ribbon. |
| **G4 — Crop-safe** | A 9:16 frame drops cleanly over the Arena Log **or** the Telemetry Deck with no data loss (per `FRONTEND_TSD §3`). |
| **G5 — Recording-grade legibility** | High-contrast, layout-stable (no digit jitter), neon-on-obsidian that survives H.264 compression. |

---

## 1. Design Philosophy & Visual Language

### 1.1 The five design tenets

1. **Data density over decoration.** Every pixel reports state. Whitespace is structural (separating tactical zones), never cosmetic padding.
2. **Glow is meaning, not styling.** A panel only glows when it is *active/powered*; an LED only pulses when its subsystem is *live*. Light = signal.
3. **Color is a contract, not a palette.** Each hue maps to one backend state (`current_vibe`, aggression band, trigger event). The creator learns the language once and reads the battle peripherally.
4. **The screen is a HUD, not a webpage.** Fixed zones, notched corners, corner ticks, status rails — the operator's eyes return to the same coordinates every turn (motor-memory targeting).
5. **Stability for the lens.** Because this is recorded, nothing may reflow as numbers change. Tabular figures, reserved widths, fixed-height regions.

### 1.2 Color palette (precise hex)

**Structural / chassis** — the obsidian substrate that makes neon bloom:

| Token | Hex | Role |
|---|---|---|
| `--bg-void` | `#07090E` | App background (near-black, cool-blue undertone — never pure `#000`, which crushes and flattens on OLED capture). |
| `--bg-panel` | `#0D1320` | Raised tactical panels / boxes. |
| `--bg-inset` | `#0A0E16` | Wells: chat body, chart plot area, input fields. |
| `--line-hair` | `#1B2430` | Hairline borders, chart gridlines, dividers. |
| `--line-idle` | `#2A3A4A` | Default (unpowered) panel border. |

**Semantic / state accents** — the neon language (maps 1:1 to the `current_vibe` enum and aggression bands):

| Token | Hex | Meaning | Bound to |
|---|---|---|---|
| `--cyan` | `#00E5FF` | **Logic / nominal / primary** | vibe `logical`; sentiment line; structure; "ready" |
| `--cyan-dim` | `#1EA7C9` | Cooled logic | vibe `opening` |
| `--mint` | `#00FF9C` | **Healthy / online / positive** | connection LED; positive sentiment fill |
| `--amber` | `#FFB300` | **Caution / rising tension** | vibe `emotional`; "processing" |
| `--amber-hot` | `#FF8A00` | Escalating | vibe `heated` |
| `--crimson` | `#FF2A4D` | **Danger / aggression / stop** | vibe `chaotic`; aggression line; Kill Switch |
| `--crimson-deep` | `#C81E3C` | Pinned/desperate | vibe `cornered` |
| `--gold` | `#FFD23F` | **Triumph** | vibe `victory_lap` |
| `--magenta` | `#FF3DEB` | **Anomaly / event spike** | **Trigger Pulse** (event, see §1.4 rationale) |

**Typography ink:**

| Token | Hex | Role |
|---|---|---|
| `--text-hi` | `#E6F1FF` | Primary text (cool white — lower fatigue, more "screen" than `#FFF`). |
| `--text-mid` | `#8A9BB0` | Labels, secondary. |
| `--text-lo` | `#4A5A6A` | Ghost text, disabled, placeholder. |

**Glow recipe (token `--glow-<accent>`):** outer `0 0 12px <accent> @ 40% alpha` + tight `0 0 2px <accent>` + a 1 px inset top-highlight for the "lit screen" feel. Active panels intensify outer alpha to ~60%.

### 1.3 Color psychology & the State→Color contract

The palette is engineered around **arousal and pre-attentive salience**, not aesthetics:

- **Cyan (low arousal, high competence)** — reads as "systems nominal / in control." It anchors structure and the `logical` vibe so a calm debate *looks* calm. Cyan is the resting state of the room.
- **Amber (medium arousal, pre-attentive caution)** — the universal "attention" signal. Tension rising (`emotional`/`heated`) tints the room amber **before** the viewer reads a word — emotional foreshadowing for the edit.
- **Crimson (high arousal, danger, irreversibility)** — reserved so it *always* means "hot / aggressive / stop." Used for the `chaotic` vibe, the high-aggression band, and the Kill Switch. Because it is reserved, it never loses its alarm value.
- **Magenta (rarity = salience)** — the Trigger event. It is the *only* magenta in the system, so a trigger flash is impossible to miss even against a crimson-saturated chaotic frame.
- **Mint-green (life / connection)** — uptime, positive sentiment, "online." Biologically reads as "safe/healthy."
- **Gold (reward)** — `victory_lap` only. Scarcity makes the payoff feel earned on camera.
- **Obsidian base** — maximizes neon contrast for 4K legibility, reduces operator eye-fatigue across long recording sessions, and gives compression-friendly large flat dark fields (neon edges stay crisp through H.264).

> **Design decision — separate the Trigger channel from the Chaos channel.** The brief groups "Chaos/Trigger" under crimson. I recommend splitting them: `current_vibe = chaotic` is a *sustained state* (crimson room), while a **Trigger** is an *instantaneous event*. If both were crimson, a trigger firing during a chaotic vibe would be invisible — the most dramatic beat in the battle would vanish on camera. Magenta for the event keeps the two readable simultaneously. (See §3.6.)

### 1.4 Typography & data styling

A three-typeface system, all loaded via the CSS layer (Google Fonts `@import` in the injected style block):

| Tier | Face | Used for | Why |
|---|---|---|---|
| **Display** | **Orbitron** (logo only) / **Rajdhani** (titles, labels) | "AI ARENA" wordmark, module headers, status tags | Geometric sci-fi for the hero; condensed Rajdhani for headers buys horizontal density (more label per pixel). |
| **Mono / terminal** | **JetBrains Mono** (primary) · *Share Tech Mono* (alt "hacker" log skin) | Chat stream, telemetry numerals, battle ID, turn counter, LED captions | Machine-output legibility; superb glyph separation at 4K. |
| **Body / UI** | **Inter** | Help text, longer prose labels, tooltips | A grotesk keeps long-form readable where mono would tire the eye. |

**Critical rule — tabular numerals everywhere data changes.** Aggression %, sentiment, turn counter, latency, trigger count must use monospaced/tabular figures so digits **do not change width** as values update. This eliminates layout jitter on the recording (a "1" replacing a "4" must not shift the panel).

**Type scale (condensed for density):** hero 28–34 px · module title 15 px (uppercase, letter-spaced) · label 11–12 px (uppercase, `--text-mid`) · body 13–14 px · data readout 18–22 px (mono, semantic-colored, soft glow). Generous **letter-spacing** on uppercase labels reinforces the "terminal/military" register.

### 1.5 Border, glow, texture & icon language

- **Notched ("cut-corner") panels.** Major panels use a single clipped corner (top-left or top-right) instead of uniform rounded rectangles — instantly reads "military HUD," not "web card." Avoids the generic Streamlit look entirely.
- **Corner ticks / brackets.** Thin `⌐ ¬ L ⌐` bracket marks at panel corners (drawn in `--line-idle`, lighting to the active accent when the panel is live) — the classic targeting-reticle motif.
- **Double-line terminal frame (optional skin).** For the Arena Log, a retro double-rule border (outer hairline + inner inset line) sells the "console" feel.
- **Scanline texture.** A *very* low-opacity repeating horizontal gradient over panel surfaces for CRT grain. Kept faint enough that it neither hurts legibility nor balloons under compression.
- **Status LEDs.** Small filled dots (`●`) with a soft halo, CSS-pulsed. Color = subsystem state (see §3.2).
- **Icon/sigil set.** A thin, single-weight line set in the Lucide/Tabler register (described, not raster). Where a glyph is faster than an icon, use Unicode sigils consistent with the existing build: `⚔ ▶ ⏯ 💣 🔴 🧠 ⚡ ◢ ◣ ▮`.

### 1.6 The Container Strategy (the "no-scroll" engine)

Streamlit renders a single top-to-bottom flow with no native viewport grid; the no-scroll result is produced by **six deliberate levers**, all in the CSS-injection + container layer:

1. **Reclaim the canvas.** Override the main block container to `max-width: 100%` and strip the large default top/side padding. This alone converts the wasted 4K ribbon into full-bleed working space and removes a chunk of vertical bulk (fixes **D3**).
2. **Compress vertical rhythm.** Tighten inter-element margins and column gaps globally. Streamlit's default spacing is generous for documents and hostile to dashboards; halving it reclaims a full band of height.
3. **Fixed-height internal-scroll regions.** The Arena Log and the telemetry chart live in `st.container(height=…)` wells that scroll **inside themselves**. The page height becomes constant regardless of turn count — the structural fix for **G1**.
4. **Horizontal-first composition.** `st.columns` with explicit ratios is the primary layout primitive; vertical stacking is the exception. Nested columns build the sub-grids (transport cluster, vibe+trigger row).
5. **Panelize with bordered containers.** Each tactical zone is a `st.container(border=True)` styled via the CSS layer into a "tactical box" (§3.1). Panels — not the page — own their padding.
6. **Banish expanders from live content.** Expanders imply hidden state and re-flow; they are forbidden in Live Mode and reserved only for *optional* advanced fields in Setup Mode. The two sidebar entity expanders (**D2**) are dissolved into the Setup grid.

---

## 2. Grid Hierarchy & Layout Architecture — The "No-Scroll" Matrix

### 2.1 The headline decision: a two-mode canvas

The same screen serves two jobs that should never share vertical space:

```
        ┌─────────────────────┐        ┌─────────────────────┐
        │     SETUP MODE      │  ───▶  │      LIVE MODE      │
        │  (config, used 1×)  │ Initi- │  (operate, every    │
        │  full-width 2-col   │ alize  │   turn — fixed HUD) │
        │  Combatants Matrix  │ Battle │  3-band tactical    │
        └─────────────────────┘        └─────────────────────┘
                   ▲                              │
                   └──────  New Battle  ◀─────────┘
```

- **Setup Mode** (pre-`Initialize`): the full canvas becomes the **Combatants Matrix** — two large side-by-side entity panels with room to *breathe*, plus a Match-Config strip on top. No cramped sidebar expanders; no scrolling to reach Initialize (fixes **D2**, satisfies **G2**).
- **Live Mode** (post-`Initialize`): combatant config collapses to compact read-only **vitals cards**, and the canvas reflows to the fixed three-band HUD below. Controls move to the top (fixes **D1**, satisfies **G1**).

The **sidebar** persists across both as the lightweight **Config Matrix** (per `FRONTEND_TSD §Module 1`) holding only set-once globals (Backend URL, Auto-Play interval, Match Config) — collapsible so Live Mode can reclaim its width for the recording.

> **Deviation flag (intellectual honesty for a spec-driven repo):** `FRONTEND_TSD §Module 1` places *all* configuration — including persona deep-dive and voice — in the sidebar. This blueprint **refines** that: globals stay in the sidebar, but the heavy combatant config is promoted to a full-width Setup-Mode grid. Rationale: the sidebar is the literal source of the scroll pain the redesign exists to kill. A literal-to-spec fallback (keep config in-sidebar but swap the two stacked expanders for `st.tabs[Entity 1 | Entity 2]`, halving sidebar height) is documented in §2.10 if strict TSD conformance is preferred.

### 2.2 Live Mode — the master grid (vertical budget ≈ 100 vh)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║ BAND A · COMMAND BAR                                                  ~9 vh    ║
║ ┌───────────────┐  ┌──────────────────────────────┐  ┌──────────────────────┐ ║
║ │ ● STATUS  ⚔   │  │ ▶ NEXT  ⏯ AUTO  💣 BOMB      │  │       🔴 KILL SWITCH │ ║
║ │ TURN 04 / 10  │  │  (primary transport cluster) │  │    (pinned far-right)│ ║
║ │ VIBE: CHAOTIC │  └──────────────────────────────┘  └──────────────────────┘ ║
║ └───────────────┘                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ BAND B · TACTICAL GRID                                               ~76 vh    ║
║ ┌── COL 1 ~22% ──┐ ┌──────── COL 2 ~46% ────────┐ ┌──── COL 3 ~32% ─────────┐ ║
║ │ COMBATANTS DECK│ │      ARENA LOG  (HERO)     │ │   TELEMETRY DECK         │ ║
║ │                │ │                            │ │ ┌───────────┐ ┌────────┐ │ ║
║ │ ┌────────────┐ │ │  > ENTITY_1 ::             │ │ │ NEURAL    │ │ ⚡TRIG- │ │ ║
║ │ │ ◤ E1  ●LIVE│ │ │    "...spoken dialogue..." │ │ │ VIBE GAUGE│ │  GER   │ │ ║
║ │ │ persona    │ │ │                            │ │ │  (radial) │ │ PULSE  │ │ ║
║ │ │ LLM: ollama│ │ │  // THINKING (ghost box)   │ │ └───────────┘ └────────┘ │ ║
║ │ │ AGGR ▮▮▮▮�ய━│ │ │  > ENTITY_2 ::             │ │ ┌──────────────────────┐ │ ║
║ │ └────────────┘ │ │    "...spoken dialogue..." │ │ │ AGGRESSION /SENTIMENT │ │ ║
║ │ ┌────────────┐ │ │                            │ │ │ dual-axis line chart  │ │ ║
║ │ │ ◣ E2  ◦dim │ │ │   [internal-scroll well]   │ │ │ (cyan ▲ / crimson ▲)  │ │ ║
║ │ │ AGGR ▮▮━━━━│ │ │                            │ │ └──────────────────────┘ │ ║
║ │ └────────────┘ │ │  🧠 Monologue [toggle]     │ │ ┌──────────────────────┐ │ ║
║ │ ┌────────────┐ │ │                            │ │ │ DOMINANCE  E1◄──┼──►E2│ │ ║
║ │ │ MOMENTUM ▲ │ │ │                            │ │ └──────────────────────┘ │ ║
║ │ └────────────┘ │ └────────────────────────────┘ └──────────────────────────┘ ║
║ └────────────────┘                                                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ BAND C · STATUS RAIL   ◢ PROCESSING LLM…   ·  latency 1.8s  ·  ● REC 02:14   ~5vh║
╚══════════════════════════════════════════════════════════════════════════════╝
   [ SIDEBAR — collapsible — CONFIG MATRIX: Backend URL · Match Config · Auto-Play ]
```

Column ratios map to `st.columns([22, 46, 32])`. The vertical budget (9 / 76 / 5) is enforced by fixed-height containers so the page never exceeds one viewport (**G1**).

### 2.3 Band A — The Command Bar (Command Center)

A single full-width horizontal strip; the operator's hands live here. Three clusters, left→right by frequency-of-use and motor safety:

- **Status cluster (left):** connection LED · battle-ID chip (`a1b2…`) · **TURN 04 / 10** (mono, tabular) · live **VIBE** tag (background = the vibe's semantic color). This is the at-a-glance mission state.
- **Transport cluster (center-right):** `▶ NEXT TURN` (primary, cyan), `⏯ AUTO-PLAY` (toggles to `⏸ STOP`, amber when armed), `💣 CONTEXT BOMB`. The Context Bomb's text field is **decoupled** from the button — it opens a compact inline popover/field on demand rather than permanently inflating the bar (fixes **D4**).
- **Kill Switch (far right, isolated):** pinned to the top-right corner with a gutter of empty space around it — the universal "emergency" location, crimson-glowing, never adjacent to a routine button (prevents mis-clicks during fast play). Disabled state dims to `--crimson-deep` at 50%.

Pinning transport to the top is the structural cure for **D1**: the buttons pressed every turn are now permanently above the fold.

### 2.4 Band B · Column 1 — The Combatants Deck

In Live Mode the verbose config becomes three stacked compact panels:

- **Entity 1 vitals card** (top) and **Entity 2 vitals card** (below): persona name (display face), LLM provider badge, voice-status LED, and a live **aggression micro-bar** colored by band (cyan→amber→crimson). Sentiment shown as a small +/- mint/crimson delta.
- **Active-speaker treatment:** the entity speaking *this* turn **powers up** — border lights to its accent, LED goes solid, card brightens; the idle entity dims to ~50% opacity. The eye always knows who holds the floor (great for the edit).
- **Momentum panel** (bottom): the Dominance meter (§4.2).

A small `◷ EDIT` affordance on each card returns to Setup Mode for that entity if a mid-session change is needed — config is never *trapped*, just *out of the way*.

> Combatant config (LLM / Persona / Trigger / Voice) — the brief's "Combatants Matrix" — lives **here in Live Mode as read-only vitals** and **full-width in Setup Mode as editable panels** (§2.9). One conceptual zone, two render states.

### 2.5 Band B · Column 2 — The Arena Log (the hero)

The center column and the emotional center of every recording — engineered as the primary 9:16 crop target (**G4**).

- **Terminal chat stream** in a fixed-height internal-scroll well (`--bg-inset`, double-line frame, scanline grain). Each turn renders as a console line: a mono speaker prefix `> ENTITY_1 ::` colored by the entity's accent, a left border in the same accent, then the `spoken_dialogue`.
- **Internal Monologue** (`internal_monologue`): when the header toggle is ON, the strategic reasoning renders *above* the spoken line as a **dashed-border "ghost box"** — reduced opacity, italic mono, a `// THINKING` label, no fill — visually distinct from real dialogue so it never gets mistaken for spoken content on camera.
- **Auto-stick scroll:** the well auto-scrolls to the newest line; a manual scroll-up pauses auto-stick so the operator can read back without fighting the feed.
- **Header bar:** zone title + the `🧠 Internal Monologue` toggle (moved into the panel header, out of the floating column-row it occupies today).

### 2.6 Band B · Column 3 — The Live Telemetry Deck

The "video spice" zone (`FRONTEND_TSD §Module 2`), stacked for a clean 9:16 crop:

- **Neural Vibe Monitor (top-left):** a **radial gauge / pulse-ring** whose color = `current_vibe` accent and whose pulse *rate* rises with aggression. A glanceable "temperature of the room." (Replaces today's static colored box.)
- **Trigger Pulse (top-right):** an event indicator that **flashes magenta full-panel** and decays over ~1 s when a trigger fires, plus a persistent `TRIGGERS: n` tally (§3.6).
- **Aggression & Sentiment Tracker (middle):** the dual-axis line chart — **Sentiment in cyan** (`-100…100`), **Aggression in crimson** (`0…100`) — restyled dark: `--bg-inset` plot, `--line-hair` gridlines, glowing strokes, low-alpha area fills (mint under positive sentiment). Independent y-axes preserved.
- **Dominance meter (bottom):** the derived "who's winning" bar (§4.2).

### 2.7 Band C — The Status Rail

A thin IDE/DAW-style strip across the bottom: the **processing/synthesizing overlays** (`◢ PROCESSING LLM…`, `◢ VOICE SYNTHESIZING…` — §3.3), last LLM **latency**, provider, and the **● REC** timer + clip-marker hint (§4.3). It keeps transient system chatter out of the tactical grid so the grid never reflows.

### 2.8 The Sidebar — Config Matrix (collapsible)

Pared to set-once globals so it no longer drives scroll: **Backend URL** (with the existing scheme validation), **Match Config** (Topic, Turn Limit, Starting Vibe, Battle Context), **Auto-Play interval**. Persona/voice depth moves to Setup Mode. The sidebar is collapsible so Live Mode recording uses the full 4K width.

### 2.9 Setup Mode — the full-width Combatants Matrix

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MATCH CONFIG STRIP   Topic [______]  Turn Limit [10]  Vibe [logical ▾]         │
├───────────────────────────────────────┬──────────────────────────────────────┤
│  ◤ ENTITY 1                            │  ENTITY 2 ◢                           │
│  Persona Name [__________]             │  Persona Name [__________]            │
│  LLM [ollama ▾]   Persona ID [______]  │  LLM [claude ▾]   Persona ID [______] │
│  Core Belief  [ tall text area      ]  │  Core Belief  [ tall text area     ]  │
│  Trigger Point[ tall text area      ]  │  Trigger Point[ tall text area     ]  │
│  Voice ID [______]  Speed [●——— 1.1]   │  Voice ID [______]  Speed [●——— 1.0]  │
├───────────────────────────────────────┴──────────────────────────────────────┤
│                         [  ⚔  INITIALIZE BATTLE  ]   (full-width, primary)     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Two equal columns give each persona's belief/trigger text the room a sidebar can't — all fields visible at once, Initialize always in view (**G2**). LLM options: `mock · openai · claude · ollama · groq · huggingface`. Vibe options: the seven-state enum.

### 2.10 Module → Zone mapping (traceability to `FRONTEND_TSD`)

| `FRONTEND_TSD` Module | New zone | Notes / deviation |
|---|---|---|
| **M1 — Configuration Matrix (sidebar)** | Sidebar globals **+** Setup-Mode full-width grid | *Refined:* heavy combatant config promoted out of sidebar (see §2.1 flag). Strict fallback: keep in sidebar, replace 2 expanders with `st.tabs`. |
| **M2 — Visual Telemetry** | Band B · Col 3 (Telemetry Deck) + Vibe/Trigger | Vibe upgraded static box → radial pulse gauge; Trigger split to magenta event channel. |
| **M3 — Arena Log & Hidden Logic** | Band B · Col 2 (hero) | Monologue → dashed ghost-box; toggle relocated into panel header. |
| **M4 — God Mode Controls** | Band A (Command Bar) | *Relocated top* (the core no-scroll fix); Context Bomb field decoupled from button. |
| **§3 — 4K / 9:16 strategy** | §2.11 | Formalized as safe-zone columns. |
| **§3 — Status overlays** | Band C (Status Rail) + per-panel scrim | Centralized; non-reflowing. |

### 2.11 4K & 9:16 croppability spec

- The **Arena Log** (Col 2) and the **Telemetry Deck** (Col 3) are each sized so a **9:16 safe frame** lands inside them with margin — the two crops the brief and `FRONTEND_TSD §3` call out.
- A toggleable **9:16 safe-frame guide** (faint hairline rectangle overlay) lets the creator align OBS/Premiere crops live, then hide it for the take.
- All critical readouts sit inside the safe frame; decorative ticks/brackets may bleed to the edges (croppable without data loss).

---

## 3. Custom Component Wireframe Concept

### 3.1 The Panel primitive — the "tactical box"

Every zone is one reusable primitive so the HUD reads as a single engineered system:

```
   ◤───────────────────────────────────────────┐   ← notched top-left corner
   │ ⚔  MODULE TITLE                  ● STATUS │   ← header: sigil · title · LED
   ├───────────────────────────────────────────┤   ← hairline rule
   │                                           │
   │            ( zone content )               │   ← --bg-panel body, scanline grain
   │                                           │
   └───────────────────────────────  ◣ ──┘ ───┘   ← corner ticks; footer micro-status
```

Anatomy: notched corner + corner ticks (`--line-idle`, lighting to accent when active) · header (sigil, letter-spaced Rajdhani title, status LED) · hairline divider · body well · optional footer micro-status. **Idle** = `--line-idle` border, no glow. **Active/powered** = border + outer glow in the zone's accent. **Error** = crimson border + slow pulse.

### 3.2 Status LED system

| LED | State | Behaviour |
|---|---|---|
| `● cyan` | Idle / ready | steady, soft |
| `● mint` | Connected / nominal | steady |
| `● amber` | Processing / working | **pulsing** |
| `● magenta` | Trigger fired | one bright flash → decay |
| `● crimson` | Error / terminated | fast pulse |
| `◦ grey` | Offline / dimmed (idle entity) | flat, 40% |

LEDs appear in: Command Bar (backend connection), each entity card (turn/voice state), Status Rail (per-subsystem).

### 3.3 Processing & "Voice Synthesizing" overlays

Two complementary surfaces (replacing today's single `status_placeholder`):

1. **Per-panel scrim (targeted):** while a turn computes, the **active entity card** and the **Arena Log** show a translucent `--bg-void` scrim with a centered animated label — `◢ PROCESSING LLM…` then `🔊 VOICE SYNTHESIZING…` — in the speaker's accent, with a sweeping scanline or a marching `▮▮▮` block-cursor. The scrim is mounted on a placeholder and cleared on response. This localizes "the system is thinking" to *where* it's thinking.
2. **Global Status Rail (Band C):** mirrors the same state textually + shows latency, so the phase is legible even if a panel is cropped out of frame.

Both are **non-blocking and non-reflowing** — they overlay, never insert, so nothing below them jumps (recording-safe).

### 3.4 Chat bubble & monologue ghost-box

- **Spoken line:** mono speaker prefix `> ENTITY_1 ::` in the entity accent · accent left-border · `--text-hi` dialogue on `--bg-inset`. Entity 1 and Entity 2 carry different accents and left/right inflection for instant attribution.
- **Monologue ghost-box (toggle ON):** dashed border, no fill, ~70% opacity, italic mono, `// THINKING` tag, rendered *above* the spoken line. Visually "behind glass" — unmistakably not spoken content.

### 3.5 Telemetry chart styling

Dark plot (`--bg-inset`), `--line-hair` gridlines, **cyan Sentiment** stroke + **crimson Aggression** stroke, both with soft glow and low-alpha area fills (mint fill where sentiment > 0). Independent dual y-axes (`-100…100` / `0…100`). Latest datapoint carries a glowing node so the current value pops on camera. Tabular axis labels.

### 3.6 Vibe gauge & Trigger pulse

- **Neural Vibe Monitor:** a radial/segmented gauge filled in the active-vibe accent; a concentric **pulse ring** animates at a rate scaled to current aggression (calm cyan breathing → frantic crimson strobing). Label = the humanized vibe (`TOTAL CHAOS`, `VICTORY LAP`).
- **Trigger Pulse:** on a detected trigger, the panel **flashes magenta** edge-to-edge and decays over ~1 s (CSS keyframe), the LED flashes, and `TRIGGERS: n` increments. Distinct hue (magenta vs. crimson vibe) guarantees the beat is visible even mid-chaos (§1.3 rationale).

### 3.7 Streamlit implementation notes (descriptive — for the build phase)

- **CSS layer:** one injected `<style>` block holds the design tokens, font `@import`s, the `.block-container` width/padding override, the panel/LED/scrim classes, and keyframes. Centralizing it keeps per-element markup clean and avoids the CSS-bleed class of bug already fixed once in this codebase.
- **Panel targeting:** wrap each zone in `st.container(border=True)` and tag it (sentinel marker div / element key) so the CSS layer can style it without inline styles. Prefer structural targeting over per-button selectors (the Kill Switch `aria-label` technique already in `app.py` is the right pattern to generalize).
- **Fixed-height wells:** `st.container(height=…)` for Arena Log + chart (the no-scroll lever). Keep the existing graceful fallback for older Streamlit.
- **Overlays:** `st.empty()` placeholders for the scrims, written on action and cleared on response — same mechanism as today's `status_placeholder`, repositioned per §3.3.
- **Honest constraints:** Streamlit can't truly fix-position arbitrary regions; "no-scroll" is achieved by *fitting the budget*, not absolute positioning. Heavy custom interactivity (hotkeys, scrubber, safe-frame overlay) needs small custom components or a JS-bridge (`streamlit-shortcuts`, `components.html`). Flagged so scope is realistic.

---

## 4. Agent's Independent Recommendations

Three additions — each grounded in data the system *already* produces, and each serving the stated "fast-paced creator workflow."

### 4.1 ⌨️ Keyboard Transport — the Hotkey Command Layer

Bind the transport to keys so the operator never reaches for the mouse mid-take:

| Key | Action |
|---|---|
| `Space` | Next Turn |
| `A` | Toggle Auto-Play |
| `B` | Open Context-Bomb field |
| `M` | Toggle Internal Monologue |
| `K` / `Esc Esc` | Kill Switch (double-press guard) |

**Why:** this is the most direct possible answer to "fast-paced creator workflow" — it removes mouse travel and pointer-hunting from the recording loop entirely, and pairs perfectly with the top Command Bar. Implementable via a lightweight key-listener component. *Highest-leverage, lowest-cost recommendation.*

### 4.2 ⚖️ The Momentum / Dominance Meter

A single horizontal tug-of-war bar between Entity 1 and Entity 2, computed client-side from the per-turn `telemetry` already in `turn_log` (rolling aggression × sentiment-swing attributed to each speaker). A glowing marker slides toward whoever is "winning."

**Why:** the backend gives raw numbers; the *audience* wants a verdict. This converts telemetry into instant narrative — "E1 is dominating" — which is exactly the dramatic read that makes a debate clip compelling. Zero new backend work; pure derivation of existing data. Lives in Col 1 (operator) and/or Col 3 (audience).

### 4.3 🔴 Live Clip-Marker REC HUD + Turn Scrubber

A `● REC 02:14` timer in the Status Rail, plus a hotkey (`C`) that drops a **clip marker** (timestamp + turn # + current vibe) into an exportable list, and a thin **turn scrubber** along the bottom of the Arena Log. Clicking a turn re-highlights its telemetry datapoint and scrolls the log to it.

**Why:** the build already persists every `ExecuteActionResponse` in `turn_log` — so jump-to-turn and marker export are nearly free. This bridges live operation and post-production: the creator marks "the moment it went chaotic" *as it happens*, then the editor jumps straight to those timestamps. Directly serves the Shorts/Reels pipeline the whole product targets.

### 4.4 (Bonus) Vibe-reactive ambient frame

A thin outer glow around the entire app that tints to the `current_vibe` accent and pulses faster as aggression climbs. A peripheral, pre-attentive "temperature" cue that reads as cinematic on the recording without consuming any grid real estate — the cheapest possible "sci-fi engine" flourish.

---

## 5. Phasing & locked decisions

**Locked decisions (signed off 2026-06-01):**

| # | Decision | Effect on this spec |
|---|---|---|
| **DEC-1** | **Trigger = magenta `#FF3DEB` event channel**, separate from the crimson `chaotic` vibe. | §1.3 / §3.6 stand as written. The "Chaos/Trigger = crimson" grouping from the brief is **superseded**. |
| **DEC-2** | **Combatant config → full-width Setup Mode.** | §2.1 / §2.9 are the build target. This **knowingly refines `FRONTEND_TSD §Module 1`** (sidebar-only config); the `st.tabs` sidebar fallback in §2.10 is **dropped** (not built). |
| **DEC-3** | **Arena Log is the primary 9:16 hero.** | §2.5 / §2.11 stand. Telemetry Deck remains a secondary croppable frame; no operator-switchable crop in v1. |
| **DEC-4** | **v1 = pure Streamlit; custom components are a fast-follow (v1.1).** | The no-scroll HUD ships with **no new JS deps**. Keyboard transport (§4.1) and the turn scrubber (§4.3) defer to v1.1. The Dominance meter (§4.2) is pure-derivation and **stays in v1**. |

**Build order (per DEC-4):**

*v1 — pure Streamlit:*
1. CSS token layer + canvas reclaim (`.block-container` width/padding) + the panel primitive (§3.1).
2. Live-Mode 3-band grid with internal-scroll wells — **this is the scroll fix** (§2.2).
3. Setup ↔ Live mode split (§2.1, §2.9).
4. Component polish: neural vibe gauge, magenta trigger pulse, monologue ghost-box, targeted overlays (§3.3–3.6).
5. Dominance meter (§4.2) + vibe-reactive ambient frame (§4.4).

*v1.1 — custom components (fast-follow):*
6. Keyboard transport / hotkey layer (§4.1).
7. Live clip-markers + turn scrubber (§4.3).

---

## Appendix — Design token quick-reference

```
BG      void #07090E · panel #0D1320 · inset #0A0E16
LINES   hair #1B2430 · idle #2A3A4A
STATE   cyan #00E5FF · cyan-dim #1EA7C9 · mint #00FF9C · amber #FFB300
        amber-hot #FF8A00 · crimson #FF2A4D · crimson-deep #C81E3C
        gold #FFD23F · magenta(trigger) #FF3DEB
TEXT    hi #E6F1FF · mid #8A9BB0 · lo #4A5A6A
VIBE→   logical=cyan · opening=cyan-dim · emotional=amber · heated=amber-hot
        chaotic=crimson · cornered=crimson-deep · victory_lap=gold
CHART   sentiment=cyan · aggression=crimson · positive-fill=mint
FONTS   Orbitron(logo) · Rajdhani(titles/labels) · JetBrains Mono(data/log) · Inter(body)
```
