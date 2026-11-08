# 10. Agent Evaluation Framework

## 1. Purpose

Evaluate a tool-using agent, not just an isolated model answer. The project must score three aspects named in the source brief: final answer, tools used, and steps taken.

## 2. Runtime benchmark agent

Create one constrained benchmark agent that receives a task, reasons about whether a tool is required, calls only approved tools, and returns a final answer. It must use the gateway for its model call. The initial tools are:
1. Calculator: deterministic arithmetic with validated input.
2. Lookup: deterministic read-only lookup over a local fixture/knowledge table.

A third tool is optional only if it adds a distinct task category; do not add external side effects or unrestricted web access to the benchmark.

## 3. Task set

Maintain 20-50 versioned evaluation tasks as required by the brief. Each case contains a unique ID, category, prompt, expected answer or rubric, required/allowed tools, forbidden tools (if relevant), expected key facts, and scoring weights. Include direct-answer, calculation, lookup, multi-step, and code/debugging-style examples only where the implementation can score them reliably.

## 4. Scoring dimensions

| Dimension | What is measured | Example scoring method |
|---|---|---|
| Final answer | Correctness, completeness, constraint adherence | Exact match for deterministic values; rubric/key-fact checks for natural language |
| Tool selection | Whether the agent used a tool when required and avoided unnecessary tools | Required/allowed tool policy check |
| Tool execution | Correct arguments and valid tool result handling | Structured argument checks and expected result comparison |
| Steps/trajectory | Whether the sequence was reasonable, complete, and within allowed limits | Event/trace validation, step budget, no forbidden action |
| Overall pass | Meets case-level minimums across required dimensions | Weighted score plus hard-fail rules |

Do not use an LLM judge as the only evaluator. The first benchmark should use deterministic checks wherever possible. If a model-based judge is added later, calibrate it against human-labeled examples and report judge disagreement.

## 5. Scoring controls

- Store dataset version, scorer version, agent prompt version, tool version, and model configuration with every run.
- Use exact checks for arithmetic and lookup facts.
- Define acceptable answer variations in rubrics for open-text answers.
- Penalize unsupported claims and missing required facts.
- Hard-fail prohibited tool use or policy violations.
- Capture tool events and model traces so a score can be explained.

## 6. Reproducibility

Use the same task IDs, task order policy, tool fixtures, agent instructions, output-token limits, and scoring implementation across the three routing policies. Fix model sampling settings where supported. Run more than once when provider/model nondeterminism could materially affect results, and report run count and variability rather than hiding it.

## 7. Report outputs

Per task: policy, selected model, result, score by dimension, tool events, latency, token usage, cost, and error/fallback state.

Aggregate: overall and category pass rate, weighted score, cost per task, cost per passed task, p50/p95 latency, fallback/retry rate, and score variability where repeated runs exist.

## 8. Integrity rule

Never alter expected answers, scoring thresholds, or task composition after seeing policy results without creating a new dataset/scorer version and documenting the change.
