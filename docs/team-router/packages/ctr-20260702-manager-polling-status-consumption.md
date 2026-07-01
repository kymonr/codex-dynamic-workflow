# ctr-20260702-manager-polling-status-consumption

## Package Metadata

- taskId: `ctr-20260702-manager-polling-status-consumption`
- branch: `master`
- permission: Complex Task local package. Includes implementation plan, focused tests, fixture/runbook updates, manager-facing status summary formatting, package/workbench updates, local verification, and local commit after verification. Excludes real Codex thread tools, live role dispatch, broker/adapter/scheduler startup, push, PR, merge, deploy, publish/release, and global skill sync unless separately authorized.
- scope: make the manager polling doctor UX usable end-to-end from caller-supplied evidence into manager-facing handoff/closeout summaries without adding live reads.

## Objective

Make `managerPollingStatus` visible beyond raw doctor JSON. The package adds a reusable evidence fixture and runbook command for `--role-status-json`, then teaches manager-facing handoff and closeout text to include an optional `managerPolling:` section when the ledger already contains a computed polling status.

## Boundary

Included:

- Add `tests/fixtures/team_router/manager_polling_status_snapshot.json`.
- Document the fixture and evidence-only doctor command in `docs/runbooks/codex-team-router-live-orchestration.md`.
- Format optional `ledger["managerPollingStatus"]` in `src/team_router_status.py` for handoff and closeout output.
- Add focused tests for fixture/runbook coverage and handoff/closeout summary consumption.
- Update workbench/package records and implementation plan.

Excluded:

- No `read_thread`, `send_message_to_thread`, `create_thread`, `set_thread_title`, or other Codex app thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No changes to parser marker schema, registry/ledger transitions, direct-return receipt validation, production scheduling, or role dispatch.
- No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, or global skill sync unless separately authorized.

## Acceptance Criteria

- Doctor can be demonstrated with a reusable `managerPolling` fixture through `--role-status-json`.
- Runbook states that the fixture path is evidence-only and does not call live thread tools.
- Handoff output includes `managerPolling:` when the ledger carries a manager polling status mapping.
- Closeout output includes `managerPolling:` when the ledger carries a manager polling status mapping.
- The summary surface remains deterministic and does not introduce live thread-tool calls.

## Verification Record

- RED fixture/runbook tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-red1 py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v` first failed because the fixture file was missing and the runbook did not yet document `managerPolling`.
- GREEN fixture/runbook tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-green1b py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v` -> Ran 2 tests OK.
- RED formatter tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-red2b py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterManagerIntegration.test_closeout_includes_manager_polling_status_summary -v` first failed because handoff/closeout output did not include `managerPolling:`.
- GREEN formatter tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-green2 py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterManagerIntegration.test_closeout_includes_manager_polling_status_summary -v` -> Ran 2 tests OK.
- Final focused suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-focused py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture tests.test_team_router.TestTeamRouterManagerIntegration.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterManagerIntegration.test_closeout_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 6 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-compile py -B -m py_compile src\team_router_status.py scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/runbooks/codex-team-router-live-orchestration.md`, `docs/workbench.md`, and `tests/test_team_router.py` only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes the runbook, workbench, status formatter, tests, implementation plan, package doc, and fixture.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `managerPollingStatus.status: not_supplied`; `summary` includes `managerPolling=not_supplied`.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.

## Local Review And Acceptance

- Local review: pass. The change only consumes supplied data and formats existing ledger evidence; it does not add live reads, broker startup, role dispatch, or parser/ledger state transitions.
- Local acceptance: pass after focused suite, compile, diff check, truth check, doctor, and closeout checks.

## Review And Verification Gate

Current next gate: none after local closeout. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.
