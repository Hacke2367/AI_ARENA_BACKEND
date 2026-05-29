import logging
import os
from contextlib import asynccontextmanager

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
from backend_arena.src.database.db_manager import Base, engine

_VALID_SUMMARIZER_LLMS = {"mock", "openai", "claude", "groq", "ollama", "huggingface"}


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    # Schema bootstrap (dev/local only). Production should run `alembic upgrade head`.
    if os.getenv("ARENA_AUTO_CREATE_SCHEMA", "0") == "1":
        Base.metadata.create_all(bind=engine)
        log.info("ARENA_AUTO_CREATE_SCHEMA=1 — created any missing tables.")

    log.info("Arena engine startup complete. Summariser: %s", summarizer_llm)
    yield


app = FastAPI(
    title="AI Arena Fight — Backend Engine",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
