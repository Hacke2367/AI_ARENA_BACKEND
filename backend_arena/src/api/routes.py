import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from backend_arena.src.database.db_manager import get_db
from backend_arena.src.engine.fight_loop import MatchManager
from backend_arena.src.exceptions import (
    BattleNotFoundError,
    BattleTurnLimitError,
    LLMAuthError,
    LLMConnectionError,
    LLMTimeoutError,
    PersonaNotFoundError,
    RateLimitError,
)
from backend_arena.src.schemas.payloads import (
    ExecuteActionRequest,
    ExecuteActionResponse,
    InitializeBattleRequest,
    InitializeBattleResponse,
)

router = APIRouter()


def get_match_manager(db: Session = Depends(get_db)) -> MatchManager:
    return MatchManager(db)


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
    except PersonaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception(
            "Battle init failed (entity_1=%s, entity_2=%s)",
            payload.entity_1.persona_name,
            payload.entity_2.persona_name,
        )
        raise HTTPException(status_code=500, detail="Battle initialization failed") from exc


@router.post("/execute_action", response_model=ExecuteActionResponse)
async def execute_action(
    payload: ExecuteActionRequest,
    manager: MatchManager = Depends(get_match_manager),
) -> ExecuteActionResponse:
    if manager.get_battle(payload.battle_id) is None:
        raise HTTPException(status_code=404, detail="Battle session expired or invalid")

    if (
        manager.get_battle_status(payload.battle_id) == "paused"
        and payload.action_type == "next_turn"
    ):
        raise HTTPException(
            status_code=400,
            detail="Battle is paused — use kill_switch to resume or end",
        )

    loop = asyncio.get_running_loop()

    if payload.action_type == "context_bomb":
        fn = lambda: manager.context_bomb(payload.battle_id, payload.context_text)
    elif payload.action_type == "kill_switch":
        fn = lambda: manager.kill_switch(payload.battle_id)
    else:
        fn = lambda: manager.next_turn(payload.battle_id)

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, fn),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM gateway timeout")
    except BattleNotFoundError:
        raise HTTPException(status_code=404, detail="Battle not found")
    except BattleTurnLimitError:
        raise HTTPException(status_code=409, detail="Battle is complete — turn limit reached")
    except LLMAuthError:
        raise HTTPException(status_code=502, detail="LLM authentication failed")
    except LLMConnectionError:
        raise HTTPException(status_code=503, detail="LLM endpoint unreachable")
    except LLMTimeoutError:
        raise HTTPException(status_code=504, detail="LLM read timeout")
    except RateLimitError:
        raise HTTPException(status_code=429, detail="LLM rate limited — try again later")
    except Exception as exc:
        log.exception(
            "Unhandled error in execute_action (battle=%s, action=%s)",
            payload.battle_id,
            payload.action_type,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc
