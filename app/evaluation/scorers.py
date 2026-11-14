"""Scorers for final answer, tool selection/use, and execution trajectory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from app.evaluation.agent import AgentExecutionResult
from app.evaluation.dataset import EvaluationCase


@dataclass
class ScoreResult:
    case_id: str
    passed: bool
    total_score: float
    answer_score: float
    tool_score: float
    trajectory_score: float
    feedback: List[str]


class AnswerScorer:
    """Evaluates final answer accuracy and required facts."""

    @classmethod
    def score(cls, case: EvaluationCase, answer: str) -> float:
        expected = str(case.expected_answer).strip().lower()
        actual = str(answer).strip().lower()

        # Direct exact or numeric match
        if expected in actual:
            return 1.0

        # Try floating point equivalence
        try:
            exp_val = float(expected)
            act_val = float(actual)
            if abs(exp_val - act_val) < 1e-4:
                return 1.0
        except ValueError:
            pass

        # Fact coverage check
        if case.expected_facts:
            matched_facts = sum(1 for fact in case.expected_facts if fact.lower() in actual)
            coverage = matched_facts / len(case.expected_facts)
            return round(coverage, 2)

        return 0.5 if actual else 0.0


class ToolScorer:
    """Evaluates tool selection, forbidden tool avoidance, and execution validity."""

    @classmethod
    def score(cls, case: EvaluationCase, tool_events: list) -> float:
        used_tools = {e.tool_name for e in tool_events}
        req_tools = set(case.required_tools)
        forb_tools = set(case.forbidden_tools)

        # Hard failure if a forbidden tool was used
        if used_tools.intersection(forb_tools):
            return 0.0

        # If tools required, verify all were called
        if req_tools:
            if not req_tools.issubset(used_tools):
                missing = req_tools - used_tools
                return max(0.0, 1.0 - (len(missing) / len(req_tools)))

            # Verify that executions succeeded
            failed_executions = sum(1 for e in tool_events if not e.ok)
            if failed_executions > 0:
                return 0.5

            return 1.0
        else:
            # If no tools required, calling unnecessary tools incurs penalty
            if used_tools:
                return 0.5
            return 1.0


class TrajectoryScorer:
    """Evaluates execution step budget and sequence integrity."""

    @classmethod
    def score(cls, case: EvaluationCase, steps_taken: int) -> float:
        if steps_taken <= case.max_steps:
            return 1.0
        elif steps_taken <= case.max_steps + 1:
            return 0.5
        return 0.0


class CompositeScorer:
    """Aggregates dimension scores into overall case pass/fail."""

    @classmethod
    def evaluate(cls, case: EvaluationCase, result: AgentExecutionResult) -> ScoreResult:
        ans_score = AnswerScorer.score(case, result.final_answer)
        tool_score = ToolScorer.score(case, result.tool_events)
        traj_score = TrajectoryScorer.score(case, result.steps_taken)

        w_ans = case.weights.get("answer", 0.5)
        w_tool = case.weights.get("tool_selection", 0.3)
        w_traj = case.weights.get("trajectory", 0.2)

        total_score = round(ans_score * w_ans + tool_score * w_tool + traj_score * w_traj, 3)
        passed = total_score >= 0.70 and ans_score >= 0.50

        feedback = []
        if ans_score < 0.7:
            feedback.append(f"Answer score low ({ans_score})")
        if tool_score < 1.0:
            feedback.append(f"Tool score penalized ({tool_score})")
        if traj_score < 1.0:
            feedback.append(f"Trajectory exceeded optimal steps ({result.steps_taken}/{case.max_steps})")

        return ScoreResult(
            case_id=case.id,
            passed=passed,
            total_score=total_score,
            answer_score=ans_score,
            tool_score=tool_score,
            trajectory_score=traj_score,
            feedback=feedback,
        )
