class ArenaError(Exception):
    """Base for all Arena domain errors."""


class LLMAuthError(ArenaError):
    """LLM API returned 401 or 403."""


class LLMConnectionError(ArenaError):
    """LLM endpoint is unreachable (connection refused, DNS failure, etc.)."""


class LLMTimeoutError(ArenaError):
    """LLM call exceeded the read timeout."""


class RateLimitError(ArenaError):
    """Raised after 3x exponential backoff on HTTP 429 still fails."""


class BattleNotFoundError(ArenaError):
    """battle_id is not present in active state."""


class BattleTurnLimitError(ArenaError):
    """next_turn called on a battle that is complete or at turn_limit."""


class PersonaNotFoundError(ArenaError):
    """Persona JSON file not found for the given persona_id."""
