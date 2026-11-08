# 25. Glossary

- **Gateway:** Service between an application and model providers.
- **Provider adapter:** Integration layer translating gateway contracts to a provider API.
- **Model alias:** Stable internal name mapped to a configured upstream model.
- **Tier:** Configured class such as cheap or strong; not an intrinsic permanent model property.
- **Routing policy:** Rules that choose a model tier for a request.
- **Trace:** End-to-end record for one logical request, including provider attempts.
- **Attempt:** One call to a provider/model.
- **Rate card:** Versioned price assumptions used for a cost estimate.
- **Fallback:** A secondary approved model used after primary failure or policy decision.
- **Agent evaluation:** Scoring the agent's answer, tool behaviour, and execution path on known tasks.
- **Dataset version:** Immutable identifier for a fixed set of evaluation cases.
- **Scorer version:** Identifier for the scoring rules used for a benchmark.
- **Quality gap:** Difference between policy pass rates, reported in percentage points.
- **Cost reduction:** Relative cost decrease versus a defined baseline, reported as a percentage.
