"""Deterministic feature extraction for request routing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List
from app.domain.entities import ChatMessage

CODE_PATTERNS = [
    r"```",
    r"\bdef\s+\w+\(",
    r"\bclass\s+\w+[:\(]",
    r"\bimport\s+[\w\.]+",
    r"\bfrom\s+[\w\.]+\s+import",
    r"\bfunction\s*\w*\(",
    r"\bconst\s+\w+\s*=",
    r"\blet\s+\w+\s*=",
    r"SELECT\s+.*\s+FROM\s+",
]

DEBUG_KEYWORDS = {"error", "exception", "traceback", "stacktrace", "bug", "segfault", "panic", "fix this"}
MULTISTEP_PATTERNS = [
    r"\bstep\s*\d+",
    r"\bfirst\b.*\bthen\b",
    r"\bphase\s*\d+",
    r"1\.\s+.*\n2\.\s+",
    r"\bfinally\b",
]
REASONING_KEYWORDS = {"compare", "trade-off", "tradeoff", "pros and cons", "architect", "synthesize", "analyze"}


@dataclass
class RoutingFeatures:
    char_length: int
    estimated_tokens: int
    message_count: int
    has_code: bool
    is_debugging: bool
    is_multistep: bool
    has_complex_reasoning: bool

    def to_safe_summary(self) -> Dict[str, Any]:
        return asdict(self)


def extract_features(messages: List[ChatMessage]) -> RoutingFeatures:
    """Extract testable deterministic complexity signals without LLM inference."""
    full_text = " ".join(m.content for m in messages)
    lower_text = full_text.lower()

    char_length = len(full_text)
    estimated_tokens = max(1, char_length // 4)
    message_count = len(messages)

    has_code = any(re.search(p, full_text) for p in CODE_PATTERNS)
    is_debugging = any(k in lower_text for k in DEBUG_KEYWORDS)
    is_multistep = any(re.search(p, lower_text) for p in MULTISTEP_PATTERNS)
    has_complex_reasoning = any(k in lower_text for k in REASONING_KEYWORDS)

    return RoutingFeatures(
        char_length=char_length,
        estimated_tokens=estimated_tokens,
        message_count=message_count,
        has_code=has_code,
        is_debugging=is_debugging,
        is_multistep=is_multistep,
        has_complex_reasoning=has_complex_reasoning,
    )
