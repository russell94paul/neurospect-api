import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ScreenshotPhase


class ScreenshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trade_id: uuid.UUID
    user_id: uuid.UUID
    phase: ScreenshotPhase
    storage_key: str
    original_filename: str | None
    content_type: str | None
    uploaded_at: datetime
    presigned_url: str | None = None  # populated by route handler, not from ORM
