# Contribution and Change Rules

## Change discipline

- Make one logical change at a time.
- Keep public API changes backward-compatible where practical; document breaking changes.
- Update the relevant ADR when changing a major architecture choice.
- Update API, data model, routing, or evaluation docs whenever their contracts change.
- Never commit `.env`, API tokens, customer prompts, or benchmark secrets.

## Quality gates

Before considering a change complete, run the relevant unit and integration tests, formatting/lint checks, and type checks. For routing or evaluation changes, regenerate benchmark results and explain any score movement. For provider changes, run adapter contract tests with mocked responses.

## Pull-request description should include

- Problem and expected behaviour.
- Design choice and alternatives considered.
- Files/components affected.
- Tests executed and results.
- Security/privacy implications.
- Any change to cost, latency, route selection, or evaluation scores.

## Definition of a good change

It is small, testable, documented, observable, reversible where possible, and does not add unnecessary infrastructure.
