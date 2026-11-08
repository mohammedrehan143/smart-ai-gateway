# 16. CI/CD and Repository Quality

## Pull-request pipeline

1. Check formatting and lint.
2. Run static type checks.
3. Run unit tests.
4. Run integration and provider-contract tests using mocks.
5. Check database migrations.
6. Run dependency/security scanning and secret scanning.
7. Build the Docker image.
8. Run container health smoke test.

## Main-branch pipeline

Repeat all pull-request checks. Optionally publish a versioned image. Deployment to staging should require successful checks. Production/demo promotion should be a separate controlled step with credentials and spend limits configured.

## Evaluation CI

A small deterministic fixture evaluation can run in normal CI. The full 20-50 task live-provider benchmark should be triggered manually or on a controlled schedule because it consumes provider quota and can vary due to external model behaviour. Store benchmark results as build artifacts; do not fail the build on a small noisy score difference without a pre-agreed tolerance and sufficient repeated runs.

## Release metadata

Every release should identify git commit, application version, API contract version, routing policy version, provider/model configuration version, rate-card version, and evaluation dataset/scorer versions.
