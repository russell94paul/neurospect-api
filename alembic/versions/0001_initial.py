"""Initial schema: ENUMs, users, trades, trade_screenshots, indexes, triggers

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. updated_at trigger function (must exist before tables reference it)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ------------------------------------------------------------------
    # 2. ENUM types
    # ------------------------------------------------------------------
    op.execute("CREATE TYPE session_type AS ENUM ('asia', 'london', 'ny_am', 'ny_pm')")
    op.execute(
        "CREATE TYPE kill_zone_type AS ENUM "
        "('asia', 'london_open', 'ny_am_open', 'ny_pm_open', 'london_close')"
    )
    op.execute("CREATE TYPE bias_type AS ENUM ('bullish', 'bearish', 'neutral')")
    op.execute(
        "CREATE TYPE opp_type AS ENUM ('below_all', 'below_some', 'above_all', 'above_some')"
    )
    op.execute(
        "CREATE TYPE setup_type AS ENUM "
        "('consolidation', 'expansion_retracement', 'reversal', "
        "'model_2022_ote', 'london', 'daily_bias', 'smt')"
    )
    op.execute(
        "CREATE TYPE pda_type AS ENUM "
        "('fvg', 'order_block', 'rejection_block', 'ote_block', 'breaker')"
    )
    op.execute("CREATE TYPE displacement_type AS ENUM ('clean', 'choppy', 'none')")
    op.execute("CREATE TYPE outcome_type AS ENUM ('win', 'loss', 'breakeven')")
    op.execute("CREATE TYPE grade_type AS ENUM ('a_plus', 'a', 'b', 'c')")
    op.execute(
        "CREATE TYPE screenshot_phase AS ENUM "
        "('before_entry', 'entry', 'higher_tf', 'exit', 'post_trade_review')"
    )
    op.execute("CREATE TYPE trade_status AS ENUM ('pre_trade', 'active', 'closed')")

    # ------------------------------------------------------------------
    # 3. users table + updated_at trigger
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE users (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            discord_id          VARCHAR(32) UNIQUE NOT NULL,
            discord_username    VARCHAR(128),
            discord_avatar_url  TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at()
    """)

    # ------------------------------------------------------------------
    # 4. trades table + updated_at trigger
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE trades (
            -- Identity
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL REFERENCES users(id),

            -- Pre-Trade
            trade_date              DATE NOT NULL,
            instrument              VARCHAR(20) NOT NULL,
            session                 session_type,
            kill_zone               kill_zone_type,
            htf_bias                bias_type,
            htf_fvg_low             DECIMAL(12,4),
            htf_fvg_high            DECIMAL(12,4),
            draw_on_liquidity       TEXT,
            dol_price_level         DECIMAL(12,4),
            opening_price_position  opp_type,
            news_flag               BOOLEAN DEFAULT false,
            setup_type              setup_type,
            narrative               TEXT,

            -- Entry (nullable until entry)
            entry_price             DECIMAL(12,4),
            entry_time              TIMESTAMPTZ,
            stop_price              DECIMAL(12,4),
            stop_logic              TEXT,
            target_price            DECIMAL(12,4),
            target_logic            TEXT,
            entry_pda               pda_type,
            displacement_quality    displacement_type,
            smt_confirmation        BOOLEAN,

            -- Post-Trade (nullable until close)
            exit_price              DECIMAL(12,4),
            exit_time               TIMESTAMPTZ,
            outcome                 outcome_type,
            r_multiple              DECIMAL(6,2),
            mae                     DECIMAL(12,4),
            mfe                     DECIMAL(12,4),
            target_reached          BOOLEAN,
            plan_followed           BOOLEAN,
            mistake_tags            TEXT[],
            quality_grade           grade_type,
            post_trade_notes        TEXT,

            -- Metadata
            status                  trade_status NOT NULL DEFAULT 'pre_trade',
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted              BOOLEAN NOT NULL DEFAULT false,
            deleted_at              TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_trades_updated_at
            BEFORE UPDATE ON trades
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at()
    """)

    # ------------------------------------------------------------------
    # 5. trade_screenshots table
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE trade_screenshots (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trade_id          UUID NOT NULL REFERENCES trades(id),
            user_id           UUID NOT NULL REFERENCES users(id),
            phase             screenshot_phase NOT NULL,
            storage_key       VARCHAR(512) NOT NULL,
            original_filename VARCHAR(256),
            content_type      VARCHAR(64),
            uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ------------------------------------------------------------------
    # 6. Indexes
    # ------------------------------------------------------------------
    # Primary query: all trades for a user ordered by date
    op.execute(
        "CREATE INDEX ix_trades_user_date ON trades (user_id, trade_date DESC)"
    )
    # Analytics breakdowns (partial — exclude soft-deleted)
    op.execute(
        "CREATE INDEX ix_trades_user_setup ON trades (user_id, setup_type) WHERE NOT is_deleted"
    )
    op.execute(
        "CREATE INDEX ix_trades_user_session ON trades (user_id, session) WHERE NOT is_deleted"
    )
    op.execute(
        "CREATE INDEX ix_trades_user_instrument ON trades (user_id, instrument) WHERE NOT is_deleted"
    )
    op.execute(
        "CREATE INDEX ix_trades_user_outcome ON trades (user_id, outcome) WHERE NOT is_deleted"
    )
    # GIN index for mistake_tags array containment queries
    op.execute(
        "CREATE INDEX ix_trades_mistake_tags ON trades USING GIN (mistake_tags) WHERE NOT is_deleted"
    )
    # Screenshots by trade
    op.execute(
        "CREATE INDEX ix_screenshots_trade ON trade_screenshots (trade_id)"
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Reverse order: indexes → tables → ENUMs → trigger function
    # ------------------------------------------------------------------

    # Indexes
    op.execute("DROP INDEX IF EXISTS ix_screenshots_trade")
    op.execute("DROP INDEX IF EXISTS ix_trades_mistake_tags")
    op.execute("DROP INDEX IF EXISTS ix_trades_user_outcome")
    op.execute("DROP INDEX IF EXISTS ix_trades_user_instrument")
    op.execute("DROP INDEX IF EXISTS ix_trades_user_session")
    op.execute("DROP INDEX IF EXISTS ix_trades_user_setup")
    op.execute("DROP INDEX IF EXISTS ix_trades_user_date")

    # Tables (triggers dropped automatically with their tables)
    op.execute("DROP TABLE IF EXISTS trade_screenshots")
    op.execute("DROP TABLE IF EXISTS trades")
    op.execute("DROP TABLE IF EXISTS users")

    # ENUMs
    op.execute("DROP TYPE IF EXISTS trade_status")
    op.execute("DROP TYPE IF EXISTS screenshot_phase")
    op.execute("DROP TYPE IF EXISTS grade_type")
    op.execute("DROP TYPE IF EXISTS outcome_type")
    op.execute("DROP TYPE IF EXISTS displacement_type")
    op.execute("DROP TYPE IF EXISTS pda_type")
    op.execute("DROP TYPE IF EXISTS setup_type")
    op.execute("DROP TYPE IF EXISTS opp_type")
    op.execute("DROP TYPE IF EXISTS bias_type")
    op.execute("DROP TYPE IF EXISTS kill_zone_type")
    op.execute("DROP TYPE IF EXISTS session_type")

    # Trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at")
