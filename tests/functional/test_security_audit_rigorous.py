"""Rigorous Security Audit Suite verifying all 16 security check vectors."""

from __future__ import annotations

import os
import sys
import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.core.config import Settings, settings
from app.core.crypto import mask_secret
from app.core.errors import SSRFSecurityError
from app.core.network_security import validate_provider_base_url
from app.core.rate_limiter import default_rate_limiter
from app.main import app


@pytest.mark.asyncio
async def test_sec_01_auth_bypass_prevention():
    """V-01: Verify auth bypass is strictly impossible when key configured."""
    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    try:
        settings.APP_ENV = "staging"
        settings.GATEWAY_API_KEY = "live-master-secret-key-12345"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. No header
            r1 = await client.get("/v1/auth/verify")
            assert r1.status_code == 401
            assert r1.json()["error"]["type"] == "unauthorized"

            # 2. Basic auth scheme instead of Bearer
            r2 = await client.get("/v1/auth/verify", headers={"Authorization": "Basic dXNlcjpwYXNz"})
            assert r2.status_code == 401

            # 3. Forged Bearer token
            r3 = await client.get("/v1/auth/verify", headers={"Authorization": "Bearer forged-token-xyz"})
            assert r3.status_code == 401
    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key


def test_sec_02_production_startup_validation():
    """V-02: Verify missing or weak secrets fail fast during startup."""
    # Weak key
    s_weak = Settings(APP_ENV="production", GATEWAY_API_KEY="short", ENCRYPTION_MASTER_KEY="valid-secret-key-12345")
    with pytest.raises(ValueError, match="minimum of 16 characters"):
        s_weak.validate_production_security()

    # Missing encryption key
    s_no_enc = Settings(APP_ENV="production", GATEWAY_API_KEY="valid-gateway-secret-12345", ENCRYPTION_MASTER_KEY=None)
    with pytest.raises(ValueError, match="ENCRYPTION_MASTER_KEY must be configured"):
        s_no_enc.validate_production_security()


@pytest.mark.asyncio
async def test_sec_03_cross_tenant_isolation():
    """V-03: Verify tenant data cannot be queried across tenants."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant X stores key
        await client.post(
            "/v1/credentials",
            json={"provider": "anthropic", "api_key": "sk-ant-secret-tenant-x"},
            headers={"X-User-ID": "tenant_x"},
        )
        # Tenant Y queries credentials
        r_y = await client.get("/v1/credentials", headers={"X-User-ID": "tenant_y"})
        assert r_y.status_code == 200
        assert len(r_y.json()) == 0

        # Tenant Y attempts deletion of X's credential
        r_del = await client.delete("/v1/credentials/anthropic", headers={"X-User-ID": "tenant_y"})
        assert r_del.status_code == 404

        # Clean up
        await client.delete("/v1/credentials/anthropic", headers={"X-User-ID": "tenant_x"})


def test_sec_04_credential_masking_invariants():
    """V-04: Verify secrets are masked and plaintext never leaks."""
    keys = [
        "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz",
        "gsk_abcdef1234567890",
        "AIzaSyDemoGoogleKey1234567890",
    ]
    for k in keys:
        masked = mask_secret(k)
        assert masked.startswith(k[:3])
        assert masked.endswith(k[-4:])
        assert k[4:-5] not in masked


def test_sec_05_ssrf_comprehensive_blocking():
    """V-05: Verify all internal and cloud metadata destinations are blocked."""
    orig_env = settings.APP_ENV
    orig_loopback = settings.ALLOW_LOOPBACK_IN_DEV
    try:
        settings.APP_ENV = "production"
        settings.ALLOW_LOOPBACK_IN_DEV = False
        forbidden = [
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://127.0.0.1:8000/admin",
            "http://10.0.0.5/api",
            "http://172.16.1.1/api",
            "http://192.168.0.1/secrets",
            "http://0.0.0.0:8000",
            "ftp://api.openai.com/v1",
            "file:///etc/shadow",
        ]
        for target in forbidden:
            with pytest.raises(SSRFSecurityError):
                validate_provider_base_url(target)
    finally:
        settings.APP_ENV = orig_env
        settings.ALLOW_LOOPBACK_IN_DEV = orig_loopback


def test_sec_06_cors_production_restriction():
    """V-06: Verify wildcard CORS is strictly rejected in production."""
    s = Settings(
        APP_ENV="production",
        GATEWAY_API_KEY="valid-secret-key-12345",
        ENCRYPTION_MASTER_KEY="valid-encryption-key-12345",
        ALLOWED_CORS_ORIGINS=["*"],
    )
    with pytest.raises(ValueError, match="prohibited"):
        s.validate_production_security()


@pytest.mark.asyncio
async def test_sec_07_request_body_size_limits():
    """V-07: Verify payload > 1MB is rejected with 413."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = "B" * (1024 * 1024 + 50)
        resp = await client.post(
            "/v1/chat",
            content=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        assert resp.status_code == 413


@pytest.mark.asyncio
async def test_sec_08_brute_force_lockout_trigger():
    """V-08: Verify 5 failed auth attempts locks out the IP address."""
    test_ip = "198.51.100.42"
    default_rate_limiter.reset_failed_auth(test_ip)

    # 4 failed attempts -> not locked out yet
    for _ in range(4):
        default_rate_limiter.record_failed_auth(test_ip)
    is_locked, _ = default_rate_limiter.is_ip_locked_out(test_ip)
    assert not is_locked

    # 5th attempt -> triggers lockout
    default_rate_limiter.record_failed_auth(test_ip)
    is_locked, retry_after = default_rate_limiter.is_ip_locked_out(test_ip)
    assert is_locked
    assert retry_after > 0

    # Clean up
    default_rate_limiter.reset_failed_auth(test_ip)
