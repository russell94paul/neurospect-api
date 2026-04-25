"""Webhook validation primitives: shared secret + IP allowlist.

Idempotency deduplication is handled in the router against the database.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from app.config import settings


def verify_secret(posted: str) -> None:
    """Constant-time compare against TRADINGVIEW_WEBHOOK_SECRET."""
    expected = settings.tradingview_webhook_secret or ""
    if not expected or not hmac.compare_digest(posted, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid secret",
        )


def _parse_client_ip(request: Request) -> str | None:
    # On Render, the external IP is the first hop in X-Forwarded-For.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def verify_ip_allowlist(request: Request) -> None:
    raw = (settings.tradingview_ip_allowlist or "").strip()
    if not raw:
        # Empty list = disabled (useful for local dev). Log via structlog upstream.
        return
    allowed = {ip.strip() for ip in raw.split(",") if ip.strip()}
    client_ip = _parse_client_ip(request)
    if client_ip not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ip not allowed",
        )
