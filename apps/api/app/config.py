import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    ENV: str = "development"

    # DataHub Settings & Data Modes
    DATAHUB_GMS_URL: str = "http://localhost:8080"
    DATAHUB_MCP_ENDPOINT: Optional[str] = None
    DATAHUB_MCP_COMMAND: Optional[str] = None
    DATAHUB_MCP_ARGS: str = "[]"
    DATAHUB_GMS_TOKEN: Optional[str] = None
    DATAHUB_MUTATION_ENABLED: bool = False  # Security default OFF unless authorized
    SENTINEL_DATA_MODE: str = "live"  # "live" (default) or "fixture"

    # AI / LLM Settings
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    AGENT_MODEL: str = "gpt-4o"

    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_REPOSITORY: Optional[str] = None

    # Security & API Auth
    AUTH_MODE: str = "static"
    SENTINEL_AUTH_TOKEN: Optional[str] = None
    OIDC_ISSUER: Optional[str] = None
    OIDC_AUDIENCE: Optional[str] = None
    OIDC_JWKS_URL: Optional[str] = None
    OIDC_ALGORITHM: str = "RS256"
    OIDC_REQUIRED_SCOPES: str = "sentinel:mutate"
    OIDC_CLOCK_SKEW_SECONDS: int = 30
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # SQLite Database
    DATABASE_URL: str = "sqlite:///./sentinel.db"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
