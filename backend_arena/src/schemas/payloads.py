from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArenaBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VoiceParams(ArenaBaseModel):
    id: str = Field(..., min_length=1)
    speed: float = Field(..., ge=0.5, le=2.0)


class Telemetry(ArenaBaseModel):
    sentiment_score: int = Field(..., ge=-100, le=100)
    aggression_level: int = Field(..., ge=0, le=100)


class MatchConfig(ArenaBaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    turn_limit: int = Field(..., ge=1, le=50)
    current_vibe: Literal["logical", "emotional", "chaotic"]


class EntityConfig(ArenaBaseModel):
    selected_llm: Literal["mock", "openai", "claude", "ollama", "groq"]
    persona_name: str = Field(..., min_length=2, max_length=50)
    logic_core_belief: str = Field(..., min_length=10, max_length=1000)
    trigger_point: str = Field(..., min_length=5, max_length=1000)
    voice_id: str = Field(..., min_length=2, max_length=50)
    voice_speed: float = Field(..., ge=0.5, le=2.0)


class InitializeBattleRequest(ArenaBaseModel):
    match_config: MatchConfig
    entity_1: EntityConfig
    entity_2: EntityConfig


class ExecuteActionRequest(ArenaBaseModel):
    battle_id: str = Field(..., min_length=5)
    action_type: Literal["next_turn", "context_bomb", "kill_switch"]


class ExecuteActionResponse(ArenaBaseModel):
    speaker: str = Field(..., min_length=2)
    internal_monologue: str = Field(..., min_length=1)
    spoken_dialogue: str = Field(..., min_length=1)
    tts_ready_text: str = Field(..., min_length=1)
    voice_params: VoiceParams
    telemetry: Telemetry


class InitializeBattleResponse(ArenaBaseModel):
    battle_id: str = Field(..., min_length=5)
    status: str = Field(default="initialized")
    message: str
