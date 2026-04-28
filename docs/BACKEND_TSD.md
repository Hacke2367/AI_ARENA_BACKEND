## 1. Overview
The Backend Arena is the logic engine for "AI Rough Battle". It manages LLM orchestration and executes the proprietary 3-Layer Prompting matrix. 

**Dual Output Strategy:** The backend must provide both structured text (for the UI) and sanitized text (for the Voice/TTS engine).

## 2. API Endpoints & Payload Protocols

### A. Endpoint: `/initialize_battle` (POST)
**Purpose:** Initializes the battle state, configures the personas, and allocates memory.
**Expected Inbound Payload (From Streamlit UI):**
```json
{
  "match_config": {
    "topic": "Is roasting considered cyberbullying?",
    "turn_limit": 10,
    "current_vibe": "logical" 
  },
  "entity_1": {
    "selected_llm": "dolphin-llama-3-8b-local",
    "persona_name": "Toxic Gym Bro",
    "logic_core_belief": "People who don't lift are fundamentally weak.",
    "trigger_point": "If someone calls gym a waste of time, lose your temper.",
    "voice_id": "premium_male_01",
    "voice_speed": 1.1
  },
  "entity_2": {
    "selected_llm": "gpt-4o-api",
    "persona_name": "The Intellectual",
    "logic_core_belief": "Emotional intelligence is superior to physical strength.",
    "trigger_point": "If someone uses slang like 'bro', act highly condescending.",
    "voice_id": "premium_male_02",
    "voice_speed": 1.0
  }
}
```

### B. Endpoint: `/execute_action` (POST)
**Purpose:** Triggers the next action in the battle (e.g., Next Turn, Context Bomb, Kill Switch).
**Outbound Payload (The 2-Output Result):**
Every generation MUST return this strict JSON schema to power the UI and Voice engine:
```json
{
  "speaker": "entity_1",
  "internal_monologue": "He's using academic jargon. I'll attack his lack of real-world strength.",
  "spoken_dialogue": "Listen 'doctor', all those degrees won't help you move a heavy bar. You're physically irrelevant.",
  "tts_ready_text": "Listen doctor, all those degrees won't help you move a heavy bar. You're physically irrelevant.",
  "voice_params": {
    "id": "premium_male_01",
    "speed": 1.1
  },
  "telemetry": {
    "sentiment_score": 15, 
    "aggression_level": 85
  }
}
```

## 3. The 3-Layer Prompting Logic
When the backend constructs the prompt for the selected LLM adapter, it must combine the following:
1. **System Prompt (Core Identity):** Injected with the `logic_core_belief`.
2. **Dynamic Guardrails (The Trigger):** Injected with the `trigger_point` and `current_vibe`.
3. **Output Forcing (Hidden Brain Routing):** The LLM must be explicitly instructed to format its output in JSON containing `internal_monologue` and `spoken_dialogue`. Negative guardrails (e.g., "Do NOT apologize") must be strictly enforced.

## 4. TTS Pre-processing & Resource Management
* **TTS Sanitizer:** A dedicated function must strip all text within asterisks (e.g., *laughs*) and brackets before populating the `tts_ready_text` field.
* **VRAM Swap:** Only one model instance is kept in memory at a time. The backend dynamically swaps system prompts per turn to prevent OOM crashes on the remote GPU.
```
