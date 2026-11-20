"""Gateway Mode Management and Routing Priority Hierarchy.

Supports Auto, Fast, Balanced, Strong, and Expert modes with backend enforcement,
strict priority resolution, and provider/model validation.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple


class GatewayMode(str, Enum):
    """Supported gateway routing modes."""

    AUTO = "auto"
    FAST = "fast"
    BALANCED = "balanced"
    STRONG = "strong"
    EXPERT = "expert"


# Mapping of aliases and variations to canonical GatewayMode
MODE_ALIASES: Dict[str, GatewayMode] = {
    # Auto aliases
    "auto": GatewayMode.AUTO,
    "adaptive": GatewayMode.AUTO,
    "automatic": GatewayMode.AUTO,
    "default": GatewayMode.AUTO,
    # Fast aliases
    "fast": GatewayMode.FAST,
    "weak": GatewayMode.FAST,
    "cheap": GatewayMode.FAST,
    "always_cheap": GatewayMode.FAST,
    "cost_optimized": GatewayMode.FAST,
    "low_cost": GatewayMode.FAST,
    # Balanced aliases
    "balanced": GatewayMode.BALANCED,
    "moderate": GatewayMode.BALANCED,
    "performance_optimized": GatewayMode.BALANCED,
    # Strong aliases
    "strong": GatewayMode.STRONG,
    "always_strong": GatewayMode.STRONG,
    "quality_first": GatewayMode.STRONG,
    "deep_reasoning": GatewayMode.STRONG,
    # Expert aliases
    "expert": GatewayMode.EXPERT,
    "frontier": GatewayMode.EXPERT,
    "max_reasoning": GatewayMode.EXPERT,
}


def normalize_gateway_mode(mode: Optional[str]) -> GatewayMode:
    """Normalizes any user, session, or request mode string into a canonical GatewayMode.

    Defaults to GatewayMode.AUTO if unrecognised or None.
    """
    if not mode:
        return GatewayMode.AUTO
    cleaned = str(mode).strip().lower()
    return MODE_ALIASES.get(cleaned, GatewayMode.AUTO)


def is_strong_mode(mode: Optional[str]) -> bool:
    """Returns True if the mode represents an explicit Strong or Expert override."""
    norm = normalize_gateway_mode(mode)
    return norm in (GatewayMode.STRONG, GatewayMode.EXPERT)


def is_expert_mode(mode: Optional[str]) -> bool:
    """Returns True if the mode represents an explicit Expert override."""
    return normalize_gateway_mode(mode) == GatewayMode.EXPERT


def get_reasoning_effort_for_mode(mode: Optional[str], model_id: Optional[str] = None) -> str:
    """Returns the reasoning effort appropriate for the given mode and model.

    Strong and Expert modes enable the highest supported reasoning effort ('high').
    Fast mode sets 'none' or 'low'.
    """
    norm = normalize_gateway_mode(mode)
    if norm in (GatewayMode.STRONG, GatewayMode.EXPERT):
        return "high"
    elif norm == GatewayMode.FAST:
        return "none"
    elif norm == GatewayMode.BALANCED:
        return "medium"
    return "medium"


def validate_provider_and_model(
    provider: str,
    model_id: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    is_mock_allowed: bool = True,
) -> Tuple[bool, Optional[str]]:
    """Validates provider credentials, model identifier, and network endpoints."""
    if not provider or not provider.strip():
        return False, "Provider name cannot be empty."

    p = provider.strip().lower()
    valid_providers = {"openai", "groq", "google", "gemini", "anthropic", "openai_compatible", "mock"}
    if p not in valid_providers:
        return False, f"Unsupported provider '{provider}'. Must be one of: {', '.join(sorted(valid_providers))}."

    if not model_id or not model_id.strip():
        return False, "Model identifier cannot be empty."

    m = model_id.strip()
    if len(m) < 2:
        return False, f"Model ID '{m}' is too short to be valid."

    # Model availability and configuration validation against known provider models
    known_prefixes = {
        "openai": ("gpt-", "o1", "o3", "chatgpt-", "openai/"),
        "groq": ("llama", "deepseek-", "mixtral", "gemma", "qwen"),
        "anthropic": ("claude-",),
        "google": ("gemini-",),
        "gemini": ("gemini-",),
        "mock": ("mock-",),
    }
    if p in known_prefixes:
        valid_prefix = any(m.lower().startswith(pfx) for pfx in known_prefixes[p])
        if not valid_prefix:
            return False, f"Invalid or unsupported model '{model_id}' for provider '{provider}'."

    if p == "mock" and not is_mock_allowed:
        return False, "Mock provider is disallowed in live execution."

    if api_key is not None and p != "mock":
        raw_key = api_key.strip()
        if len(raw_key) < 5:
            return False, f"API key for provider '{provider}' is too short to be valid."
        k_lower = raw_key.lower()
        if any(dummy in k_lower for dummy in ("dummy", "placeholder", "your_key", "sample_key")):
            return (
                False,
                f"API key appears to be a placeholder for provider '{provider}'. Please configure a real API key.",
            )

    if base_url and base_url.strip():
        from app.core.network_security import validate_provider_base_url

        try:
            val_url = validate_provider_base_url(base_url.strip())
            if not val_url:
                return False, f"Disallowed base URL '{base_url}' (SSRF security policy)."
        except Exception as exc:
            return False, f"Invalid base URL '{base_url}': {exc}"

    return True, None
