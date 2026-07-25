"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    # Application
    app_name: str = "Daily Money Tracker"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:5173"]

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/daily_money_tracker"

    # Scheduler
    scheduler_enabled: bool = True

    # Push Notifications (VAPID)
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:admin@example.com"

    # JWT
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
