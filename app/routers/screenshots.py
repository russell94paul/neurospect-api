import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.enums import ScreenshotPhase
from app.models.screenshot import TradeScreenshot
from app.models.trade import Trade
from app.models.user import User
from app.schemas.screenshot import ScreenshotResponse
from app.services.r2 import R2Client, r2

router = APIRouter(prefix="/api/trades", tags=["screenshots"])


def get_r2() -> R2Client:
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screenshot storage not configured (R2_ENDPOINT_URL not set)",
        )
    return r2


def _assert_trade_ownership(trade: Trade | None, user_id: uuid.UUID) -> Trade:
    if trade is None or trade.is_deleted or trade.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade


def _assert_screenshot_ownership(ss: TradeScreenshot | None, user_id: uuid.UUID) -> TradeScreenshot:
    if ss is None or ss.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return ss


# ---------------------------------------------------------------------------
# POST /api/trades/{id}/screenshots
# ---------------------------------------------------------------------------

@router.post(
    "/{trade_id}/screenshots",
    response_model=ScreenshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_screenshot(
    trade_id: uuid.UUID,
    file: UploadFile,
    phase: ScreenshotPhase = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: R2Client = Depends(get_r2),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    _assert_trade_ownership(result.scalar_one_or_none(), current_user.id)

    data = await file.read()
    ext = PurePosixPath(file.filename or "image.png").suffix.lstrip(".") or "png"
    content_type = file.content_type or "image/png"
    key = storage.storage_key(current_user.id, trade_id, phase.value, ext)

    storage.upload_bytes(key, data, content_type)

    ss = TradeScreenshot(
        trade_id=trade_id,
        user_id=current_user.id,
        phase=phase,
        storage_key=key,
        original_filename=file.filename,
        content_type=content_type,
    )
    db.add(ss)
    await db.commit()
    await db.refresh(ss)

    return ScreenshotResponse(
        **{c: getattr(ss, c) for c in ScreenshotResponse.model_fields if c != "presigned_url"},
        presigned_url=storage.presign(key),
    )


# ---------------------------------------------------------------------------
# GET /api/trades/{id}/screenshots
# ---------------------------------------------------------------------------

@router.get("/{trade_id}/screenshots", response_model=list[ScreenshotResponse])
async def list_screenshots(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: R2Client = Depends(get_r2),
):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    _assert_trade_ownership(result.scalar_one_or_none(), current_user.id)

    rows = (
        await db.execute(
            select(TradeScreenshot)
            .where(TradeScreenshot.trade_id == trade_id)
            .order_by(TradeScreenshot.uploaded_at.asc())
        )
    ).scalars().all()

    return [
        ScreenshotResponse(
            **{c: getattr(ss, c) for c in ScreenshotResponse.model_fields if c != "presigned_url"},
            presigned_url=storage.presign(ss.storage_key),
        )
        for ss in rows
    ]


# ---------------------------------------------------------------------------
# DELETE /api/trades/{id}/screenshots/{sid}
# ---------------------------------------------------------------------------

@router.delete("/{trade_id}/screenshots/{screenshot_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_screenshot(
    trade_id: uuid.UUID,
    screenshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: R2Client = Depends(get_r2),
) -> Response:
    result = await db.execute(
        select(TradeScreenshot).where(
            TradeScreenshot.id == screenshot_id,
            TradeScreenshot.trade_id == trade_id,
        )
    )
    ss = _assert_screenshot_ownership(result.scalar_one_or_none(), current_user.id)

    storage.delete(ss.storage_key)
    await db.delete(ss)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
