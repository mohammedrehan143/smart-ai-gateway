"""Intelligent Prompt Classification and Multi-Agent Routing Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.domain.classifier import ComplexityClassifier, ComplexityLevel
from app.domain.entities import ChatMessage
from app.domain.intent_engine import IntentIntelligenceEngine


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
    task_category: str = "general_chat"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "reason": self.reason,
            "complexity": self.complexity,
            "confidence": round(self.confidence, 2),
            "signals": self.signals[:5],
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "task_category": self.task_category,
        }


class IntelligentRouter:
    """Intelligent prompt classification and routing engine allocating tasks between Weak and Strong agents.

    Delegates directly to the unified ComplexityClassifier and IntentIntelligenceEngine to guarantee
    architectural consistency and prevent conversation history contamination.
    """

    def __init__(self, complexity_threshold: int = 3):
        # Complexity scores: 1=Simple, 2=Moderate, 4=Complex, 5=Expert
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

        # 2. Build domain message list preserving multi-turn context
        messages: List[ChatMessage] = []
        if conversation_history:
            for m in conversation_history:
                messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))
        messages.append(ChatMessage(role="user", content=prompt))

        # 3. Classify through the unified domain classifier
        comp_res = ComplexityClassifier.classify(messages)
        profile = IntentIntelligenceEngine.analyze(messages)

        # Map domain ComplexityLevel to 1-5 scale
        if comp_res.complexity == ComplexityLevel.EXPERT:
            complexity_num = 5
            agent: Literal["weak", "strong"] = "strong"
        elif comp_res.complexity == ComplexityLevel.COMPLEX:
            complexity_num = 4
            agent = "strong"
        elif comp_res.complexity == ComplexityLevel.MODERATE:
            complexity_num = 2
            agent = "weak" if self.complexity_threshold > 2 else "strong"
        else:
            complexity_num = 1
            agent = "weak"

        # Apply threshold check
        if complexity_num >= self.complexity_threshold and agent == "weak":
            agent = "strong"
            reason = (
                comp_res.reason or "Task complexity requires advanced analytical reasoning and deep domain capability."
            )
        elif (
            complexity_num < self.complexity_threshold
            and agent == "strong"
            and comp_res.complexity not in (ComplexityLevel.COMPLEX, ComplexityLevel.EXPERT)
        ):
            agent = "weak"
            reason = (
                comp_res.reason or "Task is well-suited for cost-effective, high-velocity execution via the Weak Agent."
            )
        else:
            reason = comp_res.reason

        return RoutingDecision(
            agent=agent,
            reason=reason,
            complexity=complexity_num,
            confidence=comp_res.confidence,
            signals=comp_res.signals or profile.signals,
            task_category=profile.category.value,
        )


default_router = IntelligentRouter()
