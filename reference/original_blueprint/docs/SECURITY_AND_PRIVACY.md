# Security and Privacy

## 1. Secrets

- Store provider keys in environment variables for local development and a secret manager in deployment.
- Keep `.env` out of version control; commit `.env.example` with placeholder names only.
- Never put provider keys in frontend code, logs, screenshots, or benchmark datasets.
- Rotate any key that is accidentally exposed.

## 2. API access

- Add gateway API authentication before exposing the service publicly.
- Use per-client keys or an established identity mechanism.
- Hash stored gateway API keys; show plaintext only once if issuing keys.
- Add rate limits and request-size limits.
- Separate operator/admin endpoints from client endpoints.

## 3. Prompt and tool safety

- Treat user prompts and retrieved content as untrusted input.
- Do not let prompts alter gateway routing configuration or reveal secrets.
- Keep agent tools allowlisted and narrowly scoped.
- Require explicit authorization for any side-effecting tool.
- Do not execute generated code or shell commands in the MVP.

## 4. Data minimization

- Store only what is needed for debugging and measurement.
- Make prompt/response retention configurable.
- Redact credentials and sensitive headers.
- Avoid logging personal data unnecessarily.
- Restrict access to traces and exports.

## 5. Abuse controls

- Per-client request quotas.
- Maximum prompt and output sizes.
- Concurrency limits.
- Budget alerts and hard limits where appropriate.
- Timeouts and bounded retries to prevent resource exhaustion.

## 6. Deployment checklist

- [ ] HTTPS enabled.
- [ ] Secrets configured outside source control.
- [ ] Debug mode disabled.
- [ ] Admin routes protected.
- [ ] CORS restricted to known origins.
- [ ] Rate limiting enabled.
- [ ] Logs scrubbed.
- [ ] Database access restricted.
- [ ] Budget alerts configured with the cloud/provider.
