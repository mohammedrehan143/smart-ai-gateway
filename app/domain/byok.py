"""BYOK (Bring Your Own Key) encrypted credential manager with user isolation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret


@dataclass
class UserCredential:
    user_id: str
    provider: str
    encrypted_key: str
    base_url: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    is_active: bool = True

    @property
    def masked_key(self) -> str:
        try:
            plaintext = decrypt_secret(self.encrypted_key)
            return mask_secret(plaintext)
        except Exception:
            return "********"

    def to_safe_dict(self) -> Dict[str, Any]:
        """Returns safe representation with masked credential."""
        try:
            plaintext = decrypt_secret(self.encrypted_key)
            masked = mask_secret(plaintext)
        except Exception:
            masked = "********"

        return {
            "user_id": self.user_id,
            "provider": self.provider,
            "masked_key": masked,
            "base_url": self.base_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
        }


class BYOKManager:
    """Manages encrypted provider credentials isolated per user/project."""

    def __init__(self):
        # In-memory fast cache: Dict[(user_id, provider), UserCredential]
        self._credentials: Dict[tuple[str, str], UserCredential] = {}

    def store_credential(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> UserCredential:
        now = time.time()
        encrypted = encrypt_secret(api_key.strip())
        key_tuple = (user_id, provider.lower())

        cred = UserCredential(
            user_id=user_id,
            provider=provider.lower(),
            encrypted_key=encrypted,
            base_url=base_url.strip() if base_url else None,
            created_at=self._credentials[key_tuple].created_at if key_tuple in self._credentials else now,
            updated_at=now,
            is_active=True,
        )
        self._credentials[key_tuple] = cred
        return cred

    def get_plaintext_key(self, user_id: str, provider: str) -> Optional[str]:
        """Retrieves and decrypts the provider key for the given user."""
        key_tuple = (user_id, provider.lower())
        cred = self._credentials.get(key_tuple)
        if not cred or not cred.is_active:
            return None
        try:
            return decrypt_secret(cred.encrypted_key)
        except Exception:
            return None

    def get_decrypted_credential(self, user_id: str, provider: str) -> Tuple[Optional[str], Optional[str]]:
        return self.get_plaintext_key(user_id, provider), self.get_base_url(user_id, provider)

    def get_base_url(self, user_id: str, provider: str) -> Optional[str]:
        key_tuple = (user_id, provider.lower())
        cred = self._credentials.get(key_tuple)
        return cred.base_url if cred else None

    def has_credential(self, user_id: str, provider: str) -> bool:
        key_tuple = (user_id, provider.lower())
        cred = self._credentials.get(key_tuple)
        return bool(cred and cred.is_active)

    def list_credentials(self, user_id: str) -> List[Dict[str, Any]]:
        return [
            cred.to_safe_dict()
            for (uid, _), cred in self._credentials.items()
            if uid == user_id and cred.is_active
        ]

    def delete_credential(self, user_id: str, provider: str) -> bool:
        key_tuple = (user_id, provider.lower())
        if key_tuple in self._credentials:
            del self._credentials[key_tuple]
            return True
        return False

    def clear(self) -> None:
        self._credentials.clear()


default_byok_manager = BYOKManager()
