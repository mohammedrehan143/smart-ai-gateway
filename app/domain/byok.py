"""BYOK (Bring Your Own Key) encrypted credential manager with strict tenant isolation and persistence."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.network_security import validate_provider_base_url


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
    """Manages encrypted provider credentials strictly isolated per user/tenant with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None):
        # In-memory fast cache: Dict[(user_id, provider), UserCredential]
        self._credentials: Dict[tuple[str, str], UserCredential] = {}
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
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
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
                    CREATE TABLE IF NOT EXISTS user_credentials (
                        user_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        encrypted_key TEXT NOT NULL,
                        base_url TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        PRIMARY KEY(user_id, provider)
                    );
                    """
                )
                cursor = conn.execute(
                    "SELECT user_id, provider, encrypted_key, base_url, created_at, updated_at, is_active FROM user_credentials"
                )
                for row in cursor.fetchall():
                    cred = UserCredential(
                        user_id=row["user_id"],
                        provider=row["provider"],
                        encrypted_key=row["encrypted_key"],
                        base_url=row["base_url"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        is_active=bool(row["is_active"]),
                    )
                    self._credentials[(cred.user_id, cred.provider.lower())] = cred
        except Exception:
            pass
        finally:
            conn.close()

    def store_credential(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> UserCredential:
        if base_url:
            base_url = validate_provider_base_url(base_url)

        now = time.time()
        encrypted = encrypt_secret(api_key.strip())
        key_tuple = (user_id, provider.lower())

        existing = self._credentials.get(key_tuple)
        created_at = existing.created_at if existing else now

        cred = UserCredential(
            user_id=user_id,
            provider=provider.lower(),
            encrypted_key=encrypted,
            base_url=base_url.strip() if base_url else None,
            created_at=created_at,
            updated_at=now,
            is_active=True,
        )
        self._credentials[key_tuple] = cred

        # Persist to SQLite
        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO user_credentials (
                            user_id, provider, encrypted_key, base_url, created_at, updated_at, is_active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, provider) DO UPDATE SET
                            encrypted_key=excluded.encrypted_key,
                            base_url=excluded.base_url,
                            updated_at=excluded.updated_at,
                            is_active=excluded.is_active
                        """,
                        (
                            cred.user_id,
                            cred.provider,
                            cred.encrypted_key,
                            cred.base_url,
                            cred.created_at,
                            cred.updated_at,
                            1 if cred.is_active else 0,
                        ),
                    )
            except Exception:
                pass
            finally:
                conn.close()

        return cred

    def get_plaintext_key(self, user_id: str, provider: str) -> Optional[str]:
        """Retrieves and decrypts the provider key strictly isolated for the specified user."""
        key_tuple = (user_id, provider.lower())
        cred = self._credentials.get(key_tuple)
        if not cred:
            # Check SQLite if cache missed
            conn = self._get_connection()
            if conn:
                try:
                    with conn:
                        cursor = conn.execute(
                            "SELECT encrypted_key, base_url, created_at, updated_at, is_active FROM user_credentials WHERE user_id = ? AND provider = ?",
                            (user_id, provider.lower()),
                        )
                        row = cursor.fetchone()
                        if row:
                            cred = UserCredential(
                                user_id=user_id,
                                provider=provider.lower(),
                                encrypted_key=row["encrypted_key"],
                                base_url=row["base_url"],
                                created_at=row["created_at"],
                                updated_at=row["updated_at"],
                                is_active=bool(row["is_active"]),
                            )
                            self._credentials[key_tuple] = cred
                except Exception:
                    pass
                finally:
                    conn.close()

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
        """Lists credentials strictly isolated for the requesting user."""
        # Ensure latest state from SQLite
        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    cursor = conn.execute(
                        "SELECT provider, encrypted_key, base_url, created_at, updated_at, is_active FROM user_credentials WHERE user_id = ? AND is_active = 1",
                        (user_id,),
                    )
                    results = []
                    for row in cursor.fetchall():
                        cred = UserCredential(
                            user_id=user_id,
                            provider=row["provider"],
                            encrypted_key=row["encrypted_key"],
                            base_url=row["base_url"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                            is_active=bool(row["is_active"]),
                        )
                        self._credentials[(user_id, cred.provider)] = cred
                        results.append(cred.to_safe_dict())
                    return results
            except Exception:
                pass
            finally:
                conn.close()

        return [
            cred.to_safe_dict() for (uid, _), cred in self._credentials.items() if uid == user_id and cred.is_active
        ]

    def delete_credential(self, user_id: str, provider: str) -> bool:
        """Deletes credential strictly isolated for the user."""
        key_tuple = (user_id, provider.lower())
        deleted = False
        if key_tuple in self._credentials:
            del self._credentials[key_tuple]
            deleted = True

        conn = self._get_connection()
        if conn:
            try:
                with conn:
                    cursor = conn.execute(
                        "DELETE FROM user_credentials WHERE user_id = ? AND provider = ?",
                        (user_id, provider.lower()),
                    )
                    if cursor.rowcount > 0:
                        deleted = True
            except Exception:
                pass
            finally:
                conn.close()

        return deleted

    def clear(self) -> None:
        self._credentials.clear()


default_byok_manager = BYOKManager()
