# P15 Orchestrator And Live API Adapter Workstream

Worktree: `C:\Users\scgee\OneDrive\Documents\Projects\federated_silo_agent_p15`

Branch: `codex/p15-orchestrator`

PR base: `short-contract` until `short-contract` is merged into `main`.

## Mission

Build the live orchestrator and message bus that wires built agents into a
session so the API/UI can drive the real mechanism instead of placeholders.

## Read First

- `AGENT_NOTES.md`
- `plan.md`, section P15
- `docs/architecture/0002-orchestrator-design.md`
- `backend/ui/api.py`
- `backend/ui/state.py`
- `backend/security/`
- Built agents: A1, A2, A3, F1, F3

## Inputs

- session actions from the control API
- signed messages between built agents
- replay cache
- route approvals
- DP ledger state
- audit channel

## Outputs

- live timeline events
- component snapshots
- audit events
- final investigation artifacts
- controlled probe results

## Expected Files

- orchestrator/message-bus module under `backend/`
- live adapters in `backend/ui/`
- integration tests
- frontend schema regeneration only if API contracts change

## Constraints

- Do not bypass security layers for UI convenience.
- Preserve one-shot/replay semantics for routed artifacts.
- Keep API endpoints typed through Pydantic models.
- Avoid becoming a second business-logic implementation. Orchestrator should call importable agents/services.
- F5 can remain optional at construction time if P13 is not merged yet.

## Acceptance

- Canonical session can proceed through currently built components.
- Each cross-boundary message verifies signature, freshness, replay, and route binding where applicable.
- UI snapshots show live state for built components.
- Placeholder status remains explicit for unavailable components.
- Probe traffic still enters through normal security and policy boundaries.

## Required Checks Before PR

```powershell
uv run pytest tests\test_ui_api.py tests\test_f1.py tests\test_a3.py -q
uv run pytest -q
cd frontend
npm run build
```

## Code-Assist Loop After PR

```powershell
uv run --project "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review" "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review\review.py" --base origin/main
```

Fix accepted findings, commit, and push each round.

## Launch Prompt

You are working in `federated_silo_agent_p15` on branch
`codex/p15-orchestrator`. Implement P15 orchestrator and live API adapters using
`plan.md`, `AGENT_NOTES.md`, `docs/architecture/0002-orchestrator-design.md`,
and `docs/workstreams/p15-orchestrator.md`. Keep the write scope focused.
Commit and push, open a PR against `short-contract`, then run the local
code-review harness and fix accepted findings until clean or only explicitly
declined cosmetic/style issues remain.

