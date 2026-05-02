"""Tests for the active-trade soft singleton guard (sub-phase 1b).

Tests call route functions directly with mocked dependencies to avoid
needing a real database while still exercising the singleton logic.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest")
os.environ.setdefault("BROKER_CRED_SECRET", "S3Jb5QZQK2UhMFHN4CjCiJMf3gqrJlpYktNbxFKHt1I=")

import pytest
from fastapi.responses import JSONResponse

from app.models.enums import TradeStatus
from app.models.trade import Trade
from app.routers.trades import get_active_trade

USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ACTIVE_TRADE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _make_active_trade() -> MagicMock:
    t = MagicMock(spec=Trade)
    t.id = ACTIVE_TRADE_ID
    t.user_id = USER_ID
    t.instrument = "NQ"
    t.status = TradeStatus.active
    t.is_deleted = False
    t.entry_time = datetime(2026, 4, 26, 14, 32, tzinfo=timezone.utc)
    return t


def _make_pre_trade(trade_id: uuid.UUID | None = None) -> MagicMock:
    t = MagicMock(spec=Trade)
    t.id = trade_id or uuid.uuid4()
    t.user_id = USER_ID
    t.instrument = "NQ"
    t.status = TradeStatus.pre_trade
    t.is_deleted = False
    t.entry_time = None
    return t


def _make_db(fetched_trade=None) -> AsyncMock:
    """Minimal AsyncSession stub. fetched_trade is returned from execute()."""
    db = AsyncMock()
    db.add = MagicMock()  # synchronous in SQLAlchemy
    result = MagicMock()
    result.scalar_one_or_none.return_value = fetched_trade
    db.execute.return_value = result
    return db


def _is_conflict(result) -> bool:
    return isinstance(result, JSONResponse) and result.status_code == 409


# ---------------------------------------------------------------------------
# get_active_trade helper
# ---------------------------------------------------------------------------

class TestGetActiveTrade:
    async def test_returns_none_when_no_active_trade(self):
        db = _make_db(fetched_trade=None)
        assert await get_active_trade(db, USER_ID) is None

    async def test_returns_trade_when_active_exists(self):
        active = _make_active_trade()
        db = _make_db(fetched_trade=active)
        assert await get_active_trade(db, USER_ID) is active


# ---------------------------------------------------------------------------
# POST /api/trades singleton guard
# ---------------------------------------------------------------------------

class TestCreateTradeSingleton:
    async def test_409_when_creating_active_and_one_already_exists(self):
        from app.routers.trades import create_trade
        from app.schemas.trade import TradeCreate

        body = TradeCreate(
            trade_date=date(2026, 4, 26), instrument="NQ", status=TradeStatus.active
        )
        active = _make_active_trade()

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await create_trade(
                body=body, force=False, db=_make_db(), current_user=_make_user()
            )

        assert _is_conflict(result)
        data = json.loads(result.body)
        assert data["detail"] == "active_trade_conflict"
        assert data["active_trade_id"] == str(ACTIVE_TRADE_ID)
        assert data["instrument"] == "NQ"
        assert data["entry_time"] is not None

    async def test_force_true_bypasses_409_on_create(self):
        from app.routers.trades import create_trade
        from app.schemas.trade import TradeCreate

        body = TradeCreate(
            trade_date=date(2026, 4, 26), instrument="MNQ", status=TradeStatus.active
        )
        active = _make_active_trade()

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await create_trade(
                body=body, force=True, db=_make_db(), current_user=_make_user()
            )

        assert not _is_conflict(result)

    async def test_pre_trade_creation_never_blocked(self):
        from app.routers.trades import create_trade
        from app.schemas.trade import TradeCreate

        # Default status = pre_trade; active exists but guard doesn't fire
        body = TradeCreate(trade_date=date(2026, 4, 26), instrument="NQ")
        active = _make_active_trade()

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await create_trade(
                body=body, force=False, db=_make_db(), current_user=_make_user()
            )

        assert not _is_conflict(result)

    async def test_multiple_pre_trade_rows_for_same_user_allowed(self):
        from app.routers.trades import create_trade
        from app.schemas.trade import TradeCreate

        body = TradeCreate(trade_date=date(2026, 4, 26), instrument="ES")

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=None)):
            result = await create_trade(
                body=body, force=False, db=_make_db(), current_user=_make_user()
            )

        assert not _is_conflict(result)


# ---------------------------------------------------------------------------
# PATCH /api/trades/{id} singleton guard
# ---------------------------------------------------------------------------

class TestUpdateTradeSingleton:
    async def test_409_on_pre_trade_to_active_when_conflict(self):
        from app.routers.trades import update_trade
        from app.schemas.trade import TradeUpdate

        target_id = uuid.uuid4()
        target = _make_pre_trade(target_id)
        active = _make_active_trade()  # different trade

        body = TradeUpdate(status=TradeStatus.active)

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await update_trade(
                trade_id=target_id,
                body=body,
                force=False,
                db=_make_db(fetched_trade=target),
                current_user=_make_user(),
            )

        assert _is_conflict(result)
        data = json.loads(result.body)
        assert data["detail"] == "active_trade_conflict"
        assert data["active_trade_id"] == str(ACTIVE_TRADE_ID)

    async def test_force_true_bypasses_409_on_patch(self):
        from app.routers.trades import update_trade
        from app.schemas.trade import TradeUpdate

        target_id = uuid.uuid4()
        target = _make_pre_trade(target_id)
        active = _make_active_trade()

        body = TradeUpdate(status=TradeStatus.active)

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await update_trade(
                trade_id=target_id,
                body=body,
                force=True,
                db=_make_db(fetched_trade=target),
                current_user=_make_user(),
            )

        assert not _is_conflict(result)

    async def test_no_conflict_when_no_other_active_trade(self):
        from app.routers.trades import update_trade
        from app.schemas.trade import TradeUpdate

        target_id = uuid.uuid4()
        target = _make_pre_trade(target_id)

        body = TradeUpdate(status=TradeStatus.active)

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=None)):
            result = await update_trade(
                trade_id=target_id,
                body=body,
                force=False,
                db=_make_db(fetched_trade=target),
                current_user=_make_user(),
            )

        assert not _is_conflict(result)

    async def test_patching_non_status_fields_never_blocked(self):
        from app.routers.trades import update_trade
        from app.schemas.trade import TradeUpdate

        target_id = uuid.uuid4()
        target = _make_pre_trade(target_id)
        active = _make_active_trade()

        # No status change — singleton guard never fires
        body = TradeUpdate(instrument="ES", narrative="Updated narrative")

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=active)):
            result = await update_trade(
                trade_id=target_id,
                body=body,
                force=False,
                db=_make_db(fetched_trade=target),
                current_user=_make_user(),
            )

        assert not _is_conflict(result)

    async def test_no_conflict_when_same_trade_is_the_active_one(self):
        """If get_active_trade returns the trade being patched, existing.id == trade_id → no 409."""
        from app.routers.trades import update_trade
        from app.schemas.trade import TradeUpdate

        # Simulate an already-active trade being re-patched (edge case)
        # The transition guard won't fire since status == status, but test the id check
        target_id = ACTIVE_TRADE_ID
        target = _make_pre_trade(target_id)  # treat as pre_trade for transition
        same_trade_as_active = _make_active_trade()  # same id as target_id

        body = TradeUpdate(status=TradeStatus.active)

        with patch("app.routers.trades.get_active_trade", AsyncMock(return_value=same_trade_as_active)):
            result = await update_trade(
                trade_id=target_id,
                body=body,
                force=False,
                db=_make_db(fetched_trade=target),
                current_user=_make_user(),
            )

        # existing.id == trade_id → guard skips → no conflict
        assert not _is_conflict(result)
