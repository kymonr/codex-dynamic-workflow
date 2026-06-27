# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- Objective: Team Router skill/global reference sync and cross-thread information-format closeout alignment.
- State: local alignment updated, locally verified, reviewed, and accepted; global installed `codex-team-router` role handoff reference is synced from the repo copy.
- Last refreshed: 2026-06-27 skill reference sync and closeout alignment.
- Not done: commit, push, PR, merge, publish, release.

## Current Diff Surface

- `docs/workbench.md`
- `docs/superpowers/plans/2026-06-27-team-router-cross-thread-information-format.md`
- `docs/team-router/packages/ctr-20260627-info-format-impl.md`
- `tests/test_team_router.py`

Workspace-external sync:

- `C:\Users\Orz\.codex\skills\codex-team-router\references\role-handoff-and-review-package.md` copied from `skills/codex-team-router/references/role-handoff-and-review-package.md`.

## Verification Record

- `git status -sb`: clean before this task began.
- Global skill reference drift check before sync: only `references\role-handoff-and-review-package.md` differed between repo and `C:\Users\Orz\.codex\skills\codex-team-router`.
- `Copy-Item -LiteralPath 'D:\codex\Team Router\skills\codex-team-router\references\role-handoff-and-review-package.md' -Destination 'C:\Users\Orz\.codex\skills\codex-team-router\references\role-handoff-and-review-package.md' -Force`: pass.
- Implementation plan checkbox state changed from open to completed for the already-landed cross-thread information-format package.`r`n- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_does_not_claim_uncommitted_diff_when_used_as_current_record -v`: pass.`r`n- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 27 tests.`r`n- `py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v`: pass.`r`n- `py -m py_compile src\\team_router.py tests\\test_team_router.py`: pass.`r`n- `git diff --check`: pass; CRLF/LF warnings only for changed Markdown/test files.

## Review And Verification Gate

- Reviewer: pending in this turn.
- Verifier: pending in this turn after reviewer pass.

## Next Gate

- Run focused local validation after docs/package alignment.
- Dispatch or record reviewer/verifier closeout.
- Keep changes uncommitted unless the user separately authorizes commit.
