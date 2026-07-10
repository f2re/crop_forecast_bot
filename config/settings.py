from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    redis_url: str | None
    app_env: str
    coordination_namespace: str
    cds_api_url: str
    cds_api_key: str | None
    openrouter_api_key: str | None
    log_level: str
    scheduler_timezone: str
    heartbeat_file: Path
    open_meteo_cache_path: Path

    def validate(self) -> None:
        errors: list[str] = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not self.database_url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            errors.append("DATABASE_URL must use an async SQLAlchemy driver")
        if not self.coordination_namespace:
            errors.append("COORDINATION_NAMESPACE must not be empty")
        try:
            ZoneInfo(self.scheduler_timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"Unknown SCHEDULER_TIMEZONE: {self.scheduler_timezone}")
        if self.app_env == "production":
            if not self.database_url.startswith("postgresql+asyncpg://"):
                errors.append("Production requires PostgreSQL with asyncpg")
            if not self.redis_url:
                errors.append("Production requires REDIS_URL for FSM and scheduler leases")
        if errors:
            raise RuntimeError("Invalid runtime configuration: " + "; ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("DB_PORT", "5432"))
        db_name = os.getenv("DB_NAME", "crop_forecast_bot")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "")
        database_url = (
            f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    redis_url = os.getenv("REDIS_URL", "").strip() or None
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        database_url=database_url,
        redis_url=redis_url,
        app_env=os.getenv("APP_ENV", "development").strip().lower(),
        coordination_namespace=os.getenv(
            "COORDINATION_NAMESPACE", "crop-forecast-bot"
        ).strip(),
        cds_api_url=os.getenv(
            "CDS_API_URL", "https://cds.climate.copernicus.eu/api"
        ).strip(),
        cds_api_key=os.getenv("CDS_API_KEY", "").strip() or None,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip() or None,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        scheduler_timezone=os.getenv("SCHEDULER_TIMEZONE", "Europe/Moscow"),
        heartbeat_file=Path(
            os.getenv("HEARTBEAT_FILE", ".runtime/heartbeat")
        ).expanduser(),
        open_meteo_cache_path=Path(
            os.getenv("OPEN_METEO_CACHE_PATH", ".cache/openmeteo")
        ).expanduser(),
    )


def get_database_url() -> str:
    return get_settings().database_url


# Transitional module-level names for modules not yet migrated to dependency injection.
# The production entrypoint uses Settings directly.
_settings = get_settings()
TELEGRAM_BOT_TOKEN = _settings.telegram_bot_token
CDS_API_URL = _settings.cds_api_url
CDS_API_KEY = _settings.cds_api_key
OPENROUTER_API_KEY = _settings.openrouter_api_key
DATABASE_URL = _settings.database_url
