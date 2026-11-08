# Agent Evaluation Framework

## 1. Purpose

Measure whether the agent completes tasks correctly and whether the router achieves useful cost/quality trade-offs.

## 2. Agent under test

Use a small, controlled agent with 2–3 tools, as the source PDF proposes. Suggested tools:
- calculator: deterministic arithmetic
- lookup: controlled lookup against a small local fixture or approved source

The agent should have a constrained task scope. Do not give it arbitrary shell, filesystem, or unrestricted network access.

## 3. Dataset

Start with 20–50 tasks. Each task should include:
- stable task ID
- task category
- user prompt
- expected answer or acceptance criteria
- required tool(s), if any
- disallowed tool(s), if any
- scoring method
- difficulty label (human-assigned and documented)

Version the dataset. Keep evaluation prompts and expected answers out of the agent's runtime context.

## 4. Scoring

Use deterministic checks wherever possible:
- exact match for simple numeric/string answers
- tolerance-based checks for numeric outputs
- schema validation for structured outputs
- required-tool checks for tool-use tasks
- forbidden-tool checks
- step/trace checks for known workflow constraints

For open-ended answers, use a rubric and optionally an LLM judge. Store judge model, prompt version, score, and rationale. Sample and manually review judge outcomes.

## 5. Metrics

- task pass rate
- partial/rubric score
- tool selection accuracy
- unnecessary tool-call rate
- task completion rate
- average latency
- cost per task
- failure categories

Do not collapse all dimensions into one score without also reporting the individual metrics.

## 6. Experiment protocol

Run the same benchmark under:
1. `cheap_only`
2. `strong_only`
3. `default_router`

Control:
- dataset version
- agent instructions
- tool implementations
- temperature/decoding settings where supported
- scoring rules
- model IDs and provider settings
- concurrency and retry configuration

Save raw outputs, traces, score details, and run configuration.

## 7. Reporting

Report:
- total tasks and dataset version
- pass rate with numerator/denominator
- average and p95 latency
- total and average cost, with cost source/limitations
- tool-use compliance
- error counts
- model and router configuration
- date/time and run ID

A defensible resume statement can be written only after real runs, for example:

> Built an LLM gateway with model routing, fallback, and cost tracking; reduced measured LLM spend by **X%** while keeping benchmark pass rate within **Y percentage points** of the strong-model baseline.

Replace X and Y only with measured results. Include the benchmark size and conditions in the README.
