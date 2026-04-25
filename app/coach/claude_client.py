"""Claude call orchestration for the AI Coach.

Runs as a BackgroundTask after the webhook persists a pending coaching event.
Builds the prompt-cached system message + Layer 2 user message, parses the
Layer 3 response, and updates the row.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic, APIError
from sqlalchemy import select, update

from app.config import settings
from app.coach.prompt_loader import get_system_prompt
from app.database import AsyncSessionLocal
from app.models.coaching_event import CoachingEvent
from app.models.enums import CoachingEventStatus
from app.schemas.coach import Layer3Response

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _build_user_message(payload: dict[str, Any]) -> str:
    instrument = payload.get("instrument", "unknown")
    return (
        f"Live market context for {instrument}:\n\n```json\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n```"
    )


async def run_claude_call(event_id: UUID) -> None:
    """Background worker: fetch the pending event, call Claude, persist result."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(CoachingEvent).where(CoachingEvent.id == event_id)
            )
        ).scalar_one_or_none()
        if row is None or row.status != CoachingEventStatus.pending:
            return

        payload = row.request_payload
        system_prompt = get_system_prompt()
        user_message = _build_user_message(payload)
        client = _get_client()

        started = time.monotonic()
        try:
            resp = await client.messages.create(
                model=settings.claude_model,
                max_tokens=settings.claude_max_tokens,
                timeout=settings.claude_timeout_seconds,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
        except APIError as exc:
            await _mark_error(session, event_id, f"anthropic_api_error: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 — surface any SDK failure verbatim
            await _mark_error(session, event_id, f"unexpected: {type(exc).__name__}: {exc}")
            return

        latency_ms = int((time.monotonic() - started) * 1000)
        raw = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        cleaned = _strip_code_fence(raw)

        try:
            parsed = Layer3Response.model_validate_json(cleaned)
        except Exception as exc:  # noqa: BLE001
            await _mark_error(
                session,
                event_id,
                f"layer3_parse_error: {exc}. raw[:2000]={raw[:2000]!r}",
                latency_ms=latency_ms,
            )
            return

        await session.execute(
            update(CoachingEvent)
            .where(CoachingEvent.id == event_id)
            .values(
                status=CoachingEventStatus.complete,
                response_payload=parsed.model_dump(mode="json"),
                completed_at=datetime.now(timezone.utc),
                claude_latency_ms=latency_ms,
            )
        )
        await session.commit()


async def _mark_error(
    session, event_id: UUID, message: str, *, latency_ms: int | None = None
) -> None:
    await session.execute(
        update(CoachingEvent)
        .where(CoachingEvent.id == event_id)
        .values(
            status=CoachingEventStatus.error,
            error_message=message[:2000],
            completed_at=datetime.now(timezone.utc),
            claude_latency_ms=latency_ms,
        )
    )
    await session.commit()
