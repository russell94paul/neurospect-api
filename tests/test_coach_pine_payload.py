"""Regression tests: sample Pine Script payloads parse into Layer2Payload cleanly.

These fixtures represent what neurospect-coach.pine emits. If either the Pine
schema or the Pydantic model drifts, this catches it.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.coach import Layer2Payload


BULLISH_NY_AM = {
    "secret": "test-secret",
    "idempotency_key": "NQ1!:1714046700000:12345",
    "instrument": "NQ1!",
    "timestamp": "2026-04-22T13:45:00Z",
    "session": "ny_am",
    "open": 19820.50, "high": 19855.00, "low": 19810.25, "close": 19845.75,
    "midnight_open": 19830.00, "open_830": 19815.00, "open_930": 19822.50,
    "htf_fvg_bias": "bullish",
    "htf_fvg_range": [19800.00, 19850.00],
    "price_vs_midnight_open": "below",
    "news_flag": False,
    "structure_note": "",
    "fvg_source": "auto",
}

BEARISH_LONDON = {
    **BULLISH_NY_AM,
    "idempotency_key": "NQ1!:1714030800000:11110",
    "timestamp": "2026-04-22T03:00:00Z",
    "session": "london",
    "htf_fvg_bias": "bearish",
    "htf_fvg_range": [19900.00, 19960.00],
    "price_vs_midnight_open": "above",
    "fvg_source": "manual",
}

OFF_SESSION_NEWS = {
    **BULLISH_NY_AM,
    "idempotency_key": "NQ1!:1714071600000:99999",
    "timestamp": "2026-04-22T20:30:00Z",
    "session": "off",
    "news_flag": True,
    "structure_note": "FOMC at 14:00 ET",
}

MISSING_OPENS = {
    **BULLISH_NY_AM,
    "idempotency_key": "NQ1!:1714019400000:22222",
    "timestamp": "2026-04-22T00:10:00Z",
    "session": "off",
    "midnight_open": None,
    "open_830": None,
    "open_930": None,
    "price_vs_midnight_open": "na",
}


@pytest.mark.parametrize(
    "fixture",
    [BULLISH_NY_AM, BEARISH_LONDON, OFF_SESSION_NEWS, MISSING_OPENS],
    ids=["bullish_ny_am", "bearish_london", "off_session_news", "missing_opens"],
)
def test_pine_payload_parses(fixture: dict) -> None:
    model = Layer2Payload.model_validate(fixture)
    assert model.instrument == fixture["instrument"]
    assert model.session == fixture["session"]


def test_secret_is_required() -> None:
    bad = dict(BULLISH_NY_AM)
    del bad["secret"]
    with pytest.raises(ValidationError):
        Layer2Payload.model_validate(bad)


def test_unknown_session_rejected() -> None:
    bad = dict(BULLISH_NY_AM, session="weekend")
    with pytest.raises(ValidationError):
        Layer2Payload.model_validate(bad)


def test_extra_fields_rejected() -> None:
    bad = dict(BULLISH_NY_AM, unexpected="x")
    with pytest.raises(ValidationError):
        Layer2Payload.model_validate(bad)


def test_htf_fvg_range_is_tuple() -> None:
    model = Layer2Payload.model_validate(BULLISH_NY_AM)
    assert model.htf_fvg_range == (19800.00, 19850.00)
