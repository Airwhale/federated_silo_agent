# P18 Judge Console Polish Workstream

Worktree: `C:\Users\scgee\OneDrive\Documents\Projects\federated_silo_agent_p18`

Branch: `codex/p18-ui-polish`

PR base: `short-contract` until `short-contract` is merged into `main`.

## Mission

Polish the existing P9b browser frame into the final judge-facing console,
without bypassing the API or inventing backend state.

## Read First

- `AGENT_NOTES.md`
- `plan.md`, section P18
- `frontend/src/`
- `backend/ui/snapshots.py`
- `backend/ui/api.py`
- `tests/test_ui_api.py`

## Inputs

- P9a/P15 API snapshots
- timeline events
- attack/probe results
- model route metadata
- policy, DP, signing, replay, route approval, and audit state

## Outputs

- polished browser UI views
- inspector panels
- attack lab controls
- demo-ready state displays

## Expected Files

- `frontend/src/`
- generated API schema only if backend API changes
- UI smoke scripts or tests if practical
- minimal backend snapshot changes only if a real display gap exists

## Constraints

- Do not add a landing page. Keep the operational console as the first screen.
- Do not bypass backend trust decisions.
- Keep inputs and outputs briefly explained without consuming too much screen space.
- Do not expose secrets, private keys, raw customer names, or raw account identifiers.
- Avoid one-note palettes and oversized marketing composition.

## Acceptance

- Judges can inspect every trust domain and built component.
- Not-built components are clearly labeled.
- Attack lab can target relevant nodes without privileged bypasses.
- Each input/output has one or two brief helper sentences.
- `npm run build` passes.

## Required Checks Before PR

```powershell
cd frontend
npm run build
cd ..
uv run pytest tests\test_ui_api.py -q
```

Run full tests if backend contracts change:

```powershell
uv run pytest -q
```

## Code-Assist Loop After PR

```powershell
uv run --project "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review" "C:\Users\scgee\OneDrive\Documents\Projects\local-gemini-code-review\review.py" --base origin/main
```

Fix accepted findings, commit, and push each round.

## Launch Prompt

You are working in `federated_silo_agent_p18` on branch
`codex/p18-ui-polish`. Polish the judge console using `plan.md`,
`AGENT_NOTES.md`, and `docs/workstreams/p18-ui-polish.md`. Keep backend changes
minimal and typed. Commit and push, open a PR against `short-contract`, then run
the local code-review harness and fix accepted findings until clean or only
explicitly declined cosmetic/style issues remain.

