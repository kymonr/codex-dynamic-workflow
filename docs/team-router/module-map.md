# Team Router Module Map

This records the conservative phase 1 split plus the phase 2b1 runtime extraction, phase 2b2 direct-return contract extraction, phase 2b3 host runtime extraction, and phase 2b4 watcher runtime extraction now implemented. Public imports continue through `src/team_router.py`; direct imports from the extracted modules are internal implementation detail unless a later explicit package widens that contract.

## Current Domains

- protocol parsing: `src/team_router_protocol.py` owns `ProtocolError`, `ProtocolMessage`, marker regexes, parser tables, `_validate_task_id()`, `_iter_marker_blocks()`, and `parse_*()` helpers for `TEAM_ROUTER_PLAN`, `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, `TEAM_ROUTER_VERDICT`, `TEAM_ROUTER_ARCHITECT_REVIEW`, and `TEAM_ROUTER_QA_REVIEW`.
- gate policy: `src/team_router_policy.py` owns reviewer/architect/QA gate terms, `GATE_CLASSES`, `classify_*_gate()`, `reviewer_gate_required_for_ledger()`, `explain_team_router_gate()`, `explain_team_router_route()`, and `gate_class_requires_reviewer()`.
- facade and contract snapshot: `src/team_router.py` remains the public import surface and keeps `protocol_contract_snapshot()` because the snapshot aggregates marker schema from protocol, gate policy from policy, and still-local role/state/orchestration/side-effect/closeout contracts. It re-exports runtime, direct-return, host runtime, and watcher runtime helpers for compatibility.
- registry/ledger state: still local to `src/team_router.py`; load, save, and advance project registries, task ledgers, role bindings, search anchors, and status transitions.
- adapter runtime: `src/team_router_runtime.py` owns adapter callable dispatch helpers, send-anchor normalization, create-result thread-id extraction, and `read_thread` message normalization.
- host runtime: `src/team_router_host_runtime.py` owns host readiness, callable heartbeat scheduler validation, live orchestration context creation, and host-context conflict checks. `src/team_router.py` still owns parent entry path selection and public compatibility imports; real host integration remains a separate external host package gate.
- direct return: `src/team_router_direct_return.py` owns pure direct-return contract helpers: direct-send record selection, status/role capture eligibility, manager-inbox message parsing after the facade read window is normalized, receipt validation, receipt metadata, and malformed protocol metadata. `src/team_router.py` still owns capture/watch/state-save orchestration, malformed direct-return ledger mutation, and the public compatibility wrappers that apply read anchors.
- watcher/heartbeat: `src/team_router_watcher_runtime.py` owns first-check timing, 300 second read discipline, convergence read decisions, watcher ledger rendering, and heartbeat schedule payload construction. `src/team_router.py` still owns `_watch_next_wakeup()` role selection, ledger mutation, role-thread reads, and `watch_team_task_with_adapter()` continuation behavior.
- closeout/status: still local to `src/team_router.py` and scripts; produce closeout/handoff text, read-only closeout evidence, current-truth checks, and doctor/status summaries.
- docs/skill contract tests: keep `SKILL.md`, `references/`, workbench, packages, and fixtures aligned with runtime policy.

## Implemented Phase 1 Dependencies

| Module | Responsibility | Dependencies | Import rule |
| --- | --- | --- | --- |
| `team_router_protocol.py` | TEAM_ROUTER marker parsing, task id validation, required/allowed marker schema | Python standard library only | must not import `team_router` or `team_router_policy` |
| `team_router_policy.py` | pure gate-policy constants and classifiers | `team_router_protocol.ProtocolError` only | must not import `team_router` |
| `team_router_runtime.py` | thread-adapter call helpers, send anchors, create-result thread-id extraction, and `read_thread` message normalization | `team_router_state.StateStoreError`, `_required_str`, standard library | must not import `team_router` |
| `team_router_direct_return.py` | direct-return contract helpers, receipt validation, and malformed protocol metadata | `team_router_protocol`, `team_router_state.StateStoreError`, standard library | must not import `team_router`, `team_router_policy`, or `team_router_runtime` |
| `team_router_host_runtime.py` | host readiness, heartbeat scheduler callable validation, live orchestration context, and host-context conflict checks | `team_router_runtime`, `team_router_state`, standard library | must not import `team_router` |
| `team_router_watcher_runtime.py` | watcher timing, read discipline, convergence decisions, watcher ledger rendering, and heartbeat schedule payload construction | `team_router_policy`, `team_router_protocol`, `team_router_state`, standard library | must not import `team_router` |
| `team_router.py` | public facade, state/capture/watch/state-save/status, `protocol_contract_snapshot()` | `team_router_protocol`, `team_router_policy`, `team_router_runtime`, `team_router_direct_return`, `team_router_host_runtime`, `team_router_watcher_runtime`, standard library | re-exports moved names for compatibility |

## Deferred Future Modules

| Future module | Responsibility | First tests to move | Acceptance gate |
| --- | --- | --- | --- |
| `team_router_state.py` | registry/ledger persistence and state transitions | callback/review/verdict capture and recovery tests | on-disk state fixtures remain backward compatible |
| `team_router_status.py` | closeout, handoff, truth check, doctor/status UX | closeout helper, truth check, doctor output, workbench stale-claim tests | read-only tools cannot stage, commit, push, PR, merge, deploy, or sync |

## Extraction Order

Phase 1 completed the safe opening split: protocol parsing first, then pure gate policy, with `src/team_router.py` as facade. Phase 2b1 extracted low-level adapter call/read normalization into `src/team_router_runtime.py` without changing the public import surface. Phase 2b2 extracted pure direct-return contract helpers into `src/team_router_direct_return.py` while keeping capture/watch/state-save orchestration in the facade. Phase 2b4 extracted watcher timing/read discipline/heartbeat payload helpers into `src/team_router_watcher_runtime.py` while keeping `_watch_next_wakeup()`, ledger mutation, and role-thread orchestration in the facade. The remaining safe extraction order is: status/closeout.

Closeout/status should be extracted after state and host runtime are stable, because it consumes both ledger truth and host/readiness facts. Docs/skill contract tests should stay in the main suite throughout extraction and keep imports routed through `src/team_router.py` until a future compatibility gate explicitly changes that contract.

## Non-Goals

- No registry/ledger runtime extraction in phase 1.
- No adapter runtime extraction in phase 1; phase 2b1 now covers only low-level adapter call/read normalization.
- No direct-return capture/watch/state-save extraction in phase 2b2.
- No watcher/heartbeat extraction in phase 1; phase 2b4 now covers watcher timing/read discipline/heartbeat payload helpers only.
- No closeout/status extraction in phase 1.
- No skill-doc changes in phase 1.
- No new live dispatch behavior.
- No new package dependency.
- No commit, push, PR, merge, deploy, release, publish, or global skill sync authorization.
