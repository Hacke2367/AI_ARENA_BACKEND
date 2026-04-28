# Feature Spec 02: Core API Orchestrator (routes.py)
**Version:** 1.0.0 | **Component:** FastAPI Routing Layer

## 1. The Core Problem (Objective)
Humne Security Guard (`payloads.py`) toh bana liya, par ab humein us "Darwaze" ki zaroorat hai jahan se Frontend (Streamlit) Backend ke sath baat karega. 
**Objective:** Ek aisa central orchestration hub banana jo incoming requests ko receive kare, unhe validate karwaye, aur sahi logic controller (Match Manager) tak dispatch kare. Ye layer frontend aur backend ke beech ka "Contract Agreement" hai.

## 2. Scope & Constraints (The Guardrails)
* **Target File:** `backend_arena/src/api/routes.py`
* **Constraint 1 (No Heavy Logic):** Is file mein sirf routing aur orchestration hogi. AI ko kaise call karna hai ya database mein kaise save karna hai, ye logic yahan nahi likha jayega.
* **Constraint 2 (Async First):** Saare endpoints `async` honge taaki multiple battles ek sath handle ho sakein bina system block kiye.
* **Constraint 3 (Strict Validation):** Sirf wahi data andar aayega jo `payloads.py` ke models ko satisfy karega. Validation fail hone par turant **422 Unprocessable Entity** return hoga.

## 3. The Endpoints Contract (API Design)

### A. POST `/initialize_battle`
* **Purpose:** Nayi fight session create karna aur persona inject karna.
* **Input Payload:** `InitializeBattleRequest`
* **Success Response:** `InitializeBattleResponse` (Status 200 OK)
* **Extra Point (State Check):** Agar battle_id create hone mein koi error aata hai, toh ye endpoint **500 Internal Server Error** throw karega.

### B. POST `/execute_action`
* **Purpose:** Battle ke mid-fight commands handle karna (Next turn, Context Bomb, Kill Switch).
* **Input Payload:** `ExecuteActionRequest`
* **Success Response:** `ExecuteActionResponse` (Status 200 OK)
* **Action Routing Logic:** - Agar `action_type == "next_turn"`, toh LLM Controller call hoga.
    - Agar `action_type == "context_bomb"`, toh match state mein toxic prompt inject hoga.
    - Agar `action_type == "kill_switch"`, toh session terminate hoga.

### C. GET `/health` (Extra Point)
* **Purpose:** Monitor karna ki backend zinda hai ya nahi.
* **Response:** `{"status": "online", "version": "1.0.0"}`

## 4. Edge Cases & Disaster Management
* **Edge Case 1 (Invalid Battle ID):** Agar frontend aisa `battle_id` bhejta hai jo backend ki memory mein exist nahi karta.
  - *Handling:* Return **404 Not Found** with message "Battle session expired or invalid".
* **Edge Case 2 (Action Mismatch):** Frontend ne payload toh sahi bheja, par state "Paused" hai aur command "Next Turn" aa gaya.
  - *Handling:* Return **400 Bad Request** with "Invalid action for current state".
* **Edge Case 3 (LLM Timeout):** LLM response dene mein 60 second se zyada le raha hai.
  - *Handling:* API gatekeeper ko timeout handle karke frontend ko "Gateway Timeout" dena hoga taaki user interface hang na ho.

## 5. Technical Solution Strategy
* **Framework:** FastAPI.
* **Dependency Injection:** Hum FastAPI ka `Depends` use karenge Match Manager ko endpoints mein inject karne ke liye.
* **Pydantic Integration:** Saare route parameters type-hinted honge hamare `payloads.py` ke models se.
* **CORS Middleware:** Streamlit frontend aksar alag port par chalta hai, isliye humein strict CORS policy define karni hogi routes level par taaki "Cross-Origin" errors na aayein.

## 6. Acceptance Criteria (Testing)
1. `/initialize_battle` ko valid data dene par ek unique `battle_id` milna chahiye.
2. `/execute_action` ko galat `action_type` (jaise "force_win") bhejte hi **422 Error** aana chahiye.
3. Bina `battle_id` ke `/execute_action` hit karne par access deny hona chahiye.
4. Terminal mein `pytest` ya `curl` chalane par JSON response exactly hamare `ExecuteActionResponse` model ke keys (`speaker`, `spoken_dialogue`, etc.) se match hona chahiye.