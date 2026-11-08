# 05. API Contract

## 1. Public endpoint

`POST /v1/chat`

The first release exposes one generation endpoint. Operational health endpoints may be added, but do not expand into a large public API before the core path is stable.

### Headers

| Header | Required | Meaning |
|---|---|---|
| `Authorization: Bearer <gateway-key>` | In deployed environments | Gateway authentication. Local development may use an explicitly configured development mode. |
| `Content-Type: application/json` | Yes | JSON request body. |
| `X-Request-ID` | No | Client-provided correlation ID; validate length/characters or generate one. |
| `Idempotency-Key` | No | Optional client key for deduplicating repeat submissions if idempotency storage is implemented. |

### Request body

```json
{
  "messages": [
    {"role": "system", "content": "You are a concise assistant."},
    {"role": "user", "content": "Explain database indexing."}
  ],
  "routing": {
    "policy": "adaptive",
    "preference": "balanced"
  },
  "parameters": {
    "temperature": 0.2,
    "max_output_tokens": 500
  },
  "metadata": {
    "source": "demo-client"
  }
}
```

Contract rules:
- `messages` is required, non-empty, ordered, and role-validated.
- `routing.policy` is one of `adaptive`, `always_cheap`, or `always_strong`; default is `adaptive`.
- `routing.preference` is optional and must map to a server-defined policy; it must not accept an arbitrary provider/model identifier.
- `temperature` and output-token limits are validated against configured bounds and provider capability.
- `metadata` is optional, size-limited, and must not contain secrets.
- The API accepts only supported text content in the MVP. Multimodal payloads are future scope.

### Success response

```json
{
  "id": "req_01J...",
  "object": "gateway.completion",
  "created": 1794050000,
  "model": "configured-model-alias",
  "provider": "configured-provider",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}
  ],
  "usage": {
    "input_tokens": 120,
    "output_tokens": 75,
    "total_tokens": 195,
    "cost_estimate": 0.0000,
    "currency": "USD",
    "cost_status": "calculated"
  },
  "routing": {
    "policy": "adaptive",
    "policy_version": "1",
    "tier": "cheap",
    "reason": "Short request; no code or multi-step indicators detected",
    "fallback_used": false
  },
  "latency_ms": 842,
  "trace_id": "tr_01J...",
  "cached": false
}
```

The model alias, tokens, cost, timestamp, IDs, and latency above are illustrative contract values, not measured results or a claim about a specific provider. `cost_status` must distinguish `calculated`, `estimated`, and `unavailable`. Missing usage must not be represented as a real zero.

### Error response

```json
{
  "error": {
    "type": "provider_unavailable",
    "message": "No configured model could complete the request.",
    "retryable": false,
    "trace_id": "tr_01J..."
  }
}
```

Do not expose raw provider stack traces, internal hostnames, API keys, or full upstream response bodies.

## 2. HTTP status mapping

| Status | Use |
|---|---|
| 200 | Successful completion, including cache hit |
| 400 | Malformed request or unsupported parameter |
| 401 / 403 | Missing/invalid gateway credentials or denied access |
| 413 | Request body exceeds configured limit |
| 422 | Valid JSON but invalid semantic input |
| 429 | Gateway-level rate/quota limit reached |
| 502 | Invalid or unusable upstream response |
| 503 | No provider currently available / circuit open |
| 504 | Gateway deadline exceeded |

## 3. Operational endpoints

- `GET /health/live`: process is running; must not make external provider calls.
- `GET /health/ready`: checks required local dependencies (database/configuration) without exposing secrets. Provider reachability may be reported as a separate dependency status, not used to mark the entire process unready unless the deployment policy requires it.

## 4. Compatibility

Version the public path (`/v1`). Any incompatible schema change requires a new version or a documented migration. Additive optional fields are preferred. Record the gateway contract version in traces and benchmark reports.
