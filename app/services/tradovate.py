"""Async Tradovate REST API client.

Stateless — every function takes a BrokerCredential row + httpx.AsyncClient.
All network calls go through _authed_get / _authed_post so token refresh and
401-retry are handled in one place.

Field names are based on the Tradovate v1 API reference. Verify against real
API responses once developer app credentials (TRADOVATE_CID / TRADOVATE_SEC)
are obtained — see docs at https://api.tradovate.com.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TypedDict

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker_credential import BrokerCredential
from app.schemas.broker import BracketInfo, FillDTO

logger = logging.getLogger(__name__)

_DEMO_BASE = "https://demo.tradovateapi.com/v1"
_LIVE_BASE = "https://live.tradovateapi.com/v1"

# Module-level LRU-style cache: contract_id -> name (e.g. "NQM6")
_contract_cache: dict[int, str] = {}


class TradovateAuthError(Exception):
    """Hard authentication failure. Caller should mark creds.is_disconnected=True."""


class TradovateApiError(Exception):
    """Non-auth 4xx/5xx from Tradovate."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class OrderInfo(TypedDict):
    order_id: int
    contract_id: int
    order_type: str   # "Market" | "Stop" | "Limit" | ...
    status: str       # "Working" | "Filled" | "Cancelled" | ...
    action: str       # "buy" | "sell"
    price: Decimal | None
    oco_id: int | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base_url(environment: str) -> str:
    return _DEMO_BASE if environment == "demo" else _LIVE_BASE


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verifying signature. Returns {} on failure."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def _parse_jwt_exp(token: str) -> datetime | None:
    """Extract exp claim from a JWT without verifying signature."""
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp:
        return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    return None


def _parse_jwt_username(token: str) -> str | None:
    """Try to extract a display identifier from a JWT payload.

    Tradovate Prop tokens carry an email claim (not name). Preference order:
    name > email > sub (numeric user ID).
    """
    payload = _decode_jwt_payload(token)
    return payload.get("name") or payload.get("email") or payload.get("sub") or None


async def _authed_get(
    path: str,
    creds: BrokerCredential,
    client: httpx.AsyncClient,
    db: AsyncSession,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET with one retry after token refresh on 401."""
    url = f"{_base_url(creds.environment)}{path}"
    headers = {"Authorization": f"Bearer {creds.access_token}"}

    resp = await client.get(url, headers=headers, params=params)

    if resp.status_code == 401:
        creds = await refresh_if_needed(creds, client, db, force=True)
        headers = {"Authorization": f"Bearer {creds.access_token}"}
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            raise TradovateAuthError("401 after token refresh — creds may be revoked")

    if resp.status_code >= 400:
        raise TradovateApiError(resp.status_code, resp.text[:500])

    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def authenticate(
    username: str,
    password: str,
    environment: str,
    client: httpx.AsyncClient,
) -> dict:
    """POST credentials to Tradovate auth endpoint.

    Returns the raw token response dict on success.
    Raises TradovateAuthError on bad credentials (200 with errorText, or 401).

    NOTE: Requires valid TRADOVATE_CID / TRADOVATE_SEC app credentials from
    a registered Tradovate developer account. Without them, Tradovate triggers
    a PRISM captcha challenge that blocks automated auth.
    """
    from app.config import settings

    url = f"{_base_url(environment)}/auth/accesstokenrequest"
    payload = {
        "name": username,
        "password": password,
        "appId": settings.tradovate_app_id,
        "appVersion": "1.0",
        "cid": settings.tradovate_cid,
        "sec": settings.tradovate_sec,
    }
    resp = await client.post(url, json=payload)

    if resp.status_code == 401:
        raise TradovateAuthError("Tradovate returned 401")

    data = resp.json()

    # Tradovate returns HTTP 200 with errorText for bad credentials
    if "errorText" in data:
        raise TradovateAuthError(data["errorText"])

    # PRISM captcha challenge — app registration required
    if data.get("p-captcha"):
        raise TradovateAuthError(
            "Tradovate requires CAPTCHA — register a developer app to get "
            "TRADOVATE_CID / TRADOVATE_SEC credentials that bypass PRISM."
        )

    if "accessToken" not in data:
        raise TradovateAuthError(f"Unexpected auth response: {list(data.keys())}")

    return data


async def refresh_if_needed(
    creds: BrokerCredential,
    client: httpx.AsyncClient,
    db: AsyncSession,
    *,
    force: bool = False,
) -> BrokerCredential:
    """Re-authenticate if token is missing or expiring within 5 minutes.

    Updates creds in-place and commits. Pass force=True to always refresh
    (used on 401 retry).
    """
    from app.services.crypto import decrypt

    now = datetime.now(timezone.utc)
    expires = creds.access_token_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    needs_refresh = (
        force
        or creds.access_token is None
        or expires is None
        or expires <= now + timedelta(minutes=5)
    )
    if not needs_refresh:
        return creds

    username = decrypt(creds.username_encrypted)
    password = decrypt(creds.password_encrypted)

    # Token-only mode (prop firm accounts): no password stored, cannot auto-refresh.
    # The user must re-paste a fresh session token via POST /credentials/token.
    if not password:
        raise TradovateAuthError(
            "Session token expired — re-paste your Tradovate Bearer token in Settings"
        )

    token_data = await authenticate(username, password, creds.environment, client)

    creds.access_token = token_data.get("accessToken")
    creds.md_access_token = token_data.get("mdAccessToken")
    creds.access_token_expires_at = (
        _parse_jwt_exp(creds.access_token) if creds.access_token else None
    )
    creds.last_auth_at = now
    creds.last_auth_error = None
    creds.is_disconnected = False
    creds.updated_at = now

    await db.commit()
    await db.refresh(creds)
    return creds


async def get_contract(
    contract_id: int,
    creds: BrokerCredential,
    client: httpx.AsyncClient,
    db: AsyncSession,
) -> str:
    """Resolve a Tradovate contractId to its name (e.g. 'MNQM6'). Cached.

    Probe confirmed: /contract/{id} returns 404 on Tradovate Prop accounts.
    /contract/item?id={id} is the correct single-item endpoint.
    """
    if contract_id in _contract_cache:
        return _contract_cache[contract_id]

    data = await _authed_get("/contract/item", creds, client, db, params={"id": contract_id})
    if isinstance(data, list):
        data = data[0] if data else {}
    name: str = data.get("name", str(contract_id))
    _contract_cache[contract_id] = name
    return name


async def list_fills(
    creds: BrokerCredential,
    since: datetime,
    instrument: str | None,
    client: httpx.AsyncClient,
    db: AsyncSession,
) -> list[FillDTO]:
    """Return fills since `since`, optionally filtered by instrument prefix.

    Field names from Tradovate v1 API docs (verify against live responses):
      id          → tradovate_fill_id
      orderId     → order_id
      contractId  → resolved via get_contract()
      tradeTime   → timestamp (preferred over 'timestamp' field)
      price       → price
      qty         → qty
      action      → side ("Buy"/"Sell" normalised to "buy"/"sell")
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    raw: list[dict] = await _authed_get("/fill/list", creds, client, db)

    results: list[FillDTO] = []
    for item in raw:
        ts_str: str | None = item.get("tradeTime") or item.get("timestamp")
        if not ts_str:
            continue

        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < since:
            continue

        contract_id: int | None = item.get("contractId")
        if contract_id is None:
            continue

        name = await get_contract(contract_id, creds, client, db)

        if instrument and not name.upper().startswith(instrument.upper()):
            continue

        action = (item.get("action") or "").lower()  # "Buy" → "buy"

        results.append(
            FillDTO(
                tradovate_fill_id=item["id"],
                instrument=name,
                side=action,
                qty=int(item.get("qty", 0)),
                price=Decimal(str(item.get("price", 0))),
                timestamp=ts,
                order_id=int(item.get("orderId", 0)),
            )
        )

    return results


async def list_orders(
    creds: BrokerCredential,
    since: datetime,
    instrument: str | None,
    client: httpx.AsyncClient,
    db: AsyncSession,
) -> list[OrderInfo]:
    """Return orders since `since`, optionally filtered by instrument prefix.

    Used by the fills router to extract bracket stop/target prices.
    Field names from Tradovate v1 API docs (verify against live responses):
      id          → order_id
      contractId  → contract_id
      type        → order_type ("Market" | "Stop" | "Limit")
      status      → status ("Working" | "Filled" | "Cancelled" | ...)
      action      → action ("Buy"/"Sell" normalised to "buy"/"sell")
      price       → price (stop price for Stop orders, limit for Limit orders)
      ocoId       → oco_id (links paired stop + target orders)
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    raw: list[dict] = await _authed_get("/order/list", creds, client, db)

    results: list[OrderInfo] = []
    for item in raw:
        ts_str: str | None = item.get("timestamp")
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < since:
                continue

        contract_id: int | None = item.get("contractId")
        if contract_id is None:
            continue

        if instrument:
            name = await get_contract(contract_id, creds, client, db)
            if not name.upper().startswith(instrument.upper()):
                continue

        # Tradovate uses "price" on Limit orders, "stopPrice" on Stop orders
        price_raw = item.get("price") or item.get("stopPrice") or item.get("limitPrice")

        results.append(
            OrderInfo(
                order_id=int(item.get("id", 0)),
                contract_id=contract_id,
                order_type=item.get("type", ""),
                status=item.get("status", ""),
                action=(item.get("action") or "").lower(),
                price=Decimal(str(price_raw)) if price_raw is not None else None,
                oco_id=item.get("ocoId"),
            )
        )

    return results
