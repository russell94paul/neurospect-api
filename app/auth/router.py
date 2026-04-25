from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.discord import exchange_code, get_discord_user
from app.auth.jwt import create_access_token
from app.config import settings
from app.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class DiscordTokenRequest(BaseModel):
    code: str
    redirect_uri: str


class DebugTokenRequest(BaseModel):
    discord_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# POST /auth/discord/token
# SPA pattern: frontend POSTs the code it received from Discord redirect.
# ---------------------------------------------------------------------------

@router.post("/discord/token", response_model=TokenResponse)
async def discord_token(body: DiscordTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        discord_access_token = await exchange_code(body.code, body.redirect_uri)
        discord_user = await get_discord_user(discord_access_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discord OAuth exchange failed",
        )

    discord_id = discord_user["id"]
    username = discord_user.get("username")
    avatar_hash = discord_user.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash else None
    )

    # Upsert user row keyed on discord_id
    result = await db.execute(select(User).where(User.discord_id == discord_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            discord_id=discord_id,
            discord_username=username,
            discord_avatar_url=avatar_url,
        )
        db.add(user)
    else:
        user.discord_username = username
        user.discord_avatar_url = avatar_url

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "discord_id": discord_id})
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "discord_id": current_user.discord_id,
        "discord_username": current_user.discord_username,
        "discord_avatar_url": current_user.discord_avatar_url,
    }


# ---------------------------------------------------------------------------
# POST /auth/debug/token  — DEBUG=true only, never deployed to prod
# ---------------------------------------------------------------------------

@router.post("/debug/token", response_model=TokenResponse)
async def debug_token(body: DebugTokenRequest, db: AsyncSession = Depends(get_db)):
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    result = await db.execute(select(User).where(User.discord_id == body.discord_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            discord_id=body.discord_id,
            discord_username=f"debug_{body.discord_id}",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "discord_id": body.discord_id})
    return TokenResponse(access_token=token)
