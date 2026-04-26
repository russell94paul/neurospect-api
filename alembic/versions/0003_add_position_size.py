"""Add position_size to trades

Revision ID: 0003_add_position_size
Revises: 0002_coach_tables
Create Date: 2026-04-26

Adds the `position_size` integer column to the `trades` table. Captured at
entry as the number of contracts traded. Pulled from Tradovate fill `qty`
when broker auto-populate (broker-integration workstream) is wired up.

See concepts/architecture/trade-schema.md §Entry Fields.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_position_size"
down_revision = "0002_coach_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("position_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "position_size")
