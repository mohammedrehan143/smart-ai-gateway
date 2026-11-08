# 07. Provider Adapter Design

## 1. Objective

Keep the gateway independent of provider-specific request and response formats. Business logic calls a common adapter interface; each adapter handles upstream details.

## 2. Adapter responsibilities

- Build provider-specific request payload.
- Inject provider credential from runtime secret configuration.
- Apply connect/read/overall timeouts.
- Send request through async `httpx`.
- Parse successful response into a normalized completion.
- Extract provider-reported token usage and provider request ID when available.
- Translate upstream errors into gateway error categories.
- Avoid logging authorization headers, full prompts, or raw sensitive upstream bodies.

## 3. Normalized adapter operation

Conceptual operation: `generate(request, model_config, timeout) -> NormalizedCompletion`.

`NormalizedCompletion` should include content, finish reason, provider/model alias, provider request ID, prompt/input token count, completion/output token count, total tokens, and raw-usage availability flags. Do not make the domain layer parse provider-specific JSON.

## 4. Error categories

- `authentication_error` — invalid provider credential/configuration; do not retry automatically.
- `rate_limited` — 429 or provider equivalent; respect `Retry-After` where available.
- `timeout` — configured deadline exceeded.
- `network_error` — transient connection/DNS/TLS transport issue where retry policy permits.
- `provider_server_error` — retryable upstream 5xx where policy permits.
- `invalid_request` — client/provider contract problem; no retry.
- `unsupported_parameter` — configuration/request incompatibility; no retry.
- `invalid_response` — missing required completion payload or malformed provider response.

## 5. Model registry/configuration

Each model configuration should define alias, provider, upstream model identifier, tier, context limit (if known), max output, supported features, timeout profile, and active status. Store rate-card values separately with currency, unit, effective start/end, and source/verification note. Never hardcode provider prices inside router logic.

## 6. Contract tests

Every adapter must pass the same test suite using mocked HTTP responses: success, missing usage, 401, 429 with `Retry-After`, 5xx, timeout, malformed JSON, empty content, and unsupported parameter errors.

## 7. Provider selection

Start with a hosted API that offers a documented OpenAI-compatible chat interface, as the source brief suggests. The interface must remain replaceable. Do not assume all OpenAI-compatible providers implement every optional feature identically; capability flags and adapter tests remain required.
