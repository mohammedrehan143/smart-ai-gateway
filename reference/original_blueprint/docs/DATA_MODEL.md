# Data Model

Proposed relational model. Names are illustrative; adapt during implementation.

## 1. `requests`

One row per logical client request.

| Field | Type | Notes |
|---|---|---|
| id | UUID/text | Internal primary key |
| request_id | text | Public correlation ID, unique |
| created_at | timestamp | UTC |
| client_id | text nullable | Non-secret client identifier |
| policy_name | text | Routing policy |
| policy_version | text | Policy version |
| selected_provider | text nullable | Final successful provider |
| selected_model | text nullable | Final successful model |
| route_reason_codes | JSON | Explainable reasons |
| status | text | success/error |
| latency_ms | integer nullable | End-to-end |
| input_tokens | integer nullable | Provider-reported or explicitly estimated |
| output_tokens | integer nullable | Provider-reported or explicitly estimated |
| usage_source | text | provider/estimate/unknown |
| cost_amount | decimal nullable | Never assume zero if unknown |
| cost_currency | text nullable | e.g. USD |
| cost_status | text | exact/estimated/unknown |
| cache_hit | boolean | Cache result |
| error_code | text nullable | Normalized error |

## 2. `attempts`

One row per provider attempt.

- id
- request_id (foreign key)
- attempt_number
- provider
- model
- started_at
- completed_at
- latency_ms
- status
- error_code
- is_retry
- is_fallback
- provider_request_id (sanitized, nullable)

## 3. `model_configs`

- id
- provider
- model_name
- enabled
- capabilities JSON
- context_window
- input_price_per_million
- output_price_per_million
- price_currency
- pricing_effective_at
- timeout_ms
- quality_tier
- config_version

## 4. `evaluation_runs`

- id
- run_name
- policy_name
- dataset_version
- model_config_snapshot
- agent_version
- scorer_version
- started_at
- completed_at
- status
- aggregate_metrics JSON

## 5. `evaluation_cases`

- id
- evaluation_run_id
- task_id
- raw_output (access controlled)
- score
- passed
- tool_trace JSON
- latency_ms
- cost_amount nullable
- failure_category nullable

## 6. Retention and indexes

- Index `requests.request_id`, `requests.created_at`, `requests.selected_model`, `requests.status`.
- Index `attempts.request_id`.
- Index `evaluation_runs.started_at`.
- Define retention for prompt/response content separately from operational metadata.
- Use migrations; do not rely on ad-hoc production schema changes.
