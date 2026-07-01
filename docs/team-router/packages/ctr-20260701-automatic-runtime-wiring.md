# ctr-20260701-automatic-runtime-wiring

## Package Metadata

- taskId: `ctr-20260701-automatic-runtime-wiring`
- branch: `master`
- permission: local package for automatic Team Router runtime wiring dry-run. Includes code, tests, docs, reviewer/verifier gates, and local commit after acceptance. Excludes push, PR, merge, deploy, publish/release, production daemon, live role dispatch, real account/API use, and global skill sync.
- scope: manager startup path documentation, host-readiness required gate, dry-run runtime wiring report, package/workbench/current-truth updates.

## Objective

Move Team Router from a generic `manual_only` status toward a controlled automatic-entry gate by proving exactly when an already-running localhost broker may supply `host_context` for manager startup, without starting a daemon or dispatching live roles.

## Boundary

Included:

- Define the manager startup path from `--broker-url` / `--session-token` to host-context injection.
- Require ready host readiness before automatic entry is allowed.
- Add a dry-run smoke that reads broker `/readiness` evidence and reports callable thread-tool capability evidence without calling thread tools.
- Keep blocked or missing broker readiness in `manual_only` / `host_contract_blocked`.
- Update workbench/package/current-truth records and run reviewer/verifier gates.

Excluded:

- No push, PR, merge, deploy, publish/release, production scheduler/broker daemon, global skill sync, external account/API, or non-localhost broker.
- No live role dispatch and no dry-run calls to `create_thread`, `send_message_to_thread`, `read_thread`, or `set_thread_title`.
- No change to Team Router role protocol, direct-return parsing, registry/ledger semantics, watcher cadence, or production scheduler behavior.

## Acceptance Criteria

- Missing broker args report `manual_only` and identify `broker-url` / `session-token`.
- Blocked broker readiness cannot enable automatic entry.
- Ready broker readiness reports `automaticEntryAllowed: true` only when doctor host readiness is ready and host-context kwargs can be built.
- Dry-run report shows the manager startup path and records that no thread-tool calls were executed.
- Tests cover missing, blocked, and ready dry-run paths.

## Verification Record

- Added `scripts/team_router_runtime_wiring_check.py` as a read-only dry-run automatic runtime wiring gate.
- Missing broker args report `status: manual_only`, `orchestrationStatus: manual_only`, and missing `broker-url` / `session-token`.
- Blocked broker readiness reports `status: manual_only`, `orchestrationStatus: host_contract_blocked`, and `automaticEntryAllowed: false`.
- Ready broker readiness reports `status: ready`, `orchestrationStatus: adapter_smoke_ready`, `automaticEntryAllowed: true`, and manager startup injection `host_context`.
- Dry-run tests assert no thread-tool calls are executed; only broker `/readiness` evidence is consumed.
- RED focused tests first failed because `scripts/team_router_runtime_wiring_check.py` did not exist.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterRuntimeWiringScript -v` -> Ran 3 tests OK.
- Compile: `py -B -m py_compile src\team_router.py src\team_router_broker_adapter.py scripts\team_router_runtime_wiring_check.py scripts\team_router_broker_feasibility_check.py scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- Focused broker/runtime group: `py -B -m unittest tests.test_team_router.TestTeamRouterRuntimeWiringScript tests.test_team_router.TestTeamRouterBrokerFeasibilityScript tests.test_team_router.TestTeamRouterBrokerAdapter -v` -> Ran 33 tests OK.
- Full Team Router test module: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 397 tests OK.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.
- `git diff --check` initially reported CRLF/LF warnings plus one EOF blank-line issue in `tests/test_team_router.py`; EOF cleanup is included before final re-run.
- Reviewer v1 returned `needs_rework` for stale next-gate wording after verification had completed; rework updated workbench/package next gate to `reviewer re-check, verifier acceptance, then local commit only`.
- Reviewer v2: pass; `requiredChanges: none`; confirmed dry-run remains non-mutating and current-truth next gate is no longer stale.
- Verifier: accepted; `requiredChanges: []`; confirmed dry-run only reads `/readiness`, no thread-tool endpoints are called, reviewer stale next-gate finding is fixed, and local commit may proceed.
## Review And Verification Gate

Current next gate: none after verifier acceptance and local commit. push, PR, merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, and global skill sync remain outside this package unless explicitly authorized later.

push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, and global skill sync remain outside this package unless separately authorized.
