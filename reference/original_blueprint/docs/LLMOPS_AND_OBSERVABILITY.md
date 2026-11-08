# LLMOps and Observability

## 1. What to observe

### Request-level fields
- request ID and timestamp
- client/application identifier (non-secret)
- routing policy and version
- selected provider/model
- route reason codes
- success/error status
- end-to-end latency
- cache hit/miss
- token usage and usage source
- estimated cost, currency, pricing version

### Attempt-level fields
- attempt ID and sequence
- provider/model
- start/end timestamps
- latency
- normalized status/error category
- retry/fallback relationship
- provider request ID when safe

## 2. Metrics

- request count and success rate
- error rate by provider/model
- p50/p95 latency
- input/output tokens
- estimated spend by provider/model/day
- average cost per successful request
- cache hit ratio
- retry and fallback rate
- benchmark pass rate and score distribution

## 3. Cost calculation

When provider usage is available:

`cost = (input_tokens / 1_000_000 * input_price_per_million) + (output_tokens / 1_000_000 * output_price_per_million)`

Use the price configuration effective for the request timestamp. Account for currency and any provider-specific billing units. Mark this as estimated if it does not exactly match an invoice.

If token usage is unavailable, store cost as unknown or a separately labeled token estimate. Never silently report zero.

## 4. Logging and privacy

- Prefer metadata over storing full prompts/responses.
- Make content capture opt-in and define retention.
- Redact API keys, authorization headers, and secrets.
- Limit access to request traces.
- Do not put raw user prompts into metric labels.
- Avoid high-cardinality metric dimensions such as request IDs.

## 5. Dashboard views

1. Overview: volume, success, latency, cost.
2. Model comparison: provider/model usage and error rates.
3. Routing: route distribution and reasons.
4. Reliability: retries, fallbacks, timeouts.
5. Request explorer: sanitized request and attempt details.
6. Evaluation: policy comparison and benchmark runs.

## 6. Alert candidates

- provider error rate exceeds configured threshold
- p95 latency exceeds service objective
- fallback rate suddenly rises
- budget threshold is reached
- telemetry write failures persist

Set thresholds from observed baseline data rather than inventing universal values.
