# Feature Spec 01: Core Data Contracts & Security Guard (payloads.py)
**Version:** 1.0.0 | **Component:** Backend API Validation Layer

## 1. The Core Problem (Objective)
In a dual-LLM battle ecosystem, the biggest risks are prompt injection, context window overflow (which crashes the GPU/VRAM), and malformed JSON outputs. If a user or frontend sends a 10,000-word topic, or if the LLM returns an empty string instead of dialogue, the entire system will break. 
**Objective:** To build a bulletproof "Security Guard" using strict validation rules that sanitize every piece of data entering or leaving the backend API, before it ever reaches the AI logic.

## 2. Scope & Constraints (The Guardrails)
* **Target File:** Strictly limited to `backend_arena/src/schemas/payloads.py`.
* **Constraint 1 (No Logic):** This module will NOT contain any FastAPI routers, database connections, or LLM API calls. It is strictly for data structure definition.
* **Constraint 2 (No Garbage Policy):** The system must completely forbid unknown or extra fields. If a payload contains an undefined key, it must fail instantly.
* **Constraint 3 (Auto-Sanitization):** Every string input must be automatically stripped of leading/trailing whitespace.

## 3. The Payloads (Input & Output Rulebook)
This section defines the exact theoretical structure of all data objects.


### A. Input Models (Frontend to Backend)
**1. MatchConfig (Global Match Settings)**
* `topic` (String): The debate subject. Min 3, Max 200 chars.
* `turn_limit` (Integer): Max conversation rounds. Min 1, Max 50.
* `current_vibe` (String): Must be exactly one of: `["logical", "emotional", "chaotic"]`.

**2. EntityConfig (AI Persona Profile)**
* `selected_llm` (String): Routing target. Must be exactly one of: `["mock", "openai", "claude", "ollama", "groq"]`.
* `persona_name` (String): Name of the AI. Min 2, Max 50 chars.
* `logic_core_belief` (String): Core ideology for the prompt. Min 10, Max 1000 chars.
* `trigger_point` (String): Condition for aggression. Min 5, Max 1000 chars.
* `voice_id` (String): TTS voice identifier. Min 2, Max 50 chars.
* `voice_speed` (Float): Speed multiplier. Min 0.5, Max 2.0.

**3. InitializeBattleRequest (Setup Command)**
* Contains `match_config` (MatchConfig).
* Contains `entity_1` (EntityConfig) and `entity_2` (EntityConfig).

**4. ExecuteActionRequest (Mid-Battle Command)**
* `battle_id` (String): Unique identifier. Min 5 chars.
* `action_type` (String): Must be exactly one of: `["next_turn", "context_bomb", "kill_switch"]`.

### B. Output Models (Backend to Frontend)
**1. ExecuteActionResponse (The AI Output Contract)**
* `speaker` (String): The entity currently talking. Min 2 chars.
* `internal_monologue` (String): Hidden tactical thoughts. Cannot be empty (Min length 1).
* `spoken_dialogue` (String): Actual raw dialogue. Cannot be empty (Min length 1).
* `tts_ready_text` (String): Sanitized text for audio generation. Cannot be empty (Min length 1).
* `voice_params` (Object): Must contain `id` (String) and `speed` (Float between 0.5-2.0).
* `telemetry` (Object): Must contain `sentiment_score` (Integer, -100 to 100) and `aggression_level` (Integer, 0 to 100).

**2. InitializeBattleResponse**
* `battle_id` (String): Generated session ID. Min 5 chars.
* `status` (String): Default "initialized".
* `message` (String): Confirmation text.

## 4. Edge Cases to Handle
* **Edge Case 1:** The frontend sends a `turn_limit` of 500. 
  * *Handling:* System must throw a validation error (out of bounds).
* **Edge Case 2:** The user types `"   Gym Bro   "` with extra spaces.
  * *Handling:* System must auto-trim it to `"Gym Bro"` before processing.
* **Edge Case 3:** A malicious request adds `"override_system": true` to the payload.
  * *Handling:* System must reject the payload completely because of the "No Garbage Policy".

## 5. Technical Solution Strategy
The developer will use **Pydantic v2** to enforce this spec. A custom base class must be created utilizing `ConfigDict(extra="forbid")` to block garbage data. Every attribute must utilize the `Field(...)` mechanism to enforce the string limits (`min_length`, `max_length`), numerical limits (`ge`, `le`), and sanitization (`strip_whitespace=True`).

## 6. Acceptance Criteria (Testing)
The feature is considered complete when:
1. The developer can import the payload models in a Python shell.
2. Attempting to instantiate `MatchConfig` with a `topic` of 1 character raises a `ValidationError`.
3. Attempting to instantiate `EntityConfig` with `selected_llm` as "huggingface" raises a `ValidationError`.
4. Attempting to pass undefined fields triggers a validation failure.