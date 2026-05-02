from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, SecretStr


class BrokerCredentialsCreate(BaseModel):
    username: str
    password: SecretStr
    environment: Literal["demo", "live"] = "demo"


class BrokerTokenCreate(BaseModel):
    """Paste-mode for prop firm accounts that lack direct REST API access.

    User extracts the Bearer token from browser dev tools while logged into
    trader.tradovate.com and pastes it here. Token is stored directly;
    no auto-refresh is possible (user must re-paste when it expires).

    How to get the token:
      1. Log in at trader.tradovate.com
      2. Open DevTools (F12) → Network tab
      3. Refresh the page
      4. Click any request to demo.tradovateapi.com
      5. Headers → Authorization: Bearer <token>
      6. Copy the token (everything after "Bearer ")
    """

    access_token: str
    environment: Literal["demo", "live"] = "demo"


class BrokerCredentialsResponse(BaseModel):
    environment: str
    is_connected: bool
    last_auth_at: datetime | None
    username_masked: str


class BracketInfo(BaseModel):
    stop_price: Decimal | None
    target_price: Decimal | None


class FillDTO(BaseModel):
    tradovate_fill_id: int
    instrument: str
    side: str  # "buy" | "sell"
    qty: int
    price: Decimal
    timestamp: datetime
    order_id: int
    bracket: BracketInfo | None = None
