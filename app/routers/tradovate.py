"""Tradovate broker integration endpoints.

Prefix: /api/tradovate
Auth: all endpoints require get_current_user.

Credentials lifecycle mirrors tradingview_tokens: one active row per user,
upserted on POST /credentials, hard-deleted on DELETE /credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.broker_credential import BrokerCredential
from app.models.user import User
from app.schemas.broker import (
    BracketInfo,
    BrokerCredentialsCreate,
    BrokerCredentialsResponse,
    BrokerTokenCreate,
    FillDTO,
)
from app.services import tradovate as tv
from app.services.crypto import decrypt, encrypt
from app.services.tradovate import TradovateAuthError, TradovateApiError

router = APIRouter(prefix="/api/tradovate", tags=["tradovate"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_username(username: str) -> str:
    if len(username) <= 4:
        return "***"
    return username[:2] + "***" + username[-2:]


def _is_connected(creds: BrokerCredential) -> bool:
    if creds.is_disconnected or creds.access_token is None:
        return False
    exp = creds.access_token_expires_at
    if exp is None:
        return True
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > datetime.now(timezone.utc)


def _to_response(creds: BrokerCredential) -> BrokerCredentialsResponse:
    username = decrypt(creds.username_encrypted)
    return BrokerCredentialsResponse(
        environment=creds.environment,
        is_connected=_is_connected(creds),
        last_auth_at=creds.last_auth_at,
        username_masked=_mask_username(username),
    )


def _store_token(
    creds: BrokerCredential,
    access_token: str,
    environment: str,
    username: str,
) -> None:
    """Update creds in-place with a pasted Bearer token (token-only mode)."""
    now = datetime.now(timezone.utc)
    creds.environment = environment
    creds.username_encrypted = encrypt(username)
    creds.password_encrypted = encrypt("")  # sentinel: empty = token-only mode
    creds.access_token = access_token
    creds.md_access_token = None
    creds.access_token_expires_at = tv._parse_jwt_exp(access_token)
    creds.last_auth_at = now
    creds.last_auth_error = None
    creds.is_disconnected = False
    creds.updated_at = now


async def _get_creds(user: User, db: AsyncSession) -> BrokerCredential | None:
    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.user_id == user.id,
            BrokerCredential.broker == "tradovate",
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Credentials CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/credentials",
    response_model=BrokerCredentialsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_credentials(
    body: BrokerCredentialsCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Store Tradovate credentials. Authenticates immediately; 400 on bad creds.
    Upserts if a row already exists for this user.
    """
    username = body.username
    password = body.password.get_secret_value()

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            token_data = await tv.authenticate(username, password, body.environment, client)
        except TradovateAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Tradovate credentials: {exc}",
            )

    now = datetime.now(timezone.utc)
    access_token = token_data.get("accessToken")

    existing = await _get_creds(user, db)
    if existing:
        existing.environment = body.environment
        existing.username_encrypted = encrypt(username)
        existing.password_encrypted = encrypt(password)
        existing.access_token = access_token
        existing.md_access_token = token_data.get("mdAccessToken")
        existing.access_token_expires_at = (
            tv._parse_jwt_exp(access_token) if access_token else None
        )
        existing.last_auth_at = now
        existing.last_auth_error = None
        existing.is_disconnected = False
        existing.updated_at = now
        creds = existing
    else:
        creds = BrokerCredential(
            user_id=user.id,
            broker="tradovate",
            environment=body.environment,
            username_encrypted=encrypt(username),
            password_encrypted=encrypt(password),
            access_token=access_token,
            md_access_token=token_data.get("mdAccessToken"),
            access_token_expires_at=(
                tv._parse_jwt_exp(access_token) if access_token else None
            ),
            last_auth_at=now,
            is_disconnected=False,
        )
        db.add(creds)

    await db.commit()
    await db.refresh(creds)
    return _to_response(creds)


@router.get("/credentials", response_model=BrokerCredentialsResponse)
async def get_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerCredentialsResponse:
    creds = await _get_creds(user, db)
    if creds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No broker credentials")
    return _to_response(creds)


@router.delete("/credentials", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await db.execute(
        delete(BrokerCredential).where(
            BrokerCredential.user_id == user.id,
            BrokerCredential.broker == "tradovate",
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/credentials/token",
    response_model=BrokerCredentialsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_token(
    body: BrokerTokenCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Store a raw Tradovate Bearer token (prop firm / browser-session mode).

    For accounts that cannot use username/password auth (e.g. Lucid prop accounts
    on Tradovate Prop), the user extracts their session token from browser dev tools
    and pastes it here. Token is validated by decoding the JWT expiry; no Tradovate
    API call is made. Re-paste required when token expires.
    """
    access_token = body.access_token.strip()

    # Decode the JWT to sanity-check it and extract username if present
    expiry = tv._parse_jwt_exp(access_token)
    if expiry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token does not appear to be a valid JWT (no exp claim found). "
                   "Paste the full token from the Authorization header, not a URL.",
        )

    now = datetime.now(timezone.utc)
    if expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token is already expired (expired at {expiry.isoformat()}). "
                   "Refresh your browser session and copy a new token.",
        )

    # Use username from JWT payload if available, else fall back to sentinel
    jwt_username = tv._parse_jwt_username(access_token) or "browser-session"

    existing = await _get_creds(user, db)
    if existing:
        _store_token(existing, access_token, body.environment, jwt_username)
        creds = existing
    else:
        creds = BrokerCredential(user_id=user.id, broker="tradovate")
        _store_token(creds, access_token, body.environment, jwt_username)
        db.add(creds)

    await db.commit()
    await db.refresh(creds)
    return _to_response(creds)


@router.post("/credentials/test", response_model=BrokerCredentialsResponse)
async def test_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Re-authenticate with stored credentials. Updates last_auth_at / last_auth_error."""
    creds = await _get_creds(user, db)
    if creds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No broker credentials")

    password = decrypt(creds.password_encrypted)
    now = datetime.now(timezone.utc)

    if not password:
        # Token-only mode: check expiry without a network call
        expiry = creds.access_token_expires_at
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if not expiry or expiry <= now:
            creds.is_disconnected = True
            creds.last_auth_error = "Session token expired — re-paste in Settings"
        else:
            creds.is_disconnected = False
            creds.last_auth_at = now
            creds.last_auth_error = None
    else:
        username = decrypt(creds.username_encrypted)
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                token_data = await tv.authenticate(
                    username, password, creds.environment, client
                )
                access_token = token_data.get("accessToken")
                creds.access_token = access_token
                creds.md_access_token = token_data.get("mdAccessToken")
                creds.access_token_expires_at = (
                    tv._parse_jwt_exp(access_token) if access_token else None
                )
                creds.last_auth_at = now
                creds.last_auth_error = None
                creds.is_disconnected = False
            except TradovateAuthError as exc:
                creds.last_auth_error = str(exc)
                creds.is_disconnected = True

    creds.updated_at = now
    await db.commit()
    await db.refresh(creds)
    return _to_response(creds)


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------

@router.get("/fills", response_model=list[FillDTO])
async def get_fills(
    trade_date: str = Query(..., description="ISO date, e.g. 2026-04-26"),
    instrument: str | None = Query(None, description="Instrument prefix, e.g. NQ"),
    since_time: str | None = Query(None, description="ISO datetime lower bound"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FillDTO]:
    """Fetch fills from Tradovate for a given trade date and optional instrument.

    For each fill, attempts to find associated bracket stop/target orders and
    attaches them as fill.bracket.{stop_price, target_price}.

    NOTE: Bracket matching is best-effort (match by contract + working Stop/Limit
    orders). Verify against real fill+order responses once app credentials are
    configured — see TRADOVATE_CID / TRADOVATE_SEC in .env.example.
    """
    creds = await _get_creds(user, db)
    if creds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No broker credentials")

    if creds.is_disconnected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tradovate is disconnected — reconnect in Settings",
        )

    # Build since datetime from trade_date + optional since_time
    if since_time:
        since = datetime.fromisoformat(since_time.replace("Z", "+00:00"))
    else:
        since = datetime.fromisoformat(f"{trade_date}T00:00:00+00:00")

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            creds = await tv.refresh_if_needed(creds, client, db)
            fills = await tv.list_fills(creds, since, instrument, client, db)
            orders = await tv.list_orders(creds, since, instrument, client, db)
        except TradovateAuthError as exc:
            creds.is_disconnected = True
            creds.last_auth_error = str(exc)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tradovate authentication failed — reconnect in Settings",
            )
        except TradovateApiError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Tradovate API error {exc.status_code}",
            )

    # Index working Stop + Limit orders by contract_id for bracket lookup
    # NOTE: This matches bracket orders by contract. When Tradovate issues a
    # bracket (Stop + Limit OCO pair), both will appear here as "Working" orders.
    # For the single-active-trade case (guaranteed by 1b singleton), the first
    # Stop/Limit found per contract is the bracket. Refine with ocoId in 1c.
    working_stops: dict[int, tv.OrderInfo] = {}
    working_limits: dict[int, tv.OrderInfo] = {}
    for order in orders:
        if order["status"] not in ("Working", "PendingNew"):
            continue
        cid = order["contract_id"]
        if order["order_type"] == "Stop" and cid not in working_stops:
            working_stops[cid] = order
        elif order["order_type"] == "Limit" and cid not in working_limits:
            working_limits[cid] = order

    # Attach bracket info to each fill
    # We need contractId for matching — re-derive from cached get_contract lookups.
    # Since get_contract is cached, this is cheap.
    results: list[FillDTO] = []
    async with httpx.AsyncClient(timeout=10.0) as client2:
        for fill in fills:
            bracket: BracketInfo | None = None
            # Find contractId for this fill's instrument name via reverse cache lookup
            contract_id = next(
                (k for k, v in tv._contract_cache.items() if v == fill.instrument),
                None,
            )
            if contract_id is not None:
                stop_order = working_stops.get(contract_id)
                limit_order = working_limits.get(contract_id)
                if stop_order or limit_order:
                    bracket = BracketInfo(
                        stop_price=stop_order["price"] if stop_order else None,
                        target_price=limit_order["price"] if limit_order else None,
                    )
            results.append(fill.model_copy(update={"bracket": bracket}))

    return results
