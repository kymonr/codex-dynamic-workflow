# Team Router Review Package: ctr-20260630-watcher-status-extraction

## Package Metadata

- taskId: `ctr-20260630-watcher-status-extraction`
- permission: `local-package`
- objective: continue repo-local module extraction after host runtime by isolating watcher/status helpers while preserving public compatibility and live-host boundaries.
- scope: `src/team_router.py`, `src/team_router_watcher_runtime.py`, `tests/test_team_router.py`, `docs/workbench.md`, `docs/team-router/module-map.md`, this package file.
- outOfScope: real host adapter implementation, production heartbeat daemon, push, PR, merge, deploy, publish/release, global skill sync.

## Current Intent

- Keep `src/team_router.py` as the public facade and compatibility import surface.
- Extract only pure watcher/status-adjacent helpers when the dependency direction is clear.
- Do not change role-thread protocol, host readiness, direct-return capture, or real live host integration behavior.
- Preserve existing watcher cadence: one short first-check read, then low-frequency event-driven reads no more often than every five minutes for the same role/thread.

## Verification Plan

- Start with focused tests around watcher/status behavior before moving code.
- Run docs/module-map tests if module map changes.
- Run full `test_team_router.py` before reviewer/verifier closeout.
## Implemented Changes

- Added `src/team_router_watcher_runtime.py` as the watcher runtime extraction point for timestamp math, read discipline, convergence decisions, watcher ledger rendering, watcher read allowance, and heartbeat schedule payload construction only.
- Kept `src/team_router.py` as the public facade and compatibility surface. It still owns `_watch_next_wakeup()`, ledger mutation, role-thread reads, `_record_waiting_role_read()`, the actual `_heartbeat_scheduler_call(heartbeat_scheduler)(**payload)` side effect, and `watch_team_task_with_adapter()` continuation behavior.
- Updated `docs/team-router/module-map.md` so watcher runtime is implemented and remaining repo-local extraction order is `status/closeout`.
- Added `tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger` and updated workbench/module-map contract expectations.

## Verification Evidence

- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> OK.
- Focused watcher/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest tests.test_team_router -k watcher_runtime -k role_read -k watch_next_wakeup -k heartbeat -k module_map -v` -> Ran 15 tests OK.
- Full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 338 tests OK.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`.
- Doctor check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.


## Reviewer Rework Record

- Auxiliary reviewer evidence: multi_agent/subagent outputs are auxiliary evidence only; `019f180b-768e-7353-b11d-3640a618e542` returned `TEAM_ROUTER_REVIEW result: needs_rework` and helped identify the scheduler-call boundary issue.
- Required change: keep the external heartbeat scheduler callable invocation out of `src/team_router_watcher_runtime.py`; runtime should only return eligibility/runAt/payload helper data.
- Rework: `src/team_router_watcher_runtime.py` now provides `build_watcher_heartbeat_payload(...)`; `src/team_router.py` now calls `_heartbeat_scheduler_call(heartbeat_scheduler)(**payload)` and attaches `scheduled/result`.
- Regression coverage: `tests.test_team_router.TestTeamRouterState.test_watcher_runtime_does_not_call_heartbeat_scheduler` asserts the runtime has no `heartbeat_scheduler_call` / `(**payload)` and the facade owns the scheduler call.
- Rework focused watcher/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest tests.test_team_router -k watcher_runtime -k role_read -k watch_next_wakeup -k heartbeat -k module_map -v` -> Ran 16 tests OK.
- Rework full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 339 tests OK.

## Verifier Rework Record

- Auxiliary reviewer evidence: multi_agent/subagent `019f1810-6ff8-7503-8a1b-c706e0382e07` returned `TEAM_ROUTER_REVIEW result: pass`; this was advisory only, not a formal Team Router reviewer gate.
- Auxiliary verifier evidence: multi_agent/subagent `019f1811-9098-7433-ad07-147ee30647b1` returned `TEAM_ROUTER_VERDICT result: needs_rework`; this was advisory only and identified that `test_workbench_tracks_current_task_without_stale_diff_surface` still expected the pre-rework next-gate wording.
- Required change: align the workbench contract test with the current workbench next gate: `send the reworked watcher runtime extraction package to reviewer re-review`.
- Rework: updated `tests/test_team_router.py` workbench contract expectation only; no runtime behavior changed.

## Reviewer Gate-Text Rework Record

- Codex reviewer final re-check: role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: needs_rework` because the workbench Current Task, Review Gate/package status, and workbench test expectation disagreed about whether reviewer re-review or verifier final re-check was next.
- Required change: align `docs/workbench.md`, `tests/test_team_router.py`, and this package's gate status to the same current gate, and remove the escaped newline marker from the workbench verification list.
- Rework: updated the current next gate to reviewer re-review of this gate-text cleanup before verifier final re-check; no runtime behavior changed.
- Reviewer gate-text re-review: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass`, `requiredChanges: none`.
## Review Gate Status

- Reviewer: Codex role-thread re-review passed after gate-text cleanup; `requiredChanges: none`.
- Verifier: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass`; `remainingRisks: none`; `next: closeout`.
- Delivery: direct-send was not observed for the Codex reviewer/verifier closeout path; manager collected self-thread markers by `read_thread`, so `deliveryStatus: fallback_only`, `receiptSource: self-thread-fallback/read_thread`, and `receiptChannel: read_thread`. This was degraded delivery and not normal proactive return.
- Closeout correction reviewer direct-send observed: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass` for the delivery-record correction; Closeout correction reviewer deliveryStatus: direct_send; Closeout correction reviewer deliveryError: none.
- Closeout correction verifier direct-send observed: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass` for the delivery-record correction; Closeout correction verifier deliveryStatus: direct_send; Closeout correction verifier deliveryError: none.
- Closeout correction focused docs tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-docs'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_watcher_status_package_records_fallback_only_role_delivery -v` -> Ran 3 tests OK.
- Closeout correction watcher boundary tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-boundary'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_watcher_runtime_does_not_call_heartbeat_scheduler tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger -v` -> Ran 2 tests OK.
- Closeout correction compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-compile'; py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> OK.
- Closeout correction full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-full'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 340 tests OK.
- Closeout correction truth/doctor/closeout: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skillSync.status: match`; `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, generic dirty-state `nextAction` still says reviewer then verifier before closeout; `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, entrypoint `underTarget: true`.
- Closeout correction whitespace/status: `git diff --check` -> exit 0 with CRLF/LF warnings only; `git status -sb --untracked-files=all` -> `## master...origin/master [ahead 2]` plus this package diff/untracked files.
- Commit: not authorized for this watcher/status package unless the user explicitly grants it.

## Closeout Status

- Local package accepted by Codex reviewer and verifier role threads; original role delivery is recorded as fallback-only/read_thread collection, delivery-record correction was rechecked by direct-send reviewer/verifier callbacks, and no runtime behavior changes are pending inside this package.
- Not done: watcher/status package commit, push, PR, merge, deploy, publish/release, global skill sync, real host adapter implementation, and production scheduler/daemon.
- Next gated step: explicit commit authorization for this watcher/status package; after that commit, open the repo-local status/closeout module extraction gate while keeping real host integration as an external host package gate.
