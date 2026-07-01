# ctr-20260702-manager-polling-doctor-ux

## Package Metadata

- taskId: `ctr-20260702-manager-polling-doctor-ux`
- branch: `master`
- permission: low-risk local package for manager polling doctor UX. Includes doctor/status output wiring, focused tests, package/workbench updates, and local verification. Excludes real Codex thread tools, live role dispatch, broker/adapter/scheduler startup, push, PR, merge, deploy, publish/release, and global skill sync unless separately authorized.
- scope: expose the existing pure `manager_polling_status_update()` helper through `scripts/team_router_doctor.py` from caller-supplied evidence.

## Objective

Make the quiet manager polling decision visible in the plain doctor/status surface. When a caller supplies a bounded `managerPolling` snapshot through `--role-status-json`, doctor should report whether a read is allowed, whether manager narration should be emitted, the observed/previous status, and the `nextAllowedReadAt` boundary.

## Boundary

Included:

- Add a focused doctor JSON test for `managerPollingStatus`.
- Add `classify_manager_polling_status_snapshot()` in `scripts/team_router_doctor.py`.
- Include `managerPollingStatus` in doctor JSON and text output.
- Update workbench/package current truth and local verification notes.

Excluded:

- No `read_thread`, `send_message_to_thread`, `create_thread`, `set_thread_title`, or other Codex app thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No changes to parser marker schema, registry/ledger transitions, direct-return receipt validation, or production scheduling.
- No push, PR, merge, deploy, publish/release, live role dispatch, or global skill sync unless separately authorized.

## Acceptance Criteria

- `team_router_doctor.py --role-status-json <snapshot> --json` accepts a caller-supplied `managerPolling` evidence object.
- The JSON report includes `managerPollingStatus` with `mode: read-only`, `status`, `shouldRead`, `shouldReport`, and timing/status fields from `manager_polling_status_update()`.
- The top-level doctor `summary` includes `managerPolling=<status>`.
- Doctor remains evidence-only and does not call live thread tools.
- Existing role status, host readiness, broker injection, and manager polling helper tests remain green.

## Verification Record

- RED focused test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-red py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot -v` first failed with `KeyError: 'managerPollingStatus'`.
- GREEN focused test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-green py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot -v` -> Ran 1 test OK.
- Focused regression suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-focused py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_can_inject_host_readiness_from_broker tests.test_team_router.TestTeamRouterState.test_router_doctor_rejects_host_readiness_file_and_broker_args_together tests.test_team_router.TestTeamRouterState.test_router_doctor_reports_plain_status_without_dispatch tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_reports_status_changes_only -v` -> Ran 10 tests OK.
- Final focused suite with workbench current-state test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-final-tests py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_can_inject_host_readiness_from_broker tests.test_team_router.TestTeamRouterState.test_router_doctor_rejects_host_readiness_file_and_broker_args_together tests.test_team_router.TestTeamRouterState.test_router_doctor_reports_plain_status_without_dispatch tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_reports_status_changes_only tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 11 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-compile py -B -m py_compile scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/workbench.md` and `tests/test_team_router.py` only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes `docs/workbench.md`, `scripts/team_router_doctor.py`, `tests/test_team_router.py`, and untracked package doc.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `managerPollingStatus.status: not_supplied`; `summary` includes `managerPolling=not_supplied`; `nextAction` says reviewer then verifier before closeout.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; dirty local package surface remains uncommitted.
- Local reviewer pass: no blocking findings. The diff keeps doctor evidence-only, consumes only caller-supplied `managerPolling` snapshot data, and does not introduce live `read_thread`, broker, scheduler, or dispatch paths.
- Local verifier acceptance: fresh 11-test focused suite OK, compile exit 0, `git diff --check` exit 0 with CRLF/LF warnings only, `truth_check` reports `staleClaims: []`, `doctor` exposes default `managerPollingStatus.status: not_supplied`, and `closeout_check` exits 0.

## Review And Verification Gate

Current next gate: none after local closeout. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.
