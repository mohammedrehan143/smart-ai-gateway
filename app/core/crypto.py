"""Cryptographic operations, secret masking, and encryption for BYOK credential isolation."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import List, Optional
from cryptography.fernet import Fernet
from app.core.config import settings

# Deterministic key derivation from gateway master secret or application environment
def _get_master_fernet() -> Fernet:
    secret_seed = settings.GATEWAY_API_KEY or "smart-ai-gateway-default-in-memory-salt-2026"
    derived_32_bytes = hashlib.sha256(secret_seed.encode("utf-8")).digest()
    urlsafe_key = base64.urlsafe_b64encode(derived_32_bytes)
    return Fernet(urlsafe_key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypts plaintext API keys or credentials using Fernet (AES-128-CBC + HMAC-SHA256)."""
    if not plaintext:
        return ""
    fernet = _get_master_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypts ciphertext back to plaintext credential."""
    if not ciphertext:
        return ""
    fernet = _get_master_fernet()
    decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


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
