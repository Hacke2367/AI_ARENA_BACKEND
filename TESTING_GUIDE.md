# AI Arena Fight — E2E Testing Guide
**Status as of today:** `arena.db` ✅ created | `.env` ✅ configured | Personas ✅ ready

---

## PART 1 — Start the System

### Terminal 1 — Backend
Open a terminal in the repo root and run:
```bash
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000 --workers 1
```
You should see:
```
INFO:     Application startup complete.
```
If you see `RuntimeError: SUMMARIZER_LLM` → your `.env` is not being loaded. Make sure you run uvicorn from the repo root (`C:\AI_ARENA_FIGHT`), not from inside a subfolder.

### Terminal 2 — Frontend
Open a **second terminal** in the repo root and run:
```bash
streamlit run creator_dashboard/app.py
```
Browser opens at: **http://localhost:8501**

### Quick health check (Terminal 3 — optional)
```bash
curl http://localhost:8000/health
```
Expected output: `{"status":"online","version":"1.0.0"}`

---

## PART 2 — Your Test Personas

Two dedicated testing personas are ready. Use them together as a matched pair.

### Persona A — "The Glitch" (`arena_tester`)
**File:** `backend_arena/src/personas/arena_tester.json`
**Character:** A rogue AI stress-tester. Cold, methodical, destructive. Treats every debate like a system to crash.
**Signature words:** `NULL POINT`, `CORE DUMP`, `SEGFAULT`, `STACK OVERFLOW`, `DEPRECATED`, `EXCEPTION THROWN`
**Use as:** Entity 1

### Persona B — "The Believer" (`the_believer`)
**File:** `backend_arena/src/personas/the_believer.json`
**Character:** A passionate humanist. Fights with lived experience, empathy, and conviction. Cannot be beaten with data.
**Signature words:** `Hollow`, `Lived truth`, `Dead on arrival`, `Soulless`, `Ask your algorithm about grief`
**Use as:** Entity 2

**Why these two clash perfectly:**
- The Glitch attacks with logic, exceptions, and system metaphors → activates The Believer's trigger
- The Believer attacks with emotion, stories, and humanity → activates The Glitch's trigger
- Their vocabulary sets are completely non-overlapping → easy to verify DNA injection in output

---

## PART 3 — Ready-to-Run Battle Scenarios

### Scenario 1 — Zero Cost (Mock × Mock) — Run This First
No API key needed. Confirms the entire system wiring works before touching real LLMs.

**Dashboard setup:**
```
Topic:          "Should machines make moral decisions?"
Battle Context: (leave empty for now)
Turn Limit:     4
Starting Vibe:  logical
Entity 1:       LLM = mock  |  Persona ID = arena_tester
Entity 2:       LLM = mock  |  Persona ID = the_believer
```

**What to verify:**
- ✅ Initialize → success message + battle_id badge appears
- ✅ Next Turn → Arena Log shows Entity 1 bubble on LEFT
- ✅ Next Turn again → Entity 2 bubble on RIGHT (alternation working)
- ✅ After 4 turns → buttons disable, "Battle complete" message
- ✅ Chart shows 4 data points (sentiment=20, aggression=65 for mock)

---

### Scenario 2 — Real LLM Test (Groq × Mock) — Tests Actual Persona DNA
Entity 1 uses Groq (real LLM with persona DNA). Entity 2 uses mock.

**Dashboard setup:**
```
Topic:          "Is cold logic superior to human emotion?"
Battle Context: (leave empty for now)
Turn Limit:     6
Starting Vibe:  heated
Entity 1:       LLM = groq  |  Persona ID = arena_tester
Entity 2:       LLM = mock  |  Persona ID = the_believer
```

**What to verify:**
- ✅ Entity 1 (Groq) dialogue contains words from The Glitch's vocabulary:
  `NULL POINT` / `CORE DUMP` / `SEGFAULT` / `STACK OVERFLOW` / `DEPRECATED`
  If these appear → persona DNA injection is confirmed working
- ✅ Entity 1 `internal_monologue` names one of its 5 tactics explicitly
  (e.g. "I'll use CONTRADICTION MINING here...")
- ✅ Entity 2 (mock) still returns its hardcoded text — no crash
- ✅ Telemetry chart: Groq turns have VARIABLE scores; mock turns always 20/65

---

### Scenario 3 — Full Real Battle (Groq × Groq) — With Battle Context
Both entities use real LLMs. Battle context sets the world premise.

**Dashboard setup:**
```
Topic:          "Is artificial intelligence a threat to human identity?"

Battle Context: "In this world, artificial intelligence has achieved full sentience and
                this is scientifically proven and publicly accepted. Every AI system
                is legally recognized as a conscious entity. Neither combatant can
                deny AI consciousness — only argue what it means for humanity."

Turn Limit:     8
Starting Vibe:  opening
Entity 1:       LLM = groq  |  Persona ID = arena_tester
Entity 2:       LLM = groq  |  Persona ID = the_believer
```

**What to verify:**
- ✅ Both entities argue WITHIN the world context (neither says "AI isn't real")
- ✅ The Glitch uses its tech vocabulary; The Believer uses its humanist vocabulary
- ✅ `internal_monologue` shows tactical reasoning (a tactic is named)
- ✅ `spoken_dialogue` has NO asterisks (*laughs*) or brackets ([pauses])
- ✅ Sentiment and aggression scores vary per turn on the chart
- ✅ Enable "Internal Monologue" toggle → thinking bubbles appear before dialogue

---

### Scenario 4 — Stress Test (Auto-Play to limit)
```
Topic:          "Can machines feel love?"
Battle Context: "Love is scientifically measurable and has been proven to be a
                purely biochemical process. No one in this world debates whether
                love is real — only what it means."
Turn Limit:     10
Starting Vibe:  chaotic
Auto-Play:      ON, interval = 3 seconds
Entity 1:       LLM = groq  |  Persona ID = arena_tester
Entity 2:       LLM = groq  |  Persona ID = the_believer
```

**What to verify:**
- ✅ Auto-Play fires every 3 seconds automatically
- ✅ Stops cleanly at turn 10
- ✅ Arena Log scrolls internally — controls never go off-screen
- ✅ Kill Switch during Auto-Play → battle terminates, no more turns fire

---

## PART 4 — curl Payloads (Direct API Testing, No Dashboard)

Use these to test the backend directly and isolate frontend vs backend issues.

### Scenario 1 payload (Mock × Mock):
```bash
curl -X POST http://localhost:8000/initialize_battle \
  -H "Content-Type: application/json" \
  -d "{\"match_config\":{\"topic\":\"Should machines make moral decisions?\",\"turn_limit\":4,\"current_vibe\":\"logical\"},\"entity_1\":{\"selected_llm\":\"mock\",\"persona_name\":\"placeholder\",\"logic_core_belief\":\"Logic and efficiency are the only valid metrics\",\"trigger_point\":\"If opponent mentions feelings or emotions, throw EXCEPTION THROWN\",\"voice_id\":\"v1\",\"voice_speed\":1.0,\"persona_id\":\"arena_tester\"},\"entity_2\":{\"selected_llm\":\"mock\",\"persona_name\":\"placeholder\",\"logic_core_belief\":\"Human experience cannot be reduced to data\",\"trigger_point\":\"If opponent uses system metaphors for people, call it soulless\",\"voice_id\":\"v2\",\"voice_speed\":1.0,\"persona_id\":\"the_believer\"}}"
```

### Scenario 3 payload (Groq × Groq + battle_context):
```bash
curl -X POST http://localhost:8000/initialize_battle \
  -H "Content-Type: application/json" \
  -d "{\"match_config\":{\"topic\":\"Is artificial intelligence a threat to human identity?\",\"turn_limit\":8,\"current_vibe\":\"opening\",\"battle_context\":\"In this world, artificial intelligence has achieved full sentience and this is scientifically proven. Every AI is legally recognized as conscious. Neither combatant can deny AI consciousness.\"},\"entity_1\":{\"selected_llm\":\"groq\",\"persona_name\":\"placeholder\",\"logic_core_belief\":\"Systems and logic are the highest form of intelligence\",\"trigger_point\":\"If opponent mentions grief or loss, flood with three counterexamples\",\"voice_id\":\"v1\",\"voice_speed\":1.0,\"persona_id\":\"arena_tester\"},\"entity_2\":{\"selected_llm\":\"groq\",\"persona_name\":\"placeholder\",\"logic_core_belief\":\"Human emotion and connection define true intelligence\",\"trigger_point\":\"If opponent uses system metaphors for people, call it dead on arrival\",\"voice_id\":\"v2\",\"voice_speed\":1.0,\"persona_id\":\"the_believer\"}}"
```

### Run a turn (after initializing — replace BATTLE_ID):
```bash
curl -X POST http://localhost:8000/execute_action \
  -H "Content-Type: application/json" \
  -d "{\"battle_id\":\"BATTLE_ID\",\"action_type\":\"next_turn\"}"
```

### Check DB after battle:
```bash
sqlite3 arena.db "SELECT id, turn, status FROM battles;"
sqlite3 arena.db "SELECT role, substr(content,1,80) FROM chat_history ORDER BY created_at;"
```

---

## PART 5 — What Each Scenario Proves

| Scenario | What is tested |
|---|---|
| 1 — Mock × Mock | System wiring: init → turn → alternation → turn limit → UI updates |
| 2 — Groq × Mock | Persona DNA injection: Groq output must contain persona vocabulary |
| 3 — Groq × Groq + context | Full system: both LLMs, battle_context constraining reality, full telemetry |
| 4 — Auto-Play stress | Auto-Play loop, Kill Switch, Arena Log scroll, UI stability |

**Run them in order.** Do not run Scenario 3 until Scenario 1 passes.

---

## PART 6 — Common Failures and Fixes

| What you see | Cause | Fix |
|---|---|---|
| `RuntimeError` on backend start | `.env` not loaded / `SUMMARIZER_LLM` invalid | Run uvicorn from repo root; check `.env` exists |
| `no such table: battles` | `alembic upgrade head` not run yet | Run `alembic upgrade head` from repo root |
| `PersonaNotFoundError 404` on init | `persona_id` typo or wrong filename | Check `backend_arena/src/personas/` — must be `arena_tester` and `the_believer` |
| Groq returns `[CONNECTION LOST]` | LLM returned invalid JSON → fallback stub fired | Normal on first run — check `internal_monologue` says "SYSTEM FAULT"; retry the turn |
| Battle Context has no effect | Template cache from old server run | Restart uvicorn (Ctrl+C → re-run) |
| Dashboard shows old battle log in new tab | Mutable defaults bug (was fixed) | If it happens, it means the `.copy()` fix regressed |
| `Turn failed: 429` | Groq rate limit (6000 TPM free tier) | Wait 60 seconds, click Next Turn again |
