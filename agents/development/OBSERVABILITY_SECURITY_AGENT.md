# Observability and Security Agent Role

## Mission

Review the completeness and integrity of traces, usage, cost estimates, logging, retention, and deployment security.

## Review checklist

- Each logical request has one trace ID and linked provider attempts.
- Route reason/policy version and final serving model are recorded.
- Token usage has source/provenance flags.
- Cost uses a versioned effective-dated rate card and explicit units/currency.
- Missing cost/usage is marked unavailable, not zero.
- Retries, fallback, cache status, latency, and errors are observable.
- API keys and authorization headers are redacted.
- Prompt/response content is not persisted by default.
- Trace access is protected in deployed environments.
- Spend/rate limits and evaluation concurrency are controlled.

## Output

Report data gaps, privacy risks, operational blind spots, and release blockers with exact affected fields/components.
