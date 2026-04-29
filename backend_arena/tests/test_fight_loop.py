import json
from unittest.mock import patch

import pytest

from backend_arena.src.engine.fight_loop import _FALLBACK_STUB, _active_battles
from backend_arena.src.engine import llm_router
from backend_arena.src.exceptions import BattleNotFoundError, BattleTurnLimitError
from backend_arena.src.schemas.payloads import MatchConfig


# AC1 — mock routing returns valid response with telemetry
def test_next_turn_mock_returns_valid_response(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)
    response = manager.next_turn(battle_id)

    assert response.speaker in ("entity_1", "entity_2")
    assert len(response.internal_monologue) >= 1
    assert len(response.spoken_dialogue) >= 1
    assert len(response.tts_ready_text) >= 1
    assert response.voice_params.id == "test_voice"
    assert -100 <= response.telemetry.sentiment_score <= 100
    assert 0 <= response.telemetry.aggression_level <= 100


def test_turn_alternates_speakers(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)
    r1 = manager.next_turn(battle_id)
    r2 = manager.next_turn(battle_id)
    assert r1.speaker == "entity_1"
    assert r2.speaker == "entity_2"


def test_battle_not_found_raises(manager):
    with pytest.raises(BattleNotFoundError):
        manager.next_turn("nonexistent-battle-id-xyz")


def test_turn_limit_raises_battle_turn_limit_error(manager, mock_battle_request):
    from backend_arena.src.schemas.payloads import InitializeBattleRequest
    req = InitializeBattleRequest(
        match_config=MatchConfig(topic="Short battle", turn_limit=2, current_vibe="chaotic"),
        entity_1=mock_battle_request.entity_1,
        entity_2=mock_battle_request.entity_2,
    )
    battle_id = manager.create_battle(req)
    manager.next_turn(battle_id)
    manager.next_turn(battle_id)
    with pytest.raises(BattleTurnLimitError):
        manager.next_turn(battle_id)


# AC4 — history truncation: 7 calls → stored history ≤ 12 messages (6 pairs)
def test_history_truncated_after_seven_turns(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)
    for _ in range(7):
        manager.next_turn(battle_id)
    state = _active_battles[battle_id]
    assert len(state["history"]) <= 12


# AC3 — JSON fallback stub returned on double decode failure
def test_json_fallback_stub_on_double_failure(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)

    class _BadAdapter:
        def __call__(self, *args, **kwargs):
            return "this is absolutely not json"

    with patch.object(llm_router, "route", return_value=_BadAdapter()):
        response = manager.next_turn(battle_id)

    assert response.internal_monologue == _FALLBACK_STUB["internal_monologue"]
    assert response.spoken_dialogue.startswith("[CONNECTION LOST]") or "blank" in response.spoken_dialogue
    assert response.telemetry.sentiment_score == 0
    assert response.telemetry.aggression_level == 0


def test_kill_switch_pauses_battle(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)
    response = manager.kill_switch(battle_id)
    assert response.speaker == "system"
    assert response.tts_ready_text == "Battle paused."
    assert _active_battles[battle_id]["status"] == "paused"


def test_context_bomb_injects_and_advances(manager, mock_battle_request):
    battle_id = manager.create_battle(mock_battle_request)
    response = manager.context_bomb(battle_id, "Switch to philosophy now!")
    assert response.speaker in ("entity_1", "entity_2")
    # System override message should be in stored history
    state = _active_battles[battle_id]
    system_msgs = [m for m in state["history"] if m.role == "system"]
    assert any("[SYSTEM OVERRIDE]" in m.content for m in system_msgs)
