# Deployment and Operations

## 1. Local development

- Use a supported Python version and isolated virtual environment.
- Copy `.env.example` to `.env`.
- Configure one provider key and model target.
- Start with SQLite and mocked provider tests.
- Never commit `.env`.

## 2. Environment configuration

Example variable names (values must be supplied by the developer):

```env
APP_ENV=development
DATABASE_URL=sqlite:///./gateway.db
PROVIDER_A_API_KEY=
PROVIDER_B_API_KEY=
DEFAULT_ROUTING_POLICY=default_router
REQUEST_TIMEOUT_SECONDS=30
MAX_RETRIES=2
LOG_LEVEL=INFO
```

Do not put real credentials in documentation or sample files.

## 3. Docker

The container should:
- run as a non-root user
- expose only the application port
- receive secrets at runtime
- use health checks
- avoid baking `.env` or credentials into image layers
- write logs to stdout/stderr

## 4. CI/CD

Recommended pipeline:
1. Install dependencies.
2. Lint and type-check.
3. Run unit and mocked integration tests.
4. Run deterministic evaluation smoke test.
5. Build container.
6. Deploy only from an approved branch/tag.

## 5. Deployment choice

The PDF mentions AWS as a possible shipping target and advises setting a zero-spend budget alert first. A small portfolio deployment can also use a suitable container host. Verify current free-tier limits and pricing before choosing.

## 6. Operations checklist

- [ ] Health endpoint available.
- [ ] Database backup plan defined.
- [ ] Provider budget alerts configured.
- [ ] Request and attempt logs searchable.
- [ ] Error and latency metrics visible.
- [ ] Secrets rotatable.
- [ ] Rollback procedure documented.
- [ ] Evaluation benchmark can be rerun after a deployment.
