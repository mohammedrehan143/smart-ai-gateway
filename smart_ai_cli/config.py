"""Configuration manager for Smart AI CLI storing user preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from smart_ai_cli.schemas import GatewayConfig

CONFIG_DIR = Path(os.path.expanduser("~")) / ".smartai"
CONFIG_FILE = CONFIG_DIR / "config.json"


class ConfigManager:
    """Manages CLI persistent configuration and defaults."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.config_dir = self.config_path.parent
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> GatewayConfig:
        """Loads configuration from disk, creating default if missing."""
        if not self.config_path.exists():
            cfg = GatewayConfig()
            self.save_config(cfg)
            return cfg

        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return GatewayConfig(**data)
        except Exception:
            return GatewayConfig()

    def save_config(self, config: GatewayConfig) -> None:
        """Persists configuration to disk."""
        self._ensure_dir()
        self.config_path.write_text(
            json.dumps(config.model_dump(), indent=2),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        cfg = self.load_config()
        return getattr(cfg, key, default)

    def set(self, key: str, value: Any) -> GatewayConfig:
        cfg = self.load_config()
        if hasattr(cfg, key):
            setattr(cfg, key, value)
            self.save_config(cfg)
        else:
            raise KeyError(f"Unknown config key: '{key}'")
        return cfg


default_config_manager = ConfigManager()
