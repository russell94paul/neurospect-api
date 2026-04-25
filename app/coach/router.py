"""AI Coach endpoints.

- POST /webhooks/tradingview/{user_token}  — ingestion from Pine Script
- GET  /api/coach/events/{event_id}        — polling by frontend
- GET  /api/coach/events/latest            — most recent event for user
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.coach.claude_client import run_claude_call
from app.coach.validation import verify_ip_allowlist, verify_secret
from app.deps import get_current_user, get_db
from app.models.coaching_event import CoachingEvent
from app.models.tv_token import TradingViewToken
from app.models.user import User
from app.schemas.coach import (
    CoachingEventResponse,
    Layer2Payload,
    WebhookAccepted,
)

webhook_router = APIRouter(prefix="/webhooks/tradingview", tags=["coach-webhook"])
events_router = APIRouter(prefix="/api/coach/events", tags=["coach-events"])


@webhook_router.post(
    "/{user_token}",
    response_model=WebhookAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_tradingview_alert(
    user_token: str,
    payload: Layer2Payload,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> WebhookAccepted:
    # 1. user_token → user_id
    token_row = (
        await db.execute(
            select(TradingViewToken).where(
                TradingViewToken.token == user_token,
                TradingViewToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if token_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    # 2. secret check (constant-time)
    verify_secret(payload.secret)

    # 3. IP allowlist
    verify_ip_allowlist(request)

    # 4. Pydantic parse already succeeded by virtue of the signature.
    # 5. Idempotency: relies on the UNIQUE (user_id, idempotency_key) index.

    event = CoachingEvent(
        user_id=token_row.user_id,
        idempotency_key=payload.idempotency_key,
        instrument=payload.instrument,
        alert_timestamp=payload.timestamp,
        request_payload=payload.model_dump(mode="json", exclude={"secret"}),
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(CoachingEvent).where(
                    CoachingEvent.user_id == token_row.user_id,
                    CoachingEvent.idempotency_key == payload.idempotency_key,
                )
            )
        ).scalar_one()
        return WebhookAccepted(status="duplicate", coaching_event_id=existing.id)

    background_tasks.add_task(run_claude_call, event.id)
    return WebhookAccepted(status="accepted", coaching_event_id=event.id)


@events_router.get("/latest", response_model=CoachingEventResponse)
async def get_latest_coaching_event(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoachingEventResponse:
    row = (
        await db.execute(
            select(CoachingEvent)
            .where(CoachingEvent.user_id == user.id)
            .order_by(CoachingEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no events")
    return _to_response(row)


@events_router.get("/{event_id}", response_model=CoachingEventResponse)
async def get_coaching_event(
    event_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CoachingEventResponse:
    row = (
        await db.execute(
            select(CoachingEvent).where(
                CoachingEvent.id == event_id,
                CoachingEvent.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return _to_response(row)


def _to_response(row: CoachingEvent) -> CoachingEventResponse:
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    completed_at = row.completed_at
    if completed_at is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return CoachingEventResponse(
        id=row.id,
        status=row.status.value,
        instrument=row.instrument,
        alert_timestamp=row.alert_timestamp,
        request_payload=row.request_payload,
        response_payload=row.response_payload,
        error_message=row.error_message,
        claude_latency_ms=row.claude_latency_ms,
        created_at=created_at,
        completed_at=completed_at,
    )
