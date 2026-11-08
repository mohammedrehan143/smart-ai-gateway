# Implementation Roadmap

The source brief suggests approximately 2–3 weeks. Actual duration depends on experience, provider access, and available time.

## Phase 0 — Project decisions

**Outcome:** agreed model catalog, supported request format, and benchmark task scope.

- Choose initial provider(s).
- Define cheap and strong model targets based on current availability and capability.
- Record pricing source and date.
- Decide what prompt content, if any, will be retained.

**Exit criteria:** configuration is explicit; no model or price is assumed.

## Phase 1 — Gateway foundation

**Outcome:** one working endpoint and telemetry.

- Create FastAPI app and canonical schemas.
- Implement one provider adapter.
- Add request IDs and normalized responses.
- Persist request metadata, usage, latency, and status.
- Test with a mocked provider.

**Exit criteria:** one request is traceable end-to-end.

## Phase 2 — Reliability and cache

**Outcome:** safe recovery from transient failures.

- Add second provider/model adapter.
- Add timeout and bounded retry.
- Add fallback rules.
- Add response cache for eligible requests.
- Add failure-injection tests.

**Exit criteria:** timeout and provider failure scenarios behave predictably.

## Phase 3 — Explainable routing

**Outcome:** deterministic model selection.

- Create model capability catalog.
- Implement feature extraction and rule-based router.
- Add policy version and reason codes.
- Implement cheap-only, strong-only, and default-router policies.

**Exit criteria:** identical inputs and config produce reproducible routing decisions.

## Phase 4 — Agent and evaluations

**Outcome:** repeatable benchmark.

- Build constrained agent with calculator and lookup tools.
- Create 20–50 benchmark tasks.
- Implement deterministic scorers and optional judge rubric.
- Store per-case traces and aggregate results.

**Exit criteria:** benchmark runs under all three policies and saves artifacts.

## Phase 5 — Dashboard, deployment, and proof

**Outcome:** demonstrable product.

- Build request, model, routing, reliability, and evaluation views.
- Containerize.
- Add CI checks and evaluation smoke run.
- Deploy with budget alerts.
- Document measured trade-offs and limitations.

**Exit criteria:** another person can reproduce the benchmark and inspect the design.

## Work order

Do not start with dashboard polish. First make the backend measurements trustworthy. The UI is a presentation layer over real telemetry.
