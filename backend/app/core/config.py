"""Runtime configuration, loaded from environment (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CanopyOps Treatment Assurance API"
    environment: str = "local"

    # Database (PostGIS). Overridden by docker-compose in the container network.
    database_url: str = (
        "postgresql+psycopg2://canopyops:canopyops@localhost:5432/canopyops"
    )

    # Synthetic JWT auth. NOT a real secret; the prototype issues its own tokens
    # for synthetic users only. Never reuse in production.
    jwt_secret: str = "synthetic-dev-secret-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # CORS origin for the Angular dev/prod container.
    frontend_origin: str = "http://localhost:4200"


@lru_cache
def get_settings() -> Settings:
    return Settings()
