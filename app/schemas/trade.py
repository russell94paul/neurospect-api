import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    BiasType,
    DisplacementType,
    GradeType,
    KillZoneType,
    OppType,
    OutcomeType,
    PdaType,
    SessionType,
    SetupType,
    TradeStatus,
)


class TradeCreate(BaseModel):
    # Required pre-trade fields
    trade_date: date
    instrument: str

    # Optional pre-trade fields
    session: SessionType | None = None
    kill_zone: KillZoneType | None = None
    htf_bias: BiasType | None = None
    htf_fvg_low: Decimal | None = None
    htf_fvg_high: Decimal | None = None
    draw_on_liquidity: str | None = None
    dol_price_level: Decimal | None = None
    opening_price_position: OppType | None = None
    news_flag: bool = False
    setup_type: SetupType | None = None
    narrative: str | None = None

    # Entry fields (provided when trade is taken)
    entry_price: Decimal | None = None
    entry_time: datetime | None = None
    position_size: int | None = None
    stop_price: Decimal | None = None
    stop_logic: str | None = None
    target_price: Decimal | None = None
    target_logic: str | None = None
    entry_pda: PdaType | None = None
    displacement_quality: DisplacementType | None = None
    smt_confirmation: bool | None = None

    # Allow creating in a non-default status (rare; triggers singleton guard if active)
    status: TradeStatus = TradeStatus.pre_trade


class TradeUpdate(BaseModel):
    """Partial update — all fields optional. Used for PATCH."""
    trade_date: date | None = None
    instrument: str | None = None
    session: SessionType | None = None
    kill_zone: KillZoneType | None = None
    htf_bias: BiasType | None = None
    htf_fvg_low: Decimal | None = None
    htf_fvg_high: Decimal | None = None
    draw_on_liquidity: str | None = None
    dol_price_level: Decimal | None = None
    opening_price_position: OppType | None = None
    news_flag: bool | None = None
    setup_type: SetupType | None = None
    narrative: str | None = None

    # Entry fields
    entry_price: Decimal | None = None
    entry_time: datetime | None = None
    position_size: int | None = None
    stop_price: Decimal | None = None
    stop_logic: str | None = None
    target_price: Decimal | None = None
    target_logic: str | None = None
    entry_pda: PdaType | None = None
    displacement_quality: DisplacementType | None = None
    smt_confirmation: bool | None = None

    # Post-trade fields
    exit_price: Decimal | None = None
    exit_time: datetime | None = None
    outcome: OutcomeType | None = None
    r_multiple: Decimal | None = None
    mae: Decimal | None = None
    mfe: Decimal | None = None
    target_reached: bool | None = None
    plan_followed: bool | None = None
    mistake_tags: list[str] | None = None
    quality_grade: GradeType | None = None
    post_trade_notes: str | None = None

    # Status (validated transition in route handler)
    status: TradeStatus | None = None


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID

    # Pre-Trade
    trade_date: date
    instrument: str
    session: SessionType | None
    kill_zone: KillZoneType | None
    htf_bias: BiasType | None
    htf_fvg_low: Decimal | None
    htf_fvg_high: Decimal | None
    draw_on_liquidity: str | None
    dol_price_level: Decimal | None
    opening_price_position: OppType | None
    news_flag: bool
    setup_type: SetupType | None
    narrative: str | None

    # Entry
    entry_price: Decimal | None
    entry_time: datetime | None
    position_size: int | None
    stop_price: Decimal | None
    stop_logic: str | None
    target_price: Decimal | None
    target_logic: str | None
    entry_pda: PdaType | None
    displacement_quality: DisplacementType | None
    smt_confirmation: bool | None

    # Post-Trade
    exit_price: Decimal | None
    exit_time: datetime | None
    outcome: OutcomeType | None
    r_multiple: Decimal | None
    mae: Decimal | None
    mfe: Decimal | None
    target_reached: bool | None
    plan_followed: bool | None
    mistake_tags: list[str] | None
    quality_grade: GradeType | None
    post_trade_notes: str | None

    # Broker fill IDs (read-only; set via apply-tradovate-fill endpoint in 1c)
    tradovate_fill_id_entry: int | None
    tradovate_fill_id_exit: int | None

    # Metadata
    status: TradeStatus
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None


class TradeListResponse(BaseModel):
    items: list[TradeResponse]
    total: int
    page: int
    page_size: int


class ApplyFillRequest(BaseModel):
    tradovate_fill_id: int
    role: Literal['entry', 'exit']
