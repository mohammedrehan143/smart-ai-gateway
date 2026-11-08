# Merge Notes

## What this folder contains

This folder combines the user's original 22-file Smart AI Gateway blueprint with the expanded enterprise-oriented specification pack.

- The root `docs/`, `agents/`, and `prompts/` folders contain the expanded enterprise specification and are the implementation source of truth.
- `PROJECT_CHARTER.md`, `SCOPE_AND_NON_GOALS.md`, `IMPLEMENTATION_GUIDE.md`, and `CONTRIBUTING.md` define project boundaries and engineering workflow.
- `reference/original_blueprint/` preserves the original uploaded ZIP contents exactly, including its README, 4 original agent files, 20 original docs, and original prompt collection.

## Precedence rule

When an original reference file appears to overlap with a root document, use the root enterprise document. The reference archive exists for history and traceability, not as an additional active specification.

## Product boundary preserved

This remains one integrated project with three capabilities: LLMOps/observability, agent evaluations, and policy-based model auto-routing. The router remains deterministic Python policy logic; it is not an autonomous LLM agent.
