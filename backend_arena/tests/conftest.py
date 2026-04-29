import pytest

from backend_arena.src.engine.fight_loop import _active_battles
from backend_arena.src.engine.llm_router import _adapter_cache
from backend_arena.src.schemas.payloads import EntityConfig, InitializeBattleRequest, MatchConfig


@pytest.fixture(autouse=True)
def clear_state():
    _active_battles.clear()
    _adapter_cache.clear()
    yield
    _active_battles.clear()
    _adapter_cache.clear()


@pytest.fixture
def manager():
    from backend_arena.src.engine.fight_loop import MatchManager
    return MatchManager()


@pytest.fixture
def mock_entity():
    return EntityConfig(
        selected_llm="mock",
        persona_name="TestBot",
        logic_core_belief="Logic is the ultimate truth and cannot be defeated.",
        trigger_point="When challenged on facts, double down harder.",
        voice_id="test_voice",
        voice_speed=1.0,
    )


@pytest.fixture
def mock_battle_request(mock_entity):
    return InitializeBattleRequest(
        match_config=MatchConfig(
            topic="Is Python better than Java?",
            turn_limit=10,
            current_vibe="logical",
        ),
        entity_1=mock_entity,
        entity_2=mock_entity,
    )
