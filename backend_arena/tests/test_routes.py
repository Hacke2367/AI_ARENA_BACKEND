from backend_arena.src.database.db_manager import Battle

_ENTITY = {
    "selected_llm": "mock",
    "persona_name": "LogicBot",
    "logic_core_belief": "Logic is supreme and cannot be defeated by emotion.",
    "trigger_point": "When challenged on facts, be sharper.",
    "voice_id": "voice_a",
    "voice_speed": 1.0,
}

_INIT_PAYLOAD = {
    "match_config": {
        "topic": "Is Python better than Java?",
        "turn_limit": 10,
        "current_vibe": "logical",
    },
    "entity_1": _ENTITY,
    "entity_2": {**_ENTITY, "persona_name": "DataBot", "voice_id": "voice_b", "voice_speed": 1.1},
}


def _create_battle(client) -> str:
    r = client.post("/initialize_battle", json=_INIT_PAYLOAD)
    assert r.status_code == 200, r.text
    return r.json()["battle_id"]


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "online"


def test_initialize_battle_returns_battle_id(client):
    r = client.post("/initialize_battle", json=_INIT_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert "battle_id" in data
    assert data["status"] == "initialized"


def test_execute_next_turn_returns_full_response(client):
    battle_id = _create_battle(client)
    r = client.post("/execute_action", json={"battle_id": battle_id, "action_type": "next_turn"})
    assert r.status_code == 200
    data = r.json()
    assert data["speaker"] in ("entity_1", "entity_2")
    assert "internal_monologue" in data
    assert "spoken_dialogue" in data
    assert "tts_ready_text" in data
    assert "voice_params" in data
    assert "telemetry" in data


def test_execute_action_invalid_battle_id_returns_404(client):
    r = client.post(
        "/execute_action",
        json={"battle_id": "no-such-battle-xyz", "action_type": "next_turn"},
    )
    assert r.status_code == 404


def test_execute_action_turn_limit_returns_409(client, db_session):
    battle_id = _create_battle(client)
    # Force the battle row to be at the configured turn_limit (10).
    db_session.query(Battle).filter(Battle.id == battle_id).update({"turn": 10})
    db_session.commit()
    r = client.post(
        "/execute_action",
        json={"battle_id": battle_id, "action_type": "next_turn"},
    )
    assert r.status_code == 409


def test_kill_switch_returns_system_speaker(client):
    battle_id = _create_battle(client)
    r = client.post(
        "/execute_action",
        json={"battle_id": battle_id, "action_type": "kill_switch"},
    )
    assert r.status_code == 200
    assert r.json()["speaker"] == "system"


def test_context_bomb_requires_context_text(client):
    battle_id = _create_battle(client)
    # Missing context_text — Pydantic validator should reject with 422
    r = client.post(
        "/execute_action",
        json={"battle_id": battle_id, "action_type": "context_bomb"},
    )
    assert r.status_code == 422


def test_context_bomb_with_text_succeeds(client):
    battle_id = _create_battle(client)
    r = client.post(
        "/execute_action",
        json={
            "battle_id": battle_id,
            "action_type": "context_bomb",
            "context_text": "Switch to philosophy!",
        },
    )
    assert r.status_code == 200
    assert r.json()["speaker"] in ("entity_1", "entity_2")
