# 11. Benchmark Protocol and Proof of Value

## 1. Policies to compare

- **Always-cheap:** route every eligible task to the configured cheap-tier model.
- **Always-strong:** route every eligible task to the configured strong-tier model.
- **Adaptive:** route using the deterministic policy version under evaluation.

These are the three required comparison arms. Keep provider/model IDs and rate-card versions fixed during a comparison.

## 2. Experimental controls

1. Freeze the dataset version and task IDs.
2. Freeze benchmark-agent prompt, tools, and tool fixtures.
3. Freeze scorer version and pass thresholds.
4. Use the same request/response limits for all arms unless a model capability prevents it; document any exception.
5. Keep cache disabled for the primary quality/cost comparison or use a controlled, identical cache policy across all arms. Report cache effects separately.
6. Avoid running all requests for one arm during an unusual provider incident; randomize or interleave policy order where practical.
7. Store raw per-case results and gateway traces, not only aggregate averages.

## 3. Core calculations

Let `C_strong` be total estimated cost under always-strong and `C_adaptive` total estimated cost under adaptive:

`cost_reduction_pct = ((C_strong - C_adaptive) / C_strong) * 100`

Let `P_strong` and `P_adaptive` be pass rates on the same cases:

`quality_gap_points = (P_strong - P_adaptive) * 100`

If the values are already expressed as percentages, subtract directly in percentage points. Define sign conventions in the report and avoid confusing percentage with percentage-point change.

Also report:
- cost per passed task;
- average and percentile latency;
- cheap/strong route share;
- fallback and retry rates;
- cost-status coverage (calculated/estimated/unavailable);
- category-level pass rate.

## 4. Interpretation

The adaptive router is valuable only if cost falls while quality remains within a pre-declared tolerance, and reliability/latency do not become unacceptable. Do not select a threshold after looking at the final test set. Use a tuning set to adjust heuristics and a held-out set to report the final result where dataset size permits. If the initial 20-50 tasks are too small for a meaningful split, state that limitation and present the results as an engineering benchmark, not a statistically conclusive study.

## 5. Required report sections

- Run ID, timestamp, git commit, environment.
- Dataset, agent prompt, scorer, policy, provider/model, and rate-card versions.
- Experiment controls and known deviations.
- Aggregate policy comparison.
- Per-category and per-case results.
- Failure analysis and examples of wrong routes.
- Quality/cost trade-off interpretation.
- Limitations, small-sample caveats, and next experiments.

## 6. Resume metric rule

Only fill resume placeholders such as cost reduction `X%` and quality gap `Y points` after a real benchmark has completed. Cite the benchmark run ID or report in the repository. If the run does not show savings with acceptable quality, report the honest finding and explain the router iteration; do not fabricate a success claim.
