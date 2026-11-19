"""Intelligent Prompt Classification and Multi-Agent Routing Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.domain.classifier import ComplexityClassifier, ComplexityLevel
from app.domain.entities import ChatMessage
from app.domain.intent_engine import IntentIntelligenceEngine
from app.domain.modes import GatewayMode, normalize_gateway_mode


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
    selected_mode: str = "auto"
    reasoning_effort: str = "none"
    actual_provider: Optional[str] = None
    actual_model: Optional[str] = None
    fallback_status: str = "not_triggered"

    @property
    def routing_reason(self) -> str:
        return self.reason

    @property
    def classification_level(self) -> int:
        return self.complexity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "reason": self.reason,
            "routing_reason": self.reason,
            "complexity": self.complexity,
            "classification_level": self.complexity,
            "confidence": round(self.confidence, 2),
            "signals": self.signals[:5],
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "fallback_status": self.fallback_status,
            "task_category": self.task_category,
            "selected_mode": self.selected_mode,
            "reasoning_effort": self.reasoning_effort,
            "actual_provider": self.actual_provider,
            "actual_model": self.actual_model,
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
        mode: Optional[str] = None,
    ) -> RoutingDecision:
        """Analyzes prompt intent, depth, and requirements to select optimal agent.

        Enforces priority hierarchy:
        Explicit Expert Mode > Explicit Strong Mode > Explicit Fast/Balanced Mode > Automatic Classification.
        Never relies on prompt instructions to determine mode.
        """
        # Resolve mode if supplied
        resolved_mode: Optional[GatewayMode] = normalize_gateway_mode(mode) if mode else None

        # If manual_agent is provided, map to corresponding mode
        override_prefix = "Manual user override: " if manual_agent else ""
        if manual_agent and not mode:
            if manual_agent.lower() == "strong":
                resolved_mode = GatewayMode.STRONG
            elif manual_agent.lower() == "weak":
                resolved_mode = GatewayMode.FAST

        # Priority 1: Explicit Expert Mode Override
        if resolved_mode == GatewayMode.EXPERT:
            return RoutingDecision(
                agent="strong",
                reason=f"{override_prefix}Explicit Expert Mode selected: frontier capability, deep reasoning, and multi-step verification enforced.",
                complexity=5,
                confidence=1.0,
                signals=["explicit_mode:expert", "override:expert"] + (["manual_override"] if manual_agent else []),
                selected_mode="expert",
                reasoning_effort="high",
                fallback_status="not_triggered",
            )

        # Priority 2: Explicit Strong Mode Override
        if resolved_mode == GatewayMode.STRONG:
            return RoutingDecision(
                agent="strong",
                reason=f"{override_prefix}Explicit Strong Mode selected: backend-enforced strong model override bypassing weak-agent classification.",
                complexity=4,
                confidence=1.0,
                signals=["explicit_mode:strong", "override:strong"] + (["manual_override"] if manual_agent else []),
                selected_mode="strong",
                reasoning_effort="high",
                fallback_status="not_triggered",
            )

        # Priority 3: Explicit Fast Mode Override
        if resolved_mode == GatewayMode.FAST:
            return RoutingDecision(
                agent="weak",
                reason=f"{override_prefix}Explicit Fast Mode selected: cost-effective fast tier prioritized.",
                complexity=1,
                confidence=1.0,
                signals=["explicit_mode:fast", "override:fast"] + (["manual_override"] if manual_agent else []),
                selected_mode="fast",
                reasoning_effort="none",
                fallback_status="not_triggered",
            )

        # Priority 4: Automatic Classification (Auto / Balanced Mode)
        # Note: Prompt instructions (e.g. 'SMART AI GATEWAY STRONG MODE ACTIVATION') are NEVER
        # used to set the mode. Mode is strictly request/session enforced.
        effective_mode_label = resolved_mode.value if resolved_mode else "auto"

        # Build domain message list preserving multi-turn context
        messages: List[ChatMessage] = []
        if conversation_history:
            for m in conversation_history:
                messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))
        messages.append(ChatMessage(role="user", content=prompt))

        # Classify through the unified domain classifier
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

        reasoning_effort = "high" if agent == "strong" else "none"

        return RoutingDecision(
            agent=agent,
            reason=reason,
            complexity=complexity_num,
            confidence=comp_res.confidence,
            signals=comp_res.signals or profile.signals,
            task_category=profile.category.value,
            selected_mode=effective_mode_label,
            reasoning_effort=reasoning_effort,
            fallback_status="not_triggered",
        )


default_router = IntelligentRouter()
