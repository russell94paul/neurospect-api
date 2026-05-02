"""Tests for Tradovate broker integration — crypto, schema helpers, and service layer.

Environment vars must be set before app.* imports because pydantic_settings
reads them at Settings() instantiation (module level in config.py).
"""
from __future__ import annotations

import os

# Must precede any app.* imports.
_TEST_FERNET_KEY = "S3Jb5QZQK2UhMFHN4CjCiJMf3gqrJlpYktNbxFKHt1I="
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest")
os.environ.setdefault("BROKER_CRED_SECRET", _TEST_FERNET_KEY)

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.crypto import decrypt, encrypt
from app.services.tradovate import TradovateAuthError, authenticate
from app.schemas.broker import FillDTO, BracketInfo


# ---------------------------------------------------------------------------
# crypto — encrypt / decrypt round-trip
# ---------------------------------------------------------------------------

class TestCrypto:
    def test_roundtrip_ascii(self):
        plaintext = "hello world"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_special_chars(self):
        plaintext = "p4$$w0rd!@#%^&*()=+[]{}|;':\",./<>?"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_long_string(self):
        plaintext = "a" * 1000
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_encrypt_produces_different_ciphertext_each_call(self):
        # Fernet uses a random IV so two encryptions of the same plaintext differ
        plaintext = "same input"
        assert encrypt(plaintext) != encrypt(plaintext)

    def test_decrypt_raises_on_tampered_ciphertext(self):
        from cryptography.fernet import InvalidToken
        with pytest.raises(Exception):  # InvalidToken or binascii.Error
            decrypt("notvalidbase64==")


# ---------------------------------------------------------------------------
# _mask_username helper
# ---------------------------------------------------------------------------

class TestMaskUsername:
    """Test the _mask_username helper in the router."""

    def _mask(self, username: str) -> str:
        from app.routers.tradovate import _mask_username
        return _mask_username(username)

    def test_normal_username(self):
        assert self._mask("paulrussell") == "pa***ll"

    def test_short_username_shows_stars(self):
        assert self._mask("ab") == "***"
        assert self._mask("abcd") == "***"

    def test_five_chars(self):
        result = self._mask("abcde")
        assert result.startswith("ab")
        assert result.endswith("de")
        assert "***" in result

    def test_tradovate_style_username(self):
        result = self._mask("LTTE1CU0Y79")
        assert result.startswith("LT")
        assert result.endswith("79")
        assert "***" in result


# ---------------------------------------------------------------------------
# authenticate() — mocked httpx
# ---------------------------------------------------------------------------

class TestAuthenticate:
    """authenticate() parses Tradovate auth responses correctly."""

    _GOOD_RESPONSE = {
        "accessToken": "header.eyJleHAiOjE3NDYwMDAwMDB9.sig",
        "mdAccessToken": "md.token.here",
        "userId": 12345,
        "userStatus": "Active",
        "name": "testuser",
    }

    async def _call_authenticate(self, response_json: dict, status_code: int = 200) -> dict:
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = response_json

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        return await authenticate("testuser", "testpass", "demo", mock_client)

    async def test_success_returns_token_dict(self):
        result = await self._call_authenticate(self._GOOD_RESPONSE)
        assert result["accessToken"] == self._GOOD_RESPONSE["accessToken"]
        assert result["mdAccessToken"] == self._GOOD_RESPONSE["mdAccessToken"]

    async def test_error_text_raises_auth_error(self):
        with pytest.raises(TradovateAuthError, match="Incorrect"):
            await self._call_authenticate(
                {"errorText": "Incorrect username or password. Please try again, noting that passwords are case-sensitive."}
            )

    async def test_401_raises_auth_error(self):
        with pytest.raises(TradovateAuthError):
            await self._call_authenticate({}, status_code=401)

    async def test_captcha_raises_auth_error(self):
        with pytest.raises(TradovateAuthError, match="CAPTCHA"):
            await self._call_authenticate(
                {
                    "p-ticket": "someticket",
                    "p-time": 15,
                    "p-captcha": True,
                    "p-message": "Rate limit exceeded",
                }
            )

    async def test_missing_access_token_raises(self):
        with pytest.raises(TradovateAuthError, match="Unexpected"):
            await self._call_authenticate({"userId": 1})


# ---------------------------------------------------------------------------
# FillDTO schema
# ---------------------------------------------------------------------------

class TestFillDTO:
    def test_fill_dto_without_bracket(self):
        from datetime import datetime, timezone
        fill = FillDTO(
            tradovate_fill_id=999,
            instrument="NQM6",
            side="buy",
            qty=2,
            price=Decimal("21500.25"),
            timestamp=datetime(2026, 4, 26, 14, 30, tzinfo=timezone.utc),
            order_id=12345,
        )
        assert fill.bracket is None
        assert fill.tradovate_fill_id == 999

    def test_fill_dto_with_bracket(self):
        from datetime import datetime, timezone
        fill = FillDTO(
            tradovate_fill_id=999,
            instrument="NQM6",
            side="buy",
            qty=1,
            price=Decimal("21500.00"),
            timestamp=datetime(2026, 4, 26, 14, 30, tzinfo=timezone.utc),
            order_id=12345,
            bracket=BracketInfo(
                stop_price=Decimal("21450.00"),
                target_price=Decimal("21600.00"),
            ),
        )
        assert fill.bracket is not None
        assert fill.bracket.stop_price == Decimal("21450.00")
        assert fill.bracket.target_price == Decimal("21600.00")
