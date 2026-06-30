# Team Router Module Map

This records the conservative phase 1 split plus the phase 2b1 runtime extraction, phase 2b2 direct-return contract extraction, phase 2b3 host runtime extraction, phase 2b4 watcher runtime extraction, phase 2b5 status/closeout text extraction, and phase 2b6 read-only status tool extraction, dispatch prompt path-handoff compaction, reviewer/verifier package-handoff prompt compression, the first registry/ledger state helper extraction, the observation-content ledger helper cut, and the latest executor callback observation helper cut now implemented. Public imports continue through `src/team_router.py`; direct imports from the extracted modules are internal implementation detail unless a later explicit package widens that contract.

## Current Domains

- protocol parsing: `src/team_router_protocol.py` owns `ProtocolError`, `ProtocolMessage`, marker regexes, parser tables, `_validate_task_id()`, `_iter_marker_blocks()`, and `parse_*()` helpers for `TEAM_ROUTER_PLAN`, `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, `TEAM_ROUTER_VERDICT`, `TEAM_ROUTER_ARCHITECT_REVIEW`, and `TEAM_ROUTER_QA_REVIEW`.
- gate policy: `src/team_router_policy.py` owns reviewer/architect/QA gate terms, `GATE_CLASSES`, `classify_*_gate()`, `reviewer_gate_required_for_ledger()`, `explain_team_router_gate()`, `explain_team_router_route()`, and `gate_class_requires_reviewer()`.
- facade and contract snapshot: `src/team_router.py` remains the public import surface and keeps `protocol_contract_snapshot()` because the snapshot aggregates marker schema from protocol, gate policy from policy, and still-local role/state/orchestration/side-effect contracts. It re-exports runtime, direct-return, host runtime, watcher runtime, and status/closeout helpers for compatibility. Role prompt transport still lives here; executor dispatch now omits overlong `executorPrompt` text when path handoff metadata points to `taskBriefPath` / `reviewPackagePath`, and reviewer/verifier package-handoff prompts point to `executorReportPath` / `reviewPackagePath` instead of copying raw callback or reviewer evidence.
- registry/ledger state: `src/team_router_state.py` owns JSON primitives, registry/task paths, role binding persistence, search anchors, review request record construction, observation-content lookup, latest executor callback observation lookup, and latest-request/return-thread ledger accessors. `src/team_router.py` still owns higher-level capture/watch/state-save orchestration and status transitions that depend on protocol, policy, direct-return, or watcher helpers.
- adapter runtime: `src/team_router_runtime.py` owns adapter callable dispatch helpers, send-anchor normalization, create-result thread-id extraction, and `read_thread` message normalization.
- host runtime: `src/team_router_host_runtime.py` owns host readiness, callable heartbeat scheduler validation, live orchestration context creation, and host-context conflict checks. `src/team_router.py` still owns parent entry path selection and public compatibility imports; real host integration remains a separate external host package gate.
- direct return: `src/team_router_direct_return.py` owns pure direct-return contract helpers: direct-send record selection, status/role capture eligibility, manager-inbox message parsing after the facade read window is normalized, receipt validation, receipt metadata, and malformed protocol metadata. `src/team_router.py` still owns capture/watch/state-save orchestration, malformed direct-return ledger mutation, and the public compatibility wrappers that apply read anchors.
- watcher/heartbeat: `src/team_router_watcher_runtime.py` owns first-check timing, 300 second read discipline, convergence read decisions, watcher ledger rendering, and heartbeat schedule payload construction. `src/team_router.py` still owns `_watch_next_wakeup()` role selection, ledger mutation, role-thread reads, and `watch_team_task_with_adapter()` continuation behavior.
- closeout/status: `src/team_router_status.py` owns closeout and handoff text helpers, role-thread lines, read anchor lines, compounding defaults, and task-update formatting. `src/team_router.py` passes `watcher_builder` wrappers so handoff text can still include facade-derived watcher metadata.
- read-only status tools: `src/team_router_status_tools.py` owns truth_check/doctor/closeout script internals that are pure read-only status helpers: `build_truth_report`, `build_closeout_report`, `find_stale_state_claims`, `truth_status`, and `next_action`. truth_check/doctor/closeout scripts are thin read-only evidence wrappers. `scripts/team_router_truth_check.py`, `scripts/team_router_doctor.py`, and `scripts/team_router_closeout_check.py` and cannot stage, commit, push, PR, merge, deploy, publish, or sync.
- docs/skill contract tests: keep `SKILL.md`, `references/`, workbench, packages, and fixtures aligned with runtime policy.

## Implemented Phase Dependencies

| Module | Responsibility | Dependencies | Import rule |
| --- | --- | --- | --- |
| `team_router_protocol.py` | TEAM_ROUTER marker parsing, task id validation, required/allowed marker schema | Python standard library only | must not import `team_router` or `team_router_policy` |
| `team_router_policy.py` | pure gate-policy constants and classifiers | `team_router_protocol.ProtocolError` only | must not import `team_router` |
| `team_router_state.py` | state/registry/task-ledger JSON primitives, role binding persistence, search anchors, review request records, observation-content lookup, latest executor callback observation lookup, and latest-request/return-thread ledger accessors | `team_router_protocol._validate_task_id`, standard library | must not import `team_router`, runtime, policy, direct-return, watcher, host, or status modules |
| `team_router_runtime.py` | thread-adapter call helpers, send anchors, create-result thread-id extraction, and `read_thread` message normalization | `team_router_state.StateStoreError`, `_required_str`, standard library | must not import `team_router` |
| `team_router_direct_return.py` | direct-return contract helpers, receipt validation, and malformed protocol metadata | `team_router_protocol`, `team_router_state.StateStoreError`, standard library | must not import `team_router`, `team_router_policy`, or `team_router_runtime` |
| `team_router_host_runtime.py` | host readiness, heartbeat scheduler callable validation, live orchestration context, and host-context conflict checks | `team_router_runtime`, `team_router_state`, standard library | must not import `team_router` |
| `team_router_watcher_runtime.py` | watcher timing, read discipline, convergence decisions, watcher ledger rendering, and heartbeat schedule payload construction | `team_router_policy`, `team_router_protocol`, `team_router_state`, standard library | must not import `team_router` |
| `team_router_status.py` | closeout and handoff text helpers, role/anchor rendering, compounding defaults, and task-update formatting | `team_router_state`, standard library | must not import `team_router` |
| `team_router_status_tools.py` | read-only truth/closeout report builders, stale-current-state checks, and doctor truth/next-action helpers | standard library only | does not import `team_router` and does not call thread tools |
| `team_router.py` | public facade, capture/watch/state-save orchestration, `protocol_contract_snapshot()` | `team_router_protocol`, `team_router_policy`, `team_router_runtime`, `team_router_direct_return`, `team_router_host_runtime`, `team_router_watcher_runtime`, `team_router_status`, `team_router_state`, standard library | re-exports moved names for compatibility |

## Deferred Future Modules

| Future module | Responsibility | First tests to move | Acceptance gate |
| --- | --- | --- | --- |
| `team_router_state.py` future expansion | higher-level registry/ledger status transitions that are still facade-local | callback/review/verdict capture and recovery tests | on-disk state fixtures remain backward compatible |

## Extraction Order

Phase 1 completed the safe opening split: protocol parsing first, then pure gate policy, with `src/team_router.py` as facade. Phase 2b1 extracted low-level adapter call/read normalization into `src/team_router_runtime.py` without changing the public import surface. Phase 2b2 extracted pure direct-return contract helpers into `src/team_router_direct_return.py` while keeping capture/watch/state-save orchestration in the facade. Phase 2b4 extracted watcher timing/read discipline/heartbeat payload helpers into `src/team_router_watcher_runtime.py` while keeping `_watch_next_wakeup()`, ledger mutation, and role-thread orchestration in the facade. Phase 2b5 extracted closeout/handoff text helpers into `src/team_router_status.py` while keeping watcher derivation in the facade through `watcher_builder`. Phase 2b6 extracted read-only status tool helpers into `src/team_router_status_tools.py` while keeping truth_check/doctor/closeout scripts as thin CLI wrappers. The dispatch prompt path-handoff fix and reviewer/verifier package-handoff compression keep prompt transport in the facade; this does not change parser/gate/direct-return semantics. The first registry/ledger state helper cut moved pure search-anchor, review-request-record, latest-request, and inherited return-thread helpers into `src/team_router_state.py`. The next ledger transition cut moved `_has_observation_content()` into `src/team_router_state.py` because it only inspects in-memory ledger observations for duplicate content. This package moved `_latest_executor_callback_observation()` into `src/team_router_state.py` because it only reads in-memory ledger observations to find the latest executor callback record. Higher-level ledger mutations remain facade-local. The remaining safe extraction order is: additional registry/ledger state transitions.

Status tool internals were extracted only after the user-output helper split was stable, because the scripts consume git truth, skill sync facts, workbench/package current-state text, and host/readiness evidence. Doctor-specific host readiness and role-thread snapshot classification remain in `scripts/team_router_doctor.py`; moving them needs a separate explicit package. Docs/skill contract tests should stay in the main suite throughout extraction and keep public runtime imports routed through `src/team_router.py` until a future compatibility gate explicitly changes that contract.

## Non-Goals

- No higher-level registry/ledger runtime extraction in phase 1, phase 2b6, the dispatch prompt path-handoff package, or the first registry/ledger helper cut.
- No adapter runtime extraction in phase 1; phase 2b1 now covers only low-level adapter call/read normalization.
- No direct-return capture/watch/state-save extraction in phase 2b2.
- No watcher/heartbeat extraction in phase 1; phase 2b4 now covers watcher timing/read discipline/heartbeat payload helpers only.
- No doctor-specific host readiness or role-thread snapshot extraction in phase 2b6.
- No skill-doc changes in phase 2b6.
- No new live dispatch behavior.
- No new host adapter implementation or production scheduler/daemon.
- No new package dependency.
- No commit, push, PR, merge, deploy, release, publish, or global skill sync authorization.
