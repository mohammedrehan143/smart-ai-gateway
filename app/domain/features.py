"""Deterministic feature extraction and complexity signal detection for request routing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from app.domain.classifier import ComplexityClassifier
from app.domain.entities import ChatMessage

CODE_PATTERNS = [
    r"```",
    r"\bdef\s+\w+\s*\(",
    r"\bclass\s+\w+[:\(]",
    r"\bimport\s+[\w\.]+",
    r"\bfrom\s+[\w\.]+\s+import",
    r"\bfunction\s*\w*\(",
    r"\bconst\s+\w+\s*=",
    r"\blet\s+\w+\s*=",
    r"SELECT\s+.*\s+FROM\s+",
]

# Actionable debugging intents and diagnostic signals (not pure dictionary definitions)
ACTIVE_DEBUG_PATTERNS = [
    r"traceback",
    r"zerodivisionerror",
    r"\b(fix (?:this|the) (?:bug|error|issue|exception))\b",
    r"\bdebug (?:this|my|the)?\b",
    r"\b(?:nullpointerexception|segmentation fault|segfault|deadlock|panic: runtime error)\b",
    r"\b(?:heap dump|memory leak|stack overflow)\b",
]

MULTISTEP_PATTERNS = [
    r"\bstep\s*\d+",
    r"\bfirst\b.*\bthen\b",
    r"\bphase\s*\d+",
    r"1\.\s+.*\n2\.\s+",
    r"\bfinally\b",
]

REASONING_PATTERNS = [
    r"\b(trade-off|tradeoff|pros and cons|architect|synthesize|security incident)\b",
    r"\b(system architecture|consensus protocol|formal proof)\b",
]


@dataclass
class RoutingFeatures:
    char_length: int
    estimated_tokens: int
    message_count: int
    has_code: bool
    is_debugging: bool
    is_multistep: bool
    has_complex_reasoning: bool
    complexity_level: str = "SIMPLE"
    required_capabilities: Optional[List[str]] = None
    classification_reason: str = ""

    def __post_init__(self):
        if self.required_capabilities is None:
            self.required_capabilities = []

    def to_safe_summary(self) -> Dict[str, Any]:
        return asdict(self)


def extract_features(messages: List[ChatMessage], has_tools: bool = False, format_json: bool = False) -> RoutingFeatures:
    """Extract testable deterministic complexity signals focused on the active user turn.

    Guarantees: Prior history provides context for token budgets, but does not falsely
    inflate feature flags (like has_code or is_debugging) for a simple greeting turn.
    """
    user_msgs = [m for m in messages if m.role == "user"]
    latest_text = user_msgs[-1].content if user_msgs else (messages[-1].content if messages else "")
    latest_lower = latest_text.lower()

    full_text = " ".join(m.content for m in messages)
    char_length = len(full_text)
    estimated_tokens = max(1, char_length // 4)
    message_count = len(messages)

    # Classify complexity into SIMPLE, MODERATE, COMPLEX, EXPERT based on active turn
    classification = ComplexityClassifier.classify(messages, has_tools=has_tools, format_json=format_json)

    # Extract feature flags directly from the active user turn
    has_code = any(re.search(p, latest_text, re.IGNORECASE) for p in CODE_PATTERNS) or (
        len(messages) > 1 and any(k in latest_lower for k in ("fix", "optimize", "refactor", "run", "code")) and any(re.search(p, full_text, re.IGNORECASE) for p in CODE_PATTERNS)
    )
    is_debugging = any(re.search(p, latest_lower) for p in ACTIVE_DEBUG_PATTERNS)
    is_multistep = any(re.search(p, latest_lower) for p in MULTISTEP_PATTERNS)
    has_complex_reasoning = any(re.search(p, latest_lower) for p in REASONING_PATTERNS)

    return RoutingFeatures(
        char_length=char_length,
        estimated_tokens=estimated_tokens,
        message_count=message_count,
        has_code=has_code,
        is_debugging=is_debugging,
        is_multistep=is_multistep,
        has_complex_reasoning=has_complex_reasoning,
        complexity_level=classification.complexity.value,
        required_capabilities=list(classification.required_capabilities),
        classification_reason=classification.reason,
    )
