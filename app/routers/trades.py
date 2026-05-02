import uuid
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.broker_credential import BrokerCredential
from app.models.enums import TradeStatus
from app.models.trade import Trade
from app.models.user import User
from app.schemas.trade import ApplyFillRequest, TradeCreate, TradeListResponse, TradeResponse, TradeUpdate
from app.services import tradovate as tv
from app.services.tradovate import TradovateApiError, TradovateAuthError

router = APIRouter(prefix="/api/trades", tags=["trades"])

# Valid status transitions — no backward moves
_TRANSITIONS = {
    TradeStatus.pre_trade: TradeStatus.active,
    TradeStatus.active: TradeStatus.closed,
}


def _assert_ownership(trade: Trade | None, user_id: uuid.UUID) -> Trade:
    if trade is None or trade.is_deleted or trade.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade


async def get_active_trade(db: AsyncSession, user_id: uuid.UUID) -> Trade | None:
    result = await db.execute(
        select(Trade).where(
            Trade.user_id == user_id,
            Trade.status == TradeStatus.active,
            Trade.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def _conflict_response(trade: Trade) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "active_trade_conflict",
            "active_trade_id": str(trade.id),
            "instrument": trade.instrument,
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        },
    )


# ---------------------------------------------------------------------------
# POST /api/trades
# ---------------------------------------------------------------------------

@router.post("", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    body: TradeCreate,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.status == TradeStatus.active and not force:
        existing = await get_active_trade(db, current_user.id)
        if existing:
            return _conflict_response(existing)
    trade = Trade(user_id=current_user.id, **body.model_dump())
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


# ---------------------------------------------------------------------------
# GET /api/trades
# ---------------------------------------------------------------------------

@router.get("", response_model=TradeListResponse)
async def list_trades(
    date_start: date | None = Query(None),
    date_end: date | None = Query(None),
    instrument: str | None = Query(None),
    session: str | None = Query(None),
    setup_type: str | None = Query(None),
    outcome: str | None = Query(None),
    trade_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(Trade)
        .where(Trade.user_id == current_user.id, Trade.is_deleted.is_(False))
    )
    if date_start:
        q = q.where(Trade.trade_date >= date_start)
    if date_end:
        q = q.where(Trade.trade_date <= date_end)
    if instrument:
        q = q.where(Trade.instrument == instrument)
    if session:
        q = q.where(Trade.session == session)
    if setup_type:
        q = q.where(Trade.setup_type == setup_type)
    if outcome:
        q = q.where(Trade.outcome == outcome)
    if trade_status:
        q = q.where(Trade.status == trade_status)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(Trade.trade_date.desc(), Trade.created_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)

    rows = (await db.execute(q)).scalars().all()
    return TradeListResponse(items=list(rows), total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# GET /api/trades/{id}
# ---------------------------------------------------------------------------

@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = _assert_ownership(result.scalar_one_or_none(), current_user.id)
    return trade


# ---------------------------------------------------------------------------
# PATCH /api/trades/{id}
# ---------------------------------------------------------------------------

@router.patch("/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: uuid.UUID,
    body: TradeUpdate,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = _assert_ownership(result.scalar_one_or_none(), current_user.id)

    # Validate status transition if requested
    if body.status is not None and body.status != trade.status:
        allowed_next = _TRANSITIONS.get(trade.status)
        if body.status != allowed_next:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition: {trade.status} → {body.status}",
            )
        # Singleton guard: block pre_trade → active if another active trade exists
        if body.status == TradeStatus.active and not force:
            existing = await get_active_trade(db, current_user.id)
            if existing and existing.id != trade_id:
                return _conflict_response(existing)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(trade, field, value)

    await db.commit()
    await db.refresh(trade)
    return trade


# ---------------------------------------------------------------------------
# POST /api/trades/{id}/apply-tradovate-fill
# ---------------------------------------------------------------------------

@router.post("/{trade_id}/apply-tradovate-fill", response_model=TradeResponse)
async def apply_tradovate_fill(
    trade_id: uuid.UUID,
    body: ApplyFillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a Tradovate fill to a trade's entry or exit fields.

    Re-fetches the fill from Tradovate rather than trusting client data.
    Idempotent: if this fill ID is already applied for the given role, returns
    the current trade unchanged.

    For entry fills: also looks up working bracket OCO orders and writes
    stop_price / target_price when found.
    """
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = _assert_ownership(result.scalar_one_or_none(), current_user.id)

    # Idempotent: no-op if this fill is already recorded
    if body.role == 'entry' and trade.tradovate_fill_id_entry == body.tradovate_fill_id:
        return trade
    if body.role == 'exit' and trade.tradovate_fill_id_exit == body.tradovate_fill_id:
        return trade

    creds_result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.user_id == current_user.id,
            BrokerCredential.broker == "tradovate",
        )
    )
    creds = creds_result.scalar_one_or_none()
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No broker credentials configured",
        )

    since = datetime(
        trade.trade_date.year,
        trade.trade_date.month,
        trade.trade_date.day,
        tzinfo=timezone.utc,
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            creds = await tv.refresh_if_needed(creds, client, db)
            fills = await tv.list_fills(creds, since, None, client, db)
            orders = (
                await tv.list_orders(creds, since, None, client, db)
                if body.role == 'entry'
                else []
            )
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

    fill = next((f for f in fills if f.tradovate_fill_id == body.tradovate_fill_id), None)
    if fill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fill {body.tradovate_fill_id} not found for {trade.trade_date}",
        )

    if body.role == 'entry':
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

        contract_id = next(
            (k for k, v in tv._contract_cache.items() if v == fill.instrument),
            None,
        )
        stop_order = working_stops.get(contract_id) if contract_id is not None else None
        limit_order = working_limits.get(contract_id) if contract_id is not None else None

        trade.entry_price = fill.price
        trade.entry_time = fill.timestamp
        trade.position_size = fill.qty
        trade.tradovate_fill_id_entry = fill.tradovate_fill_id
        if stop_order and stop_order["price"] is not None:
            trade.stop_price = stop_order["price"]
        if limit_order and limit_order["price"] is not None:
            trade.target_price = limit_order["price"]

    else:
        trade.exit_price = fill.price
        trade.exit_time = fill.timestamp
        trade.tradovate_fill_id_exit = fill.tradovate_fill_id

    await db.commit()
    await db.refresh(trade)
    return trade


# ---------------------------------------------------------------------------
# DELETE /api/trades/{id}  — soft delete
# ---------------------------------------------------------------------------

@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_trade(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = _assert_ownership(result.scalar_one_or_none(), current_user.id)

    trade.is_deleted = True
    trade.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
