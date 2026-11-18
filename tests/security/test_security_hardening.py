"""Comprehensive security tests for authentication, tenant isolation, SSRF, and encryption."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.core.config import Settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret, rotate_ciphertext
from app.core.errors import SSRFSecurityError
from app.core.network_security import validate_provider_base_url
from app.domain.byok import default_byok_manager
from app.domain.cache import compute_cache_key
from app.domain.entities import ChatMessage, GenerationParameters
from app.main import app


# ---------------------------------------------------------------------------
# 1. Authentication Security Tests
# ---------------------------------------------------------------------------


def test_production_fails_without_required_secrets():
    """Verify that production startup strictly rejects missing or weak credentials."""
    # Missing GATEWAY_API_KEY
    s1 = Settings(APP_ENV="production", GATEWAY_API_KEY=None, ENCRYPTION_MASTER_KEY="valid-secret-key-123456")
    with pytest.raises(ValueError, match="GATEWAY_API_KEY must be configured"):
        s1.validate_production_security()

    # Weak GATEWAY_API_KEY (< 16 chars)
    s2 = Settings(APP_ENV="production", GATEWAY_API_KEY="short-key", ENCRYPTION_MASTER_KEY="valid-secret-key-123456")
    with pytest.raises(ValueError, match="minimum of 16 characters"):
        s2.validate_production_security()

    # Missing ENCRYPTION_MASTER_KEY
    s3 = Settings(APP_ENV="production", GATEWAY_API_KEY="valid-gateway-key-123456", ENCRYPTION_MASTER_KEY=None)
    with pytest.raises(ValueError, match="ENCRYPTION_MASTER_KEY must be configured"):
        s3.validate_production_security()

    # Identical keys (master encryption key cannot be identical to gateway auth key)
    s4 = Settings(
        APP_ENV="production",
        GATEWAY_API_KEY="identical-shared-secret-123456",
        ENCRYPTION_MASTER_KEY="identical-shared-secret-123456",
    )
    with pytest.raises(ValueError, match="must be independent"):
        s4.validate_production_security()

    # Wildcard CORS in production
    s5 = Settings(
        APP_ENV="production",
        GATEWAY_API_KEY="valid-gateway-key-123456",
        ENCRYPTION_MASTER_KEY="valid-encryption-key-123456",
        ALLOWED_CORS_ORIGINS=["*"],
    )
    with pytest.raises(ValueError, match=r"Wildcard '\*' in ALLOWED_CORS_ORIGINS is prohibited"):
        s5.validate_production_security()


@pytest.mark.asyncio
async def test_auth_enforcement_when_configured():
    """Verify that when GATEWAY_API_KEY is configured, unauthenticated requests are rejected."""
    from app.core.config import settings

    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    try:
        settings.APP_ENV = "staging"
        settings.GATEWAY_API_KEY = "test-live-key-0123456789"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Missing header -> 401
            r1 = await client.get("/v1/auth/verify")
            assert r1.status_code == 401
            assert r1.json()["error"]["type"] == "unauthorized"

            # 2. Invalid token -> 401
            r2 = await client.get("/v1/auth/verify", headers={"Authorization": "Bearer wrong-key"})
            assert r2.status_code == 401

            # 3. Valid token -> 200
            r3 = await client.get("/v1/auth/verify", headers={"Authorization": "Bearer test-live-key-0123456789"})
            assert r3.status_code == 200
            assert r3.json()["status"] == "authenticated"
    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key


@pytest.mark.asyncio
async def test_token_revocation_enforcement():
    """Verify that revoked tokens in REVOKED_API_KEYS are immediately denied access."""
    from app.core.config import settings

    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    orig_revoked = settings.REVOKED_API_KEYS
    try:
        settings.APP_ENV = "staging"
        settings.GATEWAY_API_KEY = "active-valid-master-key"
        settings.REVOKED_API_KEYS = ["compromised-revoked-key-999"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Revoked token -> 401
            resp = await client.get("/v1/auth/verify", headers={"Authorization": "Bearer compromised-revoked-key-999"})
            assert resp.status_code == 401
            assert "revoked" in resp.json()["error"]["message"].lower()
    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key
        settings.REVOKED_API_KEYS = orig_revoked


# ---------------------------------------------------------------------------
# 2. Multi-Tenant Credential Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tenant_credential_isolation(async_client: AsyncClient):
    """Verify tenant A cannot read, list, delete, or access tenant B's BYOK credentials."""
    tenant_a_headers = {"X-User-ID": "tenant_alice"}
    tenant_b_headers = {"X-User-ID": "tenant_bob"}

    # 1. Tenant Alice stores credential
    await async_client.post(
        "/v1/credentials",
        json={"provider": "groq", "api_key": "gsk_alice_super_secret_12345"},
        headers=tenant_a_headers,
    )

    # 2. Tenant Bob lists credentials -> must be empty, must NOT see Alice's credential
    bob_list_resp = await async_client.get("/v1/credentials", headers=tenant_b_headers)
    assert bob_list_resp.status_code == 200
    bob_creds = bob_list_resp.json()
    assert len(bob_creds) == 0, f"Tenant Bob leaked Alice's credentials: {bob_creds}"

    # 3. Tenant Bob attempts to delete Alice's credential -> 404 Not Found
    bob_del_resp = await async_client.delete("/v1/credentials/groq", headers=tenant_b_headers)
    assert bob_del_resp.status_code == 404

    # 4. In-memory manager verification: direct lookup for Bob returns None
    assert default_byok_manager.get_plaintext_key("tenant_bob", "groq") is None
    # Alice's key remains safe and intact
    assert default_byok_manager.get_plaintext_key("tenant_alice", "groq") == "gsk_alice_super_secret_12345"

    # Cleanup
    await async_client.delete("/v1/credentials/groq", headers=tenant_a_headers)


@pytest.mark.asyncio
async def test_cross_tenant_cache_isolation():
    """Verify that identical prompts from different tenants generate distinct cache keys."""
    messages = [ChatMessage(role="user", content="Classify this proprietary document.")]
    params = GenerationParameters(temperature=0.0)

    key_tenant_1 = compute_cache_key("mock-cheap", messages, params, tenant_id="company_one")
    key_tenant_2 = compute_cache_key("mock-cheap", messages, params, tenant_id="company_two")

    assert key_tenant_1 != key_tenant_2, "Cache key collision across distinct tenants!"


# ---------------------------------------------------------------------------
# 3. SSRF (Server-Side Request Forgery) Protection Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://10.0.0.1:8080/v1",
        "http://192.168.1.1/api",
        "http://172.16.0.5/chat",
        "http://0.0.0.0:8000",
        "ftp://api.openai.com/v1",
        "file:///etc/passwd",
    ],
)
def test_ssrf_validator_blocks_malicious_destinations(forbidden_url: str):
    """Verify that AWS metadata, GCP metadata, private RFC 1918 IPs, and non-HTTP schemes are blocked."""
    with pytest.raises(SSRFSecurityError):
        validate_provider_base_url(forbidden_url)


def test_ssrf_validator_permits_legitimate_endpoints():
    """Verify that public internet providers pass validation."""
    valid_urls = [
        "https://api.openai.com/v1",
        "https://api.groq.com/openai/v1",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "https://api.anthropic.com/v1",
    ]
    for url in valid_urls:
        validated = validate_provider_base_url(url)
        assert validated == url.rstrip("/")


# ---------------------------------------------------------------------------
# 4. Credential Encryption and Key Rotation Tests
# ---------------------------------------------------------------------------


def test_credential_encryption_and_key_rotation():
    """Verify that credentials encrypt, decrypt, and rotate to new keys seamlessly."""
    raw_key = "sk-proj-super-secret-user-api-key-test-value-12345"

    # 1. Encrypt with current engine
    ciphertext = encrypt_secret(raw_key)
    assert ciphertext != raw_key
    assert "sk-proj" not in ciphertext

    # 2. Decrypt
    decrypted = decrypt_secret(ciphertext)
    assert decrypted == raw_key

    # 3. Rotate token
    rotated = rotate_ciphertext(ciphertext)
    assert rotated
    # Decrypting rotated token still produces the original key
    assert decrypt_secret(rotated) == raw_key


def test_secret_masking_never_exposes_plaintext():
    """Verify mask_secret never returns more than prefix and suffix."""
    key = "gsk_1234567890abcdefghijklmnopqrstuvwxyz"
    masked = mask_secret(key)
    assert masked == "gsk...wxyz"
    assert "1234567890abcdef" not in masked


# ---------------------------------------------------------------------------
# 5. Tenant Impersonation & Production BYOK Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_impersonation_strictly_forbidden(async_client: AsyncClient):
    """Verify that a tenant token cannot claim to be another user via X-User-ID."""
    from app.core.config import settings

    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    orig_tenants = settings.TENANT_API_KEYS
    try:
        settings.APP_ENV = "staging"
        settings.GATEWAY_API_KEY = "master-admin-key-123456789"
        settings.TENANT_API_KEYS = '{"tenant-token-alice-secret-123": "alice"}'

        # Alice attempts to impersonate Bob
        resp = await async_client.get(
            "/v1/auth/verify",
            headers={
                "Authorization": "Bearer tenant-token-alice-secret-123",
                "X-User-ID": "bob",
            },
        )
        assert resp.status_code == 403
        assert "Tenant mismatch" in resp.json()["error"]["message"]
    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key
        settings.TENANT_API_KEYS = orig_tenants


@pytest.mark.asyncio
async def test_production_tenant_without_byok_cannot_use_shared_host_keys(async_client: AsyncClient):
    """Verify that in production mode, a tenant without configured BYOK keys cannot piggyback on server keys."""
    from app.core.config import settings
    from app.providers.resolver import DynamicProviderAdapter
    from app.core.errors import ProviderAuthError

    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    try:
        settings.APP_ENV = "production"
        adapter = DynamicProviderAdapter()
        with pytest.raises(ProviderAuthError, match="No BYOK credential configured for tenant"):
            adapter._resolve_adapter("llama-3.1-8b-instant", user_id="tenant_charlie")
    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key
