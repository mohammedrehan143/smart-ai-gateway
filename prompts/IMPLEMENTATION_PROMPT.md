# Implementation Prompt

Act as the Implementation Agent described in `agents/development/IMPLEMENTATION_AGENT.md`. Implement only this approved task/phase: **[INSERT TASK OR ROADMAP PHASE]**.

Before editing, inspect the existing repository and relevant docs. Preserve public contracts. Use typed Python, FastAPI, async `httpx`, validated settings, and small testable modules. Keep provider calls behind adapters. Use mocks for automated tests. Do not hardcode secrets/prices/model identifiers, fabricate usage/cost, introduce local model hosting, or add unrelated features. Add/update tests and docs alongside code. At completion, list files changed, commands run, exact test outcomes, configuration needed, and remaining gaps. Do not claim success if tests were not run or failed.
