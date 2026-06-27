# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- Objective: C package for workbench stale-state defense, visible role reuse/replacement, closeout readability, and reviewer/verifier gate wording.
- State: implementation in progress in isolated worktree `C:\Users\Orz\.codex\worktrees\d8f3\Team Router`.
- Current git truth: refresh from `git status -sb --untracked-files=all` and `git diff --name-only` before reporting status. Do not copy older ahead/behind, diff-surface, next-gate, or role-callback claims into the current state without refreshing them.
- Current next gate: local C-package verification, then local commit in this isolated worktree, then reviewer gate.
- Not done: reviewer gate, verifier acceptance, push, PR, merge, publish, release.

## Current Diff Surface

Current package diff is intentionally limited to the C package surface:

- `tests/test_team_router.py`
- `docs/workbench.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/reviewer-gate.md`
- `skills/codex-team-router/references/manual-orchestration.md`

## Verification Record

Current verification:

- RED check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_manager_and_manual_docs_cover_closeout_reporting_and_compounding_decision tests.test_team_router.TestTeamRouterSkillDoc.test_conditional_reviewer_docs_cover_role_policy_reuse_and_direct_return tests.test_team_router.TestTeamRouterSkillDoc.test_manager_mode_docs_cover_standing_role_reuse_policy -v` failed as expected before the docs were updated.
- `py -m py_compile tests\test_team_router.py`: pass.
- `py -m unittest tests.test_team_router -v`: pass, 237 tests.
- `git diff --check`: first run found only new blank lines at EOF; fixed before final verification rerun.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous Manager Intake optimization records mentioned lifecycle files, global skill sync, and completed local verification. Those records are historical and do not describe the current C-package diff surface.
- Older ahead/behind, stale current diff surface, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git diff --name-only`, and the latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library. This C package does not change runtime adapter behavior.
- Real live orchestration still depends on a parent host adapter that can provide callable Codex thread tools such as `list_projects`, `create_thread`, `send_message_to_thread`, `read_thread`, and `set_thread_title`, plus the current parent thread id for `parent_thread_id`.
- Watcher/heartbeat behavior still depends on a host scheduler or automation loop calling `watch_team_task_with_adapter()` at `firstCheckAt` / `nextAllowedReadAt`.

## Review And Verification Gate

- Local verification: passed for this C package.
- Reviewer gate: required after executor callback because this is a Team Router process/rule self-change.
- Verifier gate: final acceptance only after reviewer pass or reviewer-required rework is satisfied.
