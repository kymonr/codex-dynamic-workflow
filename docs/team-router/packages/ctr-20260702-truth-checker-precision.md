# ctr-20260702-truth-checker-precision

## Package Metadata

- taskId: `ctr-20260702-truth-checker-precision`
- branch: `master`
- permission: small local package for Team Router truth checker precision. Includes stale detector logic, focused tests, package/workbench updates, local verification, and local commit. Excludes push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, and global skill sync unless separately authorized.
- scope: make `truth_check` distinguish real current pending reviewer/verifier gates from completed or historical evidence text that merely mentions reviewer/verifier.

## Objective

Reduce false-positive current-truth friction after package closeout. A clean/synced repo should still flag explicit current pending gates such as `Current next gate: reviewer/verifier focused acceptance`, but it should not flag completed-package or historical evidence sentences just because they contain the literal `reviewer/verifier` marker.

## Boundary

Included:

- Add a focused regression test for completed evidence text mentioning `reviewer/verifier`.
- Keep the existing stale current-state test that catches real pending reviewer/verifier gates.
- Narrow `_first_pending_gate_line()` so completed/historical evidence context does not count as a pending gate.
- Update workbench/package current truth and local verification notes.

Excluded:

- No live role dispatch or Codex thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No changes to parser marker schema, registry/ledger state transitions, direct-return behavior, or production scheduling.
- No push, PR, merge, deploy, publish/release, production broker startup, or global skill sync unless separately authorized.

## Acceptance Criteria

- `find_stale_state_claims()` returns no stale claim for clean/synced current sections that say completed package evidence mentioned `reviewer/verifier`.
- `find_stale_state_claims()` still flags an explicit current pending gate such as `Current next gate: reviewer/verifier focused acceptance` when the repo/global skill are clean/synced.
- `truth_check` and `closeout_check` exit 0 with `staleClaims: []` after local closeout.

## Verification Record

- RED focused test: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_truth_check_allows_completed_evidence_mentions_reviewer_verifier -v` first failed because completed evidence was reported as `current-state claims pending reviewer/verifier gate while live git/skill truth is clean/synced`.
- GREEN focused regression suite: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_truth_check_allows_completed_evidence_mentions_reviewer_verifier tests.test_team_router.TestTeamRouterState.test_truth_check_detects_stale_current_state_when_clean_synced tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_clean_synced_neutral_current_sections -v` -> Ran 3 tests OK.
- Review rework: narrowed the completed/historical exception from whole-line keyword matching to completed/historical line prefixes, then added `test_truth_check_flags_current_gate_even_when_it_mentions_historical_records` to keep real current gates flagged.
- Focused doc/status suite: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_truth_check_allows_completed_evidence_mentions_reviewer_verifier tests.test_team_router.TestTeamRouterState.test_truth_check_flags_current_gate_even_when_it_mentions_historical_records tests.test_team_router.TestTeamRouterState.test_truth_check_detects_stale_current_state_when_clean_synced tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_clean_synced_neutral_current_sections tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 5 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-truth-precision py -B -m py_compile src\team_router_status_tools.py tests\test_team_router.py` -> exit 0 after default `src\__pycache__` compile hit Windows access denied.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.

## Review And Verification Gate

Current next gate: none after local commit. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.