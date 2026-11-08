# 06. Deterministic Model Routing Policy

## 1. Purpose

Select a model tier that balances quality, latency, reliability, and cost. The initial router must be deterministic, explainable, fast, and independently testable.

## 2. Configured tiers

- **Cheap tier:** lower-cost, lower-latency configured model suitable for routine requests.
- **Strong tier:** higher-capability configured model reserved for requests likely to need stronger reasoning or more robust instruction following.

Actual provider/model identifiers live in deployment configuration, not source code. The system must not assume a model is cheap or strong forever; tier assignment and rate-card version are configurable.

## 3. Initial routing signals

Extract features without an additional LLM call:
- input character/token estimate or message length bucket;
- code block or code-like syntax present;
- explicit multi-step language or multiple requested deliverables;
- structured reasoning indicators (comparison, debugging, planning, constraints);
- configured context-size requirement;
- policy preference supplied by a trusted caller, if enabled.

Do not use hidden personal profiling or arbitrary keyword lists as the only signal. Make thresholds configurable and unit-tested. Avoid sending the full prompt to a separate classifier in the first release.

## 4. Example decision logic

1. If request exceeds the cheap model's configured context/output capability, choose strong or reject with a clear error if no model qualifies.
2. If caller explicitly selects `always_cheap`, select cheap unless the request cannot be served within its technical limits.
3. If caller selects `always_strong`, select strong.
4. Under `adaptive`, choose strong when one or more high-complexity rules trigger (e.g., code/debugging, multi-step task, long context beyond configured threshold); otherwise choose cheap.
5. If the selected model fails and fallback is permitted, try the configured alternate only if enough request deadline remains.

The exact thresholds must be stored in configuration and recorded as `policy_version`. Do not present example heuristics as empirically optimal until benchmarked.

## 5. Decision output

Every routing call returns a structured object containing:
- `policy_name` and `policy_version`;
- `selected_provider` and `selected_model_alias`;
- `selected_tier`;
- extracted feature summary (safe, non-sensitive values only);
- human-readable reason code/message;
- `fallback_model_alias` or no fallback;
- timestamp and request/trace ID.

## 6. Fallback rules

Fallback must be explicit and bounded. Never fallback to an unapproved model. Do not retry/fallback on invalid client input, authentication failure, unsupported model parameters, or other non-retryable 4xx responses. For a quality-critical request, a policy may disable downgrade fallback; this must be documented and visible in the response/trace.

## 7. Measurement and tuning

Tune policy thresholds only against a versioned benchmark. Compare:
- always-cheap: all eligible tasks sent to cheap tier;
- always-strong: all eligible tasks sent to strong tier;
- adaptive: deterministic policy under test.

Report quality gap in percentage points, cost reduction relative to always-strong, latency distributions, fallback rate, and per-category scores. Do not optimize solely for cost if quality drops beyond the accepted tolerance.

## 8. Future experiment: learned router

A learned or LLM-assisted classifier may be evaluated later as a separate policy. It must be compared against the deterministic baseline, log its confidence/rationale, have a safe fallback for uncertain predictions, and never silently replace the baseline.
