"""Multi-dimensional Intent and Task Intelligence Engine with History-Aware Isolation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from app.domain.classifier import (
    ComplexityClassifier,
    ComplexityLevel,
    SIMPLE_DEFINITION_PATTERNS,
    SIMPLE_GREETING_PATTERNS,
)
from app.domain.entities import ChatMessage


class TaskCategory(str, Enum):
    CODING = "coding"
    REASONING = "reasoning"
    RESEARCH = "research"
    SUMMARIZATION = "summarization"
    MATHEMATICS = "mathematics"
    STRUCTURED_GENERATION = "structured_generation"
    MULTIMODAL = "multimodal"
    TOOL_EXECUTION = "tool_execution"
    GENERAL_CHAT = "general_chat"


@dataclass
class TaskProfile:
    intent: str
    category: TaskCategory
    complexity: ComplexityLevel
    required_capabilities: Set[str] = field(default_factory=set)
    context_requirements: Dict[str, Any] = field(default_factory=dict)
    output_format: str = "markdown"  # plaintext, markdown, code, json, table
    tool_requirements: List[str] = field(default_factory=list)
    quality_expectation: float = 0.80  # Normalized (0.0 - 1.0)
    latency_sensitivity: str = "standard"  # ultra_low, standard, batch
    cost_constraints: Optional[float] = None  # Max USD per request
    ambiguity_score: float = 0.10  # 0.0 (crystal clear) to 1.0 (highly ambiguous)
    signals: List[str] = field(default_factory=list)

    def to_safe_summary(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "category": self.category.value,
            "complexity": self.complexity.value,
            "required_capabilities": sorted(list(self.required_capabilities)),
            "output_format": self.output_format,
            "tool_requirements": self.tool_requirements,
            "quality_expectation": self.quality_expectation,
            "latency_sensitivity": self.latency_sensitivity,
            "cost_constraints": self.cost_constraints,
            "ambiguity_score": self.ambiguity_score,
            "signals": self.signals[:5],
        }


# Pattern definitions for multi-dimensional extraction
MATH_PATTERNS = [
    r"\b(solve for|equation|integral|derivative|eigenvalue|matrix multiplication|calculate\s+\d+|factorial|polynomial)\b",
    r"\b(stochastic|bayesian|linear algebra|differential equation|combinatorics|prime number|logarithm)\b",
    r"[\d\.]+\s*[\+\-\*\/\^%]\s*[\d\.]+",
]

STRUCTURED_PATTERNS = [
    r"\b(in json format|return json|json schema|parse to yaml|structured json|generate xml|as a csv|as a table)\b",
    r"\{\s*\"[a-zA-Z0-9_\-]+\"\s*:",
]

RESEARCH_PATTERNS = [
    r"\b(literature review|academic sources|state of the art|cite sources|empirical evidence|comprehensive study)\b",
    r"\b(deep dive into|exhaustive analysis|historical background of|forensic review of)\b",
]

SUMMARIZATION_PATTERNS = [
    r"\b(summarize|summary of|tl;dr|tldr|key takeaways|executive summary|distill this|synopsis)\b",
]

MULTIMODAL_PATTERNS = [
    r"\b(attached image|describe the picture|analyze this diagram|visual inspection|ocr|chart analysis)\b",
    r"data:image\/[a-zA-Z]+;base64,",
]

TOOL_TRIGGER_PATTERNS = [
    r"\b(lookup in database|execute sql|search the web|use tool|calculate using|invoke function)\b",
]


class IntentIntelligenceEngine:
    """Understands user requests across multi-dimensional intent, capabilities, and execution requirements.

    Guarantees: Uses the latest user message as the primary classification signal.
    Past conversation history provides context for token budgets, but NEVER falsely inflates
    the complexity or alters the intent category of a simple latest message (e.g. 'Hi').
    """

    @classmethod
    def analyze(
        cls,
        messages: List[ChatMessage],
        tools: Optional[list] = None,
        format_json: bool = False,
        quality_threshold: Optional[float] = None,
        max_cost_limit: Optional[float] = None,
    ) -> TaskProfile:
        signals: List[str] = []

        # 1. Extract latest user turn as primary signal
        user_msgs = [m for m in messages if m.role == "user"]
        latest_user_msg = (
            user_msgs[-1].content.strip() if user_msgs else (messages[-1].content.strip() if messages else "")
        )
        target_text = latest_user_msg
        lower_target = target_text.lower()

        full_text = " ".join(m.content for m in messages).strip()

        # 2. Complexity Classification (focused on latest prompt)
        comp_res = ComplexityClassifier.classify(messages, has_tools=bool(tools), format_json=format_json)
        complexity = comp_res.complexity
        capabilities: Set[str] = set(comp_res.required_capabilities)
        signals.extend(comp_res.signals)

        # 3. Category Detection
        category = TaskCategory.GENERAL_CHAT
        intent = "general_query"
        output_format = "markdown"

        # Explicit tool calling presence
        tool_requirements: List[str] = []
        if tools:
            category = TaskCategory.TOOL_EXECUTION
            intent = "tool_assisted_execution"
            capabilities.add("tools")
            signals.append("tools_provided")
            for t in tools:
                if isinstance(t, dict):
                    fn_name = t.get("function", {}).get("name") or t.get("name")
                    if fn_name:
                        tool_requirements.append(fn_name)

        # Check for simple greetings and basic definitions first on latest target
        elif any(re.search(p, lower_target) for p in SIMPLE_GREETING_PATTERNS):
            category = TaskCategory.GENERAL_CHAT
            intent = "conversational_greeting"
            output_format = "markdown"
            signals.append("greeting_intent")

        elif any(re.search(p, lower_target) for p in SIMPLE_DEFINITION_PATTERNS) and len(target_text.split()) < 35:
            category = TaskCategory.GENERAL_CHAT
            intent = "factual_lookup"
            output_format = "markdown"
            signals.append("definition_intent")

        # Multimodal detection on latest message
        elif any(re.search(p, lower_target) for p in MULTIMODAL_PATTERNS):
            category = TaskCategory.MULTIMODAL
            intent = "multimodal_processing"
            capabilities.add("multimodal")
            signals.append("multimodal_intent")

        # Mathematics detection on latest message
        elif any(re.search(p, lower_target) for p in MATH_PATTERNS) and not any(
            k in lower_target for k in ["binary search", "reverse string"]
        ):
            category = TaskCategory.MATHEMATICS
            intent = "mathematical_computation"
            capabilities.update(["math", "deep_reasoning"])
            signals.append("mathematics_intent")

        # Structured output format detection
        elif format_json or any(re.search(p, lower_target) for p in STRUCTURED_PATTERNS):
            category = TaskCategory.STRUCTURED_GENERATION
            intent = "structured_data_generation"
            output_format = "json"
            capabilities.add("json")
            signals.append("structured_output_intent")

        # Summarization detection
        elif any(re.search(p, lower_target) for p in SUMMARIZATION_PATTERNS):
            category = TaskCategory.SUMMARIZATION
            intent = "text_summarization"
            capabilities.add("summarization")
            signals.append("summarization_intent")

        # Deep Research detection
        elif any(re.search(p, lower_target) for p in RESEARCH_PATTERNS):
            category = TaskCategory.RESEARCH
            intent = "in_depth_research"
            capabilities.update(["deep_reasoning", "qa"])
            signals.append("research_intent")

        # Coding detection on latest message
        elif any(k in capabilities for k in ["code_simple", "complex_code", "debugging"]) or any(
            k in lower_target
            for k in [
                "def ",
                "class ",
                "function",
                "write a python",
                "debug",
                "refactor",
                "binary search",
                "reverse a string",
                "bug",
                "traceback",
            ]
        ):
            category = TaskCategory.CODING
            intent = "code_generation_or_debug"
            output_format = "code"
            signals.append("coding_intent")

        # Reasoning & Architecture detection on latest message
        elif any(k in capabilities for k in ["architecture", "deep_reasoning", "security_analysis"]) or any(
            k in lower_target for k in ["architecture", "consensus", "trade-off", "distributed", "security incident"]
        ):
            category = TaskCategory.REASONING
            intent = "analytical_reasoning"
            signals.append("reasoning_intent")

        # Ambiguity Scoring
        ambiguity = 0.05
        if len(target_text.split()) < 4 and category == TaskCategory.GENERAL_CHAT:
            ambiguity = 0.40
        elif "?" in target_text and any(
            k in lower_target for k in ["maybe", "either", "could you clarify", "it depends"]
        ):
            ambiguity = 0.35

        # Latency sensitivity
        latency_sensitivity = "standard"
        if complexity == ComplexityLevel.SIMPLE and category == TaskCategory.GENERAL_CHAT:
            latency_sensitivity = "ultra_low"
        elif complexity == ComplexityLevel.EXPERT or category in (TaskCategory.RESEARCH, TaskCategory.REASONING):
            latency_sensitivity = "batch"

        # Quality expectation
        quality_expectation = quality_threshold or (
            0.98
            if complexity == ComplexityLevel.EXPERT
            else 0.90
            if complexity == ComplexityLevel.COMPLEX
            else 0.80
            if complexity == ComplexityLevel.MODERATE
            else 0.70
        )

        char_len = len(full_text)
        token_est = max(1, char_len // 4)

        return TaskProfile(
            intent=intent,
            category=category,
            complexity=complexity,
            required_capabilities=capabilities,
            context_requirements={
                "char_length": char_len,
                "estimated_tokens": token_est,
                "message_count": len(messages),
                "has_context_history": len(messages) > 1,
                "latest_turn_chars": len(target_text),
            },
            output_format=output_format,
            tool_requirements=tool_requirements,
            quality_expectation=quality_expectation,
            latency_sensitivity=latency_sensitivity,
            cost_constraints=max_cost_limit,
            ambiguity_score=ambiguity,
            signals=signals,
        )


default_intent_engine = IntentIntelligenceEngine()
