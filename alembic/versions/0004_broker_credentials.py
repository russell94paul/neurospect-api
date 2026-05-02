"""Broker credentials table + Tradovate fill ID columns on trades

Revision ID: 0004_broker_credentials
Revises: 0003_add_position_size
Create Date: 2026-04-26

Adds the tradovate_environment ENUM, the broker_credentials table (encrypted
Tradovate username/password + OAuth tokens), and two BIGINT fill-ID columns on
trades for idempotent fill application.

See broker-integration workstream tracker in neurospect-wiki for full design.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_broker_credentials"
down_revision = "0003_add_position_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- ENUM ---------------------------------------------------------------
    op.execute("CREATE TYPE tradovate_environment AS ENUM ('demo', 'live')")

    # -- broker_credentials -------------------------------------------------
    op.create_table(
        "broker_credentials",
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
        sa.Column("broker", sa.String(32), nullable=False, server_default="tradovate"),
        sa.Column(
            "environment",
            postgresql.ENUM("demo", "live", name="tradovate_environment", create_type=False),
            nullable=False,
            server_default="demo",
        ),
        sa.Column("username_encrypted", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("md_access_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_auth_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_auth_error", sa.Text(), nullable=True),
        sa.Column(
            "is_disconnected",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("user_id", "broker", name="uq_broker_creds_user_broker"),
    )

    # -- trades: Tradovate fill ID columns (idempotency) --------------------
    op.add_column("trades", sa.Column("tradovate_fill_id_entry", sa.BigInteger(), nullable=True))
    op.add_column("trades", sa.Column("tradovate_fill_id_exit", sa.BigInteger(), nullable=True))

    op.execute(
        "CREATE UNIQUE INDEX ix_trades_tv_fill_entry "
        "ON trades (user_id, tradovate_fill_id_entry) "
        "WHERE tradovate_fill_id_entry IS NOT NULL AND NOT is_deleted"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_trades_tv_fill_exit "
        "ON trades (user_id, tradovate_fill_id_exit) "
        "WHERE tradovate_fill_id_exit IS NOT NULL AND NOT is_deleted"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trades_tv_fill_exit")
    op.execute("DROP INDEX IF EXISTS ix_trades_tv_fill_entry")
    op.drop_column("trades", "tradovate_fill_id_exit")
    op.drop_column("trades", "tradovate_fill_id_entry")
    op.drop_table("broker_credentials")
    op.execute("DROP TYPE IF EXISTS tradovate_environment")
