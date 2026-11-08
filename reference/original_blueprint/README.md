# Smart AI Gateway — Project Blueprint

A production-minded AI infrastructure project combining **LLM routing, LLMOps, reliability, and agent evaluation**.

> This repository is the documentation and agent-design blueprint. It intentionally does not prescribe a full starter-code implementation. Use these documents as the source of truth when an AI coding agent or developer designs and implements the application.

## Product goal

Build a backend gateway that sits between client applications and one or more LLM providers. It should:

1. Accept a normalized chat request.
2. Select an appropriate model using an explainable routing policy.
3. Call the provider through a common adapter interface.
4. Retry transient failures and fall back safely when configured.
5. Record model, token, latency, cost, route reason, and outcome.
6. Expose operational metrics and request logs.
7. Run a repeatable benchmark against a fixed evaluation set.
8. Compare **always-cheap**, **always-strong**, and **router** policies using measured quality, latency, and cost.

## Core design principle

The router is not allowed to claim that a request is "easy" or "hard" without recording the evidence and policy that led to the decision. Evaluation results must come from repeatable runs, not estimates or fabricated metrics.

## Documentation map

- [`docs/PRODUCT_REQUIREMENTS.md`](docs/PRODUCT_REQUIREMENTS.md) — scope, users, requirements, acceptance criteria.
- [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — components and boundaries.
- [`docs/REQUEST_LIFECYCLE.md`](docs/REQUEST_LIFECYCLE.md) — end-to-end request flow.
- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — proposed HTTP API contract.
- [`docs/ROUTING_POLICY.md`](docs/ROUTING_POLICY.md) — routing decisions and policy evolution.
- [`docs/PROVIDER_ADAPTERS.md`](docs/PROVIDER_ADAPTERS.md) — provider abstraction and model capabilities.
- [`docs/RELIABILITY_AND_FAILURES.md`](docs/RELIABILITY_AND_FAILURES.md) — retries, fallback, timeouts, circuit breakers.
- [`docs/LLMOPS_AND_OBSERVABILITY.md`](docs/LLMOPS_AND_OBSERVABILITY.md) — logs, metrics, cost, traces.
- [`docs/EVALUATION_FRAMEWORK.md`](docs/EVALUATION_FRAMEWORK.md) — agent benchmark and scoring.
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — persistence entities and relationships.
- [`docs/SECURITY_AND_PRIVACY.md`](docs/SECURITY_AND_PRIVACY.md) — secrets, abuse controls, data handling.
- [`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md) — test layers and quality gates.
- [`docs/DEPLOYMENT_AND_OPERATIONS.md`](docs/DEPLOYMENT_AND_OPERATIONS.md) — local, container, CI, deployment.
- [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) — phased delivery plan.
- [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) — important decisions and trade-offs.
- [`agents/README.md`](agents/README.md) — agent roles and boundaries.
- [`agents/ORCHESTRATOR_AGENT.md`](agents/ORCHESTRATOR_AGENT.md) — benchmark coordinator.
- [`agents/ROUTER_REVIEW_AGENT.md`](agents/ROUTER_REVIEW_AGENT.md) — audits routing decisions.
- [`agents/EVALUATOR_AGENT.md`](agents/EVALUATOR_AGENT.md) — scores agent runs.
- [`agents/TRACE_ANALYST_AGENT.md`](agents/TRACE_ANALYST_AGENT.md) — diagnoses traces and failures.
- [`prompts/AGENT_PROMPTS.md`](prompts/AGENT_PROMPTS.md) — copy-ready system prompts.

## Suggested initial stack

- Python + FastAPI for the gateway API.
- `httpx` for asynchronous provider requests.
- SQLite for local development, PostgreSQL for deployed persistence.
- In-memory cache initially; Redis when multi-instance/shared caching is needed.
- Docker for reproducible packaging.
- GitHub Actions for tests and benchmark smoke runs.
- One or more OpenAI-compatible model providers; keep provider-specific code behind adapters.

The exact provider, model names, and prices are configuration, not hard-coded assumptions.

## Non-goals for the first release

- Training or fine-tuning a foundation model.
- Building a general-purpose autonomous agent platform.
- Guaranteeing semantic correctness from an LLM judge alone.
- Supporting every provider or every multimodal input.
- Claiming production-grade security/compliance without an actual review.

## Definition of done

The project is ready for a credible portfolio demonstration when a reviewer can:

- Send a request through one stable gateway endpoint.
- See why a model was selected.
- Inspect a request record with tokens, latency, estimated cost, and outcome.
- Simulate a provider timeout and observe safe fallback behavior.
- Run the same benchmark under all three routing policies.
- Reproduce the reported results from the documented dataset, configuration, and run command.
