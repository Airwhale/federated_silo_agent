# ADR 0001: Short Contract Pass Before Parallel Agent Work

## Status

Accepted

## Context

The next work can be parallelized across F4 SAR drafting, F5 compliance audit,
and per-domain F6 policy/Lobster Trap integration. Those components all touch
shared protocol surfaces: message envelopes, refusal or policy decisions, audit
records, and UI observability. If workers define those shapes independently,
they will create schema drift and merge conflicts in `shared/messages.py`,
`shared/enums.py`, plan documentation, and UI snapshots.

## Decision

Before parallel implementation starts, define a short shared contract pass:

- F4 receives `SARAssemblyRequest` and can return `SARContributionRequest`
  when mandatory SAR inputs are missing.
- F5 receives `AuditReviewRequest` and returns `AuditReviewResult` with typed
  `ComplianceFinding` records.
- F6 is a signed per-trust-domain policy actor. It receives
  `PolicyEvaluationRequest` and returns `PolicyEvaluationResult` with typed
  `PolicyRuleHit` records.
- F4, F5, and F6 cross-node traffic uses the existing signed message envelope.
- F6 observes policy-relevant content and metadata, but cannot mutate signing,
  replay, route approvals, DP ledgers, or A3 primitive decisions.

The pass adds strict Pydantic models and contract tests only. It does not build
business logic, live Lobster Trap adapters, agent prompts, or orchestrator
wiring.

## Consequences

Parallel workers can own disjoint implementation files while consuming the same
shared contracts. Changes to the shared contracts remain possible, but should be
treated as coordination events because they affect multiple future agents and
the UI/API surface.

This adds a small amount of placeholder surface area before implementation. The
tradeoff is intentional: a few stable boundary models are cheaper than resolving
incompatible assumptions after several workers have built against them.
