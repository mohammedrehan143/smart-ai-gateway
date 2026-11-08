# 15. Deployment and Operations

## 1. Local environment

Use a supported Python version, virtual environment, FastAPI server, SQLite database, in-memory cache, and mocked provider for day-to-day development. Configure one hosted provider only for manual smoke tests and benchmark runs. A GPU is not required.

## 2. Container contract

The implementation should provide a Docker image that:
- installs pinned runtime dependencies;
- runs as a non-root user where practical;
- reads configuration from environment variables;
- exposes the API on the configured port;
- writes logs to stdout/stderr;
- handles SIGTERM gracefully;
- does not bake secrets or local database credentials into the image.

## 3. Environment separation

- `local`: mocked provider by default, SQLite, verbose development logs with redaction.
- `test`: isolated test database and mocked provider.
- `staging`: hosted provider credentials, PostgreSQL if available, conservative rate limits, no real user data.
- `production/demo`: authentication, secret store, persistence, request limits, monitoring/alerts, controlled provider allowlist.

Do not use real production credentials in a public repository or screenshots.

## 4. Deployment checklist

1. Configure service secrets and non-secret settings.
2. Configure database and run migrations.
3. Verify readiness and liveness endpoints.
4. Verify provider connectivity using a protected smoke test.
5. Send one small authenticated test request.
6. Confirm trace, usage, and cost-status record is persisted.
7. Run the benchmark and archive its report with the git commit.
8. Configure spend/rate alerts and request limits.

## 5. Rollback

Keep the last known-good image/version. Roll back application image and configuration together when schema-compatible. Use additive database migrations; do not destructively alter historical trace/evaluation data during ordinary deploys.

## 6. Resource profile

The gateway is I/O-bound. Keep worker/process count modest for an 8 GB local machine. Evaluation concurrency must be configurable and low by default to avoid rate-limit bursts and laptop memory pressure. Do not add local LLM runtime dependencies.
