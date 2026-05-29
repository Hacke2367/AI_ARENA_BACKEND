import os

# Set BEFORE backend_arena imports so the summariser worker uses mock and the
# default file DB is never touched.
os.environ.setdefault("SUMMARIZER_LLM", "mock")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_arena.src.database.db_manager import Base, get_db
from backend_arena.src.engine import fight_loop, llm_router
from backend_arena.src.main import app
from backend_arena.src.schemas.payloads import EntityConfig, InitializeBattleRequest, MatchConfig


@pytest.fixture(autouse=True)
def _reset_router_cache():
    llm_router.route.cache_clear()
    yield
    llm_router.route.cache_clear()


@pytest.fixture
def db_session(monkeypatch):
    """
    Per-test isolated in-memory SQLite.

    StaticPool keeps a single underlying connection so that the summariser
    worker thread (which opens its own Session via fight_loop.SessionLocal)
    sees the same data as the test's main-thread session.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    # Worker thread inside fight_loop opens its own session via this name —
    # patch it to point at the test engine.
    monkeypatch.setattr(fight_loop, "SessionLocal", TestSession)

    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


@pytest.fixture
def manager(db_session):
    return fight_loop.MatchManager(db_session)


@pytest.fixture
def client(db_session):
    """
    TestClient with FastAPI's get_db dependency overridden to yield the
    test's db_session. Cleared on teardown so the override doesn't leak.
    """
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_entity():
    return EntityConfig(
        selected_llm="mock",
        persona_name="TestBot",
        logic_core_belief="Logic is the ultimate truth and cannot be defeated.",
        trigger_point="When challenged on facts, double down harder.",
        voice_id="test_voice",
        voice_speed=1.0,
    )


@pytest.fixture
def mock_battle_request(mock_entity):
    return InitializeBattleRequest(
        match_config=MatchConfig(
            topic="Is Python better than Java?",
            turn_limit=10,
            current_vibe="logical",
        ),
        entity_1=mock_entity,
        entity_2=mock_entity,
    )
