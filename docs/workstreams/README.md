# Parallel Workstream Setup

These files are launch briefs for the parallel agent branches created from
`short-contract`.

Read order for every agent:

1. `AGENT_NOTES.md`
2. `plan.md`, especially the relevant milestone section
3. The workstream file below for your branch
4. Existing tests for adjacent built components

Branches and worktrees:

| Worktree | Branch | Brief |
|---|---|---|
| `federated_silo_agent_f2` | `codex/p11-f2` | `p11-f2.md` |
| `federated_silo_agent_f4` | `codex/p12-f4` | `p12-f4.md` |
| `federated_silo_agent_f5` | `codex/p13-f5` | `p13-f5.md` |
| `federated_silo_agent_f6_policy` | `codex/p14-f6-policy` | `p14-f6-policy.md` |
| `federated_silo_agent_p15` | `codex/p15-orchestrator` | `p15-orchestrator.md` |
| `federated_silo_agent_p18` | `codex/p18-ui-polish` | `p18-ui-polish.md` |

PR base:

- Use `short-contract` as the base branch until it is merged into `main`.
- Retarget to `main` only after `main` contains the P10a contracts.

Review loop:

1. Implement the workstream.
2. Run focused tests and any required build checks.
3. Commit and push the branch.
4. Open a PR.
5. Run the local code-review harness.
6. Fix accepted findings, commit, and push each round.
7. Stop when review is clean or only explicitly declined cosmetic/style items remain.

