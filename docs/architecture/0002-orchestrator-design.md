# ADR 0002: Orchestrator Design for P15

## Status

Proposed (to be marked Accepted when P15 implementation begins).

Related: `plan.md` §P15, `AGENT_NOTES.md` workstream P15, ADR 0001.

## Context

P10–P14 build the federated AML agents (A1, A2, A3, F1, F2, F3, F4, F5) and the F6 policy actor in isolation. Each has focused tests against fixture inputs, but no agent is invoked from the live demo session today: `backend/ui/state.py::step_session` and `run_until_idle` are P9a placeholders that emit a "No live orchestrator yet" timeline event.

P15's job is to wire the built agents into a live session so a judge pressing the Step button in the console actually advances the demo through real cross-agent messages — security envelopes verified at each boundary, timeline and component snapshots updating from real runtime state.

This is the highest-risk workstream remaining. It is also the demo-correctness gate: nothing the judge clicks works end-to-end without it. AGENT_NOTES.md gives P15 only a paragraph, which is dramatically less than it needs. This ADR exists so the P15 implementer doesn't re-litigate the design while burning hackathon hours.

## Decision

### Turn semantics

One **Step** advances the session by exactly one **agent turn**: one agent's `run()` invocation, producing zero or more outbound messages. Agents do not chain themselves into multi-turn sequences; the orchestrator schedules the next agent based on session state after each turn completes.

Why per-turn rather than per-message-batch:
- Visible progress in the UI timeline at human-readable cadence
- Smaller blast radius when one agent's turn fails
- Easier to demo: each Step click corresponds to one named agent acting

**Run-until-idle** keeps advancing turns until a terminal condition:
- F4 emits a `SARDraft` (canonical success terminal)
- F4 emits a `SARContributionRequest` and no live A2 turn can satisfy the request (terminal with note)
- F5 produces a `human_review_required=True` finding (terminal with explicit halt)
- The state machine has no scheduled next turn (idle)
- A defensive turn-count cap (default 50) trips, indicating a state-machine bug

### Message bus shape

**In-process direct method calls with envelope wrapping at each trust-domain boundary.** No queue, no thread pool, no pub/sub.

The orchestrator holds references to all agent instances. When a turn runs:

1. Build the input message from the predecessor turn's outputs.
2. If the receiving agent is in a different trust domain than the sender, wrap the message in a signed `MessageEnvelope` using the sender's signing identity from the principal allowlist.
3. Call the receiving agent's `run(input_message)`.
4. Record the outbound message and any audit events on the session.
5. Update session state and append a timeline event.

Same trust domain → bare message (still Pydantic-validated, no signing roundtrip). Cross-domain → signed envelope, recipient verifies on receipt (existing security envelope helpers handle this).

Why not a pub/sub message bus: a single demo session has no concurrency model that would benefit from queues. The orchestrator is already the natural decision point and turning it into a publisher adds indirection without gain. If the hackathon evolves into a real product, the orchestrator's `run_turn` becomes a publisher in a real bus without touching agents.

### Concurrency model

**Single-threaded turn execution within a session.** The existing `session.lock` (`threading.RLock`) is held during a turn.

Probes continue to run through `run_probe` / `_commit_probe_outcome` on a separate path; that path acquires `session.lock` only briefly during commit, so a long-running orchestrator turn and a quick probe do not contend in practice. If they do contend, the orchestrator turn wins (it's already holding the lock); the probe waits, then commits.

Multiple sessions can advance concurrently — each has its own lock. A single session is single-threaded by design.

### State machine

The orchestrator's turn-scheduling logic is a state machine over `DemoSessionRuntime` state, expressed as a single function:

```python
def next_turn(session: DemoSessionRuntime) -> AgentTurn | None
```

returning the next `AgentTurn` (a dataclass of `agent_id` + `input_message`) or `None` for idle.

Canonical flow:

```
idle / first step
  -> A1 monitor turn (per-bank, scans for alerts)
A1 emits Alert
  -> A2 triage turn (Sec314bQuery or drop)
A2 emits Sec314bQuery
  -> F6 (investigator-domain policy) turn (approve / refuse)
F6 approves
  -> F1 coordinator turn (route plan)
F1 routes to per-bank A3 fan-out
  -> per-bank: F6 (bank-domain policy) -> A3 (P7 stats) -> F6 (federation-domain policy on response)
A3 returns BankAggregate
  -> F1 collects; when all banks responded, schedules F2 + F3 in parallel
F2 and F3 emit results
  -> F4 SAR drafter turn
F4 emits SARDraft (or SARContributionRequest, which loops back to A2)
  -> F5 audit review turn
F5 emits AuditReviewResult
  -> terminal
```

"In parallel" above is conceptual — in single-threaded execution, F2 and F3 turns are scheduled sequentially, but neither depends on the other so order is irrelevant.

### Probe compatibility

Probes are injected at security-boundary mechanisms (signing, envelope, replay, route_approval, dp_ledger, lobster_trap, litellm) and do NOT participate in the agent turn flow.

When a probe runs during an orchestrator session:
- Probe path commits its result under `session.lock` (existing pattern), waiting briefly if a turn is mid-flight.
- After commit, the probe is visible in the timeline and component snapshots.
- The orchestrator's next turn sees the updated state (e.g. a probe that exhausts the DP budget will cause the next F1 turn to see `route_approval.status=blocked`).

Probes can demonstrate that an attacker bypassing the orchestrator still gets caught by the security envelope / policy layer. This is the adversarial story the demo sells.

### Live API adapter

`backend/ui/state.py::step_session` becomes:

```python
def step_session(self, session_id: UUID) -> SessionSnapshot:
    session = self._session(session_id)
    with session.lock:
        turn = self._orchestrator.next_turn(session)
        if turn is None:
            session.append_event(idle_event)
            return session.to_snapshot(self.component_readiness())
        self._orchestrator.run_turn(session, turn)
        return session.to_snapshot(self.component_readiness())
```

`run_until_idle` loops `next_turn` + `run_turn` until `None`, with the 50-turn defensive cap.

Component snapshots already serve live data when a component has real state; no changes to snapshot endpoints. The "live state vs placeholder" transition happens automatically as agents start producing real outputs.

## File layout

```
backend/orchestrator/
  __init__.py           # public exports
  runtime.py            # Orchestrator class; run_turn entry point
  state_machine.py      # next_turn(session) -> AgentTurn | None
  agents.py             # AgentRegistry; per-trust-domain agent instances
  envelope.py           # cross-domain wrap/unwrap helpers
tests/
  test_orchestrator_state_machine.py   # next_turn unit tests
  test_orchestrator_run_turn.py        # single-turn end-to-end against stubs
  test_orchestrator_canonical_run.py   # S1 ring → SARDraft full flow
```

`DemoControlService.__init__` constructs an `Orchestrator` and stores it as `self._orchestrator`.

## Implementation order

Land in this order so each commit is independently shippable:

1. `backend/orchestrator/agents.py` — registry + lookup. Tests cover construction and per-trust-domain lookup.
2. `backend/orchestrator/envelope.py` — wrap/unwrap helpers reusing `backend.security` primitives. Tests cover round-trip + signature failure paths.
3. `backend/orchestrator/state_machine.py` — `next_turn`. Tests cover each state transition with a constructed session.
4. `backend/orchestrator/runtime.py` — `Orchestrator.run_turn`. Tests cover one turn end-to-end against a stub agent.
5. Replace placeholders in `backend/ui/state.py`. Tests cover Step / run-until-idle via the FastAPI client.
6. Canonical-run integration test (S1 ring → `SARDraft` emission). This is the demo-correctness gate.

## What this is NOT

- Not a distributed system. Single Python process, single thread per session.
- Not a real message broker. No durability beyond the in-memory replay cache.
- Not a workflow engine. The state machine is hard-coded for the AML demo; generalizing is out of scope for the hackathon.
- Not a scheduler. No priorities, no fairness, no deadlines. `next_turn` returns the next agent in canonical order.

## Acceptance criteria

Restated from `plan.md` §P15:

- Canonical run proceeds through A1/A2/F1/A3/P7/F3/F2/F4/F5/F6.
- Each cross-boundary message verifies signature, freshness, replay, and route binding where applicable.
- UI snapshots show live state, not placeholder state, for built components.
- Probe traffic still enters through normal security and policy boundaries.

## Consequences

**Positive:**
- The judge console becomes a live demo surface rather than a placeholder grid.
- F6 policy can be exercised at every cross-trust-domain boundary, giving the adversarial story real teeth.
- Probes and orchestrator turns compose without interfering (different code paths, brief lock overlap only at commit).

**Negative:**
- The state machine is hard-coded for one demo flow. Variant scenarios (S2 layering, S3 alternate ring) need their own state-machine branches or per-scenario state-machine factories. Acceptable for hackathon scope; tech debt afterward.
- Single-threaded turn execution means a slow LLM call blocks the session until completion. Mitigation: turn-time budget; agents that need >5s are P14/P15's job to optimize, not P9b's.
- Live LLM calls cost money during the demo. Mitigation: `stub_mode` selection at session creation; the canonical demo session uses real LLM, dev sessions can use stubs.

## Risks

- **State-machine completeness:** if `next_turn` misses a transition, the demo silently goes idle. Mitigation: explicit terminal-condition tests covering every branch.
- **Stub-vs-live transitions:** agent tests use `stub_mode=True`; the orchestrator must construct them with real `LLMClient` instances unless the session explicitly requests stub mode. Mitigation: `LLMClientConfig` passed through from session creation request, with stub mode driven by a session-level field so tests can still pin to stubs.
- **Per-domain F6 instantiation:** each trust domain has its own signed F6 instance. The orchestrator must route `PolicyEvaluationRequest` to the right per-domain F6 based on the sender's trust domain. Mitigation: covered in the AgentRegistry (`backend/orchestrator/agents.py`); lookup is `(role, trust_domain) -> Agent`.
