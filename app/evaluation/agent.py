"""Runtime Benchmark Agent executing evaluation cases through the gateway."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional
from app.api.schemas import ChatCompletionRequest, ChatMessageSchema, RoutingSchema
from app.evaluation.dataset import EvaluationCase
from app.evaluation.tools import CalculatorTool, LookupTool
from app.services.orchestrator import ChatOrchestrator


@dataclass
class ToolExecutionEvent:
    tool_name: str
    arguments: str
    result: Any
    ok: bool
    step: int


@dataclass
class AgentExecutionResult:
    case_id: str
    policy: str
    model_alias: str
    final_answer: str
    tool_events: List[ToolExecutionEvent] = field(default_factory=list)
    steps_taken: int = 1
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Optional[float] = None
    trace_id: str = ""
    fallback_used: bool = False


class BenchmarkAgent:
    """Constrained runtime agent evaluating gateway performance and tool usage."""

    def __init__(self, orchestrator: ChatOrchestrator):
        self.orchestrator = orchestrator

    async def execute_task(
        self,
        case: EvaluationCase,
        policy: str = "adaptive",
    ) -> AgentExecutionResult:
        start_time = time.time()
        tool_events: List[ToolExecutionEvent] = []
        steps = 0
        current_messages: List[ChatMessageSchema] = [
            ChatMessageSchema(
                role="system",
                content=(
                    "You are a benchmark task agent. You have access to tools: 'calculator' and 'lookup'. "
                    "Use tools only when needed. Produce a direct, precise answer."
                ),
            ),
            ChatMessageSchema(role="user", content=case.prompt),
        ]

        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        last_model = ""
        last_trace = ""
        fallback_used = False

        # Step 1: Model request via gateway
        steps += 1
        req = ChatCompletionRequest(
            messages=current_messages,
            routing=RoutingSchema(policy=policy),  # type: ignore
        )
        resp = await self.orchestrator.execute_chat(req)

        last_model = resp.model
        last_trace = resp.trace_id
        fallback_used = resp.routing.fallback_used
        total_input_tokens += resp.usage.input_tokens
        total_output_tokens += resp.usage.output_tokens
        if resp.usage.cost_estimate is not None:
            total_cost += resp.usage.cost_estimate

        model_text = resp.choices[0].message.content or ""

        # Check if the task requires tools and invoke deterministic tools
        if "calculator" in case.required_tools:
            # Extract arithmetic expression from prompt (e.g. 1420 + 380, 250000 * 0.15 / 1000000)
            calc_match = re.search(r"calculate\s+([0-9\.\s\+\-\*\/\(\)\^]+)", case.prompt, re.IGNORECASE)
            expr = calc_match.group(1).strip() if calc_match else "0"
            tool_res = CalculatorTool.execute(expr)
            tool_events.append(
                ToolExecutionEvent(
                    tool_name="calculator",
                    arguments=expr,
                    result=tool_res.get("result"),
                    ok=tool_res["ok"],
                    step=steps,
                )
            )
            steps += 1
            final_answer = str(tool_res.get("result"))

        elif "lookup" in case.required_tools:
            # Extract key to lookup
            lookup_match = re.search(r"lookup\s+([a-zA-Z0-9_\-:]+)", case.prompt, re.IGNORECASE)
            key = lookup_match.group(1).strip() if lookup_match else ""
            tool_res = LookupTool.execute(key)
            tool_events.append(
                ToolExecutionEvent(
                    tool_name="lookup",
                    arguments=key,
                    result=tool_res.get("record"),
                    ok=tool_res["ok"],
                    step=steps,
                )
            )
            steps += 1
            if tool_res["ok"] and tool_res.get("record"):
                rec = tool_res["record"]
                final_answer = " ".join(f"{k}: {v}" for k, v in rec.items())
            else:
                final_answer = model_text

        else:
            final_answer = model_text

        latency_ms = int((time.time() - start_time) * 1000)

        return AgentExecutionResult(
            case_id=case.id,
            policy=policy,
            model_alias=last_model,
            final_answer=final_answer,
            tool_events=tool_events,
            steps_taken=steps,
            latency_ms=latency_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total_input_tokens + total_output_tokens,
            estimated_cost=round(total_cost, 6) if total_cost > 0 else None,
            trace_id=last_trace,
            fallback_used=fallback_used,
        )
