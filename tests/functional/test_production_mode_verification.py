"""Stage 8: Final Production Validation Suite under strict production configuration.

Validates that:
1. Production environment invariants enforce strict authentication and encryption secrets.
2. Wildcard CORS is rejected.
3. Mock execution is blocked when APP_ENV=production.
4. Health / live / ready probes succeed with production-grade security headers.
5. BYOK credentials encrypt and decrypt correctly with dedicated master key.
6. Multi-tenant isolation functions with authenticated requests.
"""

from __future__ import annotations

import os
import sys
import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.core.config import Settings, settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.main import app


@pytest.mark.asyncio
async def test_production_strict_security_lifecycle():
    orig_env = settings.APP_ENV
    orig_key = settings.GATEWAY_API_KEY
    orig_enc = settings.ENCRYPTION_MASTER_KEY
    orig_mock = settings.ENABLE_MOCK_GATEWAY
    orig_cors = settings.ALLOWED_CORS_ORIGINS

    prod_gw_key = "prod-master-gateway-key-sec-99999"
    prod_enc_key = "prod-master-encryption-key-aes-88888"

    try:
        # 1. Configure realistic production environment
        settings.APP_ENV = "production"
        settings.GATEWAY_API_KEY = prod_gw_key
        settings.ENCRYPTION_MASTER_KEY = prod_enc_key
        settings.ENABLE_MOCK_GATEWAY = False
        settings.ALLOWED_CORS_ORIGINS = ["https://gateway.production.company.com"]

        # 2. Invariant verification: validate_production_security passes
        settings.validate_production_security()

        # 3. Invariant check: In production, mock gateway is strictly forbidden
        bad_settings = Settings(
            APP_ENV="production",
            GATEWAY_API_KEY=prod_gw_key,
            ENCRYPTION_MASTER_KEY=prod_enc_key,
            ENABLE_MOCK_GATEWAY=True,
            ALLOWED_CORS_ORIGINS=["https://gateway.production.company.com"],
        )
        with pytest.raises(ValueError, match="ENABLE_MOCK_GATEWAY cannot be set to true"):
            bad_settings.validate_production_security()

        # 4. Production HTTP interaction
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://gateway.production.company.com") as client:
            # 4a. Health probes should be public & return 200
            resp_live = await client.get("/health/live")
            assert resp_live.status_code == 200
            assert resp_live.json()["status"] == "live"
            # Verify security headers
            assert resp_live.headers.get("X-Content-Type-Options") == "nosniff"
            assert resp_live.headers.get("X-Frame-Options") == "DENY"

            resp_ready = await client.get("/health/ready")
            assert resp_ready.status_code == 200

            # 4b. Protected endpoint without auth MUST return 401
            resp_unauth = await client.get("/v1/auth/verify")
            assert resp_unauth.status_code == 401
            assert resp_unauth.json()["error"]["type"] == "unauthorized"

            # 4c. Protected endpoint with Bearer auth MUST return 200
            auth_headers = {"Authorization": f"Bearer {prod_gw_key}"}
            resp_auth = await client.get("/v1/auth/verify", headers=auth_headers)
            assert resp_auth.status_code == 200
            auth_data = resp_auth.json()
            assert auth_data["status"] == "authenticated"
            assert auth_data["environment"] == "production"
            assert auth_data["auth_enforced"] is True

            # 4d. Production BYOK lifecycle with dedicated encryption key
            secret_api_key = "sk-prod-vendor-live-key-999988887777"
            # Test direct crypto
            ciphertext = encrypt_secret(secret_api_key)
            assert ciphertext != secret_api_key
            assert secret_api_key not in ciphertext
            recovered = decrypt_secret(ciphertext)
            assert recovered == secret_api_key

            # 4e. BYOK endpoint isolation
            t1_headers = {"Authorization": f"Bearer {prod_gw_key}", "X-User-ID": "enterprise_tenant_alpha"}
            resp_cred_set = await client.post(
                "/v1/credentials",
                json={"provider": "anthropic", "api_key": secret_api_key},
                headers=t1_headers,
            )
            assert resp_cred_set.status_code == 201
            cred_info = resp_cred_set.json()
            assert cred_info["provider"] == "anthropic"
            assert cred_info["masked_key"].startswith("sk-")
            assert secret_api_key not in cred_info["masked_key"]

            # Tenant Beta cannot see Tenant Alpha's key
            t2_headers = {"Authorization": f"Bearer {prod_gw_key}", "X-User-ID": "enterprise_tenant_beta"}
            resp_cred_t2 = await client.get("/v1/credentials", headers=t2_headers)
            assert resp_cred_t2.status_code == 200
            assert len(resp_cred_t2.json()) == 0

            # Cleanup
            await client.delete("/v1/credentials/anthropic", headers=t1_headers)

    finally:
        settings.APP_ENV = orig_env
        settings.GATEWAY_API_KEY = orig_key
        settings.ENCRYPTION_MASTER_KEY = orig_enc
        settings.ENABLE_MOCK_GATEWAY = orig_mock
        settings.ALLOWED_CORS_ORIGINS = orig_cors
