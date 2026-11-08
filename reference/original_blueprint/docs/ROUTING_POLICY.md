# Routing Policy

## 1. Objective

Choose the lowest-cost eligible model that is expected to satisfy the request's capability and quality requirements. Routing is an optimization under constraints, not simply "short prompt = cheap model."

## 2. Model catalog

Each configured target should declare:
- provider and model identifier
- enabled/disabled status
- supported input/output modalities
- context window
- tool-calling support
- structured-output support
- configured input/output price per token, with currency and effective date
- timeout and concurrency limits
- quality tier or benchmark evidence
- fallback eligibility

Treat provider model names and prices as configuration that can change.

## 3. MVP rule-based router

Suggested decision order:

1. Filter out disabled or unhealthy targets.
2. Filter out models that cannot satisfy hard requirements (context size, tool calling, output format).
3. If the request explicitly requires a capability, choose only compatible targets.
4. Classify request signals using transparent rules:
   - code present
   - long context
   - multi-step reasoning requested
   - structured output required
   - tool use required
5. Choose the least expensive eligible target in the appropriate capability/quality tier.
6. If no target qualifies, return a clear routing error or use an explicitly configured safe default.
7. Persist reason codes and policy version.

## 4. Example reason codes

- `SHORT_INPUT`
- `CODE_PRESENT`
- `LONG_CONTEXT`
- `TOOL_USE_REQUIRED`
- `STRUCTURED_OUTPUT_REQUIRED`
- `HIGH_REASONING_SIGNAL`
- `CHEAP_TIER_SELECTED`
- `STRONG_TIER_SELECTED`
- `NO_ELIGIBLE_MODEL`

Reason codes should be factual and understandable. Do not present heuristic labels as proof of actual task difficulty.

## 5. Routing policies for benchmark

- `cheap_only`: always use the designated cheap model.
- `strong_only`: always use the designated strong model.
- `default_router`: apply the configured router.

All policies must use the same task set, prompt templates, decoding settings where possible, and evaluation procedure.

## 6. Future evolution

Only after the baseline works, consider:
- calibrated complexity classifier
- historical task-to-model quality estimates
- latency-aware routing
- budget-aware routing
- contextual bandits or learned policies

A learned router must be evaluated offline and guarded against regressions before production use.

## 7. Safety constraints

Routing must never downgrade a request below required capabilities. Do not route based on sensitive personal attributes. Do not infer or store sensitive traits from user prompts for model selection.
