# 17. Operations Runbook

## Symptom: high provider latency

1. Compare gateway latency with provider-attempt latency.
2. Group by provider/model alias and status.
3. Check retries and queue/concurrency settings.
4. Verify provider status/rate limiting independently.
5. Reduce concurrency or temporarily disable an unstable model if required.

## Symptom: increase in 429 responses

1. Confirm rate-limit error category and `Retry-After` handling.
2. Check request burst and evaluation concurrency.
3. Reduce benchmark concurrency and apply gateway rate limits.
4. Use approved fallback only if the routing policy permits it.
5. Do not retry indefinitely.

## Symptom: cost unexpectedly increases

1. Inspect request volume, token counts, output lengths, and model distribution.
2. Check whether fallback shifted traffic to the strong tier.
3. Verify the active rate-card version and effective dates.
4. Inspect cache hit rate and repeated request patterns.
5. Confirm there are no unauthorized clients or leaked keys.

## Symptom: evaluation pass rate drops

1. Confirm dataset, prompt, scorer, policy, and model versions match the comparison.
2. Inspect per-case score changes, not only aggregate score.
3. Group misses by task category and selected model tier.
4. Determine whether failures come from routing, model quality, tool execution, provider issues, or scorer defects.
5. Change one policy variable at a time and rerun.

## Symptom: traces are missing

1. Check database readiness and migration state.
2. Inspect telemetry persistence errors.
3. Determine whether the configured service mode is fail-open or fail-closed for trace storage.
4. Verify the application is not dropping asynchronous writes during shutdown.
5. Restore persistence and mark the affected time window as incomplete; do not fabricate missing metrics.

## Incident record minimum

Record start/end time, impact, affected provider/model, error category, mitigation, recovery, traces/run IDs, and follow-up action. Never paste credentials or raw sensitive prompts into the incident report.
