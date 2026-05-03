"""create initial schema: battles, chat_history, battle_memory

Revision ID: 8a3b2c1d0e4f
Revises:
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8a3b2c1d0e4f"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "battles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("match_config", sa.JSON(), nullable=False),
        sa.Column("entity_1", sa.JSON(), nullable=False),
        sa.Column("entity_2", sa.JSON(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("last_spoken", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("battle_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_summarized", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["battle_id"], ["battles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_history_battle_summarized",
        "chat_history",
        ["battle_id", "is_summarized"],
    )
    op.create_table(
        "battle_memory",
        sa.Column("battle_id", sa.String(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "last_summarized_turn", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.ForeignKeyConstraint(["battle_id"], ["battles.id"]),
        sa.PrimaryKeyConstraint("battle_id"),
    )


def downgrade() -> None:
    op.drop_table("battle_memory")
    op.drop_index("ix_chat_history_battle_summarized", table_name="chat_history")
    op.drop_table("chat_history")
    op.drop_table("battles")
