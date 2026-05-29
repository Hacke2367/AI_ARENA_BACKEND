"""HTTP client wrapper for Arena backend API."""
import logging
import time

import httpx

_log = logging.getLogger(__name__)

# Shared client — provides connection pooling across all API calls (Fix: no per-call TCP handshake)
_CLIENT = httpx.Client()

_RETRYABLE_STATUSES = frozenset({429, 503})
_MAX_RETRIES = 2


def _request_with_retry(method: str, url: str, timeout: float, **kwargs) -> httpx.Response:
    """Send an HTTP request, retrying on transient 429/503 responses with exponential backoff."""
    for attempt in range(_MAX_RETRIES + 1):
        r = getattr(_CLIENT, method)(url, timeout=timeout, **kwargs)
        if r.status_code not in _RETRYABLE_STATUSES or attempt == _MAX_RETRIES:
            _log.debug("%s %s → %d (attempt %d)", method.upper(), url, r.status_code, attempt + 1)
            r.raise_for_status()
            return r
        wait = 2 ** attempt
        _log.warning(
            "Retryable %d from %s — backing off %ds (attempt %d/%d)",
            r.status_code, url, wait, attempt + 1, _MAX_RETRIES,
        )
        time.sleep(wait)
    raise RuntimeError("Retry loop exited without returning")  # unreachable


def initialize_battle(payload: dict, base_url: str, timeout: float = 30.0) -> dict:
    url = f"{base_url}/initialize_battle"
    _log.debug("initialize_battle url=%s payload_keys=%s", url, list(payload.keys()))
    r = _request_with_retry("post", url, timeout, json=payload)
    data: dict = r.json()
    if "battle_id" not in data:
        raise ValueError(f"Unexpected response shape from /initialize_battle: {data}")
    _log.debug("initialize_battle success battle_id=%s", data.get("battle_id"))
    return data


def execute_action(
    battle_id: str,
    action_type: str,
    base_url: str,
    context_text: str | None = None,
    timeout: float = 90.0,
) -> dict:
    url = f"{base_url}/execute_action"
    body: dict[str, str] = {"battle_id": battle_id, "action_type": action_type}
    if context_text:
        body["context_text"] = context_text
    _log.debug("execute_action url=%s battle_id=%s action=%s", url, battle_id, action_type)
    r = _request_with_retry("post", url, timeout, json=body)
    data: dict = r.json()
    if "spoken_dialogue" not in data:
        raise ValueError(f"Unexpected response shape from /execute_action: {data}")
    _log.debug("execute_action success speaker=%s", data.get("speaker"))
    return data
