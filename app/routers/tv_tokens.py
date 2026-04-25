"""Per-user TradingView webhook token — create, read, revoke."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_current_user, get_db
from app.models.tv_token import TradingViewToken
from app.models.user import User
from app.schemas.coach import TvTokenResponse

router = APIRouter(prefix="/api/coach/tv-token", tags=["coach-tv-token"])


def _webhook_url(token: str) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/webhooks/tradingview/{token}"


def _to_response(row: TradingViewToken) -> TvTokenResponse:
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return TvTokenResponse(
        token=row.token, webhook_url=_webhook_url(row.token), created_at=created_at
    )


@router.post("", response_model=TvTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_or_rotate_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TvTokenResponse:
    # Revoke any existing active token for this user.
    await db.execute(
        update(TradingViewToken)
        .where(
            TradingViewToken.user_id == user.id,
            TradingViewToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    new_row = TradingViewToken(user_id=user.id, token=secrets.token_urlsafe(32))
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return _to_response(new_row)


@router.get("", response_model=TvTokenResponse)
async def get_current_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TvTokenResponse:
    row = (
        await db.execute(
            select(TradingViewToken).where(
                TradingViewToken.user_id == user.id,
                TradingViewToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no active token")
    return _to_response(row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await db.execute(
        update(TradingViewToken)
        .where(
            TradingViewToken.user_id == user.id,
            TradingViewToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
