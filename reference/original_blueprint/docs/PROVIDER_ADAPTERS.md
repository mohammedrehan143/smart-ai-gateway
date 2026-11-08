# Provider Adapters

## 1. Purpose

Hide provider-specific API formats behind a common interface so routing and application logic do not depend on one vendor.

## 2. Canonical interface

Conceptual operations:

- `chat(canonical_request) -> canonical_response`
- `health_check() -> provider_status`
- `estimate_cost(usage, model_config) -> cost_result`
- `normalize_error(provider_error) -> normalized_error`

## 3. Canonical response fields

- provider
- model
- assistant message
- input/output/total tokens (nullable)
- finish reason
- provider request identifier (optional)
- raw timing metadata (internal)
- normalized error when unsuccessful

## 4. Error categories

- `TIMEOUT`
- `RATE_LIMITED`
- `AUTHENTICATION`
- `INVALID_REQUEST`
- `CONTEXT_TOO_LONG`
- `PROVIDER_SERVER_ERROR`
- `NETWORK_ERROR`
- `UNKNOWN_PROVIDER_ERROR`

Each adapter maps provider-specific errors to these categories while retaining a sanitized diagnostic code.

## 5. Model capability registry

Do not assume all models support the same features. Store capability declarations in configuration and validate them before routing.

## 6. Provider integration checklist

- [ ] Credentials loaded from environment/secret manager.
- [ ] Request and response normalized.
- [ ] Timeout configured.
- [ ] Usage extraction tested.
- [ ] Error mapping tested.
- [ ] Rate-limit headers handled where available.
- [ ] Cost calculation uses dated pricing configuration.
- [ ] Logs redact secrets and sensitive prompt content.
- [ ] Contract tests pass against mocked provider responses.

## 7. Provider choice

The PDF proposes Groq free tier or any OpenAI-compatible API as a starting point. Select currently available models and verify their limits/pricing at implementation time. Keep the adapter interface provider-neutral.
