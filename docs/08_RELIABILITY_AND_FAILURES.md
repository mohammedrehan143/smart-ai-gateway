# 08. Reliability and Failure Handling

## 1. Timeouts and deadlines

Use explicit connect, read, and total request deadlines. The total gateway deadline must include provider attempts, backoff, and fallback. Do not start another attempt if the remaining deadline is insufficient to produce a useful response.

## 2. Retry policy

Retry only transient classes: network errors, timeouts, rate limits, and selected upstream 5xx responses. Use a small maximum attempt count, exponential backoff with jitter, and respect `Retry-After` when valid. Never retry deterministic client errors. Keep limits configurable and record every attempt.

## 3. Fallback policy

Fallback is a new provider attempt under the same logical trace. It must use an allowlisted model, be permitted by the routing policy, and fit within the remaining deadline. The final response must identify whether fallback was used and which configured alias served the request.

## 4. Circuit breaker (later MVP hardening)

Add only after retry/fallback works and a measurable provider instability problem exists. Model states as closed, open, and half-open. Use bounded probe requests, configuration per provider/model, and clear metrics. Do not create a circuit breaker that permanently blocks recovery.

## 5. Partial failures

- Provider failure: return normalized 502/503/504 according to cause and availability.
- Trace persistence failure: preserve the successful user response when configured to do so, emit a high-severity telemetry-degraded event, and make the lost/failed persistence observable. A strict audit deployment may instead fail closed; document the selected mode.
- Cache failure: bypass cache and continue; cache must not be a single point of failure.
- Cost rate missing: return completion with `cost_status=unavailable`; never return a false zero.
- Provider usage missing: mark token counts unavailable or estimated, with a provenance flag.

## 6. Idempotency and side effects

A chat generation request is usually retryable at the HTTP layer but can incur duplicate cost. If an idempotency key is supported, persist the key, request hash, status, and result reference with a bounded TTL. Do not apply this mechanism to arbitrary side-effecting tools without a separate execution-safety contract.

## 7. Failure testing

Use mocked upstream responses to test every retryable/non-retryable category, deadline exhaustion, fallback failure, cache outage, and trace-store outage. Add a controlled provider outage drill before public demonstration.
