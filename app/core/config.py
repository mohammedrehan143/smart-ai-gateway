"""Configuration and environment settings with production validation and Render support."""

import json
from typing import Dict, List, Literal, Optional
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
    # Additional allowed API keys for key rotation
    ALLOWED_API_KEYS: List[str] = []
    # Revoked API keys list
    REVOKED_API_KEYS: List[str] = []
    # JSON-encoded dictionary of tenant API keys mapping api_key -> user_id
    TENANT_API_KEYS: str = "{}"

    # Dedicated Credential Encryption Master Key (strictly required in production)
    ENCRYPTION_MASTER_KEY: Optional[str] = None
    # Previous encryption keys for seamless key rotation
    ENCRYPTION_PREVIOUS_KEYS: List[str] = []

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
    RATE_LIMIT_RPM: int = 120  # Default 120 requests/minute per client
    RATE_LIMIT_ENABLED: bool = True
    MAX_FAILED_AUTH_ATTEMPTS: int = 5  # Brute-force protection: max failed auths in window

    # SSRF & Network Protection
    SSRF_PROTECTION_ENABLED: bool = True
    ALLOW_LOOPBACK_IN_DEV: bool = True  # Permitted only in local/test for mock testing

    # Versioning
    ROUTING_POLICY_VERSION: str = "1.0.0"
    RATE_CARD_VERSION: str = "2026-11-01"

    # Privacy & Telemetry
    STORE_PROMPT_CONTENT: bool = False
    METRICS_ENABLED: bool = True
    ENABLE_MOCK_GATEWAY: bool = False

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

    def get_tenant_key_mappings(self) -> Dict[str, str]:
        """Parses TENANT_API_KEYS JSON string to dictionary mapping api_key -> user_id."""
        if not self.TENANT_API_KEYS:
            return {}
        try:
            parsed = json.loads(self.TENANT_API_KEYS)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def validate_production_security(self) -> None:
        """Enforces critical production security invariants at application startup.

        Raises:
            ValueError: If critical security configurations are missing or insecure in production.
        """
        if self.APP_ENV in ("production", "staging"):
            # 1. GATEWAY_API_KEY must be configured
            if not self.GATEWAY_API_KEY or len(self.GATEWAY_API_KEY.strip()) < 16:
                raise ValueError(
                    f"{self.APP_ENV.capitalize()} Security Error: GATEWAY_API_KEY must be configured with a minimum of 16 characters in production mode."
                )

            # 2. ENCRYPTION_MASTER_KEY must be configured and independent
            if not self.ENCRYPTION_MASTER_KEY or len(self.ENCRYPTION_MASTER_KEY.strip()) < 16:
                raise ValueError(
                    f"{self.APP_ENV.capitalize()} Security Error: Dedicated ENCRYPTION_MASTER_KEY must be configured with a minimum of 16 characters in production mode."
                )

            # 3. Dedicated master key must not be identical to GATEWAY_API_KEY
            if self.ENCRYPTION_MASTER_KEY.strip() == self.GATEWAY_API_KEY.strip():
                raise ValueError(
                    f"{self.APP_ENV.capitalize()} Security Error: ENCRYPTION_MASTER_KEY must be independent and not identical to GATEWAY_API_KEY."
                )

            # 4. Wildcard CORS is strictly forbidden with credentials in production
            if "*" in self.ALLOWED_CORS_ORIGINS:
                raise ValueError(
                    f"{self.APP_ENV.capitalize()} Security Error: Wildcard '*' in ALLOWED_CORS_ORIGINS is prohibited in production mode. Specify trusted origins."
                )

            # 5. Mock gateway cannot be enabled in production
            if self.ENABLE_MOCK_GATEWAY:
                raise ValueError(
                    f"{self.APP_ENV.capitalize()} Security Error: ENABLE_MOCK_GATEWAY cannot be set to true in production mode."
                )


settings = Settings()
