"""Unit tests for evaluation scorers."""

from app.evaluation.agent import ToolExecutionEvent
from app.evaluation.dataset import EvaluationCase
from app.evaluation.scorers import AnswerScorer, ToolScorer, TrajectoryScorer


def test_answer_scorer():
    case = EvaluationCase(
        id="t1",
        category="direct",
        prompt="What is 401 status?",
        required_tools=[],
        forbidden_tools=[],
        expected_answer="401 unauthorized",
        expected_facts=["401", "unauthorized"],
        max_steps=1,
        weights={"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2},
    )
    score = AnswerScorer.score(case, "The answer is 401 unauthorized.")
    assert score == 1.0


def test_tool_scorer_forbidden_penalty():
    case = EvaluationCase(
        id="t2",
        category="direct",
        prompt="What is 2+2?",
        required_tools=[],
        forbidden_tools=["lookup"],
        expected_answer=4,
        expected_facts=[],
        max_steps=1,
        weights={"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2},
    )
    # Using forbidden tool gives 0.0 tool score
    events = [ToolExecutionEvent(tool_name="lookup", arguments="foo", result={}, ok=True, step=1)]
    score = ToolScorer.score(case, events)
    assert score == 0.0


def test_trajectory_scorer():
    case = EvaluationCase(
        id="t3",
        category="calc",
        prompt="calc",
        required_tools=["calculator"],
        forbidden_tools=[],
        expected_answer=10,
        expected_facts=[],
        max_steps=2,
        weights={"answer": 0.5, "tool_selection": 0.3, "trajectory": 0.2},
    )
    assert TrajectoryScorer.score(case, steps_taken=2) == 1.0
    assert TrajectoryScorer.score(case, steps_taken=3) == 0.5
    assert TrajectoryScorer.score(case, steps_taken=5) == 0.0
