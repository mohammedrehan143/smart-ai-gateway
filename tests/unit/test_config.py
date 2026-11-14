"""Unit tests for configuration and settings."""

from app.core.config import Settings


def test_settings_default_values():
    s = Settings(APP_ENV="local")
    assert s.APP_PORT == 8000
    assert s.is_dev_mode is True
    assert s.REQUEST_TIMEOUT_SECONDS == 30.0
    assert s.CHEAP_MODEL_ALIAS == "mock-cheap"


def test_settings_auth_mode():
    s = Settings(APP_ENV="production", GATEWAY_API_KEY="secret-key")
    assert s.is_dev_mode is False
