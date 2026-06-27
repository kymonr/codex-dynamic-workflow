# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- Objective: Team Router role-task content Chinese default skill rule plus direct-return receipt hardening follow-up.
- State: local implementation complete, validated, reviewer-approved, verifier-accepted, and global installed skill reference synced; previous helper-test commit `c9d41b3` is local-only and `master` is ahead of `origin/master` by 1; this combined diff is not committed.
- Last refreshed: 2026-06-27 role task-content Chinese skill rule verifier acceptance.
- Not done: commit, push, PR, merge, publish, release.

## Current Diff Surface

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/workbench.md`

Workspace-external sync:

- Global installed skill reference synced: `skills/codex-team-router/references/role-handoff-and-review-package.md` copied to `C:\Users\Orz\.codex\skills\codex-team-router\references\role-handoff-and-review-package.md`; SHA256 `EB668B9F66B44ED4ADA8030F493BD6575F937E94FBCFB3E19B143ECE6753322A` matches repo copy.

## Verification Record

- `git status -sb --untracked-files=all` before implementation: `## master...origin/master [ahead 1]`.
- CodeGraph review: `_capture_reviewer_review_from_manager_inbox()` and `_capture_verifier_verdict_from_manager_inbox()` lacked direct helper-level coverage; `_direct_return_protocol_message()` returned metadata for the last candidate rather than the actual marker-bearing candidate when a later same-source chat message existed.
- `py -m unittest tests.test_team_router.TestTeamRouterProtocol.test_direct_return_protocol_message_uses_marker_bearing_message_metadata tests.test_team_router.TestTeamRouterProtocol.test_direct_return_protocol_message_filters_anchor_and_source_thread tests.test_team_router.TestTeamRouterManagerIntegration.test_capture_reviewer_direct_return_from_manager_inbox_records_receipt tests.test_team_router.TestTeamRouterManagerIntegration.test_capture_verifier_direct_return_from_manager_inbox_is_idempotent tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v`: pass, 5 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_team_task_prefers_manager_inbox_direct_return_callback tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_captures_reviewer_direct_return_and_sends_verifier tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_team_task_prefers_manager_inbox_direct_return_verdict tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_team_task_ignores_malformed_manager_inbox_callback_and_uses_self_thread_fallback tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_team_task_ignores_malformed_manager_inbox_verdict_and_uses_self_thread_fallback -v`: pass, 5 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterProtocol -v`: pass, 15 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 27 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`: pass, 140 tests.
- `py -m py_compile src\team_router.py tests\test_team_router.py`: pass.
- `git diff --check`: pass.
- `py -m unittest tests.test_team_router`: pass, 230 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v`: pass, 2 tests after task-content Chinese skill-rule edit.
- `py -m py_compile src\team_router.py tests\test_team_router.py`: pass after task-content Chinese skill-rule edit.
- `git diff --check`: pass after task-content Chinese skill-rule edit; CRLF warning only for `tests/test_team_router.py`.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 27 tests after task-content Chinese skill-rule edit.
- `Copy-Item -LiteralPath 'D:\codex\Team Router\skills\codex-team-router\references\role-handoff-and-review-package.md' -Destination 'C:\Users\Orz\.codex\skills\codex-team-router\references\role-handoff-and-review-package.md' -Force`: pass.
- Repo/global role-handoff reference SHA256: `EB668B9F66B44ED4ADA8030F493BD6575F937E94FBCFB3E19B143ECE6753322A` matches.
- Reviewer direct-return for `ctr-20260627-task-content-chinese-skill`: pass, `requiredChanges: none`.
- Verifier direct-return for `ctr-20260627-task-content-chinese-skill`: pass, `requiredChanges: none`.

## Review And Verification Gate

- Reviewer: `ctr-20260627-task-content-chinese-skill` direct-return review passed; `requiredChanges: none`.
- Verifier: `ctr-20260627-task-content-chinese-skill` direct-return verdict passed; `requiredChanges: none`.

## Next Gate

- Commit this new local diff only after explicit commit authorization.
- Do not push/PR/merge unless the user separately authorizes that release/closeout step.
