import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend_arena.src.engine.fight_loop import MatchManager
from backend_arena.src.schemas.payloads import (
    ExecuteActionRequest,
    ExecuteActionResponse,
    InitializeBattleRequest,
    InitializeBattleResponse,
)

router = APIRouter()

_manager = MatchManager()


def get_match_manager() -> MatchManager:
    return _manager


@router.get("/health")
async def health() -> dict:
    return {"status": "online", "version": "1.0.0"}


@router.post("/initialize_battle", response_model=InitializeBattleResponse)
async def initialize_battle(
    payload: InitializeBattleRequest,
    manager: MatchManager = Depends(get_match_manager),
) -> InitializeBattleResponse:
    try:
        battle_id = manager.create_battle(payload)
        return InitializeBattleResponse(
            battle_id=battle_id,
            status="initialized",
            message=(
                f"Battle '{payload.match_config.topic}' initialized: "
                f"{payload.entity_1.persona_name} vs {payload.entity_2.persona_name}."
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Battle initialization failed") from exc


@router.post("/execute_action", response_model=ExecuteActionResponse)
async def execute_action(
    payload: ExecuteActionRequest,
    manager: MatchManager = Depends(get_match_manager),
) -> ExecuteActionResponse:
    if manager.get_battle(payload.battle_id) is None:
        raise HTTPException(status_code=404, detail="Battle session expired or invalid")

    if manager.get_battle_status(payload.battle_id) == "paused" and payload.action_type == "next_turn":
        raise HTTPException(status_code=400, detail="Invalid action for current state")

    dispatch = {
        "next_turn": manager.next_turn,
        "context_bomb": manager.context_bomb,
        "kill_switch": manager.kill_switch,
    }

    try:
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, dispatch[payload.action_type], payload.battle_id),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM gateway timeout")
