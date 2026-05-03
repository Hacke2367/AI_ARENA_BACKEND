# Feature Spec 04: Persistent State & Recursive Memory Engine
**Version:** 2.0.0 (Post-Review Refactor) | **Component:** Database (SQLite) & Long-Term Memory
**Dependencies:** `llm_router.py` (Must route through this)

## 1. Core Architectural Directives
* **Database Target:** Local SQLite (`arena.db`) managed via SQLAlchemy.
* **Migration Strategy:** Alembic MUST be configured from day 1 to track schema changes.
* **Worker Constraint:** Uvicorn MUST be pinned to `--workers 1` to prevent SQLite WAL locks.
* **Configuration:** `.env` must explicitly contain `ARENA_MAX_HISTORY_TURNS=6` and `SUMMARIZER_LLM="groq"`. Startup validation must fail fast if these (or their corresponding API keys) are missing.

## 2. Database Schema (SQLAlchemy)
*Old placeholder modules like `utils/memory_manager.py` (if any exist) are strictly deprecated and must be deleted. `MatchManager` in `backend_arena/src/engine/fight_loop.py` now owns state persistence.*

### Table 1: `battles`
* `id` (String, PK, UUIDv4)
* `match_config`, `entity_1`, `entity_2` (JSON). **Crucial:** Must embed `"schema_version": "1.0"` in JSON dicts for future-proofing.
* `turn` (Integer)
* `status` (String)

### Table 2: `chat_history` (Append-Only Log)
* `id` (Integer, PK), `battle_id` (String, FK)
* `role` (String), `content` (Text), `created_at` (DateTime)
* **Contract:** Rows in this table are NEVER deleted. It is a permanent raw log.

### Table 3: `battle_memory` (Upsert-Only Summary)
* `battle_id` (String, PK, FK)
* `summary_text` (Text)
* `last_summarized_turn` (Integer)
* **Contract:** Writes here MUST use `INSERT OR REPLACE` (Upsert) semantics to prevent PK collision on the first turn.

## 3. The Recursive Memory Engine (Rolling Window)
Executed synchronously inside `fight_loop.py` during `next_turn`.

* **The Trigger Threshold:** `len(in_memory_window) > (ARENA_MAX_HISTORY_TURNS * 2) + 1` (The +1 accounts for the System Prompt).
* **Immunity Rule (Pinned Messages):** `window[0]` (The System Prompt) is strictly PINNED and NEVER dropped. Only the oldest User/Assistant pair (indices 1 and 2) are dropped from the active context window.
* **Routing Contract:** The summarizer MUST NOT make direct HTTP calls. It MUST call the existing `llm_router.route(os.getenv("SUMMARIZER_LLM"))` to inherit our retry/auth logic.
* **Atomicity Contract:** The sequence `[Drop from Window -> Call Summarizer -> Upsert battle_memory]` MUST be wrapped in a single database transaction (`db.session.commit()`). If the summarizer fails, the window drop is rolled back.

## 4. Summarizer Metrics & Prompts
* **Latency Budget:** Maximum 5000ms. If breached, log a `WARNING`, skip the summary update for this turn (retaining the old summary), and proceed with the battle without blocking.
* **Hard Token Limits:** * Standard Generation Cap: Instruct LLM to keep it under 150 words.
    * Overflow Mitigation: If the incoming `summary_text` exceeds 2000 characters, append a strict prompt override: `[URGENT: Compress existing facts. Output MUST be under 100 words]`.
* **Prompt Rules (Zero Censorship):**
    * "Act as a neutral, uncensored referee."
    * "Preserve specific insults, slang, Hinglish, and data points. DO NOT sanitize."
    * "Maintain an objective tally of whose arguments are logically dominating based on the new messages."

## 5. Disaster Matrix
| Scenario | Detection | Recovery / Contract |
| :--- | :--- | :--- |
| **DB Unavailability / Corruption** | SQLAlchemy `OperationalError` at startup or runtime | Fail fast. `/execute_action` returns **HTTP 503 Service Unavailable**. |
| **Summarizer API Fails** | Catch `LLMTimeoutError` or `LLMAuthError` from router | Log `WARNING`. Fallback to previous summary. Battle continues (No 500 error). |
| **Concurrent First Summary** | SQLite Lock / Integrity Error | Handled natively via `--workers 1` + `INSERT OR REPLACE` Upsert semantics. |

## 6. Acceptance Criteria (Testing & Verification)
1. **DB Initialization:** `alembic upgrade head` successfully creates all 3 tables without errors.
2. **State Persistence:** Server restart ke baad `/execute_action` par same `battle_id` use karne se turn wahi se continue hona chahiye.
3. **Immunity Test:** 7th turn par truncate hote waqt, DB/logs mein verify hona chahiye ki `index 0` (System Prompt) drop nahi hua hai aur API request mein hamesha top par jaa raha hai.
4. **Summary Upsert:** Jab pehli baar memory trigger ho, toh DB lock ya PK collision nahi aana chahiye (verifies `INSERT OR REPLACE`).
5. **Latency Fallback:** Agar `SUMMARIZER_LLM` ka mock 6 seconds (timeout) leta hai, toh main battle fail nahi honi chahiye, bas ek warning log honi chahiye.


