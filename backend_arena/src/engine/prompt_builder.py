import pathlib
from functools import lru_cache
from string import Template

from backend_arena.src.schemas.payloads import EntityConfig

_TEMPLATE_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "docs"
    / "ai_jailbreak"
    / "master_prompt.md"
)


@lru_cache(maxsize=1)
def _load_template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _format_list(items: list[str] | None) -> str:
    if not items:
        return ""
    return "\n".join(items)


def build_system_prompt(
    entity: EntityConfig,
    vibe: str,
    long_term_memory: str = "",
    battle_context: str = "",
) -> str:
    memory_block = ""
    if long_term_memory.strip():
        memory_block = f"[LONG-TERM MEMORY — DO NOT IGNORE]\n{long_term_memory}\n"

    # Render the shared world-premise block only when provided.
    # Both combatants receive the identical block — they must argue WITHIN this reality.
    context_block = ""
    if battle_context.strip():
        border = "━" * 44
        context_block = (
            f"{border}\n"
            f"WORLD PREMISE — BOTH COMBATANTS ACCEPT THIS AS ABSOLUTE TRUTH:\n"
            f"{battle_context.strip()}\n"
            f"You cannot deny or contradict this premise. Your arguments must operate WITHIN it.\n"
            f"{border}\n"
        )

    return _load_template().safe_substitute(
        persona_name=entity.persona_name,
        backstory=entity.backstory or entity.logic_core_belief or "",
        vocabulary=_format_list(entity.vocabulary),
        debate_tactics=_format_list(entity.debate_tactics),
        current_vibe=vibe.upper(),
        long_term_memory=memory_block,
        battle_context=context_block,
    )
