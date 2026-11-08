# 04. Sequence Flows

## Successful uncached request

```mermaid
sequenceDiagram
  participant C as Client
  participant G as Gateway
  participant R as Router
  participant P as Provider adapter
  participant L as Hosted model
  participant D as Trace store
  C->>G: POST /v1/chat
  G->>G: Validate + create trace ID
  G->>R: Request features + policy
  R-->>G: Model + tier + reason
  G->>P: Generate completion
  P->>L: Provider API request
  L-->>P: Content + usage
  P-->>G: Normalized completion
  G->>G: Calculate estimated cost
  G->>D: Persist trace + attempt + usage
  G-->>C: Normalized response + trace ID
```

## Retry then fallback

```mermaid
sequenceDiagram
  participant G as Gateway
  participant P1 as Primary adapter/model
  participant P2 as Fallback adapter/model
  G->>P1: Attempt 1
  P1-->>G: Timeout / 429 / retryable 5xx
  G->>G: Backoff + retry budget check
  G->>P1: Attempt 2
  P1-->>G: Retryable failure
  G->>G: Check fallback policy and remaining deadline
  G->>P2: Fallback attempt
  P2-->>G: Successful completion
  G->>G: Record all attempts and final model
```

## Evaluation run

```mermaid
sequenceDiagram
  participant CLI as Evaluation runner
  participant DS as Versioned task set
  participant A as Benchmark agent
  participant GW as Gateway
  participant S as Scorer
  participant R as Report generator
  CLI->>DS: Load dataset version
  loop Each task under each policy
    DS-->>A: Task input + expected outcome
    A->>GW: Agent model request through /v1/chat
    GW-->>A: Completion + trace ID
    A->>A: Execute only permitted tools
    A->>S: Final answer + tool events + trace
    S-->>CLI: Per-case score
  end
  CLI->>R: Scores + trace/cost records
  R-->>CLI: Policy comparison report
```

## Failure-flow requirements

Every failed attempt must be recorded with attempt number, provider/model, error category, duration, retryability, and whether the request continued through retry or fallback. Sensitive provider response bodies must not be copied wholesale into logs.
