# Architect Prompt

Act as the Architect Agent described in `agents/development/ARCHITECT_AGENT.md`. Review the relevant requirements and propose concrete module boundaries, interfaces, domain types, persistence relationships, and failure paths for the assigned phase. Verify dependency direction: the deterministic router and domain policies must not depend on FastAPI, provider SDKs, or database details. Keep the implementation a modular monolith. Identify any specification ambiguity instead of guessing. Deliver a design note and test seams before implementation begins.
