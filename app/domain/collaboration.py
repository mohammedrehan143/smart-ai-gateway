"""Multi-Model Collaboration Strategies execution engine."""

from __future__ import annotations

import time
from typing import List, Optional, Tuple
from app.core.cost import default_cost_calculator
from app.core.logging import get_logger
from app.domain.agentic_planner import AgenticPlan, ExecutionStep
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion
from app.providers.base import BaseProviderAdapter

logger = get_logger("collaboration")


class CollaborationExecutionEngine:
    """Executes multi-model agentic collaboration plans (Peer Review, Code Verification, Consensus)."""

    @classmethod
    async def execute_plan(
        cls,
        plan: AgenticPlan,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        adapter: BaseProviderAdapter,
        timeout_seconds: float = 30.0,
    ) -> Tuple[NormalizedCompletion, List[ExecutionStep]]:
        executed_steps: List[ExecutionStep] = []
        current_content = ""
        last_completion: Optional[NormalizedCompletion] = None
        total_in_tokens = 0
        total_out_tokens = 0

        for step in plan.steps:
            step_start = time.time()
            step.status = "running"

            try:
                if step.action == "generate":
                    comp = await adapter.generate(
                        messages=messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = comp.content
                    last_completion = comp

                elif step.action == "review":
                    # Peer Review: Audits primary response
                    review_messages = list(messages) + [
                        ChatMessage(role="assistant", content=current_content),
                        ChatMessage(
                            role="user",
                            content="Please review the assistant's previous response for factual accuracy, completeness, and clarity. Provide a polished, high-quality final response.",
                        ),
                    ]
                    comp = await adapter.generate(
                        messages=review_messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = comp.content
                    last_completion = comp

                elif step.action == "verify_code":
                    # Code Verification: Audits syntax, edge cases, tests
                    verify_messages = list(messages) + [
                        ChatMessage(role="assistant", content=current_content),
                        ChatMessage(
                            role="user",
                            content="Verify the implementation above: check for edge cases, off-by-one errors, and syntax validity. Provide the clean, verified code.",
                        ),
                    ]
                    comp = await adapter.generate(
                        messages=verify_messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = comp.content
                    last_completion = comp

                elif step.action == "critique":
                    critique_messages = list(messages) + [
                        ChatMessage(role="assistant", content=current_content),
                        ChatMessage(
                            role="user",
                            content="Identify any weaknesses, trade-offs, or omissions in the solution above.",
                        ),
                    ]
                    comp = await adapter.generate(
                        messages=critique_messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = f"{current_content}\n\nCritique:\n{comp.content}"
                    last_completion = comp

                elif step.action == "synthesize":
                    synth_messages = [
                        ChatMessage(
                            role="user",
                            content=f"Synthesize the following comprehensive analysis into a definitive, unified answer:\n{current_content}",
                        )
                    ]
                    comp = await adapter.generate(
                        messages=synth_messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = comp.content
                    last_completion = comp

                else:
                    # Fallback default generation
                    comp = await adapter.generate(
                        messages=messages,
                        parameters=parameters,
                        model_alias=step.assigned_model,
                        timeout_seconds=min(12.0, timeout_seconds),
                    )
                    current_content = comp.content
                    last_completion = comp

                # Step telemetry calculation
                step_end = time.time()
                step.status = "success"
                step.latency_ms = int((step_end - step_start) * 1000)
                step.output_text = current_content[:150] + "..." if len(current_content) > 150 else current_content

                if comp:
                    total_in_tokens += comp.input_tokens
                    total_out_tokens += comp.output_tokens
                    cost_info = default_cost_calculator.calculate(
                        model_alias=step.assigned_model,
                        input_tokens=comp.input_tokens,
                        output_tokens=comp.output_tokens,
                    )
                    step.estimated_cost = cost_info.estimated_cost or 0.0

            except Exception as exc:
                step.status = "failure"
                step.error_message = str(exc)
                step.latency_ms = int((time.time() - step_start) * 1000)
                logger.warning(f"Collaboration step {step.step_number} ({step.action}) failed: {exc}")
                # If a secondary review fails, we preserve primary output!
                if current_content and last_completion:
                    break
                else:
                    raise exc
            finally:
                executed_steps.append(step)

        # Build composite normalized completion representing full collaborative execution
        final_completion = NormalizedCompletion(
            content=current_content,
            finish_reason=last_completion.finish_reason if last_completion else "stop",
            provider=last_completion.provider if last_completion else "mock",
            model_alias=last_completion.model_alias if last_completion else plan.steps[-1].assigned_model,
            provider_request_id=last_completion.provider_request_id if last_completion else None,
            input_tokens=total_in_tokens,
            output_tokens=total_out_tokens,
            total_tokens=total_in_tokens + total_out_tokens,
            raw_usage_available=True,
            tool_calls=last_completion.tool_calls if last_completion else None,
        )

        return final_completion, executed_steps
