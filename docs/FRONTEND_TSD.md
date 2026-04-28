# Frontend Technical Specification Document (TSD) - V2

## 1. Overview
The Creator Dashboard (Streamlit) acts as the central command GUI. It is optimized for 4K screen recording and post-production cropping (16:9 to 9:16).

## 2. UI Modules & Layout Architecture

### Module 1: The Configuration Matrix (Sidebar)
* **Match Setup:** Input fields for Topic, Turn Limit, and Initial Vibe.
* **Persona Deep-Dive:** Text areas for "Core Beliefs" and "Trigger Matrix" for both entities.
* **Voice Engine:** Selectors for Voice IDs and pitch/speed parameters.

### Module 2: Visual Telemetry & Battle Analytics (Main Stage)
This is the most critical part for video production. We use real-time data from the backend to plot:
* **The Aggression & Sentiment Tracker:** A dual-axis line chart.
    * **Sentiment:** Tracks if the tone is positive or negative.
    * **Aggression:** Tracks the intensity of the attack based on the `aggression_level` payload.
* **Emotion Trigger Pulse:** A visual marker or "flash" on the UI whenever the backend detects that a "Trigger Point" from the persona matrix has been activated.
* **Neural Vibe Monitor:** A real-time gauge or pulse indicator that changes color/intensity based on the `current_vibe` (e.g., Cool Blue for 'Logical', Glowing Red for 'Total Chaos').

### Module 3: Arena Log & Hidden Logic
* **The Arena Log:** A clean, high-contrast chat interface.
* **Internal Monologue Toggle:** A switch to reveal/hide the `internal_monologue`. When ON, the AI's strategic reasoning is displayed in a distinct 'Thinking' bubble before the actual dialogue.

### Module 4: God Mode Controls (Transport)
* **Action Buttons:** "Next Turn", "Auto-Play", and "Inject Context Bomb".
* **The Kill Switch:** A massive, high-contrast Red button to stop all API processes immediately.

## 3. Visual Strategy for Creators
* **Fixed 4K Layout:** All modules are positioned so that a 9:16 crop (Shorts/Reels) can be placed directly over the Chat Log or the Telemetry Graphs without losing visual data.
* **Status Indicators:** "Processing LLM..." and "Voice Synthesizing..." overlays to keep the creator informed during the execution loop.