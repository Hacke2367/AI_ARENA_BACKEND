from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    current_vibe: Literal[
        "logical", "emotional", "chaotic",
        "opening", "heated", "cornered", "victory_lap",
    ]
    # Shared world-premise both LLMs accept as absolute truth (static for the full battle).
    # Optional — omitting it is fully backward-compatible.
    battle_context: Optional[str] = Field(default=None, max_length=2000)


class EntityConfig(ArenaBaseModel):
    selected_llm: Literal["mock", "openai", "claude", "ollama", "groq", "huggingface"]
    persona_name: str = Field(..., min_length=2, max_length=50)
    # Optional — falls back to a neutral default if not provided
    logic_core_belief: Optional[str] = Field(
        default="Engage in debate using logic, reasoning, and evidence.",
        min_length=10,
        max_length=1000,
    )
    # Optional — falls back to a neutral default if not provided
    trigger_point: Optional[str] = Field(
        default="Respond assertively when your position is challenged.",
        min_length=5,
        max_length=1000,
    )
    voice_id: str = Field(..., min_length=2, max_length=50)
    voice_speed: float = Field(..., ge=0.5, le=2.0)
    # Layer 1 DNA fields — Optional for backward compatibility
    persona_id: Optional[str] = None
    backstory: Optional[str] = None
    vocabulary: Optional[list[str]] = None
    debate_tactics: Optional[list[str]] = None


class InitializeBattleRequest(ArenaBaseModel):
    match_config: MatchConfig
    entity_1: EntityConfig
    entity_2: EntityConfig


class ExecuteActionRequest(ArenaBaseModel):
    battle_id: str = Field(..., min_length=5)
    action_type: Literal["next_turn", "context_bomb", "kill_switch"]
    context_text: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _context_text_required_for_bomb(self) -> "ExecuteActionRequest":
        if self.action_type == "context_bomb" and not self.context_text:
            raise ValueError("context_text is required when action_type is 'context_bomb'")
        return self


class ExecuteActionResponse(ArenaBaseModel):
    speaker: Literal["entity_1", "entity_2", "system"]
    internal_monologue: str = Field(..., min_length=1)
    spoken_dialogue: str = Field(..., min_length=1)
    tts_ready_text: str = Field(..., min_length=1)
    voice_params: VoiceParams
    telemetry: Telemetry


class InitializeBattleResponse(ArenaBaseModel):
    battle_id: str = Field(..., min_length=5)
    status: str = Field(default="initialized")
    message: str
