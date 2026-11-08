# 09. LLMOps and Observability

## 1. Goals

Answer, for every gateway request: what was requested (at a safe metadata level), where it was routed, which provider/model responded, how long it took, how many tokens were used, what the cost estimate was, whether retries/fallback/cache occurred, and whether it succeeded.

## 2. Trace model

One logical request has one trace ID and may have multiple provider attempts. Each attempt is a child record linked to the logical request. The trace should record gateway version, API contract version, routing policy/version, model alias, provider, tier, cache outcome, status, error category, start/end time, and latency.

## 3. Core metrics

| Metric | Definition |
|---|---|
| Request count | Number of accepted gateway requests by status/policy/model alias |
| Success rate | Successful logical requests / accepted requests |
| Provider error rate | Failed provider attempts / provider attempts |
| Latency | Gateway total and provider-attempt latency; report p50/p95/p99 when sample size supports it |
| Tokens | Input/output/total tokens, with source/estimation provenance |
| Cost estimate | Token usage multiplied by effective rate-card value |
| Fallback rate | Requests served by fallback / eligible requests |
| Retry rate | Requests with more than one provider attempt / requests with provider attempts |
| Cache hit rate | Eligible requests served from cache / eligible requests |
| Routing distribution | Requests by selected tier/model alias and reason code |
| Evaluation pass rate | Passed evaluation cases / evaluated cases |

## 4. Cost accounting

Use a versioned rate card with separate input/output rates per model, a declared currency, per-token or per-million-token units, and an effective date range. Normalize to a common cost unit internally. Store the rate-card ID/version used for each calculation. If provider billing/usage semantics differ, document the assumption. Label this as an estimate unless reconciled to provider invoices.

## 5. Structured logs

Use JSON logs with timestamp, level, service, environment, version, trace ID, request ID, event name, and safe structured fields. Redact secrets, auth headers, and configured personal/sensitive text. Prefer counts, hashes, categories, and IDs over raw prompts.

## 6. Trace retention

Set a retention period based on the environment and purpose. Separate operational metadata retention from optional prompt/response content retention. Default to not storing full prompt/response text in persistent telemetry; if debugging content capture is enabled, make it opt-in, access-controlled, redacted, and short-lived.

## 7. Minimum demonstration views

The MVP can produce CSV/JSON/Markdown reports with:
- request volume and success rate;
- model/tier routing distribution;
- cost estimate by model/policy;
- latency distribution;
- retries/fallback/cache statistics;
- evaluation policy comparison.

A visual dashboard is optional and should be built only after the telemetry model is stable.
