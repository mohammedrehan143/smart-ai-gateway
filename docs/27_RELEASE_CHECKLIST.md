# 27. Release Readiness Checklist

Use this checklist before creating a tagged version or publishing a public demo.

## Product and API
- [ ] README and API examples match the implemented contract.
- [ ] Public API version and error responses are documented.
- [ ] Unsupported model IDs and parameters are rejected safely.
- [ ] Health endpoints return correct status without leaking configuration.

## Engineering quality
- [ ] Formatting, lint, type checks, and all required tests pass.
- [ ] Provider adapter contract tests cover success and failure cases.
- [ ] Database migrations apply cleanly to a fresh database.
- [ ] Docker image builds and starts from documented instructions.
- [ ] No undocumented breaking API or data-model changes exist.

## Security and privacy
- [ ] No `.env`, token, API key, or private test data is committed.
- [ ] Secret scanning and dependency checks are clean or have reviewed exceptions.
- [ ] Deployed access requires authentication.
- [ ] Request size, output limits, and rate limits are configured.
- [ ] Prompt/response content retention is disabled unless explicitly justified.
- [ ] Logs and error responses do not expose credentials or sensitive payloads.

## Reliability and operations
- [ ] Timeout, retry, fallback, and deadline behaviour have been tested.
- [ ] Cache and telemetry degradation behaviour is documented.
- [ ] Spend alerts and provider quotas are configured before live evaluation.
- [ ] Deployment and rollback steps have been rehearsed.
- [ ] Operator runbook includes the known failure symptoms.

## Evaluation integrity
- [ ] Dataset, prompt, scorer, routing policy, model config, and rate card are versioned.
- [ ] All three policies ran against the same task set and comparable settings.
- [ ] Per-case results and traces are saved with the aggregate report.
- [ ] Missing token/cost data is marked unavailable, not silently set to zero.
- [ ] Cost and quality claims match the saved benchmark report.
- [ ] Small-sample limitations and provider variability are disclosed.

## Public presentation
- [ ] Architecture diagram reflects the implementation, not only the intended design.
- [ ] Demo uses non-sensitive prompts and safe credentials.
- [ ] README explains why the router is deterministic and how the benchmark validates it.
- [ ] Resume metrics are actual measured values, not projected targets.
