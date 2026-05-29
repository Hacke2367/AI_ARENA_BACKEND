# Test Strategy — Creator Dashboard (`creator_dashboard/app.py`)
**Generated:** 2026-05-20
**Source:** CODE_REVIEW.md (14 fixed issues) + `llm_router.py` + `app.py` + `api_client.py` direct analysis

---

## Summary

The dashboard has 4 interaction flows (Next Turn, Auto-Play, Context Bomb, Kill Switch) and 3 visual modules (Telemetry Chart, Vibe Monitor, Trigger Pulse). The CODE_REVIEW identified 5 production blockers that were fixed — those fixes need direct test verification. The biggest testing challenge is the Streamlit rerun model and session state behaviour. **All tests below can be run with zero API cost using the Mock adapter or Groq's free tier.**

---

## Zero-Cost Test Setup (Read This First)

### Option A — Both Entities Mock (Fastest, No Setup Required)
```
Entity 1: selected_llm = "mock"
Entity 2: selected_llm = "mock"
```
Mock returns instantly: `sentiment_score: 20`, `aggression_level: 65` every turn.
No API key needed. Use this for all functional, edge case, and stress tests.

### Option B — Mock + Groq Free Tier (Real LLM, No Credit Card)
```
Entity 1: selected_llm = "mock"
Entity 2: selected_llm = "groq"   ← free tier, no card needed
```
Setup: Go to console.groq.com → Create account → API Keys → Copy key → add to `.env`:
```
GROQ_API_KEY=gsk_xxxx
GROQ_MODEL=llama-3.1-8b-instant    ← 6000 tokens/min free, no billing required
```
Use this to test asymmetric LLM behaviour (mock vs real output format).

### Option C — Both Groq (Two Real LLMs, Zero Cost)
```
Entity 1: selected_llm = "groq"
Entity 2: selected_llm = "groq"
```
Same key, same model — tests real persona prompting and actual JSON output from LLM.
Rate limit: 6000 TPM free tier → enough for 10 turns before throttling.

### Option D — Ollama (Local, Completely Free, Needs GPU/CPU)
```
# Install Ollama: https://ollama.ai
ollama pull llama3
# Add to .env:
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
Entity 1 + 2: selected_llm = "ollama"
```
Runs 100% locally. Slow on CPU (2-3 min/turn), fast on GPU.

---

## Start Backend Before Testing
```bash
# Terminal 1 — Backend
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend  
streamlit run creator_dashboard/app.py
```

---

## 1. Happy Path Tests ✅

These verify the complete golden flow works end-to-end.

**HP-01 — Full battle with both entities as mock**
```
Setup: backend running, both entities set to "mock"
Topic: "Is Python better than JavaScript?"
Turn Limit: 4, Vibe: "logical"

Steps:
1. Fill sidebar → click "Initialize Battle"
Expected: st.success "Battle initialized! ID: xxxxxxxx..."
          battle_id badge appears in sidebar
          God Mode buttons (Next Turn, Auto-Play) become enabled

2. Click "Next Turn"
Expected: Arena Log shows entity_1's bubble: "Is that really your best shot?..."
          Telemetry chart appears with 1 data point: sentiment=20, aggression=65
          Entity_1 bubble on LEFT (user role)

3. Click "Next Turn" again
Expected: entity_2's bubble appears on RIGHT (assistant role)
          Chart has 2 points
          Entity alternation: entity_1 spoke Turn 0, entity_2 speaks Turn 1

4. Run 2 more turns until turn_limit=4 reached
Expected: Next Turn + Auto-Play buttons DISABLED
          "Battle complete — turn limit reached" info message shows
```

**HP-02 — Internal Monologue toggle**
```
After HP-01: turn on "Internal Monologue" toggle
Expected: Each bubble gets a grey italic "[Thinking — Entity Name]: Scanning opponent..." 
          line BEFORE the spoken dialogue bubble
Turn OFF toggle:
Expected: ALL thinking bubbles disappear instantly from Arena Log
```

**HP-03 — Auto-Play completes a full battle**
```
New battle: turn_limit=3, both entities mock
Click "Auto-Play" (interval=1s)
Expected:
  - 3 turns fire automatically (1s apart)
  - After turn 3, Auto-Play stops itself
  - Buttons disable, "Battle complete" message shows
  - No crash, no extra turns beyond limit
```

**HP-04 — Context Bomb works**
```
New battle: turn_limit=10, both entities mock
Leave 1 turn run first (Next Turn)
Type "The audience is booing entity_1 loudly" in Context Bomb input
Click "💣 Context Bomb"
Expected:
  - API call fires with action_type: "context_bomb" AND context_text provided
  - Response appears in Arena Log (same bubble format as normal turn)
  - Chart gets a new data point
```

**HP-05 — Kill Switch terminates active battle**
```
New battle, run 2 turns via Auto-Play
While Auto-Play is ON, click "🔴 KILL SWITCH"
Expected:
  - Auto-Play stops (no more turns fire)
  - "BATTLE TERMINATED" error banner shows
  - Next Turn + Auto-Play buttons disabled
  - Kill Switch button itself becomes disabled
```

**HP-06 — Vibe Monitor shows correct color per vibe**
```
Initialize 7 separate battles, each with a different starting_vibe:
  logical    → tile color: #4A90D9 (Cool Blue)
  opening    → tile color: #4A90D9 (Cool Blue)
  emotional  → tile color: #E8A838 (Amber)
  heated     → tile color: #E8A838 (Amber)
  chaotic    → tile color: #E84040 (Glowing Red)
  cornered   → tile color: #E84040 (Glowing Red)
  victory_lap→ tile color: #D4AF37 (Gold)
Expected: Right-click VIBE tile → Inspect Element → background-color matches
```

---

## 2. Edge Cases ⚠️

**EC-01 — Mock vs Groq asymmetric battle (both LLMs behave differently)**
```
Entity 1: mock   → returns hardcoded JSON instantly
Entity 2: groq   → returns real LLM output with variable format

Run 4 turns
Expected:
  - Turn 0 (entity_1/mock): dialogue = "Is that really your best shot?..."
  - Turn 1 (entity_2/groq): dialogue = actual LLM response
  - Chart: mock turns always score 20/65; groq turns have variable scores
  - If groq returns invalid JSON → _FALLBACK_STUB kicks in → "[CONNECTION LOST]" dialogue
  - No crash in either case
```

**EC-02 — Cross-session state isolation (mutable defaults fix verification)**
```
This is the critical bug that was fixed. Verify the fix holds:

Browser 1: Open http://localhost:8501
  → Initialize battle → run 3 turns
  → Arena Log shows 3 entries

Browser 2 (new tab / incognito): Open http://localhost:8501
  → Expected: Arena Log is EMPTY (shows "The arena is silent...")
  → Expected: battle_id shows None (no badge), all buttons disabled

If Browser 2 shows Browser 1's turns → mutable defaults bug is back
```

**EC-03 — turn_limit boundary: exactly 0 and 1 turns remaining**
```
Initialize: turn_limit=2
Run 1 turn:
  Expected: Next Turn still ENABLED (1 turn remaining)
Run 2nd turn:
  Expected: Next Turn + Auto-Play DISABLED immediately
  Expected: "Battle complete" message appears
  Expected: clicking Next Turn (if somehow active) shows no API call
```

**EC-04 — Context Bomb button disabled when text is empty**
```
Initialize a battle
Look at Context Bomb column
Expected: "💣 Context Bomb" button is DISABLED (greyed out)
Type something in the context input field
Expected: button becomes ENABLED
Clear the text field
Expected: button is DISABLED again

Try to force-enable via browser devtools and click:
  Should not fire API call (disabled attribute check is server-side guarded)
```

**EC-05 — Auto-Play with 30-second interval**
```
Initialize battle: turn_limit=4, autoplay_interval=30s
Click Auto-Play
Expected:
  - First turn fires immediately (last_fired was 0.0, elapsed >= 30)
  - Second turn fires ~30 seconds later
  - Dashboard does NOT freeze during the 30s wait (sleep is capped to remaining time)
  - Kill Switch works during the wait (within 30s response time)
```

**EC-06 — Groq free tier rate limit hit (429 response)**
```
Setup: Entity 1 + 2 = groq, turn_limit=20, interval=1s
Run Auto-Play
When Groq 429 fires (after ~6000 tokens):
  Expected: api_client retry logic kicks in (2 retries with backoff: 1s, 2s)
  Expected: if still failing → st.error shows "Turn failed: 429 — ..." 
  Expected: Auto-Play STOPS (autoplay_active=False)
  Expected: No crash
```

**EC-07 — TTS Sanitization visible in tts_ready_text (backend verification)**
```
With Groq entity: watch for LLM outputting *laughs* or [pauses]
In the actual /execute_action response JSON:
  spoken_dialogue may contain: "*laughs* You think that's logic?"
  tts_ready_text MUST be: "You think that's logic?"

Test: After a groq turn, check browser network tab → /execute_action response
  → spoken_dialogue vs tts_ready_text comparison
```

**EC-08 — Persona ID loads DNA correctly**
```
Entity 1: selected_llm=groq, persona_id=gym_bro (leave other fields minimal)
Entity 2: selected_llm=mock, persona_id=tech_bro

Initialize battle
Expected: 200 OK (persona files exist → _enrich_with_persona loads them)
Run 1 groq turn
Expected: dialogue reflects gym_bro persona vocabulary and tactics
          (words like "beta", "gains", physical strength references)
```

**EC-09 — Non-existent persona_id**
```
Entity 1: persona_id="ghost_persona" (file does not exist)
Click Initialize Battle
Expected: st.error "Init failed: 404 — Persona 'ghost_persona' not found"
Expected: battle_id stays None, buttons stay disabled
```

---

## 3. Negative Tests ❌

**NT-01 — Backend not running**
```
Stop the backend (Ctrl+C on uvicorn)
Click Next Turn in the dashboard
Expected: st.error "Cannot reach backend at http://localhost:8000. Is the server running?"
Expected: No Python traceback visible to user
Expected: Arena Log unchanged (no empty entry appended)
```

**NT-02 — Init with empty topic field**
```
Leave Topic blank, fill everything else
Click "Initialize Battle"
Expected: st.warning "Topic is required (min 3 characters)."
Expected: No API call made (network tab should show NO /initialize_battle request)
```

**NT-03 — Init with core_belief < 10 characters**
```
Entity 1 core belief: "short"  (5 chars — backend requires min 10)
Click Initialize Battle
Expected: st.warning "Entity 1 core belief must be at least 10 characters."
Expected: Validated client-side before API call
```

**NT-04 — Backend URL without http:// prefix**
```
Change Backend URL to: "localhost:8000"  (missing scheme)
Expected: st.error "Backend URL must start with http:// or https://"
Expected: st.stop() fires — rest of page does NOT render
```

**NT-05 — Context Bomb with only whitespace**
```
Type "   " (spaces only) in the context bomb input
Expected: button should remain DISABLED
          (empty string after strip → falsy → disabled=True)
```

**NT-06 — Click Kill Switch on already-terminated battle**
```
Terminate battle via Kill Switch
Expected: Kill Switch button is DISABLED (battle_active=False)
Expected: Cannot click it again — no duplicate kill call
```

**NT-07 — XSS via crafted vibe (security fix verification)**
```
This test verifies the html.escape() fix from CODE_REVIEW.

In browser console, manually set session state (if possible):
  OR: modify backend mock to return current_vibe = '</div><img src=x onerror=alert(1)>'
  
Expected: The Vibe Monitor tile shows literal text: "</DIV><IMG SRC=X ONERROR=ALERT(1)>"
Expected: NO alert popup — html.escape() converted < > into &lt; &gt;
Expected: No XSS execution
```

**NT-08 — Groq API key invalid**
```
Set GROQ_API_KEY=invalid_key in .env, restart backend
Entity 2: groq
Run Next Turn
Expected: st.error "Turn failed: 502 — LLM authentication failed"
          (LLMAuthError → HTTP 502 from routes.py → displayed in dashboard)
```

---

## 4. Stress Tests 🔥

**ST-01 — Maximum turn_limit (50 turns) with mock**
```
Initialize: turn_limit=50, both mock, auto_play_interval=1s
Click Auto-Play, let it run to completion
Expected:
  - All 50 turns complete without crash
  - Arena Log scrolls internally (doesn't push controls off screen)
  - Telemetry chart renders 50 data points without freeze
  - Total runtime: ~50-55 seconds (1s interval)
  - Final state: buttons disabled, "Battle complete" shows
```

**ST-02 — Rapid manual Next Turn clicks (double-click race)**
```
Initialize battle (mock)
Double-click "Next Turn" very fast (before rerun completes)
Expected:
  - Only ONE API call fires per click (Streamlit button is stateful)
  - Turn count increments by 1, not 2
  - No duplicate entries in Arena Log
```

**ST-03 — Kill Switch during Auto-Play mid-sleep**
```
Auto-Play interval=10s
Start Auto-Play, wait for first turn to complete
IMMEDIATELY click Kill Switch during the 10s sleep wait
Expected: Auto-Play stops within 10s (bounded by sleep duration)
          Next turn does NOT fire after Kill Switch
```

**ST-04 — Memory compression trigger (13 turns)**
```
Initialize: turn_limit=20, ARENA_MAX_HISTORY_TURNS=6 (in .env), both entities groq or mock
Run 13 turns
Expected:
  - After turn 13, oldest 2 history rows get summarized
  - battle_memory table has a non-empty summary_text
  - Subsequent turns include "[LONG-TERM MEMORY]" in the system prompt
  Verify via: sqlite3 arena.db "SELECT summary_text FROM battle_memory;"
```

**ST-05 — Large context bomb text (near 2000 char limit)**
```
Initialize battle
Paste a 1950-character string into the context bomb input
Click Context Bomb
Expected: API accepts it (backend limit is max_length=2000)
Now paste a 2100-character string
Expected: Backend returns 422 Validation Error → st.error "Turn failed: 422 — ..."
          (backend Pydantic constraint catches it, not frontend)
```

---

## 5. Test Material 🗂️

### Payloads (copy-paste ready)

**Minimal mock battle (fastest test)**
```json
{
  "match_config": {"topic": "Is Python better than JavaScript?", "turn_limit": 4, "current_vibe": "logical"},
  "entity_1": {"selected_llm": "mock", "persona_name": "Mock E1", "logic_core_belief": "Testing is important for quality software", "trigger_point": "If opponent mentions testing, go aggressive", "voice_id": "v1", "voice_speed": 1.0},
  "entity_2": {"selected_llm": "mock", "persona_name": "Mock E2", "logic_core_belief": "Production code should have zero bugs always", "trigger_point": "If opponent says 'mock', challenge their approach", "voice_id": "v2", "voice_speed": 1.0}
}
```

**Groq + Mock asymmetric battle**
```json
{
  "match_config": {"topic": "Should AI replace human developers?", "turn_limit": 6, "current_vibe": "heated"},
  "entity_1": {"selected_llm": "groq", "persona_name": "Gym Bro Dev", "logic_core_belief": "Real programmers don't use AI tools, they write everything by hand", "trigger_point": "If someone mentions Claude or ChatGPT, lose it", "voice_id": "v1", "voice_speed": 1.1, "persona_id": "gym_bro"},
  "entity_2": {"selected_llm": "mock", "persona_name": "AI Evangelist", "logic_core_belief": "AI is just a tool that amplifies human intelligence", "trigger_point": "If someone dismisses AI, cite three studies", "voice_id": "v2", "voice_speed": 1.0}
}
```

**Both Groq — real persona battle**
```json
{
  "match_config": {"topic": "Is hustle culture toxic?", "turn_limit": 8, "current_vibe": "opening"},
  "entity_1": {"selected_llm": "groq", "persona_name": "Crypto Hustler", "logic_core_belief": "Sleep is for the weak, grind 18 hours a day or fail", "trigger_point": "If someone mentions work-life balance, mock them mercilessly", "voice_id": "v1", "voice_speed": 1.2, "persona_id": "crypto_hustler"},
  "entity_2": {"selected_llm": "groq", "persona_name": "Wellness Coach", "logic_core_belief": "Sustainable performance requires rest and boundaries", "trigger_point": "If someone glorifies exhaustion, challenge with science", "voice_id": "v2", "voice_speed": 0.9}
}
```

### curl Verification Commands (while dashboard is running)
```bash
# Verify backend health
curl http://localhost:8000/health

# Initialize a mock battle directly (bypasses dashboard)
curl -X POST http://localhost:8000/initialize_battle \
  -H "Content-Type: application/json" \
  -d '{"match_config":{"topic":"Test","turn_limit":4,"current_vibe":"logical"},"entity_1":{"selected_llm":"mock","persona_name":"E1","logic_core_belief":"Test belief entity one","trigger_point":"Test trigger point here","voice_id":"v1","voice_speed":1.0},"entity_2":{"selected_llm":"mock","persona_name":"E2","logic_core_belief":"Test belief entity two","trigger_point":"Test trigger point two","voice_id":"v2","voice_speed":1.0}}'

# Run a turn (replace BATTLE_ID)
curl -X POST http://localhost:8000/execute_action \
  -H "Content-Type: application/json" \
  -d '{"battle_id":"BATTLE_ID","action_type":"next_turn"}'

# Check DB memory compression after 13+ turns
sqlite3 arena.db "SELECT battle_id, length(summary_text), last_summarized_turn FROM battle_memory;"
```

### .env File for Testing
```
ARENA_DB_PATH=./arena.db
SUMMARIZER_LLM=groq
ARENA_SUMMARY_MAX_WORDS=150
ARENA_MAX_HISTORY_TURNS=6
GROQ_API_KEY=gsk_your_key_here     ← from console.groq.com (free, no card)
GROQ_MODEL=llama-3.1-8b-instant
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

## 6. Priority Order

### 🔴 Do First (Critical — Code Review Fixes Verification)

1. **EC-02 — Cross-tab session isolation** — This was the critical data leakage bug. Must verify the `.copy()` fix works: two browser tabs should see independent session state. (CODE_REVIEW fix #1)

2. **NT-01 — Backend not running** — Most common real-world failure mode. Verify `ConnectError` shows the right message, not a traceback. (CODE_REVIEW fix: specific exception handling)

3. **HP-03 — Auto-Play completes correctly** — Verifies the epoch-check + `st.rerun()` pattern; also verifies the removed `time.sleep(0.5)` loop doesn't cause regressions. (CODE_REVIEW fix #4)

4. **HP-01 — Full mock battle end-to-end** — The single most important test. If this doesn't work, nothing else matters. Run before any other test.

5. **NT-07 — XSS escape verification** — Security fix must be confirmed. Manually check the Vibe Monitor renders as HTML-escaped text when given special characters. (CODE_REVIEW fix #5)

### 🟡 Do Next (Important — LLM Integration)

6. **EC-01 — Mock + Groq asymmetric** — First real LLM test; confirms routing, JSON parsing, and fallback stub all work with actual LLM output.

7. **EC-06 — Groq 429 rate limit** — Auto-Play can trigger rate limits quickly. Must confirm api_client retry logic fires and Auto-Play stops gracefully.

8. **HP-04 — Context Bomb** — Second most used feature after Next Turn. Needs context_text validation + response rendering test.

9. **EC-08 — Persona ID DNA loading** — Groq + gym_bro persona should produce noticeably different output than Groq without persona. Real-world persona fixture test.

10. **NT-08 — Invalid Groq API key** — Verify LLMAuthError → HTTP 502 → st.error chain works end-to-end.

### 🟢 If Time Permits (Nice to Have)

11. **ST-01 — 50-turn stress test with mock** — Confirm no memory leak or UI freeze over a full battle.

12. **EC-07 — TTS sanitization in network response** — Inspect actual response body to verify tts_ready_text strips action tags.

13. **ST-04 — Memory compression at 13 turns** — Verify summariser fires and battle_memory table gets populated. Needs Groq for summariser.

14. **EC-09 — Non-existent persona_id → 404** — Error path that's easy to miss in manual testing.

15. **HP-06 — All 7 vibe colors** — Visual check; quick but gives confidence in CSS.
