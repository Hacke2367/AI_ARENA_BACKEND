import pytest

from backend_arena.src.schemas.payloads import EntityConfig

_CANONICAL_PLACEHOLDERS = {
    "persona_name",
    "backstory",
    "vocabulary",
    "debate_tactics",
    "current_vibe",
    "long_term_memory",
}

_BASE_ENTITY = dict(
    selected_llm="mock",
    persona_name="TestBot",
    logic_core_belief="Logic always wins.",
    trigger_point="Never back down.",
    voice_id="v1",
    voice_speed=1.0,
)


# ── AC1: EntityConfig validation ──────────────────────────────────────────────

def test_entity_config_with_full_dna_validates():
    entity = EntityConfig(
        **_BASE_ENTITY,
        backstory="A detailed backstory.",
        vocabulary=["• word one", "• word two"],
        debate_tactics=["1. TACTIC ONE.", "2. TACTIC TWO."],
    )
    assert entity.backstory == "A detailed backstory."
    assert entity.vocabulary == ["• word one", "• word two"]
    assert entity.debate_tactics == ["1. TACTIC ONE.", "2. TACTIC TWO."]


def test_entity_config_without_dna_validates():
    entity = EntityConfig(**_BASE_ENTITY)
    assert entity.persona_id is None
    assert entity.backstory is None
    assert entity.vocabulary is None
    assert entity.debate_tactics is None


def test_match_config_accepts_new_vibes():
    from backend_arena.src.schemas.payloads import MatchConfig
    for vibe in ("opening", "heated", "cornered", "victory_lap"):
        mc = MatchConfig(topic="Test topic", turn_limit=5, current_vibe=vibe)
        assert mc.current_vibe == vibe


def test_match_config_accepts_legacy_vibes():
    from backend_arena.src.schemas.payloads import MatchConfig
    for vibe in ("logical", "emotional", "chaotic"):
        mc = MatchConfig(topic="Test topic", turn_limit=5, current_vibe=vibe)
        assert mc.current_vibe == vibe


# ── AC2: build_system_prompt returns merged string ────────────────────────────

@pytest.fixture()
def _patch_template(monkeypatch, tmp_path):
    tpl = tmp_path / "master_prompt.md"
    tpl.write_text(
        "NAME=$persona_name "
        "STORY=$backstory "
        "VOCAB=$vocabulary "
        "TACTICS=$debate_tactics "
        "VIBE=$current_vibe "
        "MEM=$long_term_memory",
        encoding="utf-8",
    )
    import backend_arena.src.engine.prompt_builder as pb
    monkeypatch.setattr(pb, "_TEMPLATE_PATH", tpl)
    pb._load_template.cache_clear()
    yield pb
    pb._load_template.cache_clear()


def test_build_system_prompt_injects_all_dna_fields(_patch_template):
    entity = EntityConfig(
        **_BASE_ENTITY,
        backstory="My backstory.",
        vocabulary=["• vocab line"],
        debate_tactics=["1. TACTIC."],
    )
    result = _patch_template.build_system_prompt(entity, "heated", "prior memory")
    assert "TestBot" in result
    assert "My backstory." in result
    assert "• vocab line" in result
    assert "1. TACTIC." in result
    assert "HEATED" in result
    assert "prior memory" in result


def test_build_system_prompt_falls_back_to_logic_core_belief(_patch_template):
    entity = EntityConfig(**_BASE_ENTITY)
    result = _patch_template.build_system_prompt(entity, "logical")
    assert "Logic always wins." in result


def test_build_system_prompt_omits_memory_block_when_empty(_patch_template):
    entity = EntityConfig(**_BASE_ENTITY)
    result = _patch_template.build_system_prompt(entity, "logical", "")
    assert "LONG-TERM MEMORY" not in result


def test_build_system_prompt_includes_memory_block_when_present(_patch_template):
    entity = EntityConfig(**_BASE_ENTITY)
    result = _patch_template.build_system_prompt(entity, "logical", "remembered stuff")
    assert "LONG-TERM MEMORY" in result
    assert "remembered stuff" in result


def test_build_system_prompt_joins_list_with_newlines(_patch_template):
    entity = EntityConfig(
        **_BASE_ENTITY,
        vocabulary=["• line one", "• line two", "• line three"],
    )
    result = _patch_template.build_system_prompt(entity, "chaotic")
    assert "• line one\n• line two\n• line three" in result


# ── AC3: Template placeholder validation (startup guard) ─────────────────────

def test_master_prompt_contains_all_canonical_placeholders():
    from backend_arena.src.engine.prompt_builder import _TEMPLATE_PATH
    content = _TEMPLATE_PATH.read_text(encoding="utf-8")
    for key in _CANONICAL_PLACEHOLDERS:
        assert f"${key}" in content or f"${{{key}}}" in content, (
            f"master_prompt.md is missing placeholder: ${key}"
        )


# ── AC4: Invalid persona_id raises PersonaNotFoundError ──────────────────────

def test_enrich_with_invalid_persona_id_raises(manager, mock_battle_request):
    from backend_arena.src.exceptions import PersonaNotFoundError
    bad_entity = mock_battle_request.entity_1.model_copy(
        update={"persona_id": "nonexistent_persona_xyz"}
    )
    bad_request = mock_battle_request.model_copy(update={"entity_1": bad_entity})
    with pytest.raises(PersonaNotFoundError, match="nonexistent_persona_xyz"):
        manager.create_battle(bad_request)


def test_enrich_with_valid_persona_id_loads_dna(manager, mock_battle_request):
    entity_with_id = mock_battle_request.entity_1.model_copy(
        update={"persona_id": "tech_bro"}
    )
    battle_request = mock_battle_request.model_copy(
        update={"entity_1": entity_with_id, "entity_2": entity_with_id}
    )
    battle_id = manager.create_battle(battle_request)
    assert battle_id is not None
