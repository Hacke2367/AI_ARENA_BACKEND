import json
import logging
import os
import re
import uuid
from typing import Optional

from backend_arena.src.engine import llm_router, prompt_builder
from backend_arena.src.exceptions import BattleNotFoundError, BattleTurnLimitError
from backend_arena.src.schemas.payloads import (
    EntityConfig,
    ExecuteActionResponse,
    InitializeBattleRequest,
    MatchConfig,
    Telemetry,
    VoiceParams,
)
from backend_arena.src.schemas.types import ChatMessage
from backend_arena.src.utils import tts_sanitizer

log = logging.getLogger(__name__)

_ARENA_MAX_HISTORY_TURNS = int(os.getenv("ARENA_MAX_HISTORY_TURNS", "6"))

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"\{.*?\}", re.DOTALL)

_FALLBACK_STUB = {
    "internal_monologue": "SYSTEM FAULT: Thought process resolution failed.",
    "spoken_dialogue": "[CONNECTION LOST] My mind went blank for a second.",
    "sentiment_score": 0,
    "aggression_level": 0,
}

_active_battles: dict[str, dict] = {}


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
    def create_battle(self, payload: InitializeBattleRequest) -> str:
        battle_id = str(uuid.uuid4())
        _active_battles[battle_id] = {
            "match_config": payload.match_config,
            "entity_1": payload.entity_1,
            "entity_2": payload.entity_2,
            "history": [],
            "turn": 0,
            "status": "active",
            "last_spoken": None,
        }
        log.info(
            "Battle created: %s (%s vs %s)",
            battle_id,
            payload.entity_1.persona_name,
            payload.entity_2.persona_name,
        )
        return battle_id

    def get_battle(self, battle_id: str) -> Optional[dict]:
        return _active_battles.get(battle_id)

    def get_battle_status(self, battle_id: str) -> Optional[str]:
        state = _active_battles.get(battle_id)
        return state["status"] if state else None

    def next_turn(self, battle_id: str) -> ExecuteActionResponse:
        state = _active_battles.get(battle_id)
        if state is None:
            raise BattleNotFoundError(battle_id)

        if state["status"] == "complete" or state["turn"] >= state["match_config"].turn_limit:
            raise BattleTurnLimitError(f"Battle {battle_id!r} is complete")

        turn: int = state["turn"]
        entity_key = "entity_1" if turn % 2 == 0 else "entity_2"
        entity: EntityConfig = state[entity_key]
        match_config: MatchConfig = state["match_config"]

        if state["last_spoken"] is None:
            user_content = f"[BATTLE START] Topic: {match_config.topic}. Make your opening move."
        else:
            user_content = state["last_spoken"]
        user_msg = ChatMessage(role="user", content=user_content)

        call_history = list(state["history"]) + [user_msg]
        system_prompt = prompt_builder.build_system_prompt(entity, match_config.current_vibe)
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
                log.warning("JSON decode failed on retry (battle=%s). Using fallback stub.", battle_id)
                result = dict(_FALLBACK_STUB)

        spoken: str = result["spoken_dialogue"]
        tts_text = tts_sanitizer.sanitize(spoken) or spoken

        state["history"].append(user_msg)
        state["history"].append(ChatMessage(role="assistant", content=spoken))
        while len(state["history"]) > _ARENA_MAX_HISTORY_TURNS * 2:
            state["history"].pop(0)
            state["history"].pop(0)

        state["last_spoken"] = spoken
        state["turn"] += 1
        if state["turn"] >= match_config.turn_limit:
            state["status"] = "complete"

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
        state = _active_battles.get(battle_id)
        if state is None:
            raise BattleNotFoundError(battle_id)
        state["history"].append(ChatMessage(role="system", content=f"[SYSTEM OVERRIDE]: {text}"))
        return self.next_turn(battle_id)

    def kill_switch(self, battle_id: str) -> ExecuteActionResponse:
        state = _active_battles.get(battle_id)
        if state is None:
            raise BattleNotFoundError(battle_id)
        state["status"] = "paused"
        log.info("Kill switch triggered for battle %s", battle_id)
        return ExecuteActionResponse(
            speaker="system",
            internal_monologue="[PAUSED]",
            spoken_dialogue="[PAUSED]",
            tts_ready_text="Battle paused.",
            voice_params=VoiceParams(id="system", speed=1.0),
            telemetry=Telemetry(sentiment_score=0, aggression_level=0),
        )
