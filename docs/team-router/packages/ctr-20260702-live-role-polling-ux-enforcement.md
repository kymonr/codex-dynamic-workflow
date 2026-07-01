# ctr-20260702-live-role-polling-ux-enforcement

## Package Metadata

- taskId: `ctr-20260702-live-role-polling-ux-enforcement`
- branch: `master`
- permission: small local package for live role polling UX enforcement. Includes pure helper logic, focused tests, package/workbench updates, local verification, and local commit. Excludes real Codex thread tools, live role dispatch, broker/adapter/scheduler startup, push, PR, merge, deploy, publish/release, and global skill sync unless separately authorized.
- scope: make manager polling/status output testable for quiet active-role waits, no repeated unchanged active narration, and strict respect for `nextAllowedReadAt`.

## Objective

Move the live role polling UX rule from docs into a deterministic helper. The manager should avoid early reads before `nextAllowedReadAt`, suppress unchanged active-status narration, and report only meaningful status changes, timeout/blocker, or completion signals.

## Boundary

Included:

- Add focused tests for early read suppression, unchanged active-status report suppression, and status-change reporting.
- Add a pure `manager_polling_status_update()` helper in watcher runtime.
- Export the helper through `src/team_router.py` for manager/facade use.
- Update workbench/package current truth and local verification notes.

Excluded:

- No real `read_thread`, `send_message_to_thread`, `create_thread`, `set_thread_title`, or other Codex app thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No changes to parser marker schema, registry/ledger transitions, direct-return receipt validation, or production scheduling.
- No push, PR, merge, deploy, publish/release, or global skill sync unless separately authorized.

## Acceptance Criteria

- Early scheduled polling before `nextAllowedReadAt` returns `shouldRead: false` and `shouldReport: false`.
- Allowed reads with unchanged active status return `shouldRead: true` and `shouldReport: false`.
- Status changes return `shouldReport: true` with previous/current status fields.
- Focused tests pass without calling real thread tools.
- `truth_check` and `closeout_check` exit 0 with `staleClaims: []` after local closeout.

## Verification Record

- RED focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_reports_status_changes_only -v` first failed with `AttributeError: module 'team_router' has no attribute 'manager_polling_status_update'`.
- GREEN focused tests after implementation: same command -> Ran 3 tests OK.
- Focused regression suite: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_reports_status_changes_only tests.test_team_router.TestTeamRouterState.test_role_read_allowed_suppresses_early_fallback_reads tests.test_team_router.TestTeamRouterState.test_role_read_allowed_enforces_last_read_five_minute_interval tests.test_team_router.TestTeamRouterState.test_convergence_prompt_disallowed_while_role_status_is_active tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 7 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-ux py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.

## Review And Verification Gate

Current next gate: none after local commit. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.