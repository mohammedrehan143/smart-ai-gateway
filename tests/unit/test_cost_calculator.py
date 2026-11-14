"""Unit tests for cost calculations."""

from app.core.cost import CostCalculator


def test_cost_calculation_formula():
    calculator = CostCalculator()
    # 10,000 input tokens at $0.15/1M = $0.0015
    # 5,000 output tokens at $0.60/1M = $0.003
    # Total = $0.0045
    res = calculator.calculate(
        model_alias="mock-cheap",
        input_tokens=10000,
        output_tokens=5000,
        is_provider_usage=True,
    )
    assert res.cost_status == "calculated"
    assert res.estimated_cost == 0.0045
    assert res.rate_card_id is not None
    assert res.currency == "USD"


def test_heuristic_cost_status():
    calculator = CostCalculator()
    res = calculator.calculate(
        model_alias="mock-cheap",
        input_tokens=100,
        output_tokens=50,
        is_provider_usage=False,
    )
    assert res.cost_status == "estimated"
    assert res.estimated_cost is not None


def test_unknown_model_cost_unavailable():
    calculator = CostCalculator()
    res = calculator.calculate(
        model_alias="non-existent-model",
        input_tokens=100,
        output_tokens=50,
    )
    assert res.cost_status == "unavailable"
    assert res.estimated_cost is None
