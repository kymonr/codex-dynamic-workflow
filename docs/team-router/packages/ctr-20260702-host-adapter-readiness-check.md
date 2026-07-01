# ctr-20260702-host-adapter-readiness-check

## Package Metadata

- taskId: `ctr-20260702-host-adapter-readiness-check`
- branch: `master`
- permission: local package for a read-only host-adapter readiness check. Includes script, synthetic fixtures, runbook text, focused tests, package/workbench records, and local verification. Excludes real Codex thread-tool calls, broker/adapter/scheduler startup, live role dispatch, parser/ledger changes, commit, push, PR, merge, deploy, publish/release, and global skill sync unless separately authorized.
- scope: prove whether caller-supplied Codex Desktop thread-tool evidence can be injected as in-process Python callables for Team Router without executing those tools.

## Objective

Add a minimal local readiness entry point between `manual_only` and live orchestration. The script consumes a bounded host-adapter snapshot, creates a synthetic Python-callable adapter shape, runs existing readiness classification, and reports whether the adapter-created path would be ready. Represented thread-tool methods raise if executed, so the check proves shape only.

## Boundary

Included:

- Add `scripts/team_router_host_adapter_readiness_check.py`.
- Add `tests/fixtures/team_router/host_adapter_callable_ready_snapshot.json`.
- Add `tests/fixtures/team_router/host_adapter_model_descriptors_blocked_snapshot.json`.
- Document reproduction commands in `docs/runbooks/codex-team-router-live-orchestration.md`.
- Add focused tests for ready callable snapshot, descriptor-only blocked snapshot, fixture reproduction, and runbook coverage.

Excluded:

- No `read_thread`, `send_message_to_thread`, `create_thread`, `list_projects`, `list_threads`, or `set_thread_title` execution.
- No localhost broker startup, production daemon, scheduler startup, live role dispatch, parser/registry/ledger transition changes, or direct-return behavior change.
- No commit, push, PR, merge, deploy, publish/release, or global skill sync unless separately authorized.

## Acceptance Criteria

- Ready callable snapshot reports `status: ready` and `orchestrationStatus: adapter_smoke_ready`.
- Descriptor-only snapshot reports `status: blocked` and does not claim Python callable injection.
- Reports include `adapterInjection.threadToolCallsExecuted: 0`.
- Output includes a doctor-compatible `hostReadinessSnapshot` and classified `doctorHostReadiness`.
- Runbook documents both the ready and blocked fixture commands.

## Verification Record

- RED focused tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-red py -B -m unittest tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_accepts_callable_snapshot_without_tool_calls tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_blocks_model_side_descriptors -v` first failed because `scripts/team_router_host_adapter_readiness_check.py` did not exist.
- GREEN focused tests after script implementation: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-green1 py -B -m unittest tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_accepts_callable_snapshot_without_tool_calls tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_blocks_model_side_descriptors -v` -> Ran 2 tests OK.
- RED fixture test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-red2 py -B -m unittest tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_fixture_reports_ready_without_tool_calls -v` first failed because `tests/fixtures/team_router/host_adapter_callable_ready_snapshot.json` was missing.
- Focused suite after fixtures/runbook: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-focused py -B -m unittest tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_accepts_callable_snapshot_without_tool_calls tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_blocks_model_side_descriptors tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_fixture_reports_ready_without_tool_calls tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_host_adapter_readiness_check -v` -> Ran 4 tests OK.
- Final focused suite with workbench current-state guard: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-final-tests py -B -m unittest tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_accepts_callable_snapshot_without_tool_calls tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_check_blocks_model_side_descriptors tests.test_team_router.TestTeamRouterState.test_host_adapter_readiness_fixture_reports_ready_without_tool_calls tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_host_adapter_readiness_check tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 5 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-host-adapter-compile py -B -m py_compile scripts\team_router_host_adapter_readiness_check.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/runbooks/codex-team-router-live-orchestration.md`, `docs/workbench.md`, and `tests/test_team_router.py` only.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes the runbook, workbench, tests, package doc, script, and two fixtures.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; this package does not inject host readiness into doctor without caller-supplied evidence.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.
- Ready fixture command: `py -B scripts\team_router_host_adapter_readiness_check.py --adapter-snapshot-json tests\fixtures\team_router\host_adapter_callable_ready_snapshot.json --json` -> exit 0; `status: ready`; `orchestrationStatus: adapter_smoke_ready`; `adapterInjection.threadToolCallsExecuted: 0`; `adapterInjection.heartbeatSchedulesExecuted: 0`.
- Descriptor-blocked fixture command: `py -B scripts\team_router_host_adapter_readiness_check.py --adapter-snapshot-json tests\fixtures\team_router\host_adapter_model_descriptors_blocked_snapshot.json --json` -> exit 0; `status: blocked`; `orchestrationStatus: host_contract_blocked`; missing includes `callable adapter` and callable thread tools; tool/scheduler calls remained 0.

## Review And Verification Gate

Current next gate: none after local closeout and local commit. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.
