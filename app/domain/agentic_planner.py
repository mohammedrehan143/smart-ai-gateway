"""Agentic Task Planning and Controlled Execution Graph state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from app.domain.classifier import ComplexityLevel
from app.domain.intent_engine import TaskCategory, TaskProfile


class ExecutionState(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionMode(str, Enum):
    DIRECT = "direct"  # Single-model inference for routine/simple tasks
    MULTI_STEP = "multi_step"  # Sequential sub-task decomposition
    COLLABORATIVE = "collaborative"  # Multi-model team execution (Worker, Critic, Verifier)
    TOOL_ASSISTED = "tool_assisted"  # Execution augmented with tool calls


@dataclass
class ExecutionStep:
    step_number: int
    title: str
    action: str  # "generate", "review", "verify_code", "critique", "synthesize", "tool_call"
    assigned_model: str
    status: str = "pending"  # "pending", "running", "success", "failure"
    input_text: str = ""
    output_text: str = ""
    latency_ms: int = 0
    estimated_cost: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "action": self.action,
            "assigned_model": self.assigned_model,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "cost": self.estimated_cost,
            "error": self.error_message,
        }


@dataclass
class AgenticPlan:
    mode: ExecutionMode
    strategy: str  # "direct", "peer_review", "code_verification", "consensus_synthesis", "sequential_decomposition"
    steps: List[ExecutionStep] = field(default_factory=list)
    rationale: str = ""
    max_steps_limit: int = 5
    timeout_seconds: float = 30.0

    @property
    def estimated_total_tokens(self) -> int:
        return max(100, len(self.steps) * 512)

    def to_summary(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "strategy": self.strategy,
            "total_steps": len(self.steps),
            "rationale": self.rationale,
            "steps": [s.to_dict() for s in self.steps],
        }


class AgenticTaskPlanner:
    """Intelligently plans execution topology: direct single-model vs multi-model collaboration."""

    @classmethod
    def create_plan(
        cls,
        profile: TaskProfile,
        primary_model: str,
        strong_model: str,
        cheap_model: Optional[str] = None,
        collaboration_requested: bool = False,
        collaboration_strategy: Optional[str] = None,
        max_cost_budget: Optional[float] = None,
    ) -> AgenticPlan:
        return cls.plan(
            profile=profile,
            primary_model=primary_model,
            strong_model=strong_model,
            collaboration_requested=collaboration_requested,
            collaboration_strategy=collaboration_strategy,
            max_cost_budget=max_cost_budget,
        )

    @classmethod
    def plan(
        cls,
        profile: TaskProfile,
        primary_model: str,
        strong_model: str,
        collaboration_requested: bool = False,
        collaboration_strategy: Optional[str] = None,
        max_cost_budget: Optional[float] = None,
    ) -> AgenticPlan:
        # Rule 1: Simple tasks NEVER invoke multiple models
        if profile.complexity == ComplexityLevel.SIMPLE:
            return AgenticPlan(
                mode=ExecutionMode.DIRECT,
                strategy="direct",
                steps=[
                    ExecutionStep(
                        step_number=1,
                        title="Direct Query Response",
                        action="generate",
                        assigned_model=primary_model,
                    )
                ],
                rationale="Simple query with minimal reasoning demands; direct single-model execution maximizes cost efficiency.",
            )

        # Rule 2: Budget constraints check: if budget is too low (< $0.001), force direct execution
        if max_cost_budget is not None and max_cost_budget < 0.001:
            return AgenticPlan(
                mode=ExecutionMode.DIRECT,
                strategy="direct",
                steps=[
                    ExecutionStep(
                        step_number=1,
                        title="Budget-Gated Direct Execution",
                        action="generate",
                        assigned_model=primary_model,
                    )
                ],
                rationale="Strict budget constraint active; multi-model collaboration bypassed to prevent spend overrun.",
            )

        # Rule 3: Explicit tool-assisted execution
        if profile.category == TaskCategory.TOOL_EXECUTION or profile.tool_requirements:
            return AgenticPlan(
                mode=ExecutionMode.TOOL_ASSISTED,
                strategy="tool_augmented_generation",
                steps=[
                    ExecutionStep(
                        step_number=1,
                        title="Tool Calling & Argument Extraction",
                        action="tool_call",
                        assigned_model=primary_model,
                    ),
                    ExecutionStep(
                        step_number=2,
                        title="Tool Output Synthesis",
                        action="synthesize",
                        assigned_model=primary_model,
                    ),
                ],
                rationale="Request requires external tools; planned tool execution and synthesis phases.",
            )

        # Rule 4: Multi-Model Collaboration if requested or for EXPERT / high-stakes tasks
        should_collaborate = collaboration_requested or (
            profile.complexity == ComplexityLevel.EXPERT
            and profile.category in (TaskCategory.CODING, TaskCategory.REASONING, TaskCategory.RESEARCH)
        )

        if should_collaborate:
            strat = (collaboration_strategy or "peer_review").lower()

            if profile.category == TaskCategory.CODING or strat == "code_verification":
                return AgenticPlan(
                    mode=ExecutionMode.COLLABORATIVE,
                    strategy="code_verification",
                    steps=[
                        ExecutionStep(
                            step_number=1,
                            title="Primary Implementation Draft",
                            action="generate",
                            assigned_model=primary_model,
                        ),
                        ExecutionStep(
                            step_number=2,
                            title="Static AST & Edge-Case Verification",
                            action="verify_code",
                            assigned_model=strong_model,
                        ),
                    ],
                    rationale="High-complexity coding task; paired primary generator with secondary code verification model.",
                )

            elif strat == "consensus" or profile.complexity == ComplexityLevel.EXPERT:
                return AgenticPlan(
                    mode=ExecutionMode.COLLABORATIVE,
                    strategy="consensus_synthesis",
                    steps=[
                        ExecutionStep(
                            step_number=1,
                            title="Primary Solution Analysis",
                            action="generate",
                            assigned_model=primary_model,
                        ),
                        ExecutionStep(
                            step_number=2,
                            title="Independent Critique & Contradiction Check",
                            action="critique",
                            assigned_model=strong_model,
                        ),
                        ExecutionStep(
                            step_number=3,
                            title="Consensus Synthesis",
                            action="synthesize",
                            assigned_model=strong_model,
                        ),
                    ],
                    rationale="Expert-tier technical synthesis; executing multi-model consensus and critique verification.",
                )

            else:
                # Default Peer Review
                return AgenticPlan(
                    mode=ExecutionMode.COLLABORATIVE,
                    strategy="peer_review",
                    steps=[
                        ExecutionStep(
                            step_number=1,
                            title="Initial Response Generation",
                            action="generate",
                            assigned_model=primary_model,
                        ),
                        ExecutionStep(
                            step_number=2,
                            title="Peer Review & Quality Polish",
                            action="review",
                            assigned_model=strong_model,
                        ),
                    ],
                    rationale="Quality-focused multi-model review requested; primary output audited by secondary model.",
                )

        # Rule 5: Default Moderate tasks -> Direct Execution
        return AgenticPlan(
            mode=ExecutionMode.DIRECT,
            strategy="direct",
            steps=[
                ExecutionStep(
                    step_number=1,
                    title="Direct Task Execution",
                    action="generate",
                    assigned_model=primary_model,
                )
            ],
            rationale="Task requirements fully satisfied by single model execution; multi-model overhead avoided.",
        )


default_agentic_planner = AgenticTaskPlanner()
