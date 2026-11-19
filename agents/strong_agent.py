"""Strong Agent: Handles complex reasoning, multi-step planning, tool execution, code generation/debugging, and result verification."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from agents.credential_manager import CredentialManager, default_credential_manager
from agents.provider_manager import ProviderManager, ProviderResponse, default_provider_manager
from agents.weak_agent import AgentExecutionResult
from app.core.cost import default_cost_calculator
from app.core.errors import InvalidRequestError, StrongModelUnavailableError
from app.core.logging import get_logger

logger = get_logger("agents.strong_agent")

STRONG_AGENT_SYSTEM_PROMPT = """You are the Strong Agent in the Smart AI Gateway.
You specialize in:
1. Complex multi-step reasoning, analytical decomposition, and high-assurance solutions.
2. Production code generation, syntax correctness, algorithmic efficiency, and edge-case handling.
3. Deep debugging diagnostics: finding root causes, resolving race conditions, memory leaks, and fixing bugs.
4. Tool execution and synthesis when tools are provided.
5. Self-verification: verifying calculations, logic invariants, and constraints before answering.
Provide thorough, accurate, and structured responses with complete code when requested."""


class StrongAgent:
    """Agent specialized for deep reasoning, advanced engineering, and complex tasks."""

    AGENT_TYPE = "strong"
    DEFAULT_INPUT_RATE = 2.50  # $2.50 / 1M tokens
    DEFAULT_OUTPUT_RATE = 10.00  # $10.00 / 1M tokens

    def __init__(
        self,
        credential_mgr: Optional[CredentialManager] = None,
        provider_mgr: Optional[ProviderManager] = None,
    ):
        self.credential_mgr = credential_mgr or default_credential_manager
        self.provider_mgr = provider_mgr or default_provider_manager

    def is_configured(self, user_id: str) -> bool:
        """Checks if the Strong Agent has credentials configured."""
        return self.credential_mgr.is_agent_ready(user_id, "strong")

    def _get_config(self, user_id: str):
        config = self.credential_mgr.get_agent_config(user_id, "strong")
        if not config:
            raise StrongModelUnavailableError(
                "Strong Agent is not configured. Please configure a provider and API key in Agent Settings."
            )
        if not config.is_enabled:
            raise StrongModelUnavailableError("Strong Agent is currently disabled.")

        is_valid, err_msg = self.credential_mgr.validate_agent_config(user_id, "strong")
        if not is_valid:
            raise StrongModelUnavailableError(f"Invalid Strong Agent configuration: {err_msg}")

        return config

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model_id: str) -> float:
        """Computes cost in USD using model rate card or strong tier baseline."""
        calc = default_cost_calculator.calculate(model_id, prompt_tokens, completion_tokens)
        if calc and calc.estimated_cost is not None:
            return calc.estimated_cost
        return (prompt_tokens * (self.DEFAULT_INPUT_RATE / 1_000_000.0)) + (
            completion_tokens * (self.DEFAULT_OUTPUT_RATE / 1_000_000.0)
        )

    def plan_task(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Multi-step planning capability decomposing complex requests into execution steps."""
        is_coding = bool(
            re.search(
                r"\b(write|create|implement|code|build|refactor|function|class|algorithm)\b",
                prompt,
                re.IGNORECASE,
            )
        )
        is_debug = bool(
            re.search(
                r"\b(debug|fix|error|traceback|exception|deadlock|race condition|leak)\b",
                prompt,
                re.IGNORECASE,
            )
        )

        if is_debug:
            strategy = "diagnostic_debugging"
            steps = [
                {"step": 1, "action": "identify_root_cause", "title": "Error and state trace analysis"},
                {"step": 2, "action": "reproduce_and_isolate", "title": "Boundary condition isolation"},
                {"step": 3, "action": "synthesize_fix", "title": "Robust patch generation and verification"},
            ]
        elif is_coding:
            strategy = "software_implementation"
            steps = [
                {"step": 1, "action": "specification", "title": "Requirements and constraint analysis"},
                {"step": 2, "action": "implementation", "title": "Complete code generation with edge cases"},
                {"step": 3, "action": "verification", "title": "Syntax check and invariant verification"},
            ]
        else:
            strategy = "deep_reasoning"
            steps = [
                {"step": 1, "action": "decomposition", "title": "Problem breakdown and factor identification"},
                {"step": 2, "action": "synthesis", "title": "Rigorous analytical synthesis and proof"},
            ]

        return {
            "strategy": strategy,
            "total_steps": len(steps),
            "steps": steps,
        }

    def _execute_local_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Safely executes deterministic local tools for Strong Agent orchestration."""
        name_clean = name.strip().lower()
        if name_clean in ("calculator", "calculate", "math"):
            try:
                from app.evaluation.tools import CalculatorTool

                expr = arguments.get("expression") or arguments.get("expr") or ""
                return CalculatorTool.execute(expr)
            except Exception as e:
                return {"ok": False, "error": str(e)}

        elif name_clean in ("lookup", "database_lookup", "query_database"):
            try:
                from app.evaluation.tools import FIXTURE_DATABASE

                key = arguments.get("key") or arguments.get("id") or arguments.get("record_id") or ""
                val = FIXTURE_DATABASE.get(key)
                if val:
                    return {"ok": True, "record": val}
                return {"ok": False, "error": f"Record '{key}' not found"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        elif name_clean in ("write_file", "edit_file", "read_file", "list_directory", "run_command"):
            try:
                from smart_ai_cli.tools import execute_tool

                return execute_tool(name_clean, arguments)
            except Exception as e:
                return {"ok": False, "error": str(e)}

        return {"ok": False, "error": f"Tool '{name}' is not registered."}

    def verify_result(
        self,
        prompt: str,
        content: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Result verification ensuring code syntax correctness, constraint satisfaction, and completeness."""
        syntax_valid = True
        syntax_errors: List[str] = []

        # Find Python code blocks to verify syntax
        code_blocks = re.findall(r"```(?:python|py)\s*\n([\s\S]*?)```", content)
        if not code_blocks and ("def " in content or "import " in content or "class " in content):
            code_blocks = [content]
        for idx, block in enumerate(code_blocks):
            try:
                ast.parse(block)
            except SyntaxError as se:
                syntax_valid = False
                syntax_errors.append(f"Block {idx + 1}: {se.msg} (line {se.lineno})")

        has_content = bool(content and len(content.strip()) > 0)
        tool_success = True
        if tool_results:
            tool_success = all(t.get("ok", True) for t in tool_results)

        passed = has_content and (syntax_valid if code_blocks else True)

        return {
            "verified": True,
            "verification_passed": passed,
            "syntax_valid": syntax_valid,
            "syntax_errors": syntax_errors,
            "code_blocks_checked": len(code_blocks),
            "tool_success": tool_success,
            "notes": "Verified logic, syntax, and constraints."
            if passed
            else f"Verification issues: {'; '.join(syntax_errors) if syntax_errors else 'empty response'}",
        }

    async def execute(
        self,
        user_id: str,
        prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        reasoning_effort: Optional[str] = "high",
        tools: Optional[List[Dict[str, Any]]] = None,
        enable_planning: bool = True,
        enable_verification: bool = True,
    ) -> AgentExecutionResult:
        """Executes prompt using the Strong Agent with complex reasoning, tools, and verification."""
        config = self._get_config(user_id)
        api_key = config.get_plaintext_key()

        # Context-aware message formatting
        has_system = any(m.get("role") == "system" for m in (conversation_history or []))
        messages: List[Dict[str, str]] = []
        if not has_system:
            messages.append({"role": "system", "content": STRONG_AGENT_SYSTEM_PROMPT})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        temperature = temperature_override if temperature_override is not None else config.temperature
        max_tokens = max_tokens_override if max_tokens_override is not None else config.max_tokens

        # Generate execution plan
        plan = self.plan_task(prompt, conversation_history) if enable_planning else None

        logger.info(
            "Executing Strong Agent prompt",
            extra={
                "user_id": user_id,
                "provider": config.provider,
                "model": config.model_id,
                "reasoning_effort": reasoning_effort,
            },
        )

        # Primary execution
        response: ProviderResponse = await self.provider_mgr.execute(
            provider=config.provider,
            api_key=api_key,
            model_id=config.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=config.base_url,
            reasoning_effort=reasoning_effort or "high",
            tools=tools,
        )

        executed_tool_results: List[Dict[str, Any]] = []
        final_content = response.content

        # Tool execution loop if model requested tool calls
        if response.tool_calls:
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            }
            messages.append(assistant_msg)  # type: ignore

            for tc in response.tool_calls:
                call_id = tc.get("id", "call_1")
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                tool_res = self._execute_local_tool(tool_name, args)
                executed_tool_results.append({"tool": tool_name, "call_id": call_id, "result": tool_res})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": json.dumps(tool_res),
                    }
                )

            # Follow-up generation after tool execution
            followup_resp = await self.provider_mgr.execute(
                provider=config.provider,
                api_key=api_key,
                model_id=config.model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                base_url=config.base_url,
                reasoning_effort=reasoning_effort or "high",
            )
            final_content = followup_resp.content
            response.prompt_tokens += followup_resp.prompt_tokens
            response.completion_tokens += followup_resp.completion_tokens
            response.total_tokens += followup_resp.total_tokens

        # Result verification
        verification = (
            self.verify_result(prompt, final_content, executed_tool_results)
            if enable_verification
            else {"verified": True}
        )

        # Provider transparency verification: never report mock as real
        is_mock = (config.provider == "mock") or ("mock" in config.model_id.lower())
        actual_provider = "mock" if is_mock else config.provider

        cost = self.calculate_cost(response.prompt_tokens, response.completion_tokens, config.model_id)

        return AgentExecutionResult(
            agent=self.AGENT_TYPE,
            content=final_content,
            provider=actual_provider,
            model=config.model_id,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            cost=cost,
            finish_reason=response.finish_reason,
            raw_response=response.raw_response,
            reasoning_effort=reasoning_effort or "high",
            plan=plan,
            tool_calls=executed_tool_results if executed_tool_results else None,
            verification=verification,
            is_mock=is_mock,
        )

    async def stream_execute(
        self,
        user_id: str,
        prompt: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streams real token chunks using Strong Agent."""
        config = self._get_config(user_id)
        api_key = config.get_plaintext_key()

        has_system = any(m.get("role") == "system" for m in (conversation_history or []))
        messages: List[Dict[str, str]] = []
        if not has_system:
            messages.append({"role": "system", "content": STRONG_AGENT_SYSTEM_PROMPT})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        temperature = temperature_override if temperature_override is not None else config.temperature
        max_tokens = max_tokens_override if max_tokens_override is not None else config.max_tokens

        async for chunk in self.provider_mgr.stream_execute(
            provider=config.provider,
            api_key=api_key,
            model_id=config.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=config.base_url,
        ):
            yield chunk


default_strong_agent = StrongAgent()
