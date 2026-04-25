import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import CoachingEventStatus


class CoachingEvent(Base):
    __tablename__ = "coaching_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    instrument: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[CoachingEventStatus] = mapped_column(
        SAEnum(CoachingEventStatus, name="coaching_event_status", create_type=False),
        nullable=False,
        default=CoachingEventStatus.pending,
        server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    claude_latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
