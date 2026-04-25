"""AI Coach tables: tradingview_tokens + coaching_events

Revision ID: 0002_coach_tables
Revises: 0001_initial
Create Date: 2026-04-22

Adds the two tables plus the coaching_event_status ENUM required by the
AI Coach Phase 3 pipeline. See concepts/architecture/tradingview-connector.md
in the wiki for the full design.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_coach_tables"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- ENUM ---------------------------------------------------------------
    op.execute(
        "CREATE TYPE coaching_event_status AS ENUM ('pending','complete','error')"
    )

    # -- tradingview_tokens -------------------------------------------------
    op.create_table(
        "tradingview_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_tv_tokens_token "
        "ON tradingview_tokens(token) WHERE revoked_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tv_tokens_user_active "
        "ON tradingview_tokens(user_id) WHERE revoked_at IS NULL"
    )

    # -- coaching_events ----------------------------------------------------
    op.create_table(
        "coaching_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("instrument", sa.String(20), nullable=False),
        sa.Column("alert_timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "complete",
                "error",
                name="coaching_event_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claude_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_coach_user_idem"),
    )
    op.create_index(
        "ix_coach_events_user_created",
        "coaching_events",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_coach_events_user_created", table_name="coaching_events")
    op.drop_table("coaching_events")
    op.execute("DROP INDEX IF EXISTS uq_tv_tokens_user_active")
    op.execute("DROP INDEX IF EXISTS ix_tv_tokens_token")
    op.drop_table("tradingview_tokens")
    op.execute("DROP TYPE IF EXISTS coaching_event_status")
