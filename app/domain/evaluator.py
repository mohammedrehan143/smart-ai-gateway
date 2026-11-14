"""Inline response evaluation pipeline with quality gating and escalation signals."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional
from app.domain.entities import ChatMessage


@dataclass
class InlineEvaluationResult:
    passed: bool
    overall_score: float  # 0.0 to 1.0
    relevance_score: float
    instruction_adherence_score: float
    completeness_score: float
    code_correctness_score: float
    format_validity_score: float
    feedback: List[str] = field(default_factory=list)
    should_escalate: bool = False
    escalation_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overall_score": round(self.overall_score, 4),
            "relevance": round(self.relevance_score, 2),
            "instruction_adherence": round(self.instruction_adherence_score, 2),
            "completeness": round(self.completeness_score, 2),
            "code_correctness": round(self.code_correctness_score, 2),
            "format_validity": round(self.format_validity_score, 2),
            "should_escalate": self.should_escalate,
            "escalation_reason": self.escalation_reason,
            "feedback": self.feedback,
        }


class ResponseQualityEvaluator:
    """Evaluates generated LLM responses across relevance, syntax, format, and completeness."""

    @classmethod
    def evaluate(
        cls,
        prompt_messages: List[ChatMessage],
        response_text: str,
        expected_format: str = "markdown",  # "markdown", "json", "code"
        quality_threshold: float = 0.70,
    ) -> InlineEvaluationResult:
        feedback: List[str] = []
        user_prompt = " ".join(m.content for m in prompt_messages if m.role == "user")
        lower_prompt = user_prompt.lower()
        lower_resp = response_text.lower()

        # 1. Completeness Evaluation
        if not response_text or len(response_text.strip()) == 0:
            return InlineEvaluationResult(
                passed=False,
                overall_score=0.0,
                relevance_score=0.0,
                instruction_adherence_score=0.0,
                completeness_score=0.0,
                code_correctness_score=0.0,
                format_validity_score=0.0,
                feedback=["Response is completely empty."],
                should_escalate=True,
                escalation_reason="Empty response generated.",
            )

        completeness_score = 1.0
        if len(response_text.split()) < 3 and len(user_prompt.split()) > 10:
            completeness_score = 0.4
            feedback.append("Response is suspiciously short for prompt depth.")

        # 2. Relevance Evaluation
        prompt_words = set(re.findall(r"\w{4,}", lower_prompt))
        resp_words = set(re.findall(r"\w{4,}", lower_resp))
        overlap = prompt_words.intersection(resp_words)
        relevance_score = min(1.0, len(overlap) / max(1, min(5, len(prompt_words)))) if prompt_words else 0.9

        # 3. Format Validity (JSON enforcement)
        format_validity_score = 1.0
        if expected_format == "json" or "json" in lower_prompt:
            # Check for JSON block or raw JSON
            json_str = response_text.strip()
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if match:
                json_str = match.group(1).strip()
            try:
                json.loads(json_str)
                format_validity_score = 1.0
            except json.JSONDecodeError:
                format_validity_score = 0.2
                feedback.append("Failed JSON parse validation.")

        # 4. Code Correctness (AST Syntax Validation)
        code_correctness_score = 1.0
        code_blocks = re.findall(r"```(?:python)?\s*\n([\s\S]*?)\n```", response_text)
        if code_blocks and ("python" in lower_prompt or "def " in response_text or "function" in lower_prompt):
            for block in code_blocks:
                try:
                    ast.parse(block)
                except SyntaxError as syn_err:
                    code_correctness_score = 0.3
                    feedback.append(f"Python code block failed AST syntax check: {syn_err.msg}")

        # 5. Instruction Adherence
        adherence_score = 1.0
        if "reverse" in lower_prompt and "string" in lower_prompt:
            if not any(k in lower_resp for k in ["reverse", "[::-1]", "reversed", "for"]):
                adherence_score = 0.5
                feedback.append("String reversal logic not clearly addressed.")

        # Overall weighted composite score
        overall_score = (
            (relevance_score * 0.25)
            + (adherence_score * 0.25)
            + (completeness_score * 0.20)
            + (code_correctness_score * 0.15)
            + (format_validity_score * 0.15)
        )

        passed = (
            overall_score >= quality_threshold
            and code_correctness_score >= 0.5
            and format_validity_score >= 0.5
        )

        should_escalate = not passed
        escalation_reason = None
        if should_escalate:
            escalation_reason = "; ".join(feedback) if feedback else f"Score {overall_score:.2f} below threshold {quality_threshold:.2f}"

        return InlineEvaluationResult(
            passed=passed,
            overall_score=overall_score,
            relevance_score=relevance_score,
            instruction_adherence_score=adherence_score,
            completeness_score=completeness_score,
            code_correctness_score=code_correctness_score,
            format_validity_score=format_validity_score,
            feedback=feedback,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
