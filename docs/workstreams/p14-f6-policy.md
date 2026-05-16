# P14 F6 Policy Adapter And Lobster Trap Workstream

Worktree: `C:\Users\scgee\OneDrive\Documents\Projects\federated_silo_agent_f6_policy`

Branch: `codex/p14-f6-policy`

PR base: `short-contract` until `short-contract` is merged into `main`.

## Mission

Build the Python AML policy adapter and local Lobster Trap integration behind
the F6 policy actor contract.

## Read First

- `AGENT_NOTES.md`
- `plan.md`, section P14
- `shared/messages.py`: `PolicyEvaluationRequest`, `PolicyEvaluationResult`, `PolicyRuleHit`
- `infra/lobstertrap/base_policy.yaml`
- P0 proxy smoke scripts under `scripts/`
- `backend/agents/llm_client.py`

## Inputs

- `PolicyEvaluationRequest`
- signed message metadata
- safe content summaries
- content hashes
- Lobster Trap verdicts
- AML dictionaries or redaction patterns

F6 should not receive private keys, API keys, raw transactions, raw account
identifiers, or mutable handles to route approvals, replay caches, DP ledgers,
or A3 primitives.

## Outputs

- `PolicyEvaluationResult`
- `PolicyRuleHit` records
- normalized policy `AuditEvent` records where appropriate

## Expected Files

- `backend/policy/`
- `infra/lobstertrap/aml_overlay_policy.yaml` only if verified against local LT
- `scripts/aml_policy_smoke.py` if useful
- `tests/test_aml_policy.py`
- UI/API readiness updates only if needed for policy visibility

## Constraints

- F6 is per trust domain, not one central singleton.
- Top-level decision must match the strongest rule-hit decision.
- Redaction counts must match redacted fields in rule hits.
- No policy output or audit record may leak raw customer names, private keys, API keys, or raw account IDs.
- F6 observes and evaluates. It does not mutate signing, replay, route approvals, DP ledgers, or A3 primitive decisions.

## Acceptance

- Prompt injection and private-data extraction produce typed block decisions.
- Customer-name leakage produces redaction or block according to the policy rule.
- Role/route metadata violations produce typed block decisions.
- Safe content produces allow decisions with no rule hits.
- Local smoke path exercises the real LT boundary when available.

## Required Checks Before PR

```powershell
uv run pytest tests\test_aml_policy.py tests\test_messages.py -q
uv run ruff check backend\policy tests\test_aml_policy.py
```

Run full tests if shared code changes:

```powershell
uv run pytest -q
```

## Code-Assist Loop After PR

```powershell
uv run --project "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review" "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review\review.py" --base origin/main
```

Fix accepted findings, commit, and push each round.

## Launch Prompt

You are working in `federated_silo_agent_f6_policy` on branch
`codex/p14-f6-policy`. Implement P14 F6 policy adapter and Lobster Trap
integration using `plan.md`, `AGENT_NOTES.md`, and
`docs/workstreams/p14-f6-policy.md`. Keep the write scope focused. Commit and
push, open a PR against `short-contract`, then run the local code-review
harness and fix accepted findings until clean or only explicitly declined
cosmetic/style issues remain.

