"""Sophisticated deterministic complexity classification for intelligent LLM routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set
from app.domain.entities import ChatMessage


class ComplexityLevel(str, Enum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    COMPLEX = "COMPLEX"
    EXPERT = "EXPERT"


# Expert Regex Patterns: High-stakes technical reasoning, demanding multi-stage problems, security forensics, formal proofs
EXPERT_PATTERNS = [
    r"\b(security incident|zero-day|kernel exploit|lateral movement|breach analysis|forensic analysis)\b",
    r"\b(multi-agent security incident|multi-agent exploit|adversarial attack|cve-\d+)\b",
    r"\b(formal verification|mathematical proof|safety invariant|temporal logic|tla\+)\b",
    r"\b(zero-knowledge proof|cryptographic protocol|elliptic curve|post-quantum cryptography)\b",
    r"\b(byzantine fault tolerance|consensus invariant|distributed consensus proof)\b",
]

# Complex Regex Patterns: Advanced technical reasoning, difficult debugging, system architecture, deep analysis
COMPLEX_PATTERNS = [
    r"\b(distributed system|scalable architecture|distributed architecture|microservices architecture|system architecture)\b",
    r"\b(distributed banking|distributed transaction|two-phase commit|2pc|saga pattern|event sourcing|cqrs)\b",
    r"\b(?:scalable|distributed|system|microservices|multi-agent)(?:\s+[\w\-]+){0,2}\s+(?:architecture|system)\b",
    r"\b(multi-agent\s+ai\s+platform|multi-agent\s+orchestration|agentic\s+workflow\s+architecture)\b",
    r"\b(paxos|raft|distributed consensus|sharding strategy|partitioning scheme|database sharding)\b",
    r"\b(multi-threaded|race condition|deadlock|thread contention|lock contention|goroutine leak)\b",
    r"\b(debug.*asynchronous|debug.*concurrency|deadlock|race condition|memory leak|heap dump|segfault|profiling bottleneck|asyncio deadlock)\b",
    r"\b(trade-off analysis between.*and.*under|compare the pros and cons of|pros and cons of)\b",
    r"\b(overfitting and distribution shift|distribution shift|covariate shift|concept drift|gradient vanishing|transformer attention mechanism)\b",
    r"(review|audit|debug|optimize)\s+(?:this|the)?\s*(?:python|javascript|typescript|c\+\+|code|implementation|function)?[:\s\n]+```",
    r"```[a-zA-Z0-9_\+\-]*\n[\s\S]{20,}\n```",  # Substantial multi-line embedded code snippet requiring deep inspection
]

# Moderate Regex Patterns: Explanations, ordinary coding, structured writing, multi-step tasks, basic debugging
MODERATE_PATTERNS = [
    r"\b(explain\b.*(?:example|step by step|mechanism of|how it works)|how does\b.*\bwork|compare and contrast)\b",
    r"\b(write a\s+(?:python|javascript|typescript|sql|c\+\+|java|go|rust)?\s*(?:function|script|query|component|class|program))\b",
    r"\b(reverse a string|reverse string|binary search|bubble sort|fibonacci|palindrome|linked list|two sum|fizzbuzz)\b",
    r"\b(create (?:a|an)\s+(?:[\w\-]+\s+)?(?:button|form|endpoint|route|api|modal|component)|login form in react|basic react login form)\b",
    r"\b(draft a\s+(?:polite|professional)?\s*(?:email|letter|proposal|memo|cover letter|outline|blog post))\b",
    r"\b(step 1.*step 2|first.*then.*finally|step by step)\b",
    r"\b(calculate (?:the\s+)?(?:compound interest|interest|total|area|volume|perimeter|standard deviation))\b",
    r"\b(convert\s+\d+\s*(?:km|kilometres?|miles?|meters?|kg|pounds?|celsius|fahrenheit)\s+to\b)",
    r"\b(summarise|summarize|summary of|tl;dr|tldr|key takeaways|executive summary|distill this)\b",
    r"\b(fix (?:this|the)?\s*(?:bug|error|issue|exception)|traceback:)\b",
    r"\b(debug this|help fix)\b",
]

# Simple Definition Patterns: Basic questions, definitions, standard lookups
SIMPLE_DEFINITION_PATTERNS = [
    r"^\s*(?:what is|what are|who is|who was|where is|where to|when was|when is|how to|define|meaning of|what does\b)",
    r"^\s*explain (?:what|the term|the concept of|variables|recursion|loops|functions)\b",
    r"^\s*explain\s+[a-zA-Z0-9_\-\s]{1,35}$",
]

# Simple Greeting Patterns: Conversational greetings and pleasantries
SIMPLE_GREETING_PATTERNS = [
    r"^\s*(?:hello|hi|hy|hey|yo|sup|good (?:morning|afternoon|evening)|greetings|howdy|who are you)\b",
]


@dataclass
class ClassificationResult:
    complexity: ComplexityLevel
    reason: str
    required_capabilities: Set[str] = field(default_factory=set)
    confidence: float = 0.95
    signals: List[str] = field(default_factory=list)
    level: int = 1

    def __post_init__(self):
        if self.complexity == ComplexityLevel.SIMPLE:
            self.level = 1
        elif self.complexity == ComplexityLevel.MODERATE:
            self.level = 2
        else:
            self.level = 3


class ComplexityClassifier:
    """Classifies user requests into SIMPLE, MODERATE, COMPLEX, or EXPERT based on reasoning depth and required capabilities."""

    @classmethod
    def classify(
        cls, messages: List[ChatMessage], has_tools: bool = False, format_json: bool = False
    ) -> ClassificationResult:
        from app.core.logging import get_logger

        logger = get_logger("app.domain.classifier")

        # Classify the latest user prompt independently to prevent history contamination in multi-turn chat
        user_msgs = [m for m in messages if m.role == "user"]
        target_prompt = user_msgs[-1].content.strip() if user_msgs else (" ".join(m.content for m in messages).strip())
        lower_text = target_prompt.lower()
        signals: List[str] = []
        required_capabilities: Set[str] = {"chat"}

        if has_tools:
            required_capabilities.add("tools")
        if format_json:
            required_capabilities.add("json")

        def _log_and_return(res: ClassificationResult) -> ClassificationResult:
            logger.info(
                f"[CLASSIFIER] prompt='{target_prompt[:60]}' | complexity={res.complexity.value} | level={res.level} | reason='{res.reason}'"
            )
            return res

        # 1. Check for EXPERT triggers
        for p in EXPERT_PATTERNS:
            if re.search(p, lower_text):
                signals.append(f"expert_match:{p}")
                required_capabilities.update(["deep_reasoning", "security_analysis"])
                return _log_and_return(
                    ClassificationResult(
                        complexity=ComplexityLevel.EXPERT,
                        reason="High-stakes technical reasoning, demanding multi-stage problem, or specialized security analysis.",
                        required_capabilities=required_capabilities,
                        confidence=0.98,
                        signals=signals,
                    )
                )

        # 2. Check for COMPLEX triggers
        for p in COMPLEX_PATTERNS:
            if re.search(p, lower_text):
                signals.append(f"complex_match:{p}")
                required_capabilities.update(["complex_code", "debugging", "architecture"])
                return _log_and_return(
                    ClassificationResult(
                        complexity=ComplexityLevel.COMPLEX,
                        reason="Advanced technical reasoning, complex architecture design, or deep debugging diagnostics required.",
                        required_capabilities=required_capabilities,
                        confidence=0.95,
                        signals=signals,
                    )
                )

        # 3. Check for SIMPLE Definition & Greetings BEFORE general keywords
        # If the user asks a definitional query (e.g. "What is Python?", "What is an error?")
        # or simple greeting ("Hello"), it is explicitly SIMPLE!
        for p in SIMPLE_GREETING_PATTERNS:
            if re.search(p, lower_text):
                signals.append("simple_greeting")
                required_capabilities.add("general_knowledge")
                return _log_and_return(
                    ClassificationResult(
                        complexity=ComplexityLevel.SIMPLE,
                        reason="Basic greeting or conversational pleasantry; minimal reasoning required.",
                        required_capabilities=required_capabilities,
                        confidence=0.99,
                        signals=signals,
                    )
                )

        for p in SIMPLE_DEFINITION_PATTERNS:
            if re.search(p, lower_text):
                signals.append("simple_definition")
                required_capabilities.add("general_knowledge")
                return _log_and_return(
                    ClassificationResult(
                        complexity=ComplexityLevel.SIMPLE,
                        reason="Basic factual or definitional question; standard knowledge lookup.",
                        required_capabilities=required_capabilities,
                        confidence=0.95,
                        signals=signals,
                    )
                )

        # 4. Check for MODERATE triggers
        for p in MODERATE_PATTERNS:
            if re.search(p, lower_text):
                signals.append(f"moderate_match:{p}")
                required_capabilities.update(["code_simple", "qa", "summarization"])
                return _log_and_return(
                    ClassificationResult(
                        complexity=ComplexityLevel.MODERATE,
                        reason="Detailed conceptual explanation, ordinary coding task, or structured writing.",
                        required_capabilities=required_capabilities,
                        confidence=0.92,
                        signals=signals,
                    )
                )

        # 5. Short routine heuristic: If short and no complex keywords, classify as SIMPLE
        if len(target_prompt) < 250 and not any(
            k in lower_text for k in ["analyze", "design", "architect", "audit", "optimize", "evaluate"]
        ):
            signals.append("short_routine_heuristic")
            required_capabilities.add("general_knowledge")
            return _log_and_return(
                ClassificationResult(
                    complexity=ComplexityLevel.SIMPLE,
                    reason="Basic informational request; no advanced reasoning required.",
                    required_capabilities=required_capabilities,
                    confidence=0.90,
                    signals=signals,
                )
            )

        # Default fallback is MODERATE
        signals.append("standard_general_inquiry")
        required_capabilities.add("qa")
        return _log_and_return(
            ClassificationResult(
                complexity=ComplexityLevel.MODERATE,
                reason="Standard general inquiry requiring moderate explanation or structured response.",
                required_capabilities=required_capabilities,
                confidence=0.85,
                signals=signals,
            )
        )
