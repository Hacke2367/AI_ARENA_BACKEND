import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

log = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_arena.src.api.routes import router

app = FastAPI(title="AI Arena Fight — Backend Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

_VALID_SUMMARIZER_LLMS = {"mock", "openai", "claude", "groq", "ollama", "huggingface"}


@app.on_event("startup")
def on_startup() -> None:
    summarizer_llm = os.getenv("SUMMARIZER_LLM", "groq")
    if summarizer_llm not in _VALID_SUMMARIZER_LLMS:
        raise RuntimeError(
            f"SUMMARIZER_LLM={summarizer_llm!r} is not a recognised llm_router key. "
            f"Valid options: {_VALID_SUMMARIZER_LLMS}"
        )
    if summarizer_llm == "groq" and not os.getenv("GROQ_API_KEY"):
        log.warning(
            "GROQ_API_KEY is not set — summariser calls will fail at runtime. "
            "Set it in .env or choose a different SUMMARIZER_LLM."
        )
    log.info("Arena engine startup complete. Summariser: %s", summarizer_llm)
