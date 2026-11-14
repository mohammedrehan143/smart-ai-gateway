"""Unit tests for deterministic benchmark tools (calculator and lookup)."""

from app.evaluation.tools import CalculatorTool, LookupTool


def test_calculator_basic_arithmetic():
    res = CalculatorTool.execute("25 + 75")
    assert res["ok"] is True
    assert res["result"] == 100

    res_mult = CalculatorTool.execute("12 * 8 - 6")
    assert res_mult["ok"] is True
    assert res_mult["result"] == 90


def test_calculator_division_by_zero():
    res = CalculatorTool.execute("100 / 0")
    assert res["ok"] is False
    assert "Division by zero" in res["error"]


def test_calculator_safety_no_eval():
    # Attempting code execution or attribute access must fail
    res = CalculatorTool.execute("__import__('os').system('echo pwned')")
    assert res["ok"] is False
    assert res["result"] is None


def test_lookup_existing_record():
    res = LookupTool.execute("account:101")
    assert res["ok"] is True
    assert res["record"] is not None
    assert res["record"]["name"] == "Acme Corp"


def test_lookup_missing_record():
    res = LookupTool.execute("account:99999")
    assert res["ok"] is False
    assert "not found" in res["error"]
