# ctr-20260702-manager-polling-reproducible-example

## Package Metadata

- taskId: `ctr-20260702-manager-polling-reproducible-example`
- branch: `master`
- permission: low-risk evidence-only local package. Includes fixture subset, runbook reproduction copy, focused tests, and workbench/package records. Excludes real Codex thread tools, live role dispatch, broker/adapter/scheduler startup, commit, push, PR, merge, deploy, publish/release, and global skill sync unless separately authorized.
- scope: make the manager polling status UX reproducible from docs by comparing stable doctor fields instead of a full live worktree report.

## Objective

Move the manager polling doctor UX from "works if you know the fixture" to "reproducible by following the runbook." The stable example records only fields that should remain identical across clean and dirty checkouts: `managerPollingStatus` decision fields and summary substrings.

## Boundary

Included:

- Add `tests/fixtures/team_router/manager_polling_status_expected_subset.json`.
- Extend `docs/runbooks/codex-team-router-live-orchestration.md` with PowerShell reproduction commands.
- Lock the expected stable fields in focused tests.

Excluded:

- No full doctor report snapshot, because git truth, scan files, and skill sync are live worktree evidence.
- No `read_thread`, `send_message_to_thread`, `create_thread`, or other Codex app thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No parser, registry, ledger transition, direct-return, or production scheduling changes.
- No commit, push, PR, merge, deploy, publish/release, or global skill sync unless separately authorized.

## Acceptance Criteria

- A user can run the documented `py -B scripts\team_router_doctor.py --role-status-json tests/fixtures/team_router/manager_polling_status_snapshot.json --json` command and inspect stable manager polling fields.
- The runbook names the expected subset fixture and explains why full JSON comparison is intentionally avoided.
- Tests compare the doctor output against the stable expected subset.
- The package remains evidence-only and does not add live thread-tool behavior.

## Verification Record

- RED focused tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-repro-red py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v` first failed because `tests/fixtures/team_router/manager_polling_status_expected_subset.json` and the runbook reproduction wording were missing.
- GREEN focused tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-repro-green py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v` -> Ran 2 tests OK.
- Final focused suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-repro-focused py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 3 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-repro-compile py -B -m py_compile tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/runbooks/codex-team-router-live-orchestration.md`, `docs/workbench.md`, and `tests/test_team_router.py` only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes the runbook, workbench, tests, package doc, and stable expected subset fixture.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `managerPollingStatus.status: not_supplied`; `summary` includes `managerPolling=not_supplied`.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.

## Review And Verification Gate

Current next gate: none after local closeout and local commit. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.
