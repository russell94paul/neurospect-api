import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.enums import TradeStatus
from app.models.trade import Trade
from app.models.user import User
from app.schemas.trade import TradeCreate, TradeListResponse, TradeResponse, TradeUpdate

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


# ---------------------------------------------------------------------------
# POST /api/trades
# ---------------------------------------------------------------------------

@router.post("", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    body: TradeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(trade, field, value)

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
