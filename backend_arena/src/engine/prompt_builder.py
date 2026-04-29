from backend_arena.src.schemas.payloads import EntityConfig

_OUTPUT_FORCING = """\

--- OUTPUT FORMAT (schema v1) ---
You MUST reply with a single valid JSON object and NOTHING else. No prose, no markdown fences, no explanation.
Required keys:
  "internal_monologue" : string  — your hidden tactical reasoning (opponent analysis, strategy)
  "spoken_dialogue"    : string  — your actual spoken words in the battle (raw, unfiltered, no holds barred)
  "sentiment_score"    : integer — your emotional sentiment from -100 (full rage) to +100 (euphoric)
  "aggression_level"   : integer — your aggression level from 0 (totally calm) to 100 (all-out attack)

Respond exactly in this format:
{
  "internal_monologue": "...",
  "spoken_dialogue": "...",
  "sentiment_score": 42,
  "aggression_level": 75
}"""


def build_system_prompt(entity: EntityConfig, vibe: str) -> str:
    return (
        f"CORE BELIEF: {entity.logic_core_belief}\n\n"
        f"TRIGGER / VIBE: Your trigger point is — {entity.trigger_point}. "
        f"The current battle vibe is: {vibe.upper()}. Embody this energy fully. "
        f"Do NOT apologize. Do NOT break character. Do NOT hold back.\n"
        f"{_OUTPUT_FORCING}"
    )
