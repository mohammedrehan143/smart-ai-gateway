# 21. Acceptance Criteria / Definition of Done

## Gateway
- [ ] `POST /v1/chat` validates inputs and returns the documented normalized response.
- [ ] Unsupported model aliases cannot be supplied by clients.
- [ ] Every accepted request receives a trace ID.
- [ ] Provider adapter is isolated behind a stable interface.
- [ ] Mocked-provider tests run without internet or API credentials.

## Routing
- [ ] Router is deterministic and implemented as ordinary application logic.
- [ ] It supports always-cheap, always-strong, and adaptive modes.
- [ ] Each decision records selected tier/model alias, policy version, and reason.
- [ ] Routing tests cover easy, complex, code/debug, and capability-boundary examples.

## Reliability
- [ ] Retry rules distinguish transient from non-retryable errors.
- [ ] Retry count and total deadline are bounded.
- [ ] Fallback uses only allowlisted models and is visible in traces/responses.
- [ ] Cache outage does not block successful provider requests.

## LLMOps
- [ ] Trace records include model/provider, route, status, latency, and attempts.
- [ ] Usage records distinguish provider-reported, estimated, and missing data.
- [ ] Cost estimate uses versioned rates and is never falsely reported as zero.
- [ ] Logs redact credentials and do not store full prompt content by default.

## Agent evaluation
- [ ] A runtime benchmark agent uses the gateway and approved deterministic tools.
- [ ] Versioned task set contains 20-50 cases.
- [ ] Scorer evaluates answer, tool selection/use, and steps/trajectory.
- [ ] The same task set is run under all three policies.
- [ ] Report includes pass rate, cost, latency, fallback/retry, and category results.
- [ ] Benchmark limitations and repeatability controls are documented.

## Delivery
- [ ] Docker build and health checks work.
- [ ] CI runs formatting/lint, type checks, mocked tests, security/secret checks, and image build.
- [ ] Deployment and rollback instructions are documented.
- [ ] README includes setup, API examples, architecture, benchmark instructions, and actual measured results.
- [ ] Resume metrics are derived from a saved benchmark report, never estimated in advance.
