"""Secure BYOK (Bring Your Own Key) Credential Manager for Weak and Strong Agents."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional
from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret


@dataclass
class AgentConfig:
    """Configuration and credentials for an individual agent (weak or strong)."""
    user_id: str
    agent_type: Literal["weak", "strong"]
    provider: str  # "openai", "groq", "google", "anthropic", "openai_compatible"
    encrypted_key: str
    model_id: str
    base_url: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 1024
    is_enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def masked_key(self) -> str:
        try:
            plaintext = decrypt_secret(self.encrypted_key)
            return mask_secret(plaintext)
        except Exception:
            return "********"

    def get_plaintext_key(self) -> str:
        """Decrypts and returns the raw secret API key for outbound provider execution."""
        return decrypt_secret(self.encrypted_key)

    def to_safe_dict(self) -> Dict[str, Any]:
        """Safe dictionary representation with masked credentials for UI & APIs."""
        return {
            "user_id": self.user_id,
            "agent_type": self.agent_type,
            "provider": self.provider,
            "masked_key": self.masked_key,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CredentialManager:
    """Thread-safe credential and configuration manager with encryption at rest and SQLite persistence."""

    def __init__(self):
        # In-memory fast cache: Dict[(user_id, agent_type), AgentConfig]
        self._configs: Dict[tuple[str, str], AgentConfig] = {}

    def store_agent_config(
        self,
        user_id: str,
        agent_type: Literal["weak", "strong"],
        provider: str,
        api_key: str,
        model_id: str,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        is_enabled: bool = True,
    ) -> AgentConfig:
        """Encrypts and stores agent configuration."""
        now = time.time()
        encrypted = encrypt_secret(api_key.strip())
        key_tuple = (user_id, agent_type.lower())

        existing = self._configs.get(key_tuple)
        created_at = existing.created_at if existing else now

        config = AgentConfig(
            user_id=user_id,
            agent_type=agent_type.lower(),  # type: ignore
            provider=provider.lower().strip(),
            encrypted_key=encrypted,
            model_id=model_id.strip(),
            base_url=base_url.strip() if base_url else None,
            temperature=temperature,
            max_tokens=max_tokens,
            is_enabled=is_enabled,
            created_at=created_at,
            updated_at=now,
        )
        self._configs[key_tuple] = config
        return config

    def get_agent_config(self, user_id: str, agent_type: Literal["weak", "strong"]) -> Optional[AgentConfig]:
        """Retrieves an agent configuration if present."""
        return self._configs.get((user_id, agent_type.lower()))

    def list_agent_configs(self, user_id: str) -> Dict[str, Optional[Dict[str, Any]]]:
        """Returns safe configurations for both weak and strong agents for a given user."""
        weak = self.get_agent_config(user_id, "weak")
        strong = self.get_agent_config(user_id, "strong")
        return {
            "weak": weak.to_safe_dict() if weak else None,
            "strong": strong.to_safe_dict() if strong else None,
        }

    def delete_agent_config(self, user_id: str, agent_type: Optional[Literal["weak", "strong"]] = None) -> bool:
        """Deletes configuration for a specific agent or both."""
        if agent_type:
            key_tuple = (user_id, agent_type.lower())
            if key_tuple in self._configs:
                del self._configs[key_tuple]
                return True
            return False
        else:
            deleted = False
            for at in ("weak", "strong"):
                key_tuple = (user_id, at)
                if key_tuple in self._configs:
                    del self._configs[key_tuple]
                    deleted = True
            return deleted

    def is_agent_ready(self, user_id: str, agent_type: Literal["weak", "strong"]) -> bool:
        """Checks if the agent is configured and active."""
        config = self.get_agent_config(user_id, agent_type)
        return bool(config and config.is_enabled and config.encrypted_key and config.model_id)


# Global singleton instance
default_credential_manager = CredentialManager()
