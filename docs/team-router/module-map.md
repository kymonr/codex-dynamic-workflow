# Team Router Module Map

This is a documentation-only split plan. There is no runtime extraction in this package, and public imports continue through `src/team_router.py` until a later explicit refactor package changes that contract.

## Current Domains

- protocol parsing: parse `TEAM_ROUTER_PLAN`, `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, and `TEAM_ROUTER_VERDICT` blocks, reject malformed markers, and preserve protocol field contracts.
- policy snapshot: keep `protocol_contract_snapshot()` as the central readable contract for role policy, side-effect taxonomy, handoff/review-package rules, and closeout policy.
- registry/ledger state: load, save, and advance project registries, task ledgers, role bindings, search anchors, and status transitions.
- adapter runtime: normalize thread reads, assess callable host readiness, and gate live orchestration on explicit adapter capabilities.
- direct return: validate manager-inbox direct-send messages, enforce `sourceThreadId`, `sourceRoleThreadId`, `role`, and fallback invariants.
- watcher/heartbeat: enforce first-check and 300 second read discipline, heartbeat scheduling, and timeout/control boundaries.
- closeout/status: produce closeout/handoff text, read-only closeout evidence, current-truth checks, and doctor/status summaries.
- docs/skill contract tests: keep `SKILL.md`, `references/`, workbench, packages, and fixtures aligned with runtime policy.

## Proposed Future Modules

| Future module | Responsibility | Dependencies | First tests to move | Acceptance gate |
| --- | --- | --- | --- | --- |
| `team_router_policy.py` | policy constants and `protocol_contract_snapshot()` assembly | none beyond standard library | snapshot and side-effect taxonomy assertions | no behavior change and snapshot keys unchanged |
| `team_router_protocol.py` | protocol parsing and validation | policy constants | parser rejection/acceptance tests for plan/callback/review/verdict | malformed marker tests still pass through `src/team_router.py` |
| `team_router_direct_return.py` | manager-inbox direct-send validation and self-thread fallback metadata | protocol parsing, state ids | direct-return source/role/sourceRoleThreadId tests | fallback behavior and malformed telemetry unchanged |
| `team_router_state.py` | registry/ledger persistence and state transitions | protocol parsing, policy constants | callback/review/verdict capture and recovery tests | on-disk state fixtures remain backward compatible |
| `team_router_adapter_runtime.py` | host readiness, thread adapter normalization, watcher/heartbeat timing | state, direct return | readiness, heartbeat, read discipline, fixture normalization tests | no live dispatch claim without explicit readiness evidence |
| `team_router_status.py` | closeout, handoff, truth check, doctor/status UX | state, policy constants | closeout helper, truth check, doctor output, workbench stale-claim tests | read-only tools cannot stage, commit, push, PR, merge, deploy, or sync |

## Extraction Order

The safe extraction order is: policy constants -> protocol parsing -> direct return -> state/ledger -> adapter runtime.

Closeout/status can be extracted after state and adapter runtime are stable, because it consumes both ledger truth and host/readiness facts. Docs/skill contract tests should stay in the main suite throughout extraction and keep imports routed through `src/team_router.py` until the final compatibility gate passes.

## Non-Goals

- No file moves or runtime imports change in this package.
- No new live dispatch behavior.
- No new package dependency.
- No commit, push, PR, merge, deploy, release, publish, or global skill sync authorization.
