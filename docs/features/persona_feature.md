Feature Spec 05: The Persona Engine (Jailbreak & Injection System)
Version: 1.1.0 (Reviewer Approved) | Component: Core LLM Prompting & Persona Layer

### 1. The Core Problem (Objective)
Standard LLMs revert to polite and consensus-seeking behaviors.
Objective: Ek 3-Layer Persona Engine banana jo LLM ki default conditioning ko "Jailbreak" kare. Ye engine static persona data (Layer 1) ko ek hardcore psychological template (Layer 2) ke sath mix karega.

### 2. Scope & Constraints (The Guardrails)
Target Files:

backend_arena/src/schemas/payloads.py (API and DB schema)

backend_arena/src/engine/prompt_builder.py (The core injector)

backend_arena/src/engine/fight_loop.py (Validation and loading adjustments)

backend_arena/src/personas/*.json (New folder for DNA fixtures)

Reference File: docs/ai_jailbreak/master_prompt.md (Authoritative path for the master template).

Constraint 1 (Safe Injection): prompt_builder.py must use string.Template ($variable syntax) instead of str.format() to prevent crashes if persona strings contain literal { or } characters.

Constraint 2 (Backward Compatibility): All new fields in EntityConfig MUST be Optional to prevent breaking existing API contracts (/initialize_battle) and breaking reconstruction of legacy DB rows in fight_loop.py.

### 3. The Architecture Design (The 3 Layers)
A. Layer 1: The Character DNA (Data Layer & Schema)
Schema Upgrade (payloads.py): Add the following fields to EntityConfig as optional to maintain backward compatibility:

persona_id: Optional[str] = None

backstory: Optional[str] = None

vocabulary: Optional[list[str]] = None

debate_tactics: Optional[list[str]] = None

Vibe Enum Update (payloads.py): Update MatchConfig.current_vibe to merge both legacy and new vibes: Literal["logical", "emotional", "chaotic", "opening", "heated", "cornered", "victory_lap"].

Data Loading Architecture:

The frontend/caller will pass a persona_id (e.g., "tech_bro") in the EntityConfig payload during /initialize_battle.

The backend orchestrator will read src/personas/{persona_id}.json, populate the missing backstory, vocabulary, and debate_tactics fields, and persist this enriched EntityConfig to the database. fight_loop.py will run off the DB state.

B. Layer 2: The Mixer Engine (prompt_builder.py)
Purpose: Compile the template dynamically.

Placeholder Inventory: The template will use $variable syntax. The canonical inventory is: $persona_name, $backstory, $vocabulary, $debate_tactics, $current_vibe, and $long_term_memory.

Memory Integration: prompt_builder.py's signature build_system_prompt(entity, current_vibe, long_term_memory) will be preserved. The $long_term_memory block will be injected immediately after the [6] CURRENT BATTLE CONTEXT section in the template.

C. Layer 3: Output Enforcer (The Guard)
Purpose: Ensure TTS-clean JSON output.

Execution: Enforcement is handled via the prompt instruction AND the existing backend_arena/src/engine/tts_sanitizer.py. No new regex cleaning code is required; Layer 3 acknowledges and utilizes the existing tts_sanitizer.py pipeline located in fight_loop.py.

### 4. Edge Cases & Disaster Management
Edge Case 1 (Missing Persona JSON): If a requested persona_id file does not exist during load.

Handling: Engine raises an explicit error. The API layer (routes.py) catches it and returns 404 Not Found.

Edge Case 2 (Schema Version Mismatch): A JSON file exists but is missing required keys (e.g., no debate_tactics).

Handling: Pydantic validation fails. API layer returns 422 Unprocessable Entity with field-level detail.

Edge Case 3 (Missing Placeholders in Template): The .md template is edited and a key is missing or renamed.

Handling: string.Template.safe_substitute() should be used to prevent hard crashes, but a startup unit test must validate the template against the exact Placeholder Inventory to catch drift.

### 5. Technical Solution Strategy
Templating: Use Python's built-in string.Template to eliminate injection vulnerabilities associated with curly braces.

List Joining: prompt_builder.py will convert vocabulary and debate_tactics from list to bulleted strings (\n• ) before passing them to the template.

### 6. Acceptance Criteria (Testing Dependencies)
Tests: Update tests/test_prompt_builder.py to verify string.Template substitution using dummy EntityConfig data.

Backward Compatibility: Run existing fight_loop tests. Legacy fixtures (without new fields) must continue to load without ValidationError.

Template Validation: A new test ensures docs/ai_jailbreak/master_prompt.md contains all canonical placeholders ($persona_name, $backstory, etc.).