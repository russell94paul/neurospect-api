import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BrokerCredential(Base):
    __tablename__ = "broker_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    broker: Mapped[str] = mapped_column(String(32), nullable=False, default="tradovate")
    environment: Mapped[str] = mapped_column(
        SAEnum("demo", "live", name="tradovate_environment", create_type=False),
        nullable=False,
        default="demo",
    )

    # Fernet-encrypted user credentials (key in BROKER_CRED_SECRET)
    username_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # OAuth tokens from Tradovate (refreshed automatically)
    access_token: Mapped[str | None] = mapped_column(Text)
    md_access_token: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Diagnostic
    last_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_auth_error: Mapped[str | None] = mapped_column(Text)
    is_disconnected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
