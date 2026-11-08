# 20. Error Taxonomy

| Internal category | Retry? | Typical client mapping | Notes |
|---|---|---|---|
| `invalid_request` | No | 400/422 | Correct the request; do not contact provider. |
| `unauthorized` | No | 401/403 | Do not disclose credential validation internals. |
| `rate_limited` | Yes, bounded | 503 or 429 based on gateway policy | Respect upstream retry guidance; gateway quota is distinct. |
| `timeout` | Yes, bounded | 504 | Check remaining deadline before another attempt. |
| `network_error` | Yes, bounded | 503 | Classify transport failures carefully. |
| `provider_server_error` | Yes, bounded | 502/503 | Retry only selected upstream status classes. |
| `provider_auth_error` | No | 503 | Usually configuration/credential fault; alert operator. |
| `unsupported_parameter` | No | 400/422 | Fix model capability or request parameters. |
| `invalid_provider_response` | Usually no | 502 | Record safe metadata; do not leak raw response. |
| `provider_unavailable` | No further attempt | 503 | No eligible provider remains. |
| `telemetry_degraded` | Not a client model error | 200 with alert or fail-closed per mode | Persistence failure policy must be explicit. |

Every error carries a trace ID. Internally retain exception context in access-controlled logs, with secrets and sensitive payloads redacted.
