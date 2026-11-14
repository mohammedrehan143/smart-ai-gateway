"""Configuration and environment settings with production validation and Render support."""

from typing import List, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["local", "test", "staging", "production"] = "local"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    PORT: Optional[int] = None  # Injected automatically by Render/Cloud platforms
    LOG_LEVEL: str = "INFO"

    # Gateway Auth (Strictly required in production)
    GATEWAY_API_KEY: Optional[str] = None

    # Persistence (Supports SQLite and PostgreSQL)
    DATABASE_URL: str = "sqlite:///./gateway_traces.db"

    # Caching
    CACHE_BACKEND: Literal["memory", "redis"] = "memory"
    CACHE_TTL_SECONDS: int = 300
    REDIS_URL: Optional[str] = None

    # Models & Tiers
    CHEAP_MODEL_ALIAS: str = "mock-cheap"
    STRONG_MODEL_ALIAS: str = "mock-strong"
    FALLBACK_MODEL_ALIAS: str = "mock-strong"

    # Execution & Protection Limits
    REQUEST_TIMEOUT_SECONDS: float = 30.0
    MAX_PROVIDER_ATTEMPTS: int = 3
    MAX_INPUT_TOKENS: int = 8192
    MAX_OUTPUT_TOKENS: int = 4096
    MAX_REQUEST_BODY_BYTES: int = 1_048_576  # 1 MB protection against DoS
    RATE_LIMIT_RPM: int = 120                 # Default 120 requests/minute per client

    # Versioning
    ROUTING_POLICY_VERSION: str = "1.0.0"
    RATE_CARD_VERSION: str = "2026-11-01"

    # Privacy & Telemetry
    STORE_PROMPT_CONTENT: bool = False
    METRICS_ENABLED: bool = True

    # Security
    ALLOWED_CORS_ORIGINS: List[str] = ["*"]

    # Primary External Provider Credentials (e.g. OpenAI / OpenRouter / Groq)
    PROVIDER_API_KEY: Optional[str] = None
    PROVIDER_BASE_URL: str = "https://api.openai.com/v1"

    # Optional Dedicated Credentials for Cheap vs Strong Models
    CHEAP_PROVIDER_API_KEY: Optional[str] = None
    CHEAP_PROVIDER_BASE_URL: Optional[str] = None

    STRONG_PROVIDER_API_KEY: Optional[str] = None
    STRONG_PROVIDER_BASE_URL: Optional[str] = None

    @property
    def effective_port(self) -> int:
        return self.PORT or self.APP_PORT

    @property
    def is_dev_mode(self) -> bool:
        return self.APP_ENV in ("local", "test") and not self.GATEWAY_API_KEY


settings = Settings()
