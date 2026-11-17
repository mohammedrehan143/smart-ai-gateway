"""Intelligent Prompt Classification and Multi-Agent Routing Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

# Complex & Expert Patterns requiring the Strong Agent
STRONG_PATTERNS = [
    # System Architecture & Distributed Systems
    r"\b(distributed system|scalable architecture|microservices architecture|system architecture)\b",
    r"\b(two-phase commit|2pc|saga pattern|event sourcing|cqrs|paxos|raft|distributed consensus)\b",
    r"\b(high-throughput distributed|sharding strategy|partitioning scheme|database sharding)\b",
    # Concurrency, Race Conditions, Deadlocks, Advanced Debugging
    r"\b(multi-threaded|race condition|deadlock|thread contention|lock contention|goroutine leak)\b",
    r"\b(memory leak|heap dump|segfault|profiling bottleneck|asyncio deadlock|buffer overflow)\b",
    r"\b(debug.*concurrency|debug.*asynchronous.*deadlock|debug.*multi-threaded)\b",
    # Advanced AI, Machine Learning, Data Science
    r"\b(overfitting and distribution shift|covariate shift|concept drift|gradient vanishing)\b",
    r"\b(multi-agent AI platform|multi-agent orchestration|agentic workflow architecture)\b",
    r"\b(transformer attention mechanism from scratch|reinforcement learning from human feedback|rlhf)\b",
    # Formal Verification, Cryptography, Security Forensics
    r"\b(formal verification|mathematical proof|zero-knowledge proof|zk-snark|post-quantum)\b",
    r"\b(security incident|zero-day|kernel exploit|lateral movement|breach analysis|forensic analysis)\b",
    r"\b(cve-\d+|adversarial attack|reverse engineering binary)\b",
    # Multi-file complex refactoring
    r"\b(architect a complete|design an end-to-end|design a scalable distributed)\b",
]

# Simple / Routine Patterns suited for the Weak Agent
WEAK_PATTERNS = [
    # Direct lookups and definitions
    r"^\s*(?:what is|what are|who is|who was|where is|when was|define|meaning of|what does\b)",
    r"^\s*(?:explain\s+(?:what|the term|variables in|the concept of)\b)",
    # Greetings & Pleasantries
    r"^\s*(?:hello|hi|hey|good (?:morning|afternoon|evening)|greetings|howdy|who are you)\b",
    # Conversions & Unit Calculations
    r"\b(convert\s+\d+\s*(?:km|kilometres?|miles?|meters?|kg|pounds?|celsius|fahrenheit)\s+to\b)",
    r"\b(calculate\s+\d+\s*[\+\-\*\/]\s*\d+)\b",
    # Text Summarization & Translation
    r"\b(summarise|summarize|tl;dr|tldr|key points of|translate this to|translate the following)\b",
    # Formatting & Extraction
    r"\b(format as|convert to json|convert to markdown|extract names from|extract emails)\b",
    # Simple & Routine Coding
    r"\b(reverse a string|reverse string|binary search|bubble sort|fibonacci|palindrome)\b",
    r"\b(basic react login form|login form in react|simple button|hello world|fizzbuzz)\b",
    r"\b(write a\s+(?:python|javascript|typescript|bash)?\s*(?:function|script)\s+to\s+(?:reverse|add|count|sort|print|check))\b",
]


@dataclass
class RoutingDecision:
    """Structured decision output from the prompt router."""
    agent: Literal["weak", "strong"]
    reason: str
    complexity: int  # 1 to 5
    confidence: float  # 0.0 to 1.0
    signals: List[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "reason": self.reason,
            "complexity": self.complexity,
            "confidence": round(self.confidence, 2),
            "signals": self.signals[:5],
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


class IntelligentRouter:
    """Intelligent prompt classification and routing engine allocating tasks between Weak and Strong agents."""

    def __init__(self, complexity_threshold: int = 3):
        # Complexity scores: 1=Simple, 2=Routine, 3=Moderate, 4=Complex, 5=Expert
        # By default: <= 2 -> Weak Agent, >= 3 -> Strong Agent
        self.complexity_threshold = complexity_threshold

    def classify_and_route(
        self,
        prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        manual_agent: Optional[Literal["weak", "strong"]] = None,
    ) -> RoutingDecision:
        """Analyzes prompt intent, depth, and requirements to select optimal agent."""
        # 1. Check for manual user override
        if manual_agent and manual_agent.lower() in ("weak", "strong"):
            agent_type: Literal["weak", "strong"] = manual_agent.lower()  # type: ignore
            return RoutingDecision(
                agent=agent_type,
                reason=f"Manual user override selected {agent_type.capitalize()} Agent.",
                complexity=2 if agent_type == "weak" else 4,
                confidence=1.0,
                signals=["manual_override"],
            )

        text = prompt.strip()
        lower = text.lower()
        signals: List[str] = []

        # 2. Check for Strong Agent triggers (Complexity 4-5)
        for pattern in STRONG_PATTERNS:
            if re.search(pattern, lower):
                signals.append(f"strong_match:{pattern}")
                # Check if expert (level 5) vs complex (level 4)
                is_expert = any(
                    k in lower for k in [
                        "formal verification", "zero-knowledge", "zk-snark", "exploit", "cve-",
                        "kernel", "byzantine", "multi-agent ai platform",
                    ]
                )
                complexity = 5 if is_expert else 4
                return RoutingDecision(
                    agent="strong",
                    reason="Requires advanced architectural design, complex concurrency debugging, or deep technical reasoning.",
                    complexity=complexity,
                    confidence=0.96,
                    signals=signals,
                )

        # 3. Check for Weak Agent triggers (Complexity 1-2)
        for pattern in WEAK_PATTERNS:
            if re.search(pattern, lower):
                signals.append(f"weak_match:{pattern}")
                is_simple = any(
                    k in lower for k in [
                        "what is", "define", "hello", "hi", "convert 10", "summarise", "summarize",
                    ]
                ) and len(text.split()) < 35
                complexity = 1 if is_simple else 2
                return RoutingDecision(
                    agent="weak",
                    reason="The task is straightforward, factual, or routine and requires minimal reasoning.",
                    complexity=complexity,
                    confidence=0.94,
                    signals=signals,
                )

        # 4. Multi-heuristic structural and semantic analysis
        word_count = len(text.split())
        has_code_block = "```" in text or "def " in text or "class " in text
        has_multi_step = bool(re.search(r"\b(first|second|then|finally|step \d|stage \d)\b", lower))
        has_deep_reasoning = bool(re.search(r"\b(trade-off|compare and contrast|architectural implications|root cause)\b", lower))

        complexity = 2
        confidence = 0.88

        if has_deep_reasoning or (has_code_block and has_multi_step and word_count > 60):
            complexity = 4
            signals.append("deep_reasoning_or_multistep_code")
        elif has_code_block and word_count > 120:
            complexity = 3
            signals.append("long_code_context")
        elif word_count > 250:
            complexity = 3
            signals.append("high_context_length")
        elif word_count < 25 and not has_code_block:
            complexity = 1
            signals.append("short_routine_query")
        else:
            complexity = 2
            signals.append("standard_task")

        # Decide agent based on threshold
        if complexity >= self.complexity_threshold:
            agent = "strong"
            reason = "Task complexity requires advanced analytical reasoning and deep domain capability."
        else:
            agent = "weak"
            reason = "Task is well-suited for cost-effective, high-velocity execution via the Weak Agent."

        return RoutingDecision(
            agent=agent,
            reason=reason,
            complexity=complexity,
            confidence=confidence,
            signals=signals,
        )


default_router = IntelligentRouter()
