"""Cache key generation and eligibility rules with tenant isolation."""

from __future__ import annotations

import hashlib
import json
from typing import List
from app.domain.entities import ChatMessage, GenerationParameters


def compute_cache_key(
    model_alias: str,
    messages: List[ChatMessage],
    parameters: GenerationParameters,
    tenant_id: str = "default",
) -> str:
    """Compute deterministic SHA-256 cache key from model, messages, parameters, and tenant ID."""
    normalized_messages = [
        {"role": m.role, "content": m.content, "name": m.name}
        for m in messages
    ]
    key_dict = {
        "tenant_id": tenant_id,
        "model": model_alias,
        "messages": normalized_messages,
        "temperature": parameters.temperature,
        "max_output_tokens": parameters.max_output_tokens,
    }
    raw_json = json.dumps(key_dict, sort_keys=True)
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def is_cache_eligible(parameters: GenerationParameters, force_cache: bool = False) -> bool:
    """Determine whether request output is deterministic and eligible for response caching."""
    if force_cache:
        return True
    # Deterministic inference (temperature 0) is inherently safe to cache
    return parameters.temperature == 0.0
