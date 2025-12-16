import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Учетные данные для Copernicus CDS API
CDS_API_URL = os.getenv("CDS_API_URL")
CDS_API_KEY = os.getenv("CDS_API_KEY")

# OpenRouter API для LLM рекомендаций
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "crop_forecast_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def get_database_url() -> str:
    """Get async database URL for PostgreSQL"""
    # If DATABASE_URL is set, use it directly
    if DATABASE_URL:
        # Convert postgresql:// to postgresql+asyncpg:// if needed
        if DATABASE_URL.startswith("postgresql://"):
            return DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return DATABASE_URL
    # Otherwise, construct from individual components
    return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
