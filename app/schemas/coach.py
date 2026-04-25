"""Pydantic schemas for the AI Coach pipeline.

Layer 2 is the payload TradingView sends via webhook (Pine Script → FastAPI).
Layer 3 is the JSON Claude returns. Both mirror the schemas documented in
processes/distributed-workflow/active/ai-coach.md in the wiki.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Layer 2 — market context sent by TradingView
# ---------------------------------------------------------------------------

Session = Literal["asia", "london", "ny_am", "ny_pm", "off"]
Bias = Literal["bullish", "bearish", "neutral"]
PriceVsMidnight = Literal["below", "above", "at", "na"]
FvgSource = Literal["auto", "manual"]


class Layer2Payload(BaseModel):
    """What the Pine Script alert() posts to /webhooks/tradingview/{token}."""

    model_config = ConfigDict(extra="forbid")

    secret: str
    idempotency_key: str = Field(min_length=1, max_length=256)
    instrument: str = Field(min_length=1, max_length=20)
    timestamp: datetime
    session: Session
    open: float
    high: float
    low: float
    close: float
    midnight_open: float | None = None
    open_830: float | None = None
    open_930: float | None = None
    htf_fvg_bias: Bias = "neutral"
    htf_fvg_range: tuple[float, float] | None = None
    price_vs_midnight_open: PriceVsMidnight = "na"
    news_flag: bool = False
    structure_note: str | None = None
    fvg_source: FvgSource = "auto"


# ---------------------------------------------------------------------------
# Layer 3 — Claude's coaching response
# ---------------------------------------------------------------------------


class ChecklistItem(BaseModel):
    id: str
    met: bool
    note: str = ""


class ValidStrategy(BaseModel):
    strategy_id: str
    confidence: Literal["high", "medium", "low"]
    checklist: list[ChecklistItem] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    watch_for: str = ""


Layer3Bias = Literal["bullish", "bearish", "neutral", "stand_aside"]


class Layer3Response(BaseModel):
    """Claude's JSON output, matching system-prompt-template.md §Output Format."""

    model_config = ConfigDict(extra="allow")  # tolerate future prompt-level additions

    bias: Layer3Bias
    narrative: str
    valid_strategies: list[ValidStrategy] = Field(default_factory=list)
    invalid_strategies: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API response envelopes
# ---------------------------------------------------------------------------


class WebhookAccepted(BaseModel):
    status: Literal["accepted", "duplicate"]
    coaching_event_id: UUID


class CoachingEventResponse(BaseModel):
    id: UUID
    status: Literal["pending", "complete", "error"]
    instrument: str
    alert_timestamp: datetime
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = None
    error_message: str | None = None
    claude_latency_ms: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class TvTokenResponse(BaseModel):
    token: str
    webhook_url: str
    created_at: datetime
