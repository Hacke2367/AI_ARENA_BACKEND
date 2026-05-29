# Code Review — Creator Dashboard
**Level:** Expert | **Target:** `creator_dashboard/`
**Files Reviewed:** `app.py`, `api_client.py`
**Reviewer Standard:** Production-grade — all edge cases, security, performance, observability

---

## 📄 `api_client.py` — Expert Review

**Code Quality:** 6/10
**Improvement Chance:** 40%
**Verdict:** Clean wrapper but missing three expert-level requirements: connection pooling, retry logic, and observability.

### ✅ What's Good
- Correct use of `raise_for_status()` — exceptions propagate cleanly to the caller
- Context manager (`with httpx.Client`) is the right pattern
- Function signatures are minimal and clear — no hidden coupling

### ⚠️ Issues Found

🔴 **High Priority**

- **No connection pooling — new TCP handshake on every call.** Lines 6 and 22 create a new `httpx.Client` for every API call. During Auto-Play with 50 turns, this means 50 complete TCP connection cycles. Fix: lift a single `httpx.Client` to module level or pass it in as a dependency. Example: `_CLIENT = httpx.Client(timeout=90.0)` at module top, then reuse it per call.

- **No retry logic for transient backend errors.** If the backend returns 429 (rate limited) or 503 (LLM endpoint down), the exception immediately propagates. The Auto-Play loop then halts permanently. At expert level, transient errors should get 1–2 retries with exponential backoff before surfacing to the UI. Use `httpx` with `tenacity` or a manual retry loop for `status_code in (429, 503)`.

🟡 **Medium Priority**

- **No response schema validation.** `r.json()` returns raw `dict`. If the backend changes its shape or returns an error body with 200 status, the caller will get a `KeyError` with no helpful context. Add at minimum a key-presence check: `if "battle_id" not in data: raise ValueError(f"Unexpected response shape: {data}")`.

- **No logging.** At expert level, every outbound HTTP call should be logged at DEBUG level (method, URL, status code, elapsed time). Currently there is zero observability into what the client is sending/receiving.

🟢 **Low Priority**

- **`body: dict` annotation is untyped.** `dict` without parameters means `dict[Any, Any]`. Prefer `dict[str, str | None]` to make intent explicit.

---

## 📄 `app.py` — Expert Review

**Code Quality:** 5/10
**Improvement Chance:** 45%
**Verdict:** Solid structure and correct Streamlit patterns, but has one real data-leakage bug, one unhandled exception path, two blocking sleeps that hurt production use, and an XSS surface in the HTML injection.

### ✅ What's Good
- Session state guard pattern (`if _k not in st.session_state`) is the correct Streamlit idiom
- Auto-Play uses the epoch-check + `st.rerun()` pattern — correctly avoids a blocking loop
- `_handle_turn_error` separates exception types cleanly — easy to extend
- `try/except TypeError` fallback for `st.container(height=)` is a correct compatibility move
- Altair independent Y-axes is the right call for two different-domain series
- Input validation mirrors backend Pydantic constraints before hitting the network

### ⚠️ Issues Found

🔴 **High Priority**

- **Mutable shared default values cause cross-session data leakage.** `_SS_DEFAULTS` at lines 42–55 stores `[]` and `{}` as literal objects. The guard at line 56–58 assigns `st.session_state[_k] = _v` — this gives the session a **reference** to the same list object, not a copy. When `ss.turn_log.append(response)` runs during a battle, it mutates `_SS_DEFAULTS["turn_log"]`. When a second browser tab opens a new session, the guard fires again and assigns the already-mutated list — the new session sees the previous battle's log. Fix: copy on assignment:
  ```python
  st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v
  ```

- **`httpx.TimeoutException` not caught in the Initialize Battle handler.** Lines 363–366 catch `ConnectError` and `HTTPStatusError` but not `TimeoutException`. If `/initialize_battle` takes longer than 30 seconds (e.g., a slow LLM call during persona loading), the exception is uncaught and Streamlit surfaces a raw Python traceback to the user. Fix: add `except httpx.TimeoutException: st.error("Init timed out — backend is not responding.")` after line 366.

- **`time.sleep(1)` inside `_run_turn` blocks the server thread every turn.** Line 184 sleeps for 1 second during the "Voice Synthesizing..." overlay. In a Streamlit deployment serving multiple users, this holds the server thread for 1 second on every single turn execution. Over 10 turns in Auto-Play, that's 10 seconds of thread-blocking just for a cosmetic overlay. Fix: remove the sleep entirely — the `status_placeholder.empty()` call at line 185 is sufficient. The overlay will still flash visibly between the LLM response arriving and the next rerun.

- **`time.sleep(0.5)` in the Auto-Play poll loop blocks the server thread continuously.** Line 586 sleeps 0.5 seconds on every rerun cycle while Auto-Play is waiting for the next interval. During a 30-second Auto-Play interval, this fires 60 times and holds the thread for 30 cumulative seconds. Fix: instead of polling with sleep, calculate the remaining wait and use a single `time.sleep(remaining)` capped at a short value only when necessary, or accept the rerun overhead without sleeping at all.

- **XSS surface in `unsafe_allow_html` with unescaped session state value.** Line 412 injects `st.session_state.current_vibe` directly into an HTML string:
  ```python
  f"🧠 VIBE<br>{st.session_state.current_vibe.upper().replace('_', ' ')}"
  ```
  `current_vibe` is set from a `selectbox` (safe), but also written to session state from `init_payload` which flows from backend responses. If the backend returns a crafted string like `</div><script>alert(1)</script>`, it executes in the user's browser. Fix: always escape before injecting:
  ```python
  import html
  html.escape(st.session_state.current_vibe.upper().replace("_", " "))
  ```

🟡 **Medium Priority**

- **`status_placeholder` is positioned below the Arena Log, not above it.** Line 516 creates `status_placeholder = st.empty()` inside Section 9, after the Arena Log divider. The spec says the overlay should appear "above the Arena Log, below the Telemetry section." Move `status_placeholder = st.empty()` to just after `st.divider()` at line 465 (after Section 7, before Section 8).

- **Bare `except Exception` in `_run_turn` swallows bugs silently.** Line 176 catches all exceptions, including things like `AttributeError` from a bug in `api_client` itself. These get shown to the user as "Unexpected error: ..." with no log, making debugging impossible. Fix: catch specific httpx exceptions explicitly, then re-raise unknown ones after logging:
  ```python
  except (httpx.ConnectError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
      ...
  except Exception as exc:
      logging.error("Unhandled error in _run_turn", exc_info=True)
      st.error(f"Unexpected error — check server logs.")
      raise
  ```

- **CSS selector bleeds to ALL last-column buttons on the page.** Lines 23–35 use `div[data-testid="stHorizontalBlock"] > div:last-child .stButton > button` which targets the last column's button in **every** horizontal block layout on the page. If any other `st.columns()` call produces a button in its last column, it gets red-styled unintentionally. Fix: wrap the God Mode button row in a container with a unique class, then scope the CSS to that class.

- **`_log_header` column is declared but never used.** Line 470: `_log_header, _toggle_col = st.columns([4, 1])`. Nothing is rendered into `_log_header`, creating an empty invisible column. Use `_` for throwaway: `_, _toggle_col = st.columns([4, 1])`.

- **`base_url` is not validated before use.** The text input at line 214 accepts any string. A URL like `file:///etc/passwd` or a malformed string would raise an exception not caught by `ConnectError`. Add a minimal check: `if not base_url.startswith(("http://", "https://")):  st.error("Backend URL must start with http:// or https://"); st.stop()`.

- **No logging anywhere.** Neither file uses Python's `logging` module. At minimum, `_run_turn` should log `battle_id`, `action_type`, and response status at DEBUG level. Without this, debugging a failed Auto-Play session requires adding temporary `st.write()` calls.

🟢 **Low Priority**

- **`_build_telemetry_chart` type hint uses a forward-reference string unnecessarily.** Line 93: `-> "alt.LayerChart | None"` — since `altair` is already imported at the top, this can be `-> alt.LayerChart | None` (no quotes needed; the string form is for when the type isn't available at parse time).

- **`creator_dashboard/` has no `__init__.py`.** This is not a Python package. `import api_client` works because Streamlit manipulates `sys.path`, but this is fragile. Running `python creator_dashboard/app.py` from a different directory or importing from tests would fail. Add an empty `__init__.py`.

---

## 📊 Overall Project Report — Expert Review

**Files Reviewed:** 2
**Overall Quality Score:** 5/10
**Overall Improvement Chance:** 43%
**Verdict:** ❌ Not production-ready. Five issues are production blockers: the session state mutation bug can corrupt new users' views; the missing TimeoutException handler crashes on slow init; the two blocking sleeps degrade every user under concurrent load; and the XSS surface is a security hole even if low-probability.

### Score Breakdown

| File | Score | Expert OK? |
|------|-------|-----------|
| `api_client.py` | 6/10 | ❌ (no pooling, no retry, no logging) |
| `app.py` | 5/10 | ❌ (data bug, unhandled exception, blocking sleeps, XSS) |

### Common Issues (Across Both Files)
- **No logging** — neither file emits a single log line; debugging requires adding temporary prints
- **No retry logic** — transient backend failures permanently halt the battle session

---

### 🔴 Critical Fixes (Do First)

1. **`app.py` line 57** — Copy mutable defaults on assignment: `_v.copy() if isinstance(_v, (list, dict)) else _v`
2. **`app.py` line 366** — Add `except httpx.TimeoutException` to the init battle handler
3. **`app.py` line 184** — Remove `time.sleep(1)` — the "Voice Synthesizing" overlay does not need a hard block
4. **`app.py` line 586** — Remove `time.sleep(0.5)` from Auto-Play loop or replace with a `time.sleep(max(0, remaining))` calculated once
5. **`app.py` line 412** — Wrap `current_vibe` value in `html.escape()` before injecting into HTML string

### 🟡 Important Improvements

6. **`api_client.py` lines 6, 22** — Lift `httpx.Client` to module level for connection reuse
7. **`api_client.py`** — Add retry logic (1–2 retries with backoff) for 429 and 503 status codes
8. **`app.py` line 516** — Move `status_placeholder = st.empty()` to line 466 (after telemetry, before Arena Log)
9. **`app.py` line 176** — Replace bare `except Exception` with specific httpx exceptions + re-raise unknowns after logging
10. **`app.py` lines 23–35** — Scope the Kill Switch CSS selector to avoid bleeding to other button columns

### 🟢 Nice to Have

11. **Both files** — Add `import logging` and emit at least one log line per significant operation
12. **`app.py` line 470** — Replace `_log_header` with `_` to signal the column is intentionally empty
13. **`app.py` line 214** — Add URL scheme validation before passing `base_url` to `api_client`
14. **`creator_dashboard/`** — Add `__init__.py` to make it a proper package
