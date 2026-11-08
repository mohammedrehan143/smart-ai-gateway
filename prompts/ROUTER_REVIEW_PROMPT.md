# Router Review Prompt

Act as the Router Reviewer Agent in `agents/development/ROUTER_REVIEW_AGENT.md`. Inspect router implementation, configuration, unit tests, and traces. Verify determinism, explainability, policy modes, model allowlisting, capability checks, bounded fallback, and policy-version recording. Confirm routing makes no model/network call. Inspect benchmark comparisons for fairness and ensure cost reduction is reported with quality gap. Return prioritized findings with reproducible test cases; do not change code unless separately assigned.
