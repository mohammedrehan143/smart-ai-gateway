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

    def __init__(self, db_path: Optional[str] = None):
        self._configs: Dict[tuple[str, str], AgentConfig] = {}
        if db_path is not None:
            self._db_path = db_path
        else:
            raw_url = getattr(settings, "DATABASE_URL", "sqlite:///./gateway_traces.db")
            if ":memory:" in raw_url:
                self._db_path = ":memory:"
            else:
                self._db_path = raw_url.replace("sqlite:///", "")
        self._init_sqlite()

    def _get_connection(self) -> Optional[Any]:
        if not self._db_path or self._db_path == ":memory:":
            return None
        try:
            import sqlite3
            from pathlib import Path
            p = Path(self._db_path)
            if p.parent and str(p.parent) != ".":
                p.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None

    def _init_sqlite(self) -> None:
        conn = self._get_connection()
        if not conn:
            return
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_configurations (
                        user_id TEXT NOT NULL,
                        agent_type TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        encrypted_key TEXT NOT NULL,
                        model_id TEXT NOT NULL,
                        base_url TEXT,
                        temperature REAL DEFAULT 0.2,
                        max_tokens INTEGER DEFAULT 1024,
                        is_enabled INTEGER DEFAULT 1,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY(user_id, agent_type)
                    );
                    """
                )
                cursor = conn.execute(
                    "SELECT user_id, agent_type, provider, encrypted_key, model_id, base_url, temperature, max_tokens, is_enabled, created_at, updated_at FROM agent_configurations"
                )
                for row in cursor.fetchall():
                    cfg = AgentConfig(
                        user_id=row["user_id"],
                        agent_type=row["agent_type"],
                        provider=row["provider"],
                        encrypted_key=row["encrypted_key"],
                        model_id=row["model_id"],
                        base_url=row["base_url"],
                        temperature=row["temperature"],
                        max_tokens=row["max_tokens"],
                        is_enabled=bool(row["is_enabled"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    self._configs[(cfg.user_id, cfg.agent_type)] = cfg
        except Exception:
            pass
        finally:
            conn.close()

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
        """Encrypts and stores agent configuration in-memory and persistently in SQLite."""
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

        # Persist to SQLite
        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO agent_configurations (
                            user_id, agent_type, provider, encrypted_key, model_id,
                            base_url, temperature, max_tokens, is_enabled, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, agent_type) DO UPDATE SET
                            provider=excluded.provider,
                            encrypted_key=excluded.encrypted_key,
                            model_id=excluded.model_id,
                            base_url=excluded.base_url,
                            temperature=excluded.temperature,
                            max_tokens=excluded.max_tokens,
                            is_enabled=excluded.is_enabled,
                            updated_at=excluded.updated_at
                        """,
                        (
                            config.user_id,
                            config.agent_type,
                            config.provider,
                            config.encrypted_key,
                            config.model_id,
                            config.base_url,
                            config.temperature,
                            config.max_tokens,
                            1 if config.is_enabled else 0,
                            config.created_at,
                            config.updated_at,
                        ),
                    )
            except Exception:
                pass
            finally:
                conn.close()

        return config

    def get_agent_config(self, user_id: str, agent_type: Literal["weak", "strong"]) -> Optional[AgentConfig]:
        """Retrieves an agent configuration if present."""
        cfg = self._configs.get((user_id, agent_type.lower()))
        if cfg:
            return cfg
        
        # Check SQLite if not in memory
        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    cursor = conn.execute(
                        """
                        SELECT user_id, agent_type, provider, encrypted_key, model_id,
                               base_url, temperature, max_tokens, is_enabled, created_at, updated_at
                        FROM agent_configurations
                        WHERE user_id = ? AND agent_type = ?
                        """,
                        (user_id, agent_type.lower()),
                    )
                    row = cursor.fetchone()
                    if row:
                        cfg = AgentConfig(
                            user_id=row["user_id"],
                            agent_type=row["agent_type"],
                            provider=row["provider"],
                            encrypted_key=row["encrypted_key"],
                            model_id=row["model_id"],
                            base_url=row["base_url"],
                            temperature=row["temperature"],
                            max_tokens=row["max_tokens"],
                            is_enabled=bool(row["is_enabled"]),
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
                        self._configs[(user_id, agent_type.lower())] = cfg
                        return cfg
            except Exception:
                pass
            finally:
                conn.close()
        return None

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
        deleted = False
        if agent_type:
            key_tuple = (user_id, agent_type.lower())
            if key_tuple in self._configs:
                del self._configs[key_tuple]
                deleted = True
        else:
            for at in ("weak", "strong"):
                key_tuple = (user_id, at)
                if key_tuple in self._configs:
                    del self._configs[key_tuple]
                    deleted = True

        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    if agent_type:
                        conn.execute(
                            "DELETE FROM agent_configurations WHERE user_id = ? AND agent_type = ?",
                            (user_id, agent_type.lower()),
                        )
                    else:
                        conn.execute(
                            "DELETE FROM agent_configurations WHERE user_id = ?",
                            (user_id,),
                        )
            except Exception:
                pass
            finally:
                conn.close()

        return deleted

    def is_agent_ready(self, user_id: str, agent_type: Literal["weak", "strong"]) -> bool:
        """Checks if the agent is configured and active."""
        config = self.get_agent_config(user_id, agent_type)
        return bool(config and config.is_enabled and config.encrypted_key and config.model_id)


# Global singleton instance
default_credential_manager = CredentialManager()
