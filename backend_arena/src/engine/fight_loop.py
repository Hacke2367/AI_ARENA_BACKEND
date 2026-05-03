import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

from sqlalchemy.orm import Session

from backend_arena.src.database.db_manager import Battle, BattleMemory, ChatHistory
from backend_arena.src.database.memory_engine import run_memory_compression
from backend_arena.src.engine import llm_router, prompt_builder
from backend_arena.src.exceptions import BattleNotFoundError, BattleTurnLimitError
from backend_arena.src.schemas.payloads import (
    EntityConfig,
    ExecuteActionResponse,
    InitializeBattleRequest,
    Telemetry,
    VoiceParams,
)
from backend_arena.src.schemas.types import ChatMessage
from backend_arena.src.utils import tts_sanitizer

log = logging.getLogger(__name__)

_ARENA_MAX_HISTORY_TURNS = int(os.getenv("ARENA_MAX_HISTORY_TURNS", "6"))
# window[0] is always the pinned system-prompt slot; +1 accounts for it
_EVICTION_THRESHOLD = (_ARENA_MAX_HISTORY_TURNS * 2) + 1
_SUMMARIZER_TIMEOUT_S = float(os.getenv("SUMMARIZER_TIMEOUT_S", "5.0"))
_SCHEMA_VERSION = "1.0"

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"\{.*?\}", re.DOTALL)

_FALLBACK_STUB = {
    "internal_monologue": "SYSTEM FAULT: Thought process resolution failed.",
    "spoken_dialogue": "[CONNECTION LOST] My mind went blank for a second.",
    "sentiment_score": 0,
    "aggression_level": 0,
}


def _parse_llm_output(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(raw)
    if m:
        return json.loads(m.group(1))
    m = _BARE_JSON.search(raw)
    if m:
        return json.loads(m.group(0))
    raise json.JSONDecodeError("No JSON found in LLM output", raw, 0)


class MatchManager:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_battle(self, payload: InitializeBattleRequest) -> str:
        battle_id = str(uuid.uuid4())
        schema_tag = {"schema_version": _SCHEMA_VERSION}
        db_battle = Battle(
            id=battle_id,
            match_config={**payload.match_config.model_dump(), **schema_tag},
            entity_1={**payload.entity_1.model_dump(), **schema_tag},
            entity_2={**payload.entity_2.model_dump(), **schema_tag},
            turn=0,
            status="active",
        )
        self.db.add(db_battle)
        self.db.commit()
        log.info(
            "Battle created: %s (%s vs %s)",
            battle_id,
            payload.entity_1.persona_name,
            payload.entity_2.persona_name,
        )
        return battle_id

    def get_battle(self, battle_id: str) -> Optional[Battle]:
        return self.db.get(Battle, battle_id)

    def get_battle_status(self, battle_id: str) -> Optional[str]:
        battle = self.db.get(Battle, battle_id)
        return battle.status if battle else None

    def next_turn(self, battle_id: str) -> ExecuteActionResponse:
        battle = self.db.get(Battle, battle_id)
        if battle is None:
            raise BattleNotFoundError(battle_id)

        mc = battle.match_config
        turn = battle.turn

        if battle.status == "complete" or turn >= mc["turn_limit"]:
            raise BattleTurnLimitError(f"Battle {battle_id!r} is complete")

        entity_key = "entity_1" if turn % 2 == 0 else "entity_2"
        raw_entity = battle.entity_1 if entity_key == "entity_1" else battle.entity_2
        entity = EntityConfig(
            **{k: v for k, v in raw_entity.items() if k != "schema_version"}
        )

        # Fetch long-term memory summary (empty string if none exists yet)
        memory_row = self.db.get(BattleMemory, battle_id)
        long_term = memory_row.summary_text if memory_row else ""

        # Build system prompt with memory injected at the top
        system_prompt = prompt_builder.build_system_prompt(
            entity, mc["current_vibe"], long_term
        )

        # Reconstruct context window from all non-summarized DB rows.
        # window[0] = pinned system-prompt entry (id=None, never evicted).
        # window[1:] = non-summarized chat_history rows ordered by creation time.
        history_rows = (
            self.db.query(ChatHistory)
            .filter(
                ChatHistory.battle_id == battle_id,
                ChatHistory.is_summarized == False,  # noqa: E712
            )
            .order_by(ChatHistory.created_at.asc())
            .all()
        )
        window: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt, id=None)
        ] + [
            ChatMessage(role=r.role, content=r.content, id=r.id)
            for r in history_rows
        ]

        # Build the user message for this turn
        if battle.last_spoken is None:
            user_content = (
                f"[BATTLE START] Topic: {mc['topic']}. Make your opening move."
            )
        else:
            user_content = battle.last_spoken

        # call_history = non-pinned history + new user prompt (system prompt is separate)
        call_history = list(window[1:]) + [ChatMessage(role="user", content=user_content)]

        adapter = llm_router.route(entity.selected_llm)
        raw = adapter(system_prompt, call_history)

        try:
            result = _parse_llm_output(raw)
        except json.JSONDecodeError:
            log.warning(
                "JSON decode failed on first attempt (battle=%s). Raw: %.300s",
                battle_id,
                raw,
            )
            raw2 = adapter(system_prompt, call_history)
            try:
                result = _parse_llm_output(raw2)
            except json.JSONDecodeError:
                log.warning(
                    "JSON decode failed on retry (battle=%s). Using fallback stub.",
                    battle_id,
                )
                result = dict(_FALLBACK_STUB)

        spoken: str = result["spoken_dialogue"]
        tts_text = tts_sanitizer.sanitize(spoken) or spoken

        # Persist new messages; flush to obtain DB-assigned PKs before eviction
        new_user_row = ChatHistory(
            battle_id=battle_id, role="user", content=user_content
        )
        new_asst_row = ChatHistory(
            battle_id=battle_id, role="assistant", content=spoken
        )
        self.db.add(new_user_row)
        self.db.add(new_asst_row)
        self.db.flush()

        # Append to window with their DB PKs populated
        window.append(ChatMessage(role="user", content=user_content, id=new_user_row.id))
        window.append(ChatMessage(role="assistant", content=spoken, id=new_asst_row.id))

        # --- Recursive Eviction + Summarisation Loop ---
        # window[0] is the pinned system-prompt slot and is NEVER evicted.
        # Eviction always targets window[1] and window[2] (oldest non-pinned pair).
        # On any failure the loop breaks immediately — messages remain in the active
        # window with is_summarized=False, so compression retries on the next turn.
        current_summary = long_term
        while len(window) > _EVICTION_THRESHOLD:
            if len(window) < 3:
                break
            evicted = [window[1], window[2]]
            try:
                with ThreadPoolExecutor(max_workers=1) as _pool:
                    _future = _pool.submit(
                        run_memory_compression,
                        battle_id,
                        current_summary,
                        evicted,
                        turn,
                        self.db,
                    )
                    current_summary = _future.result(timeout=_SUMMARIZER_TIMEOUT_S)

                # Update is_summarized strictly by PK — never by content or role
                self.db.query(ChatHistory).filter(
                    ChatHistory.id == evicted[0].id
                ).update({"is_summarized": True})
                self.db.query(ChatHistory).filter(
                    ChatHistory.id == evicted[1].id
                ).update({"is_summarized": True})

                del window[2]
                del window[1]

            except FuturesTimeout:
                log.warning(
                    "Summariser timed out (battle=%s, turn=%d, limit=%.1fs) — "
                    "retaining window for next-turn retry.",
                    battle_id,
                    turn,
                    _SUMMARIZER_TIMEOUT_S,
                )
                break
            except Exception as exc:
                log.warning(
                    "Memory compression failed (battle=%s, turn=%d): %s — "
                    "retaining window for next-turn retry.",
                    battle_id,
                    turn,
                    exc,
                )
                break

        # Persist updated battle state
        battle.turn += 1
        battle.last_spoken = spoken
        if battle.turn >= mc["turn_limit"]:
            battle.status = "complete"

        self.db.commit()

        return ExecuteActionResponse(
            speaker=entity_key,
            internal_monologue=result["internal_monologue"],
            spoken_dialogue=spoken,
            tts_ready_text=tts_text,
            voice_params=VoiceParams(id=entity.voice_id, speed=entity.voice_speed),
            telemetry=Telemetry(
                sentiment_score=int(result["sentiment_score"]),
                aggression_level=int(result["aggression_level"]),
            ),
        )

    def context_bomb(self, battle_id: str, text: str) -> ExecuteActionResponse:
        battle = self.db.get(Battle, battle_id)
        if battle is None:
            raise BattleNotFoundError(battle_id)
        bomb_row = ChatHistory(
            battle_id=battle_id,
            role="system",
            content=f"[SYSTEM OVERRIDE]: {text}",
        )
        self.db.add(bomb_row)
        self.db.commit()
        return self.next_turn(battle_id)

    def kill_switch(self, battle_id: str) -> ExecuteActionResponse:
        battle = self.db.get(Battle, battle_id)
        if battle is None:
            raise BattleNotFoundError(battle_id)
        battle.status = "paused"
        self.db.commit()
        log.info("Kill switch triggered for battle %s", battle_id)
        return ExecuteActionResponse(
            speaker="system",
            internal_monologue="[PAUSED]",
            spoken_dialogue="[PAUSED]",
            tts_ready_text="Battle paused.",
            voice_params=VoiceParams(id="system", speed=1.0),
            telemetry=Telemetry(sentiment_score=0, aggression_level=0),
        )
