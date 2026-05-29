import json

import pytest

from backend_arena.src.engine.llm_router import MockAdapter, OllamaAdapter, route
from backend_arena.src.exceptions import LLMConnectionError
from backend_arena.src.schemas.types import ChatMessage


# AC1 — mock adapter returns valid JSON with all four required fields
def test_mock_adapter_returns_valid_json():
    adapter = MockAdapter()
    raw = adapter("system prompt", [])
    data = json.loads(raw)
    assert "internal_monologue" in data
    assert "spoken_dialogue" in data
    assert "sentiment_score" in data
    assert "aggression_level" in data
    assert isinstance(data["sentiment_score"], int)
    assert isinstance(data["aggression_level"], int)


def test_mock_adapter_ignores_chat_history():
    adapter = MockAdapter()
    history = [ChatMessage(role="user", content="Hello")]
    raw = adapter("sys", history)
    assert json.loads(raw)  # must still be valid JSON


def test_route_mock_returns_mock_adapter():
    adapter = route("mock")
    assert isinstance(adapter, MockAdapter)


def test_route_same_instance_cached():
    a1 = route("mock")
    a2 = route("mock")
    assert a1 is a2


def test_route_unknown_llm_raises():
    with pytest.raises(ValueError, match="Unknown LLM"):
        route("totally_unknown_provider_xyz")


# AC2 — invalid Ollama URL raises LLMConnectionError instead of hanging
def test_ollama_invalid_url_raises_connection_error(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:19999")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    adapter = OllamaAdapter()
    with pytest.raises(LLMConnectionError):
        adapter("system prompt", [])
