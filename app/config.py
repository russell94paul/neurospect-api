from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str
    database_url_sync: str = ""

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        # Prefer explicit DATABASE_URL_SYNC; fall back to deriving from DATABASE_URL.
        url = self.database_url_sync or self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg2://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        return url

    # JWT
    jwt_secret: str
    jwt_expire_minutes: int = 43200

    # Discord OAuth
    discord_client_id: str = ""
    discord_client_secret: str = ""

    # Cloudflare R2
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "neurospect-screenshots"

    # AI Coach — TradingView webhook
    tradingview_webhook_secret: str = ""
    tradingview_ip_allowlist: str = ""  # comma-separated; empty = disabled
    public_base_url: str = "http://localhost:8000"  # used in generated webhook URLs

    # AI Coach — Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 2048
    claude_timeout_seconds: float = 30.0
    ai_coach_prompt_dir: str = str(
        Path(__file__).parent / "coach" / "prompts"
    )

    # CORS — comma-separated allowed origins (e.g. "http://localhost:5173,https://neurospect.app")
    cors_origins: list[str] = ["http://localhost:5173"]

    # Debug mode — enables /auth/debug/token; never true in prod
    debug: bool = False


settings = Settings()  # type: ignore[call-arg]
