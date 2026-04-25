"""
Raw SQL analytics queries.
All closed-trade queries filter: user_id = :user_id AND NOT is_deleted AND outcome IS NOT NULL.
"""
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DOW_NAMES = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
              4: "Thursday", 5: "Friday", 6: "Saturday"}

# R-distribution constants
_R_MIN = -10.0
_R_MAX = 10.0
_R_BINS = 40
_BIN_WIDTH = (_R_MAX - _R_MIN) / _R_BINS


async def get_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    sql = text("""
        WITH closed AS (
            SELECT
                outcome,
                r_multiple,
                setup_type,
                trade_date,
                created_at,
                ROW_NUMBER() OVER (ORDER BY trade_date ASC, created_at ASC) AS rn
            FROM trades
            WHERE user_id       = :user_id
              AND NOT is_deleted
              AND status        = 'closed'
              AND outcome IS NOT NULL
        ),
        grouped AS (
            SELECT
                outcome,
                rn,
                rn - ROW_NUMBER() OVER (PARTITION BY outcome ORDER BY rn) AS grp
            FROM closed
        ),
        streak_lens AS (
            SELECT outcome, grp, COUNT(*) AS len
            FROM grouped
            GROUP BY outcome, grp
        ),
        current_grp AS (
            -- Group that contains the most recent trade
            SELECT g.outcome, g.grp
            FROM grouped g
            WHERE g.rn = (SELECT MAX(rn) FROM closed)
        ),
        setup_win_rates AS (
            SELECT
                setup_type::text                                          AS st,
                COUNT(*)                                                  AS total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)         AS wins
            FROM closed
            WHERE setup_type IS NOT NULL
            GROUP BY setup_type
            HAVING COUNT(*) >= 3
        )
        SELECT
            (
                SELECT COUNT(*)
                FROM trades
                WHERE user_id = :user_id AND NOT is_deleted
            )                                                             AS total_trades,
            COUNT(*)                                                      AS closed_trades,
            ROUND(
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                             AS win_rate,
            ROUND(AVG(r_multiple)::numeric, 4)                           AS avg_r_multiple,
            (
                SELECT st FROM setup_win_rates
                ORDER BY wins::float / total DESC
                LIMIT 1
            )                                                             AS best_setup_type,
            COALESCE((
                SELECT sl.len
                FROM streak_lens sl
                JOIN current_grp cg ON sl.outcome = cg.outcome AND sl.grp = cg.grp
                WHERE sl.outcome = 'win'
            ), 0)                                                         AS current_win_streak,
            COALESCE((
                SELECT sl.len
                FROM streak_lens sl
                JOIN current_grp cg ON sl.outcome = cg.outcome AND sl.grp = cg.grp
                WHERE sl.outcome = 'loss'
            ), 0)                                                         AS current_loss_streak,
            COALESCE(
                (SELECT MAX(len) FROM streak_lens WHERE outcome = 'win'), 0
            )                                                             AS longest_win_streak,
            COALESCE(
                (SELECT MAX(len) FROM streak_lens WHERE outcome = 'loss'), 0
            )                                                             AS longest_loss_streak
        FROM closed
    """)
    row = (await db.execute(sql, {"user_id": str(user_id)})).mappings().one()
    return dict(row)


async def get_by_setup(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            setup_type::text                                              AS "group",
            COUNT(*)                                                      AS total,
            SUM(CASE WHEN outcome = 'win'       THEN 1 ELSE 0 END)       AS wins,
            SUM(CASE WHEN outcome = 'loss'      THEN 1 ELSE 0 END)       AS losses,
            SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END)       AS breakevens,
            ROUND(
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                             AS win_rate,
            ROUND(AVG(r_multiple)::numeric, 4)                           AS avg_r_multiple
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
          AND setup_type IS NOT NULL
        GROUP BY setup_type
        ORDER BY win_rate DESC NULLS LAST
    """)
    rows = (await db.execute(sql, {"user_id": str(user_id)})).mappings().all()
    return [dict(r) for r in rows]


async def get_by_session(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            session::text                                                 AS "group",
            COUNT(*)                                                      AS total,
            SUM(CASE WHEN outcome = 'win'       THEN 1 ELSE 0 END)       AS wins,
            SUM(CASE WHEN outcome = 'loss'      THEN 1 ELSE 0 END)       AS losses,
            SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END)       AS breakevens,
            ROUND(
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                             AS win_rate,
            ROUND(AVG(r_multiple)::numeric, 4)                           AS avg_r_multiple
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
          AND session IS NOT NULL
        GROUP BY session
        ORDER BY win_rate DESC NULLS LAST
    """)
    rows = (await db.execute(sql, {"user_id": str(user_id)})).mappings().all()
    return [dict(r) for r in rows]


async def get_by_instrument(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            instrument                                                    AS "group",
            COUNT(*)                                                      AS total,
            SUM(CASE WHEN outcome = 'win'       THEN 1 ELSE 0 END)       AS wins,
            SUM(CASE WHEN outcome = 'loss'      THEN 1 ELSE 0 END)       AS losses,
            SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END)       AS breakevens,
            ROUND(
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                             AS win_rate,
            ROUND(AVG(r_multiple)::numeric, 4)                           AS avg_r_multiple
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
        GROUP BY instrument
        ORDER BY win_rate DESC NULLS LAST
    """)
    rows = (await db.execute(sql, {"user_id": str(user_id)})).mappings().all()
    return [dict(r) for r in rows]


async def get_by_day_of_week(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            EXTRACT(DOW FROM trade_date)::int                             AS day_of_week,
            COUNT(*)                                                      AS total,
            SUM(CASE WHEN outcome = 'win'       THEN 1 ELSE 0 END)       AS wins,
            SUM(CASE WHEN outcome = 'loss'      THEN 1 ELSE 0 END)       AS losses,
            SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END)       AS breakevens,
            ROUND(
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0), 4
            )                                                             AS win_rate,
            ROUND(AVG(r_multiple)::numeric, 4)                           AS avg_r_multiple
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
        GROUP BY day_of_week
        ORDER BY day_of_week ASC
    """)
    rows = (await db.execute(sql, {"user_id": str(user_id)})).mappings().all()
    return [
        {**dict(r), "day_name": _DOW_NAMES.get(r["day_of_week"], "Unknown")}
        for r in rows
    ]


async def get_mistakes(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            unnest(mistake_tags)  AS tag,
            COUNT(*)              AS count
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
          AND mistake_tags IS NOT NULL
        GROUP BY tag
        ORDER BY count DESC
    """)
    rows = (await db.execute(sql, {"user_id": str(user_id)})).mappings().all()
    return [dict(r) for r in rows]


async def get_r_distribution(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    sql = text("""
        SELECT
            WIDTH_BUCKET(r_multiple, :r_min, :r_max, :bins)  AS bucket,
            COUNT(*)                                          AS count
        FROM trades
        WHERE user_id       = :user_id
          AND NOT is_deleted
          AND outcome IS NOT NULL
          AND r_multiple IS NOT NULL
          AND r_multiple BETWEEN :r_min AND :r_max
        GROUP BY bucket
        ORDER BY bucket ASC
    """)
    rows = (await db.execute(sql, {
        "user_id": str(user_id),
        "r_min": _R_MIN,
        "r_max": _R_MAX,
        "bins": _R_BINS,
    })).mappings().all()

    return [
        {
            "bucket": r["bucket"],
            "r_low":  Decimal(str(round(_R_MIN + (r["bucket"] - 1) * _BIN_WIDTH, 4))),
            "r_high": Decimal(str(round(_R_MIN + r["bucket"] * _BIN_WIDTH, 4))),
            "count":  r["count"],
        }
        for r in rows
    ]
