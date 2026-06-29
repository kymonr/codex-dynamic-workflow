# Team Router Module Map

This records the conservative phase 1 split that is now implemented. Public imports continue through `src/team_router.py`; direct imports from the extracted modules are internal implementation detail unless a later explicit package widens that contract.

## Current Domains

- protocol parsing: `src/team_router_protocol.py` owns `ProtocolError`, `ProtocolMessage`, marker regexes, parser tables, `_validate_task_id()`, `_iter_marker_blocks()`, and `parse_*()` helpers for `TEAM_ROUTER_PLAN`, `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, `TEAM_ROUTER_VERDICT`, `TEAM_ROUTER_ARCHITECT_REVIEW`, and `TEAM_ROUTER_QA_REVIEW`.
- gate policy: `src/team_router_policy.py` owns reviewer/architect/QA gate terms, `GATE_CLASSES`, `classify_*_gate()`, `reviewer_gate_required_for_ledger()`, `explain_team_router_gate()`, `explain_team_router_route()`, and `gate_class_requires_reviewer()`.
- facade and contract snapshot: `src/team_router.py` remains the public import surface and keeps `protocol_contract_snapshot()` because the snapshot aggregates marker schema from protocol, gate policy from policy, and still-local role/state/orchestration/side-effect/closeout contracts.
- registry/ledger state: still local to `src/team_router.py`; load, save, and advance project registries, task ledgers, role bindings, search anchors, and status transitions.
- adapter runtime: still local to `src/team_router.py`; normalize thread reads, assess callable host readiness, and gate live orchestration on explicit adapter capabilities.
- direct return: still local to `src/team_router.py`; validate manager-inbox direct-send messages, enforce `sourceThreadId`, `sourceRoleThreadId`, `role`, and fallback invariants.
- watcher/heartbeat: still local to `src/team_router.py`; enforce first-check and 300 second read discipline, heartbeat scheduling, and timeout/control boundaries.
- closeout/status: still local to `src/team_router.py` and scripts; produce closeout/handoff text, read-only closeout evidence, current-truth checks, and doctor/status summaries.
- docs/skill contract tests: keep `SKILL.md`, `references/`, workbench, packages, and fixtures aligned with runtime policy.

## Implemented Phase 1 Dependencies

| Module | Responsibility | Dependencies | Import rule |
| --- | --- | --- | --- |
| `team_router_protocol.py` | TEAM_ROUTER marker parsing, task id validation, required/allowed marker schema | Python standard library only | must not import `team_router` or `team_router_policy` |
| `team_router_policy.py` | pure gate-policy constants and classifiers | `team_router_protocol.ProtocolError` only | must not import `team_router` |
| `team_router.py` | public facade, runtime/state/direct-return/adapter/watcher/status, `protocol_contract_snapshot()` | `team_router_protocol`, `team_router_policy`, standard library | re-exports moved names for compatibility |

## Deferred Future Modules

| Future module | Responsibility | First tests to move | Acceptance gate |
| --- | --- | --- | --- |
| `team_router_direct_return.py` | manager-inbox direct-send validation and self-thread fallback metadata | direct-return source/role/sourceRoleThreadId tests | fallback behavior and malformed telemetry unchanged |
| `team_router_state.py` | registry/ledger persistence and state transitions | callback/review/verdict capture and recovery tests | on-disk state fixtures remain backward compatible |
| `team_router_adapter_runtime.py` | host readiness, thread adapter normalization, watcher/heartbeat timing | readiness, heartbeat, read discipline, fixture normalization tests | no live dispatch claim without explicit readiness evidence |
| `team_router_status.py` | closeout, handoff, truth check, doctor/status UX | closeout helper, truth check, doctor output, workbench stale-claim tests | read-only tools cannot stage, commit, push, PR, merge, deploy, or sync |

## Extraction Order

Phase 1 completed the safe opening split: protocol parsing first, then pure gate policy, with `src/team_router.py` as facade. The remaining safe extraction order is: direct return -> state/ledger -> adapter runtime -> status/closeout.

Closeout/status should be extracted after state and adapter runtime are stable, because it consumes both ledger truth and host/readiness facts. Docs/skill contract tests should stay in the main suite throughout extraction and keep imports routed through `src/team_router.py` until a future compatibility gate explicitly changes that contract.

## Non-Goals

- No registry/ledger runtime extraction in phase 1.
- No adapter runtime extraction in phase 1.
- No direct-return capture extraction in phase 1.
- No watcher/heartbeat extraction in phase 1.
- No closeout/status extraction in phase 1.
- No skill-doc changes in phase 1.
- No new live dispatch behavior.
- No new package dependency.
- No commit, push, PR, merge, deploy, release, publish, or global skill sync authorization.
