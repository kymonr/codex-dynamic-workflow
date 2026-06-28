# Team Router Handoff Package: ctr-20260628-anchor-and-closeout-freshness-fix

## Task Summary / 任务摘要

- taskId: `ctr-20260628-anchor-and-closeout-freshness-fix`
- objective: P0 cleanup for malformed direct-send anchor text and stale closeout/verifier-gate wording after verifier pass.
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: docs/tests cleanup only; no runtime edit, no commit, no push, no PR, no release.

## Changes / 改动

- Fixed malformed direct-send anchor text in `manager-mode.md` so it uses `threadId=<returnThreadId>` with backticks instead of malformed `hreadId` text.
- Refreshed `docs/workbench.md` so the previous role-request package records reviewer accepted/pass and verifier accepted/pass.
- Refreshed `docs/team-router/packages/ctr-20260628-role-request-direct-send-and-waiting-fix.md` so remainingTodos is none for the local package and no longer says verifier acceptance remains pending.
- Added focused tests covering malformed anchor text and closeout freshness.

## Verification / 验证

- RED: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_anchor_and_closeout_freshness_after_verifier_pass -v` failed before docs/package updates because this package file did not exist.
- GREEN focused check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_anchor_and_closeout_freshness_after_verifier_pass -v`: pass; `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v`: pass.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 36 tests.
- `git diff --check`: pass; Git printed CRLF/LF normalization warnings for existing working-copy files, with no whitespace errors.

## Excluded Changes / 未纳入改动

- No runtime behavior changes.
- No edits to `src/team_router.py`.
- No README, runbook, global skill, commit, push, PR, merge, publish, or release.
- P1 runtime generator wording remains out of scope.

## Remaining Todos / 剩余事项

- remainingTodos: none for this local package; local closeout/commit only if explicitly authorized.
