"""Unit tests for the webhook validation primitives."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.coach import validation
from app.config import settings


def _make_request(*, xff: str | None = None, client_ip: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_ip, 0) if client_ip else None,
    }
    return Request(scope)


def test_verify_secret_happy(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_webhook_secret", "shh", raising=False)
    validation.verify_secret("shh")  # no exception


def test_verify_secret_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_webhook_secret", "shh", raising=False)
    with pytest.raises(HTTPException) as exc:
        validation.verify_secret("nope")
    assert exc.value.status_code == 401


def test_verify_secret_unset(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_webhook_secret", "", raising=False)
    with pytest.raises(HTTPException) as exc:
        validation.verify_secret("anything")
    assert exc.value.status_code == 401


def test_ip_allowlist_disabled(monkeypatch):
    monkeypatch.setattr(settings, "tradingview_ip_allowlist", "", raising=False)
    validation.verify_ip_allowlist(_make_request(client_ip="1.2.3.4"))


def test_ip_allowlist_blocks(monkeypatch):
    monkeypatch.setattr(
        settings, "tradingview_ip_allowlist", "52.89.214.238,34.212.75.30", raising=False
    )
    with pytest.raises(HTTPException) as exc:
        validation.verify_ip_allowlist(_make_request(client_ip="9.9.9.9"))
    assert exc.value.status_code == 403


def test_ip_allowlist_allows_via_xff(monkeypatch):
    monkeypatch.setattr(
        settings, "tradingview_ip_allowlist", "52.89.214.238", raising=False
    )
    req = _make_request(xff="52.89.214.238, 10.0.0.1", client_ip="10.0.0.1")
    validation.verify_ip_allowlist(req)
