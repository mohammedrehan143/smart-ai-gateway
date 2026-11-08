# 18. Cost Model and Spend Controls

## Cost formula

For a model with input and output rates expressed per million tokens:

`estimated_cost = (input_tokens * input_rate_per_million + output_tokens * output_rate_per_million) / 1_000_000`

The implementation must normalize provider rate units before calculating. If rate units are per token or per thousand tokens, convert them explicitly and test the conversion.

## Cost provenance

Every estimate stores:
- provider and model alias;
- input/output token counts and usage source;
- rate-card ID/version;
- rate units and currency;
- calculated/estimated/unavailable status;
- calculation timestamp.

Provider invoices may include discounts, taxes, caching semantics, or other adjustments not represented in a simple token rate card. Therefore call this value an estimate unless reconciled to billing data.

## Spend controls

- Per-request input/output limits.
- Gateway authentication and rate limiting.
- Low default evaluation concurrency.
- Manual control for full live benchmark runs.
- Provider-side billing alerts and budget alerts where available.
- Fallback restrictions to prevent uncontrolled use of expensive models.
- Clear display of unknown/unavailable cost rather than zero.

## Benchmark cost metrics

Report total cost estimate, mean cost per task, cost per passed task, cost reduction relative to always-strong, and rate-card coverage. Exclude failed attempts only if their provider usage is known to be non-billable; otherwise include recorded billable usage or clearly disclose that the data is unavailable.
