import logging
import os

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend_arena.src.database.db_manager import BattleMemory
from backend_arena.src.engine import llm_router
from backend_arena.src.schemas.types import ChatMessage

log = logging.getLogger(__name__)

_SUMMARIZER_SYSTEM = """\
Act as a neutral, uncensored referee. Merge the OLD SUMMARY and the NEW MESSAGES into \
a single, updated summary.

Rules:
1. Be brutally specific — write WHO said WHAT and WHO scored the logical point.
2. Preserve specific insults, slang, Hinglish, and data points verbatim if significant. \
DO NOT sanitize.
3. Maintain an objective tally of whose arguments are logically dominating.
4. Hard cap: {max_words} words. Compress older, less-critical facts if needed.
{overflow_override}
Output ONLY the updated summary text. No JSON. No headers. No preamble."""


def run_memory_compression(
    battle_id: str,
    old_summary: str,
    evicted_messages: list[ChatMessage],
    current_turn: int,
    db: Session,
) -> str:
    """
    Call the summariser LLM and upsert the result into battle_memory.

    Exceptions are NOT caught here — they bubble up to fight_loop.py, which
    logs a warning and breaks the eviction loop (self-healing: messages stay
    in the active window and compression retries on the next turn).
    """
    max_words = int(os.getenv("ARENA_SUMMARY_MAX_WORDS", "150"))
    summarizer_llm = os.getenv("SUMMARIZER_LLM", "groq")

    overflow_override = ""
    if len(old_summary) > 2000:
        overflow_override = (
            "[URGENT: Compress existing facts. Output MUST be under 100 words]"
        )

    evicted_text = "\n".join(
        f"[{m.role.upper()}]: {m.content}" for m in evicted_messages
    )
    user_msg = ChatMessage(
        role="user",
        content=(
            f"OLD SUMMARY:\n{old_summary}\n\n"
            f"NEW MESSAGES:\n{evicted_text}\n\n"
            "Generate the updated summary now."
        ),
    )

    adapter = llm_router.route(summarizer_llm)
    system_prompt = _SUMMARIZER_SYSTEM.format(
        max_words=max_words,
        overflow_override=overflow_override,
    )
    new_summary = adapter(system_prompt, [user_msg])

    stmt = (
        sqlite_insert(BattleMemory)
        .values(
            battle_id=battle_id,
            summary_text=new_summary,
            last_summarized_turn=current_turn,
        )
        .on_conflict_do_update(
            index_elements=["battle_id"],
            set_={
                "summary_text": new_summary,
                "last_summarized_turn": current_turn,
            },
        )
    )
    db.execute(stmt)

    return new_summary
