from typing import Optional

from backend_arena.src.schemas.payloads import ExecuteActionResponse, InitializeBattleRequest


class MatchManager:
    def create_battle(self, payload: InitializeBattleRequest) -> str:
        raise NotImplementedError

    def get_battle(self, battle_id: str) -> Optional[dict]:
        return None  # stub: every battle_id is "not found" until Feature 03

    def get_battle_status(self, battle_id: str) -> Optional[str]:
        return None  # stub: no state until Feature 03

    def next_turn(self, battle_id: str) -> ExecuteActionResponse:
        raise NotImplementedError

    def context_bomb(self, battle_id: str) -> ExecuteActionResponse:
        raise NotImplementedError

    def kill_switch(self, battle_id: str) -> ExecuteActionResponse:
        raise NotImplementedError
