"""Cryptographic operations, secret masking, key rotation, and encryption for BYOK credential isolation."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import List, Optional
from cryptography.fernet import Fernet, MultiFernet
from app.core.config import settings


def _derive_fernet(secret: str) -> Fernet:
    """Derives a Fernet cipher instance from an arbitrary string secret using SHA-256."""
    derived_32_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    urlsafe_key = base64.urlsafe_b64encode(derived_32_bytes)
    return Fernet(urlsafe_key)


def get_crypto_engine() -> MultiFernet:
    """Returns a MultiFernet instance supporting current encryption and key rotation/migration.

    In production mode, a dedicated ENCRYPTION_MASTER_KEY is strictly required.
    Fallback seeds are permitted only in local and test environments.
    """
    keys: List[Fernet] = []

    # 1. Primary dedicated master encryption key
    if settings.ENCRYPTION_MASTER_KEY:
        keys.append(_derive_fernet(settings.ENCRYPTION_MASTER_KEY))
    elif settings.APP_ENV == "production":
        raise RuntimeError("CRITICAL SECURITY FAILURE: ENCRYPTION_MASTER_KEY must be configured in production mode.")
    elif settings.GATEWAY_API_KEY:
        # Dev/local mode fallback to gateway api key if dedicated key not provided
        keys.append(_derive_fernet(settings.GATEWAY_API_KEY))
    else:
        # Non-production only test/dev fallback
        keys.append(_derive_fernet("smart-ai-gateway-dev-in-memory-salt-key-do-not-use-in-prod"))

    # 2. Previous encryption keys for seamless key rotation
    for prev_key in settings.ENCRYPTION_PREVIOUS_KEYS:
        if prev_key and prev_key.strip():
            keys.append(_derive_fernet(prev_key.strip()))

    # 3. In non-production, allow decryption of legacy data encrypted with older keys
    if settings.APP_ENV != "production":
        legacy_keys = [
            settings.GATEWAY_API_KEY,
            "smart-ai-gateway-default-in-memory-salt-2026",
        ]
        for lk in legacy_keys:
            if lk:
                f = _derive_fernet(lk)
                if f not in keys:
                    keys.append(f)

    return MultiFernet(keys)


def encrypt_secret(plaintext: str) -> str:
    """Encrypts plaintext API keys or credentials using the primary master key."""
    if not plaintext:
        return ""
    engine = get_crypto_engine()
    encrypted_bytes = engine.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypts ciphertext back to plaintext credential using primary or previous rotation keys."""
    if not ciphertext:
        return ""
    engine = get_crypto_engine()
    decrypted_bytes = engine.decrypt(ciphertext.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def rotate_ciphertext(ciphertext: str) -> str:
    """Re-encrypts a ciphertext with the newest primary key while verifying it with rotation keys."""
    if not ciphertext:
        return ""
    engine = get_crypto_engine()
    rotated_bytes = engine.rotate(ciphertext.encode("utf-8"))
    return rotated_bytes.decode("utf-8")


def mask_secret(secret: str) -> str:
    """Masks sensitive credentials for safe logging and client display (e.g., sk-...4f8b)."""
    if not secret:
        return ""
    stripped = secret.strip()
    if len(stripped) <= 8:
        return "********"
    prefix = stripped[:3]
    suffix = stripped[-4:]
    return f"{prefix}...{suffix}"


_SECRET_REGEXES = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"gsk_[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
]


def redact_secrets_from_text(text: str, known_secrets: Optional[List[str]] = None) -> str:
    """Scrubs known credentials and heuristic API key patterns from text and logs."""
    if not text:
        return ""
    redacted = text
    if known_secrets:
        for secret in known_secrets:
            if secret and len(secret) > 4:
                redacted = redacted.replace(secret, "[REDACTED_SECRET]")

    for pattern in _SECRET_REGEXES:
        redacted = pattern.sub("[REDACTED_KEY]", redacted)

    return redacted
