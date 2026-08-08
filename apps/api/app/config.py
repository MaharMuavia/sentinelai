import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    ENV: str = "development"

    # DataHub Settings & Data Modes
    DATAHUB_GMS_URL: str = "http://localhost:8080"
    DATAHUB_MCP_ENDPOINT: str = "http://localhost:8080/mcp"
    DATAHUB_GMS_TOKEN: Optional[str] = None
    DATAHUB_MUTATION_ENABLED: bool = False  # Security default OFF unless authorized
    SENTINEL_DATA_MODE: str = "live"  # "live" (default) or "fixture"

    # AI / LLM Settings
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    AGENT_MODEL: str = "gpt-4o"

    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_REPOSITORY: Optional[str] = "acme/data-platform"

    # Security & API Auth
    SENTINEL_AUTH_TOKEN: Optional[str] = None

    # SQLite Database
    DATABASE_URL: str = "sqlite:///./sentinel.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
