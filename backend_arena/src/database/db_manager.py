import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = f"sqlite:///{os.getenv('ARENA_DB_PATH', './arena.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class Battle(Base):
    __tablename__ = "battles"

    id = Column(String, primary_key=True)
    match_config = Column(JSON, nullable=False)
    entity_1 = Column(JSON, nullable=False)
    entity_2 = Column(JSON, nullable=False)
    turn = Column(Integer, default=0, nullable=False)
    status = Column(String, default="active", nullable=False)
    last_spoken = Column(Text, nullable=True)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    battle_id = Column(String, ForeignKey("battles.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    is_summarized = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_chat_history_battle_summarized", "battle_id", "is_summarized"),
    )


class BattleMemory(Base):
    __tablename__ = "battle_memory"

    battle_id = Column(String, ForeignKey("battles.id"), primary_key=True)
    summary_text = Column(Text, nullable=False, default="")
    last_summarized_turn = Column(Integer, default=0, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
