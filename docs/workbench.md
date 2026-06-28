# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- taskId: `ctr-20260628-anchor-and-closeout-freshness-fix`
- Objective: Clean up malformed direct-send anchor wording and refresh closeout state after verifier pass.
- State: executor local-package cleanup in the main workspace; anchor cleanup and closeout freshness after verifier pass.
- Prior package status: `ctr-20260628-role-request-direct-send-and-waiting-fix` reviewer accepted/pass and verifier accepted/pass.
- Current git truth: refresh from `git status -sb --untracked-files=all` and `git diff --name-only` before reporting status. Do not copy older ahead/behind, diff-surface, next-gate, or role-callback claims into the current state without refreshing them.
- Current next gate: local closeout/commit only if explicitly authorized.
- Not done: commit, push, PR, merge, publish, release.

## Current Diff Surface

Current package diff for `ctr-20260628-anchor-and-closeout-freshness-fix` is intentionally limited to:

- `tests/test_team_router.py`
- `docs/workbench.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manual-orchestration.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `skills/codex-team-router/references/direct-return.md`
- `docs/team-router/packages/ctr-20260628-role-request-direct-send-and-waiting-fix.md`
- `docs/team-router/packages/ctr-20260628-anchor-and-closeout-freshness-fix.md`

## Verification Record

Current verification:

- RED check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_anchor_and_closeout_freshness_after_verifier_pass -v` failed before docs/package updates because `docs/team-router/packages/ctr-20260628-anchor-and-closeout-freshness-fix.md` did not exist.
- GREEN focused check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_anchor_and_closeout_freshness_after_verifier_pass -v`: pass; `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v`: pass.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 36 tests.
- `git diff --check`: pass; Git printed CRLF/LF normalization warnings for existing working-copy files, with no whitespace errors.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates. Remaining local work is closeout/commit only if explicitly authorized.
- Previous `ctr-20260628-live-capability-state-fix` records clarified exposed app tools vs missing Python adapter/runtime orchestration. That remains true but is not the current task.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git diff --name-only`, and the latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library. This package does not change runtime behavior.
- Cleanup scope is limited to malformed `hreadId` anchor text, current workbench freshness, and the accepted/pass status in the previous role-request package.
- No P1 runtime generator wording change is included.

## Review And Verification Gate

- Reviewer gate: accepted/pass for `ctr-20260628-role-request-direct-send-and-waiting-fix` and `ctr-20260628-anchor-and-closeout-freshness-fix`; requiredChanges: none.
- Verifier gate: verifier accepted/pass for `ctr-20260628-role-request-direct-send-and-waiting-fix` and `ctr-20260628-anchor-and-closeout-freshness-fix`; remaining local work is closeout/commit only if explicitly authorized.
- Next gated step: local closeout/commit only if explicitly authorized.
