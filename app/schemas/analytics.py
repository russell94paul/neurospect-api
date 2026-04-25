from decimal import Decimal

from pydantic import BaseModel


class SummaryResponse(BaseModel):
    total_trades: int
    closed_trades: int
    win_rate: float | None           # None if no closed trades
    avg_r_multiple: float | None     # None if no closed trades with r_multiple
    best_setup_type: str | None      # setup_type with highest win rate (min 3 trades)
    current_win_streak: int
    current_loss_streak: int
    longest_win_streak: int
    longest_loss_streak: int


class BreakdownRow(BaseModel):
    """Shared shape for by-setup, by-session, by-instrument breakdowns."""
    group: str                       # the group value (e.g. "consolidation", "london")
    total: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float | None
    avg_r_multiple: float | None


class BySetupResponse(BaseModel):
    rows: list[BreakdownRow]


class BySessionResponse(BaseModel):
    rows: list[BreakdownRow]


class ByInstrumentResponse(BaseModel):
    rows: list[BreakdownRow]


class DayOfWeekRow(BaseModel):
    day_of_week: int                 # 0 = Sunday … 6 = Saturday (Postgres EXTRACT(DOW))
    day_name: str
    total: int
    wins: int
    losses: int
    breakevens: int
    win_rate: float | None
    avg_r_multiple: float | None


class ByDayOfWeekResponse(BaseModel):
    rows: list[DayOfWeekRow]


class MistakeRow(BaseModel):
    tag: str
    count: int


class MistakesResponse(BaseModel):
    rows: list[MistakeRow]


class RBucket(BaseModel):
    bucket: int
    r_low: Decimal
    r_high: Decimal
    count: int


class RDistributionResponse(BaseModel):
    bins: int = 40
    r_min: float = -10.0
    r_max: float = 10.0
    buckets: list[RBucket]
