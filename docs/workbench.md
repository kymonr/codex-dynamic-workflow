# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: accepted local-package `ctr-20260630-watcher-status-extraction`; host adapter/scheduler gate is committed in `0345f53`, watcher runtime extraction was accepted by Codex reviewer/verifier role threads, original closeout delivery is recorded as fallback-only/read_thread, and the delivery-record correction was rechecked by direct-send reviewer/verifier callbacks.
- Last package objective: continue the repo-local module extraction after host runtime, starting with watcher/status boundaries without changing real host integration behavior.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. Repo/global skill comparison remains `status: match` unless this package explicitly edits skill files.
- Current next gate: explicit commit authorization for this watcher/status package. After that local commit, the next repo-local gate is status/closeout module extraction; Real live host integration remains an external host package gate.
## Current Diff Surface

Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The closeout package files are recorded in the review package, and the exact current surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Active package verification:

- Implementation: added `src/team_router_watcher_runtime.py` for watcher timing/read-discipline/convergence/watcher-ledger/heartbeat schedule payload helpers; `src/team_router.py` keeps `_watch_next_wakeup()`, ledger mutation, role-thread reads, `watch_team_task_with_adapter()`, and compatibility imports.
- Docs/tests: updated `docs/team-router/module-map.md`, current workbench expectations, and focused watcher runtime behavior coverage.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> OK.
- Focused watcher/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest tests.test_team_router -k watcher_runtime -k role_read -k watch_next_wakeup -k heartbeat -k module_map -v` -> Ran 15 tests OK.
- Workbench current-task contract test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 1 test OK.
- Full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 338 tests OK.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty surface is `docs/team-router/module-map.md`, `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, plus untracked package doc and `src/team_router_watcher_runtime.py`.
- Doctor check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.
- Auxiliary reviewer evidence: multi_agent/subagent outputs are auxiliary evidence only; `019f180b-768e-7353-b11d-3640a618e542` returned `needs_rework` and helped identify that the actual `heartbeat_scheduler_call(heartbeat_scheduler)(**payload)` side-effect needed to stay in `src/team_router.py`.
- Rework implementation: `src/team_router_watcher_runtime.py` now exposes `build_watcher_heartbeat_payload(...)`; `src/team_router.py` performs `_heartbeat_scheduler_call(heartbeat_scheduler)(**payload)` and attaches `scheduled/result`.
- Rework regression test: `tests.test_team_router.TestTeamRouterState.test_watcher_runtime_does_not_call_heartbeat_scheduler` asserts runtime has no `heartbeat_scheduler_call` / `(**payload)` and facade owns the scheduler call.
- Rework compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> OK.
- Rework focused watcher/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest tests.test_team_router -k watcher_runtime -k role_read -k watch_next_wakeup -k heartbeat -k module_map -v` -> Ran 16 tests OK.
- Rework full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 339 tests OK.
- Auxiliary reviewer evidence: multi_agent/subagent `019f1810-6ff8-7503-8a1b-c706e0382e07` returned `pass`; this was advisory only, not a formal Team Router reviewer gate.
- Auxiliary verifier evidence: multi_agent/subagent `019f1811-9098-7433-ad07-147ee30647b1` returned `needs_rework`; this was advisory only and identified that `test_workbench_tracks_current_task_without_stale_diff_surface` expected old next-gate text after workbench moved to reviewer re-review wording.
- Verifier rework: updated the workbench contract test to expect `send the reworked watcher runtime extraction package to reviewer re-review`.
- Auxiliary reviewer evidence: multi_agent/subagent `019f1815-1904-7f13-b35f-739fc0c530dd` returned `pass`; this was advisory only, not a formal Team Router reviewer gate.
- Codex reviewer final re-check result: role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `needs_rework`; required aligning the Current Task next gate, package status, workbench contract test, and this verification list formatting.
- Reviewer-required gate-text cleanup: updated `docs/workbench.md`, `tests/test_team_router.py`, and the watcher/status package status so the current gate no longer claims verifier-only closeout while reviewer re-review is still pending.
- Reviewer gate-text re-review result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `pass`; `requiredChanges: none`.
- Verifier final result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `pass`; `remainingRisks: none`; `next: closeout`.
- Role delivery correction: direct-send was not observed for the Codex reviewer/verifier closeout path; manager collected the self-thread-marker by `read_thread`, so `deliveryStatus: fallback_only`, `receiptSource: self-thread-fallback/read_thread`, and `receiptChannel: read_thread`. This was degraded delivery and not normal proactive return.
- Closeout correction reviewer direct-send observed: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass` for the delivery-record correction; Closeout correction reviewer deliveryStatus: direct_send; Closeout correction reviewer deliveryError: none.
- Closeout correction verifier direct-send observed: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass` for the delivery-record correction; Closeout correction verifier deliveryStatus: direct_send; Closeout correction verifier deliveryError: none.
- Closeout correction focused docs tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-docs'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_watcher_status_package_records_fallback_only_role_delivery -v` -> Ran 3 tests OK.
- Closeout correction watcher boundary tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-boundary'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_watcher_runtime_does_not_call_heartbeat_scheduler tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger -v` -> Ran 2 tests OK.
- Closeout correction compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-compile'; py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> OK.
- Closeout correction full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-watcher-extraction-full'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 340 tests OK.
- Closeout correction truth/doctor/closeout: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skillSync.status: match`; `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, generic dirty-state `nextAction` still says reviewer then verifier before closeout; `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, entrypoint `underTarget: true`.
- Closeout correction whitespace/status: `git diff --check` -> exit 0 with CRLF/LF warnings only; `git status -sb --untracked-files=all` -> `## master...origin/master [ahead 2]` plus this package diff/untracked files.
Previous package verification:

- RED focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> failed before implementation because downstream prompts copied raw callback/review payloads and `find_stale_state_claims(...)` returned no workbench/package-lag claim.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> Ran 2 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-prompt-compact'; py -B -m py_compile src\team_router.py scripts\team_router_truth_check.py tests\test_team_router.py` -> OK.
- Initial truth check while package is dirty: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are this package's runtime/test/docs edits.
- Initial doctor check while package is dirty: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `hostReadiness.summary: no host readiness snapshot supplied; manual orchestration only`.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 337 tests OK.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are this package's runtime/test/docs edits before commit.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-role-thread-readiness-status` completed read-only role-thread status UX in `scripts/team_router_doctor.py`; it added `--role-status-json` and `roleThreadStatus` from supplied snapshots only.
- Previous `ctr-20260628-live-capability-state-fix` clarified exposed app tools versus missing Python callable adapter/runtime orchestration. That remains the baseline boundary for this package.
- Previous `ctr-20260628-trust-and-modularity` is a completed historical package covering the current-state truth checker, module split plan, and initial doctor/status UX. Its recorded diff surface, verifier evidence, and sync state are not current git truth.
- Previous `ctr-20260628-team-router-optimization-1-6` is a completed historical package. Its recorded dirty surface, skill sync result, reviewer evidence, and P2 step labels are not current git truth.
- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, the truth/doctor scripts, and latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library.
- Runtime/docs/tests changes require an active package plus reviewer/verifier gates.
- Workbench current state must not claim old completed tasks as active work.
- Stale-current-state detection and doctor nextAction in this package are evidence-only UX; they do not modify dispatch, watcher cadence, registry, ledger, or protocol parsing.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- Watcher runtime extraction intentionally keeps `_watch_next_wakeup()`, ledger mutation, role-thread reads, and `watch_team_task_with_adapter()` in the facade. Moving those remains out of this package.
- `team_router_status.py` / closeout-status extraction is still pending and should be the next repo-local module gate only after reviewer/verifier accept this package.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.
## Review And Verification Gate

- Current gate: watcher runtime extraction package accepted by reviewer and verifier; local closeout is recorded, but commit is not authorized yet.
- Next gated step: explicit commit authorization for this watcher/status package. After that commit, open the repo-local status/closeout module extraction gate; real live host integration remains blocked until an external host supplies callable adapter/scheduler evidence.
