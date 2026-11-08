# Calculator Tool Contract

## Purpose

Provide deterministic arithmetic for benchmark cases where calculation is required.

## Input contract

Accept a constrained expression or structured operands/operators. Validate numeric values and allowed operators. Reject arbitrary code, function calls, attribute access, imports, file operations, and unbounded expressions.

## Output contract

Return structured output with `ok`, numeric `result`, and a safe error category when invalid. Preserve numeric precision according to the task's specified tolerance.

## Evaluation events

Record tool name, validated input representation, status, and result fingerprint/value needed by the scorer. Do not record unrelated prompt content.

## Security

Never use Python `eval` on raw model-generated strings. Parse a restricted grammar or accept structured operations and calculate with safe arithmetic functions. Apply limits to expression length and numeric magnitude.
