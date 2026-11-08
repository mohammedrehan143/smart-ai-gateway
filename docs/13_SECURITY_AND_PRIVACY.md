# 13. Security and Privacy Requirements

## 1. Secrets

- Load provider keys and gateway authentication secrets from environment variables or deployment secret storage.
- Keep `.env` local and in `.gitignore`; commit only a redacted `.env.example` listing variable names and descriptions.
- Never log credentials, authorization headers, cookies, or full secret-bearing configuration.
- Rotate exposed keys immediately and remove them from repository history where applicable.

## 2. Authentication and access

The local demo may use a development-only access mode. Any public deployment must require gateway authentication. Compare secrets safely, keep keys out of query strings, and add rate limiting before exposing the service to the internet. A future multi-tenant version needs tenant-scoped keys, quotas, and trace access boundaries.

## 3. Input controls

- Enforce request body, message count, content length, and output-token limits.
- Validate roles and accepted parameters.
- Reject unknown model identifiers; callers select a policy, not arbitrary upstream model names.
- Treat prompt content and tool outputs as untrusted data.
- Prevent benchmark tools from accessing the filesystem, shell, network, or secrets.

## 4. Logging and retention

- Redact auth headers and secret-like strings.
- Default to metadata-only traces; do not persist raw prompts/responses unless explicitly enabled.
- If content capture is enabled, document purpose, access, retention, and deletion process.
- Limit trace access and protect exported benchmark reports if they include user content.

## 5. Provider and tool security

Use TLS for external API calls. Set explicit timeouts. Do not let provider responses instruct the gateway to execute arbitrary local commands. Benchmark tools must be allowlisted, deterministic, read-only where possible, and validated at their input boundary.

## 6. Deployment hardening checklist

- Authentication enabled.
- Secrets configured via platform secret store.
- HTTPS enforced at ingress.
- Request size and rate limits enabled.
- Debug mode disabled.
- CORS restricted if browser clients are introduced.
- Database access restricted and backups configured.
- Logs redacted and retention configured.
- Dependencies pinned and vulnerability checks included in CI.

## 7. Threat scenarios

| Threat | Control |
|---|---|
| API key leaks in logs/repo | Secret redaction, `.gitignore`, secret scanning, key rotation |
| Cost exhaustion | Auth, rate limits, output limits, quotas/alerts |
| Prompt injection in task/tool data | Treat content as untrusted; tools have strict schemas and allowlists |
| Provider response abuse | Normalize/validate response, never execute returned instructions as code |
| Cross-user trace exposure | Authentication and authorization checks on trace access |
| Benchmark contamination | Versioned fixtures and immutable expected answers per dataset version |
