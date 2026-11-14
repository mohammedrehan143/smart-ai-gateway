"""Secure credential manager using OS Keyring with local fallback."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

KEYRING_SERVICE_NAME = "smartai_cli"
KEYRING_USERNAME = "gateway_api_key"

FALLBACK_CREDENTIALS_FILE = Path(os.path.expanduser("~")) / ".smartai" / "credentials.json"


class AuthManager:
    """Handles secure storage, retrieval, and removal of gateway API keys."""

    def __init__(self, service_name: str = KEYRING_SERVICE_NAME, username: str = KEYRING_USERNAME):
        self.service_name = service_name
        self.username = username
        self.fallback_file = FALLBACK_CREDENTIALS_FILE

    def _get_keyring_impl(self):
        try:
            import keyring
            return keyring
        except ImportError:
            return None

    def get_api_key(self) -> Optional[str]:
        """Retrieves API key from keyring, falling back to secure credentials file."""
        # 1. Environment variable override
        env_key = os.environ.get("SMARTAI_API_KEY") or os.environ.get("GATEWAY_API_KEY")
        if env_key:
            return env_key.strip()

        # 2. Keyring lookup
        keyring_mod = self._get_keyring_impl()
        if keyring_mod:
            try:
                val = keyring_mod.get_password(self.service_name, self.username)
                if val:
                    return val.strip()
            except Exception:
                pass

        # 3. Secure file fallback
        if self.fallback_file.exists():
            try:
                data = json.loads(self.fallback_file.read_text(encoding="utf-8"))
                return data.get("api_key")
            except Exception:
                return None

        return None

    def set_api_key(self, api_key: str) -> None:
        """Stores API key in OS Keyring and fallback file."""
        cleaned_key = api_key.strip()
        keyring_mod = self._get_keyring_impl()
        stored_in_keyring = False

        if keyring_mod:
            try:
                keyring_mod.set_password(self.service_name, self.username, cleaned_key)
                stored_in_keyring = True
            except Exception:
                stored_in_keyring = False

        # Always update secure fallback file as well
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
        self.fallback_file.write_text(
            json.dumps({"api_key": cleaned_key, "keyring_active": stored_in_keyring}),
            encoding="utf-8",
        )
        try:
            # Set restrictive permissions (read/write only by owner)
            self.fallback_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

    def delete_api_key(self) -> None:
        """Removes API key from Keyring and fallback storage."""
        keyring_mod = self._get_keyring_impl()
        if keyring_mod:
            try:
                keyring_mod.delete_password(self.service_name, self.username)
            except Exception:
                pass

        if self.fallback_file.exists():
            try:
                self.fallback_file.unlink()
            except Exception:
                pass

    def has_api_key(self) -> bool:
        return bool(self.get_api_key())


default_auth_manager = AuthManager()
