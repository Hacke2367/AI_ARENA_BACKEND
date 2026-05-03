# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Spec-Driven Development — CRITICAL

**Always read `docs/` before writing any code.** The specs in `docs/BACKEND_TSD.md`, `docs/FRONTEND_TSD.md`, and `docs/SYSTEM_ARCHITECTURE.md` are the authoritative source of truth for all logic, payloads, and architecture decisions. They override any generic coding patterns.

## Project Overview

"AI Rough Battle" orchestrates persona-based LLM debates using a proprietary **Internal Monologue** architecture: before generating a spoken response, each AI internally processes the opponent's strategy and formulates a tactical approach. Every turn produces two outputs — a hidden `internal_monologue` and a public `spoken_dialogue`.

## Architecture

**Decoupled microservices — pure Python stack:**
- `backend_arena/` — FastAPI server: persona engine, LLM routing, state management
- `creator_dashboard/` — Streamlit GUI: real-time control, telemetry visualization, battle analytics

**Target runtime:** Remote cloud GPU instances (RunPod, Vast.ai, Lambda Labs) accessed via VS Code Remote SSH. Only one LLM is kept in VRAM at a time; system prompts are swapped per turn to avoid OOM.

## Backend Source Map (`backend_arena/src/`)

| Path | Responsibility |
|---|---|
| `api/routes.py` | FastAPI endpoints: `POST /initialize_battle`, `POST /execute_action` |
| `engine/fight_loop.py` | Orchestrates turn sequencing and battle state |
| `engine/llm_router.py` | Universal adapter — routes to local (Ollama/vLLM) or external (OpenAI, Claude, Groq) |
| `engine/prompt_builder.py` | Assembles the 3-Layer prompt (Core Belief → Trigger/Vibe → Output Forcing) |
| `schemas/payloads.py` | Pydantic v2 models for all inbound/outbound payloads |
| `utils/memory_manager.py` | JSON-based persistent battle state |
| `utils/tts_sanitizer.py` | Strips `*actions*` and `[brackets]` from text before populating `tts_ready_text` |

## Key Data Contracts

`/initialize_battle` payload: `match_config` (topic, turn_limit, current_vibe) + `entity_1` + `entity_2` (each with `selected_llm`, `persona_name`, `logic_core_belief`, `trigger_point`, `voice_id`, `voice_speed`).

`/execute_action` response (strict schema — never deviate):
```json
{
  "speaker": "entity_1",
  "internal_monologue": "...",
  "spoken_dialogue": "...",
  "tts_ready_text": "...",
  "voice_params": { "id": "...", "speed": 1.1 },
  "telemetry": { "sentiment_score": 15, "aggression_level": 85 }
}
```

## 3-Layer Prompting

Every LLM call must stack these layers in order:
1. **System Prompt** — injects `logic_core_belief`
2. **Dynamic Guardrails** — injects `trigger_point` + `current_vibe`; enforces negative guardrails ("Do NOT apologize")
3. **Output Forcing** — instructs the LLM to return structured JSON with `internal_monologue` and `spoken_dialogue` keys

## Commands

**Backend**
```bash
# Install dependencies
pip install -r backend_arena/requirements.txt

# Run dev server (from repo root)
uvicorn backend_arena.src.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend (creator_dashboard)**
```bash
# Install Streamlit and any dashboard dependencies
pip install streamlit

# Run the dashboard (from repo root)
streamlit run creator_dashboard/app.py
```

## Dependencies

Backend pinned versions: `fastapi==0.104.1`, `uvicorn==0.24.0`, `pydantic==2.5.0`, `httpx==0.25.1`, `anthropic==0.31.0`, `numpy==1.24.3`, `python-dotenv==1.0.0`.

Frontend: Streamlit (Python).

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

 ## /audit

  When the user types `/audit`, invoke the Skill tool with `skill: "audit"` before doing anything else.
  This skill delegates a full codebase audit to an isolated sub-agent and writes `ARCHITECTURE_STATE.md`
  to the repo root. It does NOT run inline — all analysis happens in a separate context window.
