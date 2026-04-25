from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.analytics import (
    ByDayOfWeekResponse,
    ByInstrumentResponse,
    BySessionResponse,
    BySetupResponse,
    BreakdownRow,
    DayOfWeekRow,
    MistakeRow,
    MistakesResponse,
    RBucket,
    RDistributionResponse,
    SummaryResponse,
)
from app.services import analytics as svc

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await svc.get_summary(db, current_user.id)
    return SummaryResponse(**data)


@router.get("/by-setup", response_model=BySetupResponse)
async def by_setup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await svc.get_by_setup(db, current_user.id)
    return BySetupResponse(rows=[BreakdownRow(**r) for r in rows])


@router.get("/by-session", response_model=BySessionResponse)
async def by_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await svc.get_by_session(db, current_user.id)
    return BySessionResponse(rows=[BreakdownRow(**r) for r in rows])


@router.get("/by-instrument", response_model=ByInstrumentResponse)
async def by_instrument(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await svc.get_by_instrument(db, current_user.id)
    return ByInstrumentResponse(rows=[BreakdownRow(**r) for r in rows])


@router.get("/by-day-of-week", response_model=ByDayOfWeekResponse)
async def by_day_of_week(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await svc.get_by_day_of_week(db, current_user.id)
    return ByDayOfWeekResponse(rows=[DayOfWeekRow(**r) for r in rows])


@router.get("/mistakes", response_model=MistakesResponse)
async def mistakes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await svc.get_mistakes(db, current_user.id)
    return MistakesResponse(rows=[MistakeRow(**r) for r in rows])


@router.get("/r-distribution", response_model=RDistributionResponse)
async def r_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    buckets = await svc.get_r_distribution(db, current_user.id)
    return RDistributionResponse(buckets=[RBucket(**b) for b in buckets])
