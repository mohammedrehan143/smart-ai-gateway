# API Contract

The following is a proposed MVP contract. Keep it stable even if providers differ.

## 1. `POST /v1/chat`

### Request

```json
{
  "messages": [
    {"role": "user", "content": "Explain binary search with an example."}
  ],
  "task_type": "general",
  "routing_policy": "default",
  "max_output_tokens": 500,
  "temperature": 0.2,
  "metadata": {
    "application": "demo-client"
  }
}
```

`task_type`, `routing_policy`, and metadata are optional. Do not trust client-supplied claims as security authorization.

### Response

```json
{
  "request_id": "req_example",
  "response": {
    "role": "assistant",
    "content": "..."
  },
  "model": {
    "provider": "provider_a",
    "name": "configured-model-id"
  },
  "routing": {
    "policy": "default",
    "policy_version": "v1",
    "reason_codes": ["SHORT_INPUT", "GENERAL_TASK"]
  },
  "usage": {
    "input_tokens": 120,
    "output_tokens": 180,
    "total_tokens": 300,
    "source": "provider"
  },
  "latency_ms": 840,
  "cost": {
    "amount": 0.0003,
    "currency": "USD",
    "status": "estimated"
  },
  "cached": false
}
```

The example values are illustrative only. If a provider does not return usage, use null/unknown and optionally a clearly labeled estimate.

## 2. `GET /v1/requests/{request_id}`

Returns request summary and attempt history. Apply authorization so a client can only inspect its own requests unless it has operator privileges.

## 3. `GET /v1/health`

Returns service health and dependency status. Do not expose secret values, internal hostnames, or sensitive configuration.

## 4. `GET /v1/metrics/summary`

Operator-facing aggregate metrics:
- total requests
- success/error counts
- average and percentile latency
- token totals
- estimated cost totals
- cache hit ratio
- model/provider usage
- fallback and retry counts

## 5. Error response

```json
{
  "error": {
    "code": "UPSTREAM_TIMEOUT",
    "message": "The model provider did not respond within the allowed time.",
    "request_id": "req_example",
    "retryable": true
  }
}
```

Do not leak provider stack traces or credentials.

## 6. Contract rules

- Use explicit schema versioning if breaking changes become necessary.
- Return a request ID on success and failure whenever possible.
- Keep provider-specific fields inside normalized metadata, not at the top-level public contract.
- Never claim exact cost when only a rough estimate is available.
