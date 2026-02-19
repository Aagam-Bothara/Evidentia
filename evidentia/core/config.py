"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import Enum

from pydantic_settings import BaseSettings


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class Settings(BaseSettings):
    """Global application settings — loaded from .env or environment."""

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    # Server
    evidentia_host: str = "0.0.0.0"
    evidentia_port: int = 8000
    evidentia_env: Environment = Environment.DEVELOPMENT
    evidentia_debug: bool = False
    evidentia_log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://evidentia:evidentia@localhost:5432/evidentia"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_provider: LLMProvider = LLMProvider.OPENAI
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Tool API keys (BYO-API)
    serpapi_key: str | None = None
    semantic_scholar_api_key: str | None = None
    ncbi_api_key: str | None = None
    openalex_email: str | None = None

    # Security
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 43200  # 30 days
    allowed_origins: str = "http://localhost:8000,http://localhost:3000"

    # Object storage
    s3_bucket: str = "evidentia-docs"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Execution budgets
    max_tool_calls_per_run: int = 50
    max_retries_per_step: int = 3
    tool_timeout_seconds: int = 30

    @property
    def is_production(self) -> bool:
        return self.evidentia_env == Environment.PRODUCTION


def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
