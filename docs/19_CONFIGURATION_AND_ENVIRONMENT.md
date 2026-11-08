# 19. Configuration and Environment Contract

The implementation must define and document configuration in one validated settings layer. The following are logical settings; names may be refined but must remain documented.

| Setting | Purpose | Secret? |
|---|---|---|
| `APP_ENV` | local/test/staging/production | No |
| `APP_HOST`, `APP_PORT` | Bind address/port | No |
| `GATEWAY_API_KEY` | Gateway authentication | Yes |
| `DATABASE_URL` | Persistence connection | Potentially |
| `CACHE_BACKEND` | memory/redis | No |
| `REDIS_URL` | Redis connection | Potentially |
| `PROVIDER_A_API_KEY` | Hosted provider credential | Yes |
| `PROVIDER_A_BASE_URL` | Provider API base URL | No, but protect config integrity |
| `CHEAP_MODEL_ALIAS` | Allowlisted cheap model alias | No |
| `STRONG_MODEL_ALIAS` | Allowlisted strong model alias | No |
| `REQUEST_TIMEOUT_SECONDS` | Total request deadline | No |
| `MAX_PROVIDER_ATTEMPTS` | Bounded attempts | No |
| `CACHE_TTL_SECONDS` | Response cache TTL | No |
| `ROUTING_POLICY_VERSION` | Active policy version | No |
| `RATE_CARD_VERSION` | Active rate-card version | No |
| `MAX_INPUT_TOKENS` | Input guardrail where available | No |
| `MAX_OUTPUT_TOKENS` | Output guardrail | No |
| `LOG_LEVEL` | Structured log verbosity | No |
| `STORE_PROMPT_CONTENT` | Explicit opt-in for content capture | No |

Validate required settings at startup and fail with actionable messages that never print secret values. Provide `.env.example` with placeholders only when implementing the application; do not commit a real `.env`.
