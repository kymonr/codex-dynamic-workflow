# ctr-20260701-broker-host-readiness-injection

## Package Metadata

- taskId: `ctr-20260701-broker-host-readiness-injection`
- branch: `codex/desktop-plugin-feasibility-spike`
- permission: local package for broker/adapter startup readiness and host-readiness injection. Includes code, tests, docs, reviewer/verifier gates, and local commit after acceptance. Excludes push, PR, merge, deploy, publish/release, production daemon, real account/API use, and global skill sync.
- scope: localhost broker adapter/readiness mapping, doctor host-readiness injection, focused tests, workbench/package/plan records.

## Objective

Make the existing localhost broker adapter path feed the Team Router host-readiness surface directly, so a real Codex Desktop/plugin broker can prove adapter-created readiness through a caller-supplied broker URL/token without pretending model-side tools are Python callables.

## Boundary

Included:

- Map broker `/readiness` evidence into the existing `scripts/team_router_doctor.py --host-readiness-json` snapshot shape.
- Add doctor CLI support for broker readiness injection from `--broker-url` and `--session-token`.
- Preserve localhost-only broker URL validation and scheduler callback allowlist.
- Keep startup/readiness as evidence against an already-running localhost broker; no production daemon is installed.
- Update docs/workbench/package plan and run reviewer/verifier gates.

Excluded:

- No push, PR, merge, deploy, publish/release, production scheduler daemon, global skill sync, external account/API, or non-localhost broker.
- No live role dispatch unless separately authorized.
- No change to Team Router role protocol, direct-return parsing, registry/ledger semantics, or watcher cadence.

## Acceptance Criteria

- Broker readiness can produce a doctor-compatible host snapshot with `adapterCallable`, `callableTools`, `parentThreadId`, `heartbeatSchedulerCallable`, and `runtimeProbe`.
- Doctor can load that snapshot from broker args and report `adapter_smoke_ready` only when broker readiness is ready and runtime probe is ready.
- Blocked broker readiness remains `host_contract_blocked` and lists missing runtime/contract items.
- Feasibility script includes the host-readiness snapshot in JSON output without mutating Desktop state.
- Tests cover ready and blocked broker-injected readiness.

## Verification Record

- Added `broker_host_readiness_snapshot()` in `src/team_router_broker_adapter.py` to map broker `/readiness` evidence into doctor snapshot fields.
- Added `hostReadinessSnapshot` to `scripts/team_router_broker_feasibility_check.py --json` output.
- Added `scripts/team_router_doctor.py --broker-url --session-token --json` host readiness injection; `--host-readiness-json` and broker args are mutually exclusive.
- Focused new tests: `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_readiness_snapshot_maps_ready_broker_for_doctor tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_readiness_snapshot_maps_blocked_broker_for_doctor tests.test_team_router.TestTeamRouterBrokerFeasibilityScript.test_broker_feasibility_check_includes_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_can_inject_host_readiness_from_broker tests.test_team_router.TestTeamRouterState.test_router_doctor_rejects_host_readiness_file_and_broker_args_together -v` -> Ran 5 tests OK.
- Existing broker/feasibility group: `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter tests.test_team_router.TestTeamRouterBrokerFeasibilityScript -v` -> Ran 29 tests OK.
- Existing doctor host-readiness group: focused 6 doctor/status tests -> Ran 6 tests OK.
- Full suite before reviewer rework: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 393 tests OK.
- Reviewer v1 returned needs_rework: blocked broker readiness with otherwise-ready runtime/tool fields could map to doctor `adapter_smoke_ready`.
- Rework: `broker_host_readiness_snapshot()` now blocks the runtimeProbe when top-level broker readiness is not ready or broker missing is non-empty; regression covers blocked broker with ready tools/runtime remaining `host_contract_blocked`.
- Rework focused tests: 6 tests OK.
- Broker/feasibility group after rework: 30 tests OK.
- Full suite after rework: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 394 tests OK.
- Reviewer v2: pass; `requiredChanges: none`; confirmed blocked broker readiness cannot classify as `adapter_smoke_ready` and no production daemon/live dispatch overclaim remains.
- Verifier: accepted; `requiredChanges: none`; confirmed broker readiness injection satisfies the host-readiness gate and local commit may proceed after acceptance.

## Review And Verification Gate

Current next gate: none after verifier acceptance and local commit.

push, PR, merge, deploy, publish/release, production broker startup, and global skill sync remain outside this package unless separately authorized.
