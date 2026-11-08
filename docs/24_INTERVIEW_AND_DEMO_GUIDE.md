# 24. Interview and Demo Guide

## 5-minute demo sequence

1. Show the architecture and explain why the gateway sits between the app and providers.
2. Send a simple request and show the cheap-tier route decision and trace.
3. Send a code/multi-step request and show the strong-tier decision with reason.
4. Trigger a mocked provider failure and demonstrate bounded retry/fallback.
5. Run a small evaluation and show per-policy quality, cost, latency, and route distribution.
6. Explain one failure case and what you changed based on the evidence.

## Questions you should be able to answer

### How does your router choose a model?
Explain the deterministic features, configured thresholds, policy modes, decision record, and why the router is not an LLM agent in the baseline.

### How do you evaluate an agent rather than only a model response?
Explain task fixtures, tool-use requirements, argument validation, trajectory capture, case-level scoring, and aggregate pass rate.

### How do you calculate cost?
Explain provider-reported tokens, versioned input/output rates, effective dates, estimate provenance, and why invoice reconciliation may differ.

### What happens when a provider times out or rate-limits?
Explain request deadlines, bounded backoff, `Retry-After`, retryable classification, fallback eligibility, and trace records.

### Why not use an existing gateway library?
Acknowledge that mature gateway products exist. Explain that the project's learning objective is to implement and measure the core routing/evaluation loop directly, then compare the trade-offs. Do not claim the custom gateway is more mature than established products.

## Claims to avoid

- Do not claim a percentage cost reduction until a benchmark report proves it.
- Do not claim production scale from a single-machine demo.
- Do not claim all providers are interchangeable; capability differences exist.
- Do not call rule-based routing machine learning.
- Do not call one evaluation run statistically conclusive when the task set is small.
