"""Integration tests for all smartai CLI commands with mocked client responses."""

import json
from pathlib import Path
from typer.testing import CliRunner
from smart_ai_cli.client import GatewayClient
from smart_ai_cli.main import app
from smart_ai_cli.schemas import (
    BenchmarkRunResponse,
    BenchmarkSummaryItem,
    CostAnalyticsResponse,
    ModelCostSummary,
    ModelInfo,
    ModelsResponse,
    PricingInfo,
    ProviderCostSummary,
    RoutingDecisionRecord,
    RoutingDecisionsResponse,
    UsageAnalyticsResponse,
)

runner = CliRunner(env={"COLUMNS": "200"})


def test_cli_models_command(monkeypatch):
    mock_models = ModelsResponse(
        object="list",
        data=[
            ModelInfo(
                id="mock-cheap",
                alias="mock-cheap",
                provider="mock",
                upstream_model_id="mock-cheap-v1",
                tier="cheap",
                context_window=16384,
                max_output_tokens=4096,
                pricing=PricingInfo(input_rate_per_million=0.15, output_rate_per_million=0.60),
            ),
            ModelInfo(
                id="mock-strong",
                alias="mock-strong",
                provider="mock",
                upstream_model_id="mock-strong-v1",
                tier="strong",
                context_window=128000,
                max_output_tokens=8192,
                pricing=PricingInfo(input_rate_per_million=2.50, output_rate_per_million=10.00),
            ),
        ],
        total=2,
    )
    monkeypatch.setattr(GatewayClient, "list_models", lambda self: mock_models)

    # Table format
    res = runner.invoke(app, ["models"])
    assert res.exit_code == 0
    assert "mock-cheap" in res.stdout
    assert "mock-strong" in res.stdout
    assert "$0.15" in res.stdout

    # JSON format
    json_res = runner.invoke(app, ["models", "--json"])
    assert json_res.exit_code == 0
    parsed = json.loads(json_res.stdout)
    assert len(parsed) == 2


def test_cli_usage_command(monkeypatch):
    mock_usage = UsageAnalyticsResponse(
        total_requests=42,
        total_input_tokens=1500,
        total_output_tokens=800,
        total_tokens=2300,
        avg_latency_ms=120.5,
        cache_hits=6,
        cache_hit_rate=0.1428,
        fallback_count=1,
        policy_breakdown={"adaptive": 35, "always_cheap": 7},
        model_breakdown={"mock-cheap": 30, "mock-strong": 12},
        recent_requests=[
            {
                "id": "req_1",
                "trace_id": "tr_test_trace_12345",
                "policy": "adaptive",
                "model": "mock-cheap",
                "status": "success",
                "latency_ms": 95,
                "cached": False,
            }
        ],
    )
    monkeypatch.setattr(GatewayClient, "get_usage", lambda self, since=None, limit=50: mock_usage)

    res = runner.invoke(app, ["usage"])
    assert res.exit_code == 0
    assert "42" in res.stdout
    assert "2,300" in res.stdout
    assert "120.5ms" in res.stdout
    assert "adaptive" in res.stdout


def test_cli_cost_command(monkeypatch):
    mock_cost = CostAnalyticsResponse(
        total_spend=0.012540,
        calculated_spend=0.012000,
        estimated_spend=0.000540,
        currency="USD",
        model_breakdown={
            "mock-cheap": ModelCostSummary(spend=0.004500, tokens=1200, requests=25),
            "mock-strong": ModelCostSummary(spend=0.008040, tokens=1100, requests=17),
        },
        provider_breakdown={
            "mock": ProviderCostSummary(spend=0.012540, requests=42),
        },
    )
    monkeypatch.setattr(GatewayClient, "get_cost", lambda self, since=None: mock_cost)

    res = runner.invoke(app, ["cost"])
    assert res.exit_code == 0
    assert "$0.012540 USD" in res.stdout
    assert "mock-cheap" in res.stdout
    assert "mock-strong" in res.stdout


def test_cli_route_command(monkeypatch):
    mock_routing = RoutingDecisionsResponse(
        decisions=[
            RoutingDecisionRecord(
                trace_id="tr_route_test_001",
                policy="adaptive",
                selected_provider="mock",
                selected_model="mock-strong",
                tier="strong",
                reason="Request contains complex Python AST parsing code",
                features={"has_code": True, "has_debug": False, "is_multistep": False},
                latency_ms=110,
                total_tokens=180,
                cost_estimate=0.00045,
            )
        ],
        count=1,
    )
    monkeypatch.setattr(GatewayClient, "get_routing_decisions", lambda self, limit=20, trace_id=None: mock_routing)

    res = runner.invoke(app, ["route"])
    assert res.exit_code == 0
    assert "tr_route_test_00" in res.stdout
    assert "strong" in res.stdout
    assert "code" in res.stdout


def test_cli_benchmark_command(monkeypatch, tmp_path: Path):
    mock_bench = BenchmarkRunResponse(
        dataset_version="1.0.0",
        cases_evaluated=5,
        summaries={
            "adaptive": BenchmarkSummaryItem(
                policy="adaptive",
                total_cases=5,
                passed_cases=5,
                pass_rate_pct=100.0,
                avg_score=0.98,
                total_cost=0.000450,
                avg_cost_per_task=0.000090,
                avg_latency_ms=35.0,
                fallback_count=0,
            ),
            "always_strong": BenchmarkSummaryItem(
                policy="always_strong",
                total_cases=5,
                passed_cases=5,
                pass_rate_pct=100.0,
                avg_score=0.99,
                total_cost=0.001200,
                avg_cost_per_task=0.000240,
                avg_latency_ms=85.0,
                fallback_count=0,
            ),
        },
        adaptive_savings_vs_strong_pct=62.5,
    )
    monkeypatch.setattr(GatewayClient, "run_benchmark", lambda self, policies=None, sample_size=None: mock_bench)

    export_file = tmp_path / "bench.json"
    res = runner.invoke(app, ["benchmark", "--samples", "5", "--export", str(export_file)])
    assert res.exit_code == 0
    assert "62.5%" in res.stdout
    assert export_file.exists()


def test_cli_ask_command(monkeypatch):
    mock_resp = {
        "id": "req_ask_test_001",
        "model": "mock-cheap",
        "choices": [{"message": {"content": "This is an automated test reply."}}],
        "usage": {"total_tokens": 12, "cost_estimate": 0.000005},
        "routing": {"tier": "cheap", "policy": "adaptive"},
        "latency_ms": 15,
        "cached": False,
        "trace_id": "tr_ask_test_trace",
    }
    monkeypatch.setattr(GatewayClient, "chat", lambda self, messages, policy="adaptive", temperature=0.2: mock_resp)

    res = runner.invoke(app, ["ask", "What is testing?", "--no-stream"])
    assert res.exit_code == 0
    assert "This is an automated test reply." in res.stdout
    assert "mock-cheap" in res.stdout


def test_cli_chat_command_streaming(monkeypatch):
    def mock_stream(self, conversation, policy=None, temperature=None):
        yield {"choices": [{"delta": {"content": "Streamed chat answer."}}]}
        yield {
            "choices": [{"delta": {}}],
            "model": "mock-cheap",
            "routing": {"tier": "cheap", "policy": "adaptive"},
            "usage": {"total_tokens": 14, "cost_estimate": 0.000007},
            "latency_ms": 18,
        }

    monkeypatch.setattr(GatewayClient, "stream_chat", mock_stream)

    res = runner.invoke(app, ["chat"], input="Explain recursion\n/exit\n")
    assert res.exit_code == 0
    assert "Streamed chat answer." in res.stdout
    assert "mock-cheap" in res.stdout
    assert "Assistant:" not in res.stdout
    assert "You:" not in res.stdout
    assert "❯" in res.stdout


def test_cli_chat_command_non_streaming(monkeypatch):
    mock_resp = {
        "id": "req_chat_test_002",
        "model": "mock-strong",
        "choices": [{"message": {"content": "Non-streamed direct answer."}}],
        "usage": {"total_tokens": 20, "cost_estimate": 0.000050},
        "routing": {"tier": "strong", "policy": "always_strong"},
        "latency_ms": 45,
        "cached": False,
        "trace_id": "tr_chat_test_002",
    }
    monkeypatch.setattr(GatewayClient, "chat", lambda self, messages, policy="adaptive", temperature=0.2: mock_resp)

    res = runner.invoke(app, ["chat", "--no-stream"], input="Hello world\n/exit\n")
    assert res.exit_code == 0
    assert "Non-streamed direct answer." in res.stdout
    assert "mock-strong" in res.stdout
    assert "Assistant:" not in res.stdout
    assert "You:" not in res.stdout
    assert "❯" in res.stdout
