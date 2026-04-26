import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
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


class Trade(Base):
    __tablename__ = "trades"

    # Identity
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Pre-Trade
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument: Mapped[str] = mapped_column(String(20), nullable=False)
    session: Mapped[SessionType | None] = mapped_column(
        SAEnum(SessionType, name="session_type", create_type=False)
    )
    kill_zone: Mapped[KillZoneType | None] = mapped_column(
        SAEnum(KillZoneType, name="kill_zone_type", create_type=False)
    )
    htf_bias: Mapped[BiasType | None] = mapped_column(
        SAEnum(BiasType, name="bias_type", create_type=False)
    )
    htf_fvg_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    htf_fvg_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    draw_on_liquidity: Mapped[str | None] = mapped_column(Text)
    dol_price_level: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    opening_price_position: Mapped[OppType | None] = mapped_column(
        SAEnum(OppType, name="opp_type", create_type=False)
    )
    news_flag: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    setup_type: Mapped[SetupType | None] = mapped_column(
        SAEnum(SetupType, name="setup_type", create_type=False)
    )
    narrative: Mapped[str | None] = mapped_column(Text)

    # Entry (nullable until taken)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    entry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position_size: Mapped[int | None] = mapped_column(Integer)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    stop_logic: Mapped[str | None] = mapped_column(Text)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    target_logic: Mapped[str | None] = mapped_column(Text)
    entry_pda: Mapped[PdaType | None] = mapped_column(
        SAEnum(PdaType, name="pda_type", create_type=False)
    )
    displacement_quality: Mapped[DisplacementType | None] = mapped_column(
        SAEnum(DisplacementType, name="displacement_type", create_type=False)
    )
    smt_confirmation: Mapped[bool | None] = mapped_column(Boolean)

    # Post-Trade (nullable until closed)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[OutcomeType | None] = mapped_column(
        SAEnum(OutcomeType, name="outcome_type", create_type=False)
    )
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    mae: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    mfe: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    target_reached: Mapped[bool | None] = mapped_column(Boolean)
    plan_followed: Mapped[bool | None] = mapped_column(Boolean)
    mistake_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    quality_grade: Mapped[GradeType | None] = mapped_column(
        SAEnum(GradeType, name="grade_type", create_type=False)
    )
    post_trade_notes: Mapped[str | None] = mapped_column(Text)

    # Metadata
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus, name="trade_status", create_type=False),
        nullable=False,
        default=TradeStatus.pre_trade,
        server_default="pre_trade",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
