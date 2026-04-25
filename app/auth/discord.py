import httpx

from app.config import settings

_DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
_DISCORD_USER_URL = "https://discord.com/api/users/@me"


async def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange Discord OAuth2 authorization code for an access token.
    Returns the Discord access token string.
    """
    data = {
        "client_id": settings.discord_client_id,
        "client_secret": settings.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _DISCORD_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def get_discord_user(access_token: str) -> dict:
    """Fetch Discord user profile using an access token.
    Returns dict with at least: id, username, avatar.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _DISCORD_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()
