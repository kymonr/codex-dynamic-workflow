# ctr-20260628-role-thread-readiness-status

## Objective

Add a read-only manager-facing role-thread readiness/status surface so Team Router can explain whether role-thread evidence is missing, not visible, actively running, waiting for protocol output, or already returned the expected protocol marker.

## Completed Scope

- Added `classify_role_thread_status` and `classify_role_thread_status_snapshot` to `scripts/team_router_doctor.py`.
- Added `--role-status-json <path>` to `scripts/team_router_doctor.py`.
- Added `roleThreadStatus` to the doctor JSON report.
- Locked the status vocabulary: `missing`, `created_not_visible`, `visible_waiting`, `active_wait`, and `protocol_returned`.
- Updated quality-gate docs and workbench current-state records.

## Explicit Non-Scope

- No changes to `src/team_router.py` dispatch, watcher cadence, registry, ledger, or protocol parsing.
- No automatic `read_thread`, continuous polling, thread creation, message sending, or live role dispatch.
- No push, PR, merge, deploy, publish, or release in this package.

## Verification Evidence

- RED classifier: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_role_thread_readiness_states -v` failed before implementation.
- GREEN classifier: same command passed after the pure classifier was added.
- RED CLI: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot -v` failed before `--role-status-json` existed.
- GREEN CLI: focused classifier + CLI tests passed after doctor integration.
- RED docs gate: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots -v` failed before quality-gate documentation was added.
- GREEN docs gate: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> OK.
- Focused state tests: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 41 tests OK.
- Focused docs tests: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 39 tests OK.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- Final full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m unittest tests.test_team_router` -> Ran 274 tests OK.
- Final whitespace check: `git diff --check` -> exit 0 with CRLF/LF warnings only.
- Post-sync truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `gitStatusShort: []`, `diffFiles: []`, `skillSync.status: match`, branch `master...origin/master [ahead 2]`.
- Post-sync doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: clean_synced`, `orchestrationStatus: manual_only`, `roleThreadStatus: {mode: read-only, roles: []}` by default.
- Post-sync skill sync check: `py -B scripts\team_router_skill_sync_check.py --check` -> `status: match`.

## Reviewer And Verifier

- Reviewer: thread `019f0ea7-0ad7-7931-9e2e-89c13401c14a` first returned `needs_rework` because this package doc and `docs/workbench.md` still described local verification as pending. Required current-state documentation rework was applied, then reviewer re-review returned `pass` with `requiredChanges: none`.
- Verifier: thread `019f0eaa-ac70-7831-9b12-5d7f28686c72` first returned `needs_rework` on stale reviewer-gate wording; after docs rework and tests, verifier re-check returned `pass` with `requiredChanges: none`.
- Local commit: `73596fa Add role thread readiness status`.
- Global skill sync: `py -B scripts\\team_router_skill_sync_check.py --sync` -> `status: match`.

## Current Next Gate

1. Ask for the next explicit gate: push/PR, or stop.
