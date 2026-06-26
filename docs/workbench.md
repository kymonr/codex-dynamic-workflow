# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- Objective: harden Team Router workflow around manager write boundaries, lightweight role routing, proactive role return, bounded CONTROL closeout, and persistent project records.
- State: uncommitted local diff only.
- Last refreshed: 2026-06-26 review-fix pass for compounding/workbench recording findings.
- Not done: stage, commit, push, PR, publish, release.

## Current Diff Surface

- `docs/compounding.md`
- `docs/workbench.md`
- `docs/runbooks/codex-team-router-live-orchestration.md`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/agent-assist-policy.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manual-orchestration.md`
- `skills/codex-team-router/references/role-closeout.md`
- `src/team_router.py`
- `tests/test_team_router.py`

## Verification Record

- `py -m py_compile src\team_router.py tests\test_team_router.py`: pass
- `git diff --check`: pass; observed CRLF/LF normalization warning for `docs/runbooks/codex-team-router-live-orchestration.md`
- Focused unittest for protocol/docs closeout coverage: pass
- Review-fix focused unittest for compounding/workbench recording: pass
- Expanded related unittest classes: pass

## Next Gate

- Keep this diff unstaged until the user asks for stage/commit.
- If more workflow rules are added, update `docs/compounding.md` for durable lessons and this workbench for current-task state.