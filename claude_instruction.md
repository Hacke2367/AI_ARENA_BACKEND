# Claude Code Operational Rules & Constraints

## 1. The Prime Directive: Context vs. Tasks
Before writing any code, you MUST understand the difference between Global Context and Active Tasks:
* **Global Context:** Read the root `docs/` directory (e.g., `BACKEND_TSD.md`, `FRONTEND_TSD.md`) ONLY to understand the system architecture, boundaries, and payload structures. 
* **Active Tasks:** Do NOT attempt to build the entire master architecture at once. Your coding tasks will strictly come from Rule 6.

## 2. Tech Stack Boundaries (Pure Python)
* **Backend:** FastAPI ONLY.
* **Frontend:** Streamlit ONLY.
* **Prohibited:** Do NOT generate any JavaScript, React, Next.js, Node.js, HTML, or CSS files. This is a 100% Python-native engineering environment.

## 3. The 3-Layer Prompting Integrity
You are building the "Internal Monologue" architecture. 
* NEVER allow the LLM to default to generic chatbot behavior.
* ALWAYS enforce the strict JSON schema output from the LLM containing `internal_monologue` and `spoken_dialogue`. 
* NEVER let the backend return plain text strings for the `execute_action` generation result. It must always be the structured JSON payload.

## 4. VRAM & Hardware Constraints
Assume the application is running on a single rented Cloud GPU (e.g., RTX 3090/4090).
* Do NOT attempt to load two large models into VRAM simultaneously.
* Implement a dynamic system prompt swapping mechanism to cycle between the two personas while keeping only one model loaded in memory at any given time.

## 5. Execution Protocol: No Fluff
* Write hardcore, production-ready code.
* Include proper error handling for LLM timeouts, JSON parsing failures, and API limit breaches.
* Do not add features outside the specifications unless explicitly instructed by the user. 
* Focus purely on decoupled microservices execution.

## 6. Development Workflow (Agile Feature Branching)
* **Execution Trigger:** Look for specific feature specifications inside the `docs/features/` directory (e.g., `docs/features/01_setup_api.md`).
* Always check the current working git branch.
* Build, test, and complete ONLY the specific feature described in the current feature spec. Stop execution once the feature is functional.